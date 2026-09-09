"""
Create one test account per role, so each can be tried in the browser.

    python manage.py seed_test_users
    python manage.py seed_test_users --student-admin
    python manage.py seed_test_users --list

The command prompts for a password and applies it to every account it
creates. Nothing is written into the file, the command line, or the shell
history. Existing accounts keep the password they already have.

These are test accounts on a development database. Do not create them on
anything real, and delete them before this system carries live data:

    python manage.py seed_test_users --delete

Testing as a superuser proves nothing, because a superuser bypasses every
permission check. That is the whole reason this exists.
"""

from getpass import getpass

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import access, models

#: role -> (username, first name)
ACCOUNTS = {
    access.ADMIN: ("admin_test_1", "Admin"),
    access.ACADEMIC_ADMIN: ("academic_admin_test_1", "Academic Admin"),
    access.IT_ADMIN: ("it_admin_test_1", "IT Admin"),
    access.HEAD_OF_DEPARTMENT: ("hod_test_1", "Head of Department"),
    access.TEACHING_STAFF: ("teacher_test_1", "Teacher"),
    access.PAPER_SETTER: ("setter_test_1", "Paper Setter"),
    access.MARKING_REVIEWER: ("reviewer_test_1", "Marking Reviewer"),
    access.EXAM_OPERATIONS: ("examops_test_1", "Exam Operations"),
    access.NON_ACADEMIC_STAFF: ("office_test_1", "Office Staff"),
    access.STUDENT: ("student_test_1", "Student"),
    access.GUARDIAN: ("guardian_test_1", "Guardian"),
    access.GUEST: ("guest_test_1", "Guest"),
}

#: Roles whose accounts may open the admin at all. A real student or
#: guardian account should never have is_staff; --student-admin grants it
#: anyway, for the sake of trying row scoping in the browser.
NON_ADMIN_ROLES = access.NON_ADMIN_ROLES


class Command(BaseCommand):
    help = "Create one test account per role, for trying permissions in the browser."

    def add_arguments(self, parser):
        parser.add_argument(
            "--student-admin", action="store_true",
            help="Also let the student, guardian and guest accounts open the "
                 "admin, so row scoping can be seen there. Never do this for "
                 "a real account.",
        )
        parser.add_argument(
            "--delete", action="store_true",
            help="Remove every test account this command creates.",
        )
        parser.add_argument(
            "--list", action="store_true",
            help="Show the accounts and their roles without writing anything.",
        )

    def handle(self, *args, **options):
        if options["list"]:
            return self._report()

        if options["delete"]:
            names = [u for u, _ in ACCOUNTS.values()]
            deleted, _ = models.AppUser.all_objects.filter(username__in=names).delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted} row(s)."))
            return

        missing = [r for r in ACCOUNTS if not Group.objects.filter(name=r).exists()]
        if missing:
            raise CommandError(
                "These roles do not exist yet: " + ", ".join(missing) +
                "\nRun `manage.py seed_roles` first."
            )

        password = getpass("Password for the test accounts: ")
        again = getpass("Again: ")
        if not password or password != again:
            raise CommandError("Passwords did not match. Nothing was written.")

        created, existing = [], []
        with transaction.atomic():
            for role, (username, first_name) in ACCOUNTS.items():
                user, is_new = models.AppUser.objects.get_or_create(
                    username=username,
                    defaults={
                        "first_name": first_name,
                        "last_name": "Test",
                        "is_staff": role not in NON_ADMIN_ROLES,
                    },
                )
                if is_new:
                    user.set_password(password)
                    created.append((username, role))
                else:
                    existing.append((username, role))

                if options["student_admin"] and role in NON_ADMIN_ROLES:
                    user.is_staff = True

                user.save()
                user.groups.set([Group.objects.get(name=role)])

            self._link_profiles()

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Created"))
        for username, role in created:
            self.stdout.write(f"  {username:26} {role}")
        if existing:
            self.stdout.write(self.style.MIGRATE_HEADING("Already existed (password unchanged)"))
            for username, role in existing:
                self.stdout.write(f"  {username:26} {role}")
        self.stdout.write("")
        self.stdout.write(
            "Log in at /admin/ as each in turn to see what that role may do.\n"
            "Delete them before this database carries live data:\n"
            "    manage.py seed_test_users --delete\n"
        )

    # -- profiles ------------------------------------------------------
    def _link_profiles(self):
        """
        Give the teacher, student and guardian accounts the records their
        roles need. Row scoping answers "their own rows", so a student
        account with no Student row sees nothing at all, and the test
        would look like a bug.
        """
        teacher_user = models.AppUser.objects.filter(username="teacher_test_1").first()
        if teacher_user and not models.Teacher.objects.filter(user=teacher_user).exists():
            models.Teacher.objects.create(user=teacher_user, staff_no="TEST-T1")
            self.stdout.write("  linked a Teacher record to teacher_test_1")

        student_user = models.AppUser.objects.filter(username="student_test_1").first()
        student = None
        if student_user:
            student = models.Student.objects.filter(user=student_user).first()
            if student is None:
                student = models.Student.objects.create(
                    user=student_user, admission_no="TEST-S1",
                    first_name="Student", last_name="Test",
                )
                self.stdout.write("  linked a Student record to student_test_1")

            grade = models.Grade.objects.first()
            if grade and not models.Enrolment.objects.filter(student=student).exists():
                models.Enrolment.objects.create(
                    student=student, grade=grade,
                    academic_year=models.timezone.localdate().year,
                )
                self.stdout.write(f"  enrolled student_test_1 in {grade}")
            elif not grade:
                self.stdout.write(self.style.WARNING(
                    "  no grades exist, so student_test_1 was not enrolled"
                ))

        guardian_user = models.AppUser.objects.filter(username="guardian_test_1").first()
        if guardian_user and student and not models.GuardianLink.objects.filter(
            user=guardian_user, student=student
        ).exists():
            models.GuardianLink.objects.create(
                user=guardian_user, student=student, relationship="guardian",
                is_primary=True,
            )
            self.stdout.write("  linked guardian_test_1 to student_test_1")

    def _report(self):
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Test accounts"))
        for role, (username, _) in ACCOUNTS.items():
            exists = models.AppUser.objects.filter(username=username).exists()
            mark = "exists" if exists else "-"
            self.stdout.write(f"  {username:26} {role:22} {mark}")
        self.stdout.write("")
