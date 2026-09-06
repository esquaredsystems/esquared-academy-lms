"""
Give existing handouts a version 1 for the sheet they already carry.

    python manage.py backfill_sheets

Sheets became versioned after some handouts already existed. Those have a
file attached but no version recorded, so they would read as "v0" and a
replacement would be numbered oddly. This records what is already there as
version 1 and changes nothing else. Safe to run twice.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app import models


class Command(BaseCommand):
    help = "Record each handout's existing sheet as version 1."

    def handle(self, *args, **options):
        done = skipped = 0
        with transaction.atomic():
            for handout in models.Handout.objects.filter(voided=False):
                if handout.sheets.filter(voided=False).exists():
                    skipped += 1
                    continue
                files = handout.files("handout")
                if not files:
                    skipped += 1
                    continue
                models.HandoutSheet.objects.create(
                    handout=handout, attachment=files[0], version_no=1,
                    note="Recorded from the file already attached.",
                )
                done += 1

        self.stdout.write(self.style.SUCCESS(
            f"{done} handout(s) given a version 1; {skipped} already had one "
            "or had no sheet."
        ))
