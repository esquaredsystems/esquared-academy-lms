"""
Management command: seed_student_logins
=======================================
Creates a Django AppUser account for every Student record that does not already
have one.  The username is the admission_no field.

Usage
-----
  venv\Scripts\python.exe manage.py seed_student_logins          # dry run (shows what would happen)
  venv\Scripts\python.exe manage.py seed_student_logins --commit # actually creates accounts

The accounts are created with an *unusable* password (no one can log in yet).
Use reset_login <admission_no> --set afterwards to activate each one.
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import access
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

        try:
            student_group = Group.objects.get(name=access.STUDENT)
        except Group.DoesNotExist:
            raise CommandError(
                "There is no 'Student' role yet. Run:  manage.py seed_roles"
            )

        students = (
            Student.objects.filter(voided=False)
            .select_related("user")
            .order_by("admission_no")
        )

        created = 0
        skipped = 0
        errors = []

        for student in students:
            adm = student.admission_no
            if not adm:
                errors.append(f"  SKIP  {student.first_name} {student.last_name or ''} — no admission number")
                skipped += 1
                continue

            existing = AppUser.objects.filter(username=adm).first()
            if existing is not None:
                note = ""
                if not existing.groups.exists() and not dry:
                    existing.groups.add(student_group)
                    note = "  (gave it the Student role)"
                elif not existing.groups.exists():
                    note = "  (has no role — would add Student)"
                self.stdout.write(
                    f"  EXISTS  {adm}  ({student.first_name} {student.last_name or ''}){note}"
                )
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
                            # The whole interface lives under /admin/, and
                            # Django's admin login refuses anyone without
                            # this flag — so a student cannot even sign in
                            # without it. What actually keeps a student out
                            # of everything else is the Student role's
                            # narrow permissions plus the row scoping in
                            # access.py, which AuditAdmin now applies.
                            is_staff=True,
                        )
                        # Without a role the account signs in to an empty
                        # screen, which reads as a broken system rather than
                        # a missing step.
                        user.groups.add(student_group)
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
