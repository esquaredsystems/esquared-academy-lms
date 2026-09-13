"""
Put the O Level paper code into each subject's full name.

    venv\\Scripts\\python.exe manage.py set_subject_names            # report only
    venv\\Scripts\\python.exe manage.py set_subject_names --commit   # apply it

Each subject's full name becomes "Name (code)" — English Language (1123),
History of Pakistan (2059/01) — and the code is also stored on its own in
the subject's id_number field. The codes are Cambridge's own, taken from
the school's setup workbook.

Safe to run again: the name is rebuilt from the base name and the code
each time, so the code is never doubled up. Subjects not listed here
(Science, Activity — which have no O Level code) are left untouched.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app import models

# short_name -> (proper full name, O Level paper code)
SUBJECTS = {
    "ENG":  ("English Language",          "1123"),
    "MATH": ("Mathematics",               "4024"),
    "PHY":  ("Physics",                   "5054"),
    "CHEM": ("Chemistry",                 "5070"),
    "ISL":  ("Islamiyat",                 "2058"),
    "PST1": ("History of Pakistan",       "2059/01"),
    "PST2": ("Environment of Pakistan",   "2059/02"),
    "CS":   ("Computer Science",          "2210"),
    "BUS":  ("Business",                  "7081"),
    "ACC":  ("Accounting",                "7707"),
    "ECON": ("Economics",                 "2281"),
    "URDU": ("Urdu Language",             "3248"),
}


class Command(BaseCommand):
    help = "Add the O Level paper code to each subject's full name."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true",
                            help="Apply the changes. Without this it only reports.")

    def handle(self, *args, **options):
        commit = options["commit"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Subject names" + ("" if commit else "   — REPORT ONLY, nothing written")
        ))
        self.stdout.write("")

        changed = missing = same = 0
        with transaction.atomic():
            for short_name, (base, code) in SUBJECTS.items():
                subject = models.Subject.objects.filter(short_name=short_name).first()
                if subject is None:
                    self.stdout.write(self.style.WARNING(
                        f"  {short_name:6} not found — skipped"
                    ))
                    missing += 1
                    continue

                new_full = f"{base} ({code})"
                if subject.full_name == new_full and subject.id_number == code:
                    self.stdout.write(f"  {short_name:6} already correct: {new_full}")
                    same += 1
                    continue

                self.stdout.write(
                    f"  {short_name:6} {subject.full_name!r}  ->  {new_full!r}"
                )
                if commit:
                    subject.full_name = new_full
                    subject.id_number = code
                    subject.save()
                changed += 1

            if not commit:
                transaction.set_rollback(True)

        self.stdout.write("")
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Done — {changed} updated, {same} already correct, {missing} not found."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Report only — {changed} would change, {same} already correct, "
                f"{missing} not found. Run again with --commit to apply."
            ))
        self.stdout.write("")
