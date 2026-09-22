"""
Can one student see another child's record?

The permission system says a student may view the Student table — that is
what shows them their own record. It says nothing about which rows. This
is the check that the row scoping is actually applied where the screens
are.

Run it on its own, from the project root:

    venv\Scripts\python.exe -m app.check_row_scoping

It is a standalone script, not part of the test suite: it builds its own
test database at import time. That is also why it is NOT called
`tests_row_scoping.py` — `manage.py test` collects every file matching
`test*.py`, so under that name Django imported it while gathering tests,
the setup below ran a second time inside a run that had already started,
and the whole suite died before reaching the real tests.
"""
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "lms.settings"); django.setup()
from django.test.utils import setup_test_environment
from django.test.runner import DiscoverRunner
setup_test_environment(); r=DiscoverRunner(verbosity=0,interactive=False); old=r.setup_databases()
from django.contrib.auth.models import Group
from django.test import Client
from app import models
from app.role_setup import ensure_roles
ensure_roles()

g = models.AcademyClass.objects.create(short_name="S1", full_name="Senior 1", level=3, sort_order=3)
sub = models.Subject.objects.create(short_name="ENG", full_name="English")
syl = models.Syllabus.objects.create(subject=sub, academy_class=g, academic_year=2627)

# Me
u = models.AppUser.objects.create_user(username="26070108", password="x", is_staff=True)
u.groups.add(Group.objects.get(name="Student"))
me = models.Student.objects.create(admission_no="26070108", first_name="Aariz",
                                   last_name="Tunia", national_id="11111-1111111-1",
                                   guardian_name="MyParent", address="My house")
me.user = u; me.save()
en_me = models.Enrolment.objects.create(student=me, academy_class=g, academic_year=2627)

# Another child, whose data must never appear
other = models.Student.objects.create(admission_no="26070109", first_name="Abbas",
                                      last_name="Abid", national_id="99999-9999999-9",
                                      guardian_name="OtherParent", address="Their house")
en_other = models.Enrolment.objects.create(student=other, academy_class=g, academic_year=2627)

h = models.Handout.objects.create(syllabus=syl, title="Sheet 1", is_assignment=True,
                                  status=models.HandoutStatus.ACTIVE)
s_me = models.Submission.objects.create(handout=h, enrolment=en_me, round_no=1,
                                        state=models.SubmissionState.APPROVED)
s_other = models.Submission.objects.create(handout=h, enrolment=en_other, round_no=1,
                                           state=models.SubmissionState.APPROVED)
models.MarkLine.objects.create(submission=s_other, label="Q1", out_of=10, awarded=2)

# A teacher, who must still see everything
t = models.AppUser.objects.create_user(username="uxair.ahm", password="x", is_staff=True)
t.groups.add(Group.objects.get(name="Teacher"))
models.Teacher.objects.create(staff_no="T-001", user=t)

SECRETS = {
    "the other child's name":        "Abbas",
    "their admission number":        "26070109",
    "their national ID":             "99999-9999999-9",
    "their guardian's name":         "OtherParent",
    "their address":                 "Their house",
}

print("=" * 68)
print("AS A STUDENT — what leaks?")
print("=" * 68)
c = Client(); c.force_login(u)
failed = []
for path, label in [("/admin/app/student/", "student list"),
                    ("/admin/app/enrolment/", "enrolment list"),
                    ("/admin/app/submission/", "submission list"),
                    ("/admin/app/markline/", "marks list")]:
    resp = c.get(path)
    if resp.status_code != 200:
        print(f"  {label:<18} -> {resp.status_code} (not reachable)")
        continue
    body = resp.content.decode()
    leaks = [name for name, needle in SECRETS.items() if needle in body]
    mine = "26070108" in body or "Aariz" in body
    if leaks:
        print(f"  {label:<18} -> LEAKS: {', '.join(leaks)}")
        failed.append(label)
    else:
        print(f"  {label:<18} -> clean (own rows visible: {mine})")

# Direct object access, not just the list
resp = c.get(f"/admin/app/student/{other.pk}/change/")
direct_ok = resp.status_code in (302, 403) or "OtherParent" not in resp.content.decode()
print(f"  opening the other child's record directly -> {resp.status_code} "
      f"{'blocked' if direct_ok else 'LEAKED'}")
if not direct_ok: failed.append("direct record access")

print()
print("=" * 68)
print("AS A TEACHER — does the fix break their lists?")
print("=" * 68)
tc = Client(); tc.force_login(t)
for path, label, expect in [("/admin/app/student/", "student list", "26070109"),
                            ("/admin/app/submission/", "submission list", None)]:
    resp = tc.get(path)
    body = resp.content.decode() if resp.status_code == 200 else ""
    sees = (expect in body) if expect else (resp.status_code == 200)
    print(f"  {label:<18} -> {resp.status_code}, sees all rows: {sees}")
    if resp.status_code == 200 and not sees:
        failed.append(f"teacher lost access to {label}")

print()
print("=" * 68)
if failed:
    print("STILL LEAKING / BROKEN:", ", ".join(failed))
    raise SystemExit(1)
print("NO LEAKS. Teacher access intact.")
r.teardown_databases(old)
