"""
Management command: seed_student_logins
=======================================
Creates a Django AppUser account for every Student record that does not already
have one.  The username is the admission_number field.

Usage
-----
  venv\Scripts\python.exe manage.py seed_student_logins          # dry run (shows what would happen)
  venv\Scripts\python.exe manage.py seed_student_logins --commit # actually creates accounts

The accounts are created with an *unusable* password (no one can log in yet).
Use reset_login <admission_no> --set afterwards to activate each one.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app.models import AppUser, Student


class Command(BaseCommand):
    help = "Create Django user accounts for all students (username = admission number)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            default=False,
            help="Actually create accounts. Without this flag the command is a dry run.",
        )

    def handle(self, *args, **options):
        commit = options["commit"]
        dry = not commit

        if dry:
            self.stdout.write(
                self.style.WARNING(
                    "DRY RUN — no accounts will be created. Pass --commit to apply."
                )
            )

        students = (
            Student.objects.filter(voided=False)
            .select_related("user")
            .order_by("admission_number")
        )

        created = 0
        skipped = 0
        errors = []

        for student in students:
            adm = student.admission_number
            if not adm:
                errors.append(f"  SKIP  {student.first_name} {student.last_name or ''} — no admission number")
                skipped += 1
                continue

            if AppUser.objects.filter(username=adm).exists():
                self.stdout.write(f"  EXISTS  {adm}  ({student.first_name} {student.last_name or ''})")
                skipped += 1
                continue

            if dry:
                self.stdout.write(f"  WOULD CREATE  {adm}  ({student.first_name} {student.last_name or ''})")
            else:
                try:
                    with transaction.atomic():
                        user = AppUser.objects.create_user(
                            username=adm,
                            password=None,           # unusable password — must use reset_login --set
                            first_name=student.first_name,
                            last_name=student.last_name or "",
                            is_active=True,
                            is_staff=False,
                        )
                        # Link the user back to the Student record if the FK is free
                        if student.user_id is None:
                            student.user = user
                            student.save(update_fields=["user"])
                    self.stdout.write(
                        self.style.SUCCESS(f"  CREATED  {adm}  ({student.first_name} {student.last_name or ''})")
                    )
                    created += 1
                except Exception as exc:
                    errors.append(f"  ERROR  {adm} — {exc}")

        self.stdout.write("")
        if errors:
            for msg in errors:
                self.stdout.write(self.style.ERROR(msg))

        mode = "Would create" if dry else "Created"
        self.stdout.write(
            self.style.SUCCESS(
                f"\n{mode} {created} account(s).  Skipped / already exist: {skipped}.  Errors: {len(errors)}."
            )
        )

        if dry and (created > 0 or skipped > 0):
            self.stdout.write(
                self.style.WARNING(
                    "\nRun with  --commit  to apply the changes shown above."
                )
            )
