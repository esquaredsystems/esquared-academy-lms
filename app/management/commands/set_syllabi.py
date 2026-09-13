"""
Set which subjects each class studies this year, and void the rest.

    venv\\Scripts\\python.exe manage.py set_syllabi            # report only
    venv\\Scripts\\python.exe manage.py set_syllabi --commit   # apply it

A "syllabus" here is one subject taught to one class in one year. This sets
the syllabi for Senior 2 and Senior 3 for the current session (2627), and
voids every other syllabus so only these remain:

    Senior 2 (S2): PST1, PST2, ISL, URDU
    Senior 3 (S3): ENG, MATH, PHY, CHEM, CS, BUS, ACC, ECON

E1, E2 and S1 are left for later — their syllabi are not created here, and
any that already exist for them are voided along with everything else.

Safe to run again. Voiding is the system's soft delete; a voided syllabus
(and its syllabus-topic links) disappears from every list but can be
unvoided. Nothing is hard-deleted.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import models

YEAR = 2627  # the 2026-27 session

TARGET = {
    "S2": ["PST1", "PST2", "ISL", "URDU"],
    "S3": ["ENG", "MATH", "PHY", "CHEM", "CS", "BUS", "ACC", "ECON"],
}


class Command(BaseCommand):
    help = "Create the S2 and S3 syllabi for this year; void all others."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=YEAR,
                            help=f"Academic year. Default {YEAR} (2026-27).")
        parser.add_argument("--commit", action="store_true",
                            help="Apply it. Without this it only reports.")

    def handle(self, *args, **options):
        year = options["year"]
        commit = options["commit"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Syllabi for {year}" + ("" if commit else "   — REPORT ONLY, nothing written")
        ))

        # resolve grades and subjects up front, so a typo fails loudly
        grades, subjects, plan = {}, {}, []
        for grade_code, subject_codes in TARGET.items():
            grade = models.Grade.objects.filter(short_name=grade_code).first()
            if grade is None:
                raise CommandError(f"No class called {grade_code!r}.")
            grades[grade_code] = grade
            for sc in subject_codes:
                subject = models.Subject.objects.filter(short_name=sc).first()
                if subject is None:
                    raise CommandError(f"No subject called {sc!r} (is it voided?).")
                subjects[sc] = subject
                plan.append((grade, subject))

        # the exact set we intend to keep live
        keep_keys = {(g.pk, s.pk, year) for g, s in plan}

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Keeping / creating"))
        created = kept = 0
        with transaction.atomic():
            for grade, subject in plan:
                existing = models.Syllabus.all_objects.filter(
                    subject=subject, grade=grade, academic_year=year
                ).first()
                if existing is None:
                    state = "create"
                    created += 1
                    if commit:
                        models.Syllabus.objects.create(
                            subject=subject, grade=grade, academic_year=year,
                            full_name=f"{subject.full_name} - {grade.short_name} ({year})",
                        )
                else:
                    state = "keep" + (" (unvoid)" if existing.voided else "")
                    kept += 1
                    if commit and existing.voided:
                        existing.unvoid()
                self.stdout.write(f"  {grade.short_name:3} {subject.short_name:5} {state}")

            # void every other live syllabus, and its topic links
            surplus = [
                s for s in models.Syllabus.objects.select_related("grade", "subject")
                if (s.grade_id, s.subject_id, s.academic_year) not in keep_keys
            ]
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("Voiding all others"))
            if not surplus:
                self.stdout.write("  (none)")
            voided_syl = voided_links = 0
            for s in surplus:
                self.stdout.write(
                    f"  {s.grade.short_name:3} {s.subject.short_name:5} {s.academic_year}  void"
                )
                if commit:
                    for link in models.SyllabusTopic.objects.filter(syllabus=s):
                        if not link.voided:
                            link.void(reason="syllabus not offered")
                            voided_links += 1
                    s.void(reason="not among this year's offered syllabi")
                voided_syl += 1

            if not commit:
                transaction.set_rollback(True)

        self.stdout.write("")
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Done - {created} created, {kept} kept, {voided_syl} voided "
                f"({voided_links} syllabus-topic link(s) voided with them)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Report only - would create {created}, keep {kept}, void {voided_syl}. "
                "Run again with --commit to apply."
            ))
        self.stdout.write("")
