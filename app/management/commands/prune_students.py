"""
Retire the student accounts that are not on the school's list.

    python manage.py prune_students                    # report only — writes nothing
    python manage.py prune_students --commit           # retire them
    python manage.py prune_students --list docs/keep_students.txt

The list in `docs/keep_students.txt` is the roll: 99 admission numbers.
Anything else carrying a student login — demo data, seeded test accounts,
a duplicate created during an import — is not a child at this school and
should not be able to sign in.

Nothing is deleted. Accounts are **voided**, the same soft delete the rest
of the schema uses: the row stays, its `active_flag` is cleared so the
admission number is free again, and the login is deactivated so it cannot
be used. `manage.py prune_students` is therefore reversible by unvoiding,
and the audit trail of who retired what survives.

A student who has actually handed work in is never retired silently. They
are listed and skipped, because an account with a real submission attached
is far more likely to be a mis-typed roll than a stray demo row. Pass
`--force` once you have read that list and still mean it.
"""

from pathlib import Path

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import access, models

DEFAULT_LIST = "docs/keep_students.txt"


def read_keep_list(path):
    """The admission numbers to keep. Blank lines and #comments ignored."""
    file = Path(path)
    if not file.exists():
        raise CommandError(f"No list at {path}.")
    keep = []
    for line in file.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if line:
            keep.append(line)
    if not keep:
        raise CommandError(f"{path} has no admission numbers in it.")
    return set(keep), keep


class Command(BaseCommand):
    help = "Void every student account that is not on the keep list."

    def add_arguments(self, parser):
        parser.add_argument("--list", dest="path", default=DEFAULT_LIST,
                            help=f"The roll to keep. Default {DEFAULT_LIST}.")
        parser.add_argument("--commit", action="store_true",
                            help="Apply it. Without this the command only reports.")
        parser.add_argument("--force", action="store_true",
                            help="Also retire accounts that have handed work in.")

    def handle(self, *args, **options):
        keep, ordered = read_keep_list(options["path"])
        commit = options["commit"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Keeping {len(keep)} student account(s) from {options['path']}"
            + ("" if commit else "   — REPORT ONLY, nothing will be written")
        ))

        students = list(
            models.Student.objects.select_related("user").order_by("admission_no")
        )
        kept = [s for s in students if s.admission_no in keep]
        surplus = [s for s in students if s.admission_no not in keep]

        # Student logins that never had a Student row — seeded test accounts,
        # mostly. They are student accounts too, and they can sign in.
        student_group = Group.objects.filter(name=access.STUDENT).first()
        loose = []
        if student_group:
            linked = {s.user_id for s in students if s.user_id}
            loose = [
                u for u in models.AppUser.objects.filter(groups=student_group)
                          .order_by("username")
                if u.pk not in linked and u.username not in keep and not u.is_superuser
            ]

        missing = sorted(keep - {s.admission_no for s in students})

        # -- what each surplus account is carrying -----------------------
        rows = []
        for student in surplus:
            work = models.Submission.objects.filter(
                enrolment__student=student, voided=False
            ).count()
            marks = models.TopicResult.objects.filter(
                student_subject__enrolment__student=student, voided=False
            ).count()
            register = models.AttendanceRecord.objects.filter(
                enrolment__student=student, voided=False
            ).count()
            rows.append({
                "student": student,
                "work": work,
                "marks": marks,
                "register": register,
                "has_history": bool(work or marks),
            })

        # -- report ------------------------------------------------------
        self.stdout.write("")
        self.stdout.write(f"  student records ........... {len(students)}")
        self.stdout.write(f"  on the list, keeping ...... {len(kept)}")
        self.stdout.write(f"  not on the list ........... {len(surplus)}")
        if loose:
            self.stdout.write(f"  student logins with no record  {len(loose)}")
        if missing:
            self.stdout.write(self.style.WARNING(
                f"  on the list but not in the database  {len(missing)}"
            ))

        if missing:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING("On your list, but no student record exists"))
            for adm in missing:
                self.stdout.write(f"  {adm}")
            self.stdout.write("  (a typo in the list, or an import that has not been run)")

        for r in rows:
            r["held_back"] = r["has_history"] and not options["force"]
        held_back = [r for r in rows if r["held_back"]]
        going = [r for r in rows if not r["held_back"]]

        if going or loose:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("To retire"))
            for r in going:
                s = r["student"]
                note = []
                if r["register"]:
                    note.append(f"{r['register']} register mark(s)")
                if r["work"]:
                    note.append(f"{r['work']} submission(s)")
                if r["marks"]:
                    note.append(f"{r['marks']} topic result(s)")
                self.stdout.write(
                    f"  {s.admission_no:<12} {s.full_name[:34]:<34}"
                    + (f"  [{', '.join(note)}]" if note else "")
                )

        for u in loose:
            self.stdout.write(f"  {u.username:<12} {u.get_full_name() or '—':<34}  [login only, no student record]")

        if held_back:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "Held back — these have real work against them"
            ))
            for r in held_back:
                s = r["student"]
                self.stdout.write(
                    f"  {s.admission_no:<12} {s.full_name[:34]:<34}"
                    f"  {r['work']} submission(s), {r['marks']} topic result(s)"
                )
            self.stdout.write("  Read that list. If you still mean it, run again with --force.")

        if not going and not loose:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS("Nothing to retire — the roll already matches."))
            self.stdout.write("")
            return

        if not commit:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "Report only — nothing was written. Run again with --commit to apply."
            ))
            self.stdout.write("")
            return

        # -- apply -------------------------------------------------------
        reason = "not on the academy's roll"
        voided_students = voided_users = voided_rows = 0

        with transaction.atomic():
            for r in going:
                student = r["student"]
                for subject in models.StudentSubject.objects.filter(
                    enrolment__student=student, voided=False
                ):
                    subject.void(reason=reason)
                    voided_rows += 1
                for membership in models.CohortMembership.objects.filter(
                    enrolment__student=student, voided=False
                ):
                    membership.void(reason=reason)
                    voided_rows += 1
                for enrolment in models.Enrolment.objects.filter(
                    student=student, voided=False
                ):
                    enrolment.void(reason=reason)
                    voided_rows += 1

                user = student.user
                student.void(reason=reason)
                voided_students += 1

                if user is not None and not user.is_superuser:
                    voided_users += self._retire(user, reason)

            for user in loose:
                voided_users += self._retire(user, reason)

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Retired {voided_students} student record(s) and {voided_users} login(s); "
            f"{voided_rows} enrolment and subject row(s) voided with them."
        ))
        self.stdout.write(
            "Nothing was deleted. Each row is voided, so an account brought back "
            "is a matter of unvoiding it in the admin."
        )
        self.stdout.write("")

    @staticmethod
    def _retire(user, reason):
        """Stop the login working, then void the account. One row, both facts."""
        user.is_active = False
        user.suspended = True
        user.save(update_fields=["is_active", "suspended"])
        if not user.voided:
            user.void(reason=reason)
        return 1
