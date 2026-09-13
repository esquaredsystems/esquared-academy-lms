"""
Load or remove the demo school: three teachers, twenty students.

    python manage.py seed_demo             # load
    python manage.py seed_demo --remove    # void every demo row
    python manage.py seed_demo --year 2027

The admin's Demo page calls this same command, so the button and the
command can never drift apart.

Idempotent. Demo rows are found again by their DEMO- prefix, so removing
never touches anything real, and loading twice changes nothing.

Requires the curriculum: run seed_curriculum first, or there are no
syllabi to enrol anyone into.
"""

import random
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import access, demo_data, models


class Command(BaseCommand):
    help = "Load (or remove) demo teachers, students, enrolments and subject choices."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=date.today().year)
        parser.add_argument(
            "--remove", action="store_true",
            help="Void every demo row instead of creating them.",
        )
        parser.add_argument("--created-by", type=str, default=None)

    def handle(self, *args, **options):
        self.year = options["year"]
        user = self._resolve_user(options["created_by"])
        self.counts = {}

        with transaction.atomic():
            if options["remove"]:
                self._remove(user)
            else:
                self._load(user)

        for label, count in self.counts.items():
            self.stdout.write(f"  {label:22} {count}")
        self.stdout.write("")

    # -- helpers -------------------------------------------------------
    def _resolve_user(self, username):
        if username:
            try:
                return models.AppUser.objects.get(username=username)
            except models.AppUser.DoesNotExist:
                raise CommandError(f"No user named {username!r}.")
        user = models.AppUser.objects.filter(is_superuser=True).order_by("id").first()
        if not user:
            raise CommandError("No superuser to attribute the demo data to.")
        return user

    def _count(self, label, n=1):
        self.counts[label] = self.counts.get(label, 0) + n

    # -- loading -------------------------------------------------------
    def _load(self, user):
        syllabi = models.Syllabus.objects.filter(academic_year=self.year)
        if not syllabi.exists():
            raise CommandError(
                f"No syllabi for {self.year}. Run `manage.py seed_curriculum` first."
            )

        academy_classes = {g.short_name: g for g in models.AcademyClass.objects.all()}
        by_academy_class = {}
        for syllabus in syllabi.select_related("subject", "academy_class"):
            by_academy_class.setdefault(syllabus.academy_class.short_name, []).append(syllabus)

        self._load_teachers(user, syllabi)
        self._load_students(user, academy_classes, by_academy_class)
        self._load_results(user)

    def _load_teachers(self, user, syllabi):
        try:
            teaching_staff = Group.objects.get(name=access.TEACHER)
        except Group.DoesNotExist:
            teaching_staff = None

        for row in demo_data.TEACHERS:
            account = models.AppUser.objects.filter(username=row["username"]).first()
            if account is not None and (account.suspended or not account.is_active):
                account.suspended = False
                account.is_active = True
                account.save()
                self._count("reinstated logins", 1)
            if account is None:
                account = models.AppUser.objects.create_user(
                    username=row["username"],
                    email=row["email"],
                    password=demo_data.DEMO_PASSWORD,
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    is_staff=True,
                    created_by=user,
                )
                self._count("teacher logins", 1)
            if teaching_staff:
                account.groups.add(teaching_staff)

            # all_objects, not objects: a removed demo was voided, not
            # deleted, so a reload restores those rows rather than
            # creating a second set beside them.
            teacher = models.Teacher.all_objects.filter(
                staff_no=row["staff_no"]
            ).first()
            if teacher is None:
                teacher = models.Teacher.objects.create(
                    user=account, staff_no=row["staff_no"], created_by=user
                )
                self._count("teachers", 1)
            else:
                self._revive(teacher, "teachers")

            # One teacher, several subjects — and every academy_class that runs them.
            for syllabus in syllabi:
                if syllabus.subject.short_name not in row["teaches"]:
                    continue
                _, created = self._get_or_create(
                    models.TeachingAssignment,
                    {"created_by": user},
                    teacher=teacher, syllabus=syllabus, role="primary",
                )
                if created:
                    self._count("teaching assignments", 1)

    def _load_students(self, user, academy_classes, by_academy_class):
        for index, row in enumerate(demo_data.STUDENTS, start=1):
            academy_class = academy_classes.get(row["academy_class"])
            if academy_class is None:
                continue

            student = models.Student.all_objects.filter(
                admission_no=row["admission_no"]
            ).first()
            if student is None:
                student = models.Student.objects.create(
                    admission_no=row["admission_no"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    guardian_name=row["guardian_name"],
                    guardian_contact=f"{demo_data.PHONE_PREFIX}{2000 + index:04d}",
                    created_by=user,
                )
                self._count("students", 1)
            else:
                self._revive(student, "students")

            enrolment, created = self._get_or_create(
                models.Enrolment,
                {"created_by": user},
                student=student, academy_class=academy_class, academic_year=self.year,
            )
            if created:
                self._count("enrolments", 1)

            for syllabus in self._subjects_for(row, academy_class, by_academy_class):
                _, made = self._get_or_create(
                    models.StudentSubject,
                    {"created_by": user},
                    enrolment=enrolment, syllabus=syllabus,
                )
                if made:
                    self._count("subject choices", 1)

    def _load_results(self, user):
        """
        Mark part of every demo subject, so the maps are not all blank.

        The marks are pseudo-random but seeded from the admission number
        and the subject, so a reload reproduces them exactly rather than
        shuffling a student's history under them.
        """
        taken = (
            models.StudentSubject.objects
            .filter(enrolment__student__admission_no__startswith=demo_data.PREFIX)
            .select_related("enrolment__student", "syllabus__subject")
        )
        # A removed demo voided these; restore them in one statement
        # before deciding what still needs marking.
        restored = models.TopicResult.all_objects.filter(
            student_subject__in=taken, voided=True
        ).update(
            voided=False, voided_by=None, date_voided=None, void_reason=None,
            active_flag=True,
        )
        if restored:
            self._count("restored topic marks", restored)

        already = set(
            models.TopicResult.all_objects
            .filter(student_subject__in=taken)
            .values_list("student_subject_id", flat=True)
        )

        new_rows = []
        for student_subject in taken:
            if student_subject.pk in already:
                continue

            student = student_subject.enrolment.student
            subject = student_subject.syllabus.subject
            topics = student_subject.syllabus.assessable_topics()
            if not topics:
                continue

            person = random.Random(student.admission_no)
            ability = person.uniform(*demo_data.ABILITY_RANGE)

            rng = random.Random(f"{student.admission_no}:{subject.short_name}")
            # A student is a little better at some subjects than others.
            ability += rng.uniform(-6, 6)
            covered = int(len(topics) * rng.uniform(*demo_data.COVERAGE_RANGE))
            start = date(student_subject.enrolment.academic_year, 1, 15)

            for index, topic in enumerate(topics[:covered]):
                score = min(100, max(5, rng.gauss(ability, demo_data.MARK_SPREAD)))
                new_rows.append(models.TopicResult(
                    student_subject=student_subject,
                    topic=topic,
                    score_pct=Decimal(f"{score:.0f}"),
                    assessed_on=start + timedelta(days=7 * index),
                    method=models.EvalMethod.TEACHER,
                    created_by=user,
                ))

        if new_rows:
            models.TopicResult.objects.bulk_create(new_rows, batch_size=500)
            self._count("topic marks", len(new_rows))

    def _subjects_for(self, row, academy_class, by_academy_class):
        """
        Core everywhere; in the terminal academy_class, core plus this student's
        chosen electives. This is the school's rule, applied from the
        data rather than hard-coded per academy_class.
        """
        syllabi = by_academy_class.get(academy_class.short_name, [])
        core = [s for s in syllabi if s.is_core]
        if not academy_class.is_terminal:
            return core

        wanted = set(row.get("electives", []))
        electives = [
            s for s in syllabi if not s.is_core and s.subject.short_name in wanted
        ]
        return core + electives

    def _get_or_create(self, model, defaults, **lookup):
        obj = model.all_objects.filter(**lookup).first()
        if obj:
            self._revive(obj, model._meta.verbose_name_plural)
            return obj, False
        return model.objects.create(**lookup, **defaults), True

    def _revive(self, obj, label):
        """Bring a voided demo row back rather than duplicating it."""
        if not obj.voided:
            return obj
        obj.voided = False
        obj.voided_by = None
        obj.date_voided = None
        obj.void_reason = None
        obj.save()
        self._count(f"restored {label}", 1)
        return obj

    # -- removal -------------------------------------------------------
    def _remove(self, user):
        prefix = demo_data.PREFIX
        reason = "demo data removed"

        students = models.Student.objects.filter(admission_no__startswith=prefix)
        teachers = models.Teacher.objects.filter(staff_no__startswith=prefix)

        subject_choices = models.StudentSubject.objects.filter(
            enrolment__student__in=students
        )
        topic_results = models.TopicResult.objects.filter(
            student_subject__enrolment__student__in=students
        )
        enrolments = models.Enrolment.objects.filter(student__in=students)
        assignments = models.TeachingAssignment.objects.filter(teacher__in=teachers)

        for label, queryset in (
            ("topic marks", topic_results),
            ("subject choices", subject_choices),
            ("enrolments", enrolments),
            ("teaching assignments", assignments),
            ("students", students),
            ("teachers", teachers),
        ):
            rows = list(queryset)
            for row in rows:
                row.void(user=user, reason=reason)
            if rows:
                self._count(f"voided {label}", len(rows))

        # The logins stay: they are ordinary accounts, and voiding them
        # would take their audit references with them. They are suspended
        # instead, so nobody can sign in as a demo teacher by accident.
        usernames = [t["username"] for t in demo_data.TEACHERS]
        suspended = models.AppUser.objects.filter(username__in=usernames)
        for account in suspended:
            account.suspended = True
            account.is_active = False
            account.save()
        if suspended:
            self._count("suspended logins", suspended.count())
