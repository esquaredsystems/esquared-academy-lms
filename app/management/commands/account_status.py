"""
Who can actually log in, and who is still waiting on a password.

    python manage.py account_status
    python manage.py account_status --pending     # just the ones not done
    python manage.py account_status --role Student

Written for the setup week, when a hundred accounts are being brought up
a few at a time and the only question that matters is "how far have I
got". An account is only counted as ready when it could really log in:
it exists, it is active, it is not voided, and it has a usable password.
An account with no password is not a login, it is a placeholder — so the
two are counted separately rather than added together.
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from app import models


class Command(BaseCommand):
    help = "Report how many accounts exist, and how many can actually log in."

    def add_arguments(self, parser):
        parser.add_argument(
            "--pending", action="store_true",
            help="List the accounts that still need a password.",
        )
        parser.add_argument(
            "--role", default=None,
            help="Only this role, e.g. --role Student.",
        )
        parser.add_argument(
            "--limit", type=int, default=40,
            help="How many names to list. Default 40.",
        )

    def handle(self, *args, **options):
        users = models.AppUser.all_objects.all()
        if options["role"]:
            users = users.filter(groups__name=options["role"])

        live = [u for u in users if not u.voided]
        ready = [u for u in live if u.is_active and u.has_usable_password()]
        waiting = [u for u in live if not (u.is_active and u.has_usable_password())]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Accounts"))
        self.stdout.write(f"  registered (can log in) ... {len(ready)}")
        self.stdout.write(f"  created, no password yet .. {len(waiting)}")
        self.stdout.write(f"  voided .................... {users.count() - len(live)}")
        self.stdout.write(f"  {'-' * 34}")
        self.stdout.write(f"  total ..................... {users.count()}")
        self.stdout.write("")

        # Per role, because the setup is done role by role.
        self.stdout.write(self.style.MIGRATE_HEADING("By role"))
        rows = []
        for group in Group.objects.all().order_by("name"):
            members = [u for u in live if group in u.groups.all()]
            if not members:
                continue
            done = len([u for u in members if u.is_active and u.has_usable_password()])
            rows.append((group.name, done, len(members)))
        width = max([len(r[0]) for r in rows], default=10)
        for name, done, total in rows:
            bar = "done" if done == total else f"{total - done} to go"
            self.stdout.write(f"  {name:<{width}}  {done:>3} / {total:<3}  {bar}")

        no_role = [u for u in live if not u.groups.exists()]
        if no_role:
            self.stdout.write(
                self.style.WARNING(
                    f"\n  {len(no_role)} account(s) have no role yet — they can log in "
                    f"but will see nothing. Assign a group in the admin."
                )
            )

        # Student records are created by import_setup; the logins are a
        # separate step, so the gap between the two is worth naming.
        students = models.Student.objects.filter(voided=False)
        linked = students.exclude(user__isnull=True).count()
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Students"))
        self.stdout.write(f"  student records ........... {students.count()}")
        self.stdout.write(f"  with a login account ...... {linked}")
        if students.count() > linked:
            self.stdout.write(
                self.style.WARNING(
                    f"  {students.count() - linked} student(s) have no account yet — "
                    f"run: manage.py seed_student_logins --commit"
                )
            )

        if options["pending"] and waiting:
            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING("Still need a password"))
            for user in waiting[: options["limit"]]:
                roles = ", ".join(user.groups.values_list("name", flat=True)) or "no role"
                self.stdout.write(f"  {user.username:<24} {roles}")
            if len(waiting) > options["limit"]:
                self.stdout.write(f"  … and {len(waiting) - options['limit']} more")
            self.stdout.write("")
            self.stdout.write("Set one with:  manage.py reset_login <username> --set")

        self.stdout.write("")
