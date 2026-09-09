"""
Show one account's login state and, optionally, set its password.

    python manage.py reset_login reviewer_test_1            # just report
    python manage.py reset_login reviewer_test_1 --set      # report, then set a password
    python manage.py reset_login new_user_1      --set --create  # create + set password
    python manage.py reset_login 26070108 --set --password Aariz  # non-interactive (scripted)

Written for the moment a test account "won't accept the password". It
prints the three things the admin login actually checks — the account
exists, is active, and is staff — so the real reason is visible rather
than guessed. With --set it prompts for a new password (typing is
invisible, nothing is written to the shell history) and makes sure the
account is active and, for a staff role, staff.

--create: if the account does not exist yet, create it (unusable password),
then continue as normal. Useful for the first setup of non-teacher roles
where import_setup hasn't pre-created the account.

--password: supply the new password directly instead of being prompted.
Intended for bulk/scripted setup where getpass cannot be driven. Note the
value is passed as a command-line argument, so avoid it for secrets that
must not appear in a process listing.

This is a development helper for test accounts. It is not for changing a
real person's password without their knowledge.
"""

from getpass import getpass

from django.core.management.base import BaseCommand, CommandError

from app import access, models


class Command(BaseCommand):
    help = "Report an account's login state, and optionally set its password."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument(
            "--set", action="store_true",
            help="Prompt for a new password and apply it, activating the account.",
        )
        parser.add_argument(
            "--create", action="store_true",
            help="Create the account if it does not exist, then proceed.",
        )
        parser.add_argument(
            "--password",
            default=None,
            help="Set this password non-interactively instead of prompting "
                 "(implies --set). Intended for bulk/scripted setup.",
        )

    def handle(self, *args, **options):
        username = options["username"]
        pw_arg    = options["password"]
        do_set    = options["set"] or pw_arg is not None
        do_create = options["create"]

        user = models.AppUser.all_objects.filter(username=username).first()

        if user is None:
            if do_create:
                user = models.AppUser.objects.create_user(
                    username=username,
                    password=None,
                    is_active=True,
                    is_staff=False,
                )
                self.stdout.write(self.style.SUCCESS(
                    f"Created new account: {username}"
                ))
            else:
                near = list(
                    models.AppUser.all_objects
                    .filter(username__icontains=username.split("_")[0])
                    .values_list("username", flat=True)[:10]
                )
                raise CommandError(
                    f"No account called {username!r}.\n"
                    + (f"Did you mean one of: {', '.join(near)}\n" if near else "")
                    + "\nTo create it as you set the password:\n"
                    + f"    manage.py reset_login {username} --set --create\n"
                    + "To create accounts for every student at once:\n"
                    + "    manage.py seed_student_logins --commit"
                )

        groups = list(user.groups.values_list("name", flat=True))
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Account: {user.username}"))
        self.stdout.write(f"  active ............ {user.is_active}")
        self.stdout.write(f"  staff (admin) ..... {user.is_staff}")
        self.stdout.write(f"  superuser ......... {user.is_superuser}")
        self.stdout.write(f"  suspended ......... {user.suspended}")
        self.stdout.write(f"  has a password .... {user.has_usable_password()}")
        self.stdout.write(f"  voided ............ {user.voided}")
        self.stdout.write(f"  roles ............. {', '.join(groups) or '(none)'}")
        self.stdout.write("")

        # Name the likely blockers plainly.
        problems = []
        if user.voided:
            problems.append("the account is voided (soft-deleted)")
        if not user.is_active:
            problems.append("the account is not active")
        if not user.is_staff and not user.is_superuser:
            problems.append("the account is not staff, so /admin/ refuses it")
        if not user.has_usable_password():
            problems.append("the account has no usable password set")
        if problems:
            self.stdout.write(self.style.WARNING("Why the login is refused:"))
            for p in problems:
                self.stdout.write(f"  - {p}")
            self.stdout.write("")

        if not do_set:
            self.stdout.write("Run again with --set to choose a password and fix these.")
            return

        if pw_arg is not None:
            password = pw_arg
            if not password:
                raise CommandError("Empty --password. Nothing was changed.")
        else:
            password = getpass("New password: ")
            again = getpass("Again: ")
            if not password or password != again:
                raise CommandError("Passwords did not match. Nothing was changed.")

        user.set_password(password)
        user.is_active = True
        user.voided = False
        user.active_flag = True
        # A role that is meant to use the admin should be able to reach it.
        if groups and not (set(groups) & access.NON_ADMIN_ROLES):
            user.is_staff = True
        user.save()

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Password set for {user.username}. active={user.is_active}, "
            f"staff={user.is_staff}. Try logging in now."
        ))
