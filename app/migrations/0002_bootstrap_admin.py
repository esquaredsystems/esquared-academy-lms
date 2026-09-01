"""
Create the first superuser so a fresh database has someone who can log in.

The defaults are admin / admin. That is fine on a laptop and dangerous
anywhere else, so:

  * nothing is created if any superuser already exists;
  * DJANGO_BOOTSTRAP_ADMIN=false skips this migration entirely;
  * DJANGO_BOOTSTRAP_ADMIN_USERNAME / _PASSWORD / _EMAIL override the
    defaults, which is how any deployed environment should run it.

Change the password before this database is reachable by anyone else.
"""

import os

from django.db import migrations


def env_bool(key, default):
    return str(os.environ.get(key, default)).strip().lower() in {"1", "true", "yes", "on"}


def create_admin(apps, schema_editor):
    if not env_bool("DJANGO_BOOTSTRAP_ADMIN", "true"):
        return

    AppUser = apps.get_model("app", "AppUser")
    if AppUser.objects.filter(is_superuser=True).exists():
        return

    username = os.environ.get("DJANGO_BOOTSTRAP_ADMIN_USERNAME", "admin")
    password = os.environ.get("DJANGO_BOOTSTRAP_ADMIN_PASSWORD", "admin")
    email = os.environ.get("DJANGO_BOOTSTRAP_ADMIN_EMAIL", "admin@example.com")

    if AppUser.objects.filter(username=username).exists():
        return

    # Historical models have no manager methods, so the password is hashed
    # with the hasher directly rather than through create_superuser().
    from django.contrib.auth.hashers import make_password
    from django.utils import timezone

    user = AppUser.objects.create(
        username=username,
        email=email,
        password=make_password(password),
        first_name="Site",
        last_name="Administrator",
        is_staff=True,
        is_superuser=True,
        is_active=True,
        date_joined=timezone.now(),
        date_created=timezone.now(),
    )
    user.created_by = user
    user.save(update_fields=["created_by"])


def remove_admin(apps, schema_editor):
    """Reverse: void the bootstrap account rather than deleting it."""
    AppUser = apps.get_model("app", "AppUser")
    username = os.environ.get("DJANGO_BOOTSTRAP_ADMIN_USERNAME", "admin")
    AppUser.objects.filter(username=username, is_superuser=True).update(
        is_active=False, voided=True, void_reason="bootstrap admin migration reversed"
    )


class Migration(migrations.Migration):

    dependencies = [
        ("app", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_admin, remove_admin),
    ]
