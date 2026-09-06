"""
Print what each role can actually see in the admin.

    python manage.py role_audit
    python manage.py role_audit --role "Paper Setter"

The left menu is built by the theme, not by Django, so what a role is
*shown* and what a role may *do* can drift apart. This reports the second
one — the permissions themselves — so the two can be compared.
"""

from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from app import access

ACTIONS = ("view", "add", "change", "delete")


class Command(BaseCommand):
    help = "Report the models each role may view, add, change or delete."

    def add_arguments(self, parser):
        parser.add_argument("--role", help="Report one role only.")

    def handle(self, *args, **options):
        wanted = options.get("role")
        roles = [wanted] if wanted else access.ROLES

        for role in roles:
            group = Group.objects.filter(name=role).first()
            if group is None:
                self.stdout.write(self.style.ERROR(f"{role}: no such group"))
                continue

            held = set(
                group.permissions.values_list("content_type__app_label", "codename")
            )
            by_model = {}
            for app_label, codename in held:
                action, _, model = codename.partition("_")
                if action not in ACTIONS:
                    continue
                by_model.setdefault(f"{app_label}.{model}", set()).add(action)

            self.stdout.write("")
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"{role}  —  {len(by_model)} models, {len(held)} permissions"
            ))
            if not by_model:
                self.stdout.write("  (nothing)")
                continue
            for model in sorted(by_model):
                marks = "".join(
                    a[0].upper() if a in by_model[model] else "·" for a in ACTIONS
                )
                self.stdout.write(f"  {marks}  {model}")

        self.stdout.write("")
        self.stdout.write("Columns are View Add Change Delete; a dot means not held.")
        self.stdout.write("")
