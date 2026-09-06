"""
Clear saved admin dashboard layouts so they rebuild from the current one.

    python manage.py reset_dashboards
    python manage.py reset_dashboards --user teacher_test_1

Jet stores each user's dashboard in the database the first time they open
it, and users may rearrange their own panels. That means a change to
`app/dashboard.py` does not reach anyone who has already visited the admin
— they keep the layout that was saved for them.

This deletes those saved layouts. Nothing else is touched: the next visit
rebuilds the dashboard from the current code. Run it after changing the
dashboard.
"""

from django.core.management.base import BaseCommand
from jet.dashboard.models import UserDashboardModule

from app import models


class Command(BaseCommand):
    help = "Clear saved dashboard layouts so they rebuild from app/dashboard.py."

    def add_arguments(self, parser):
        parser.add_argument("--user", help="One username only. Default: everyone.")

    def handle(self, *args, **options):
        rows = UserDashboardModule.objects.all()
        username = options.get("user")

        if username:
            user = models.AppUser.objects.filter(username=username).first()
            if user is None:
                self.stdout.write(self.style.ERROR(f"No such user: {username}"))
                return
            rows = rows.filter(user=user.pk)

        count = rows.count()
        rows.delete()
        self.stdout.write(self.style.SUCCESS(
            f"Cleared {count} saved dashboard panel(s). "
            "They rebuild from app/dashboard.py on the next visit."
        ))
