"""
Void the topics that belong to subjects the academy no longer teaches.

    venv\\Scripts\\python.exe manage.py prune_topics            # report only
    venv\\Scripts\\python.exe manage.py prune_topics --commit   # void them

The academy keeps twelve subjects (see KEEP below, with Pakistan Studies
split into PST1 History and PST2 Environment). Any topic hanging off any
other subject — Biology, Science, the auto-added Activity, or anything
else — is not part of the curriculum and is voided so it stops cluttering
the topic list and the pickers.

Nothing is deleted. Topics are voided (the system's soft delete), so a
mistake is undone by unvoiding, and the audit trail survives. Topics under
the twelve kept subjects are never touched.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app import models

# The subjects the academy teaches, by short name. Everything else is surplus.
KEEP = {"ENG", "MATH", "PHY", "CHEM", "ISL", "PST1", "PST2",
        "CS", "BUS", "ACC", "ECON", "URDU"}


class Command(BaseCommand):
    help = "Void topics whose subject is not one of the twelve kept subjects."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true",
                            help="Apply it. Without this it only reports.")

    def handle(self, *args, **options):
        commit = options["commit"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Topics to void" + ("" if commit else "   — REPORT ONLY, nothing written")
        ))

        # Live topics whose subject is not on the keep list.
        surplus = (
            models.Topic.objects
            .exclude(subject__short_name__in=KEEP)
            .select_related("subject")
            .order_by("subject__short_name", "path")
        )

        by_subject = {}
        for topic in surplus:
            by_subject.setdefault(topic.subject.short_name, []).append(topic)

        if not by_subject:
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                "Nothing to void — every live topic already belongs to one of the "
                "twelve subjects."
            ))
            self.stdout.write("")
            return

        total = 0
        self.stdout.write("")
        for short_name in sorted(by_subject):
            rows = by_subject[short_name]
            full = rows[0].subject.full_name
            self.stdout.write(f"  {short_name} — {full}: {len(rows)} topic(s)")
            for t in rows[:8]:
                self.stdout.write(f"       {t.full_name[:60]}")
            if len(rows) > 8:
                self.stdout.write(f"       … and {len(rows) - 8} more")
            total += len(rows)

        if commit:
            with transaction.atomic():
                for rows in by_subject.values():
                    for topic in rows:
                        if not topic.voided:
                            topic.void(reason="subject not taught by the academy")
            self.stdout.write("")
            self.stdout.write(self.style.SUCCESS(
                f"Voided {total} topic(s) across {len(by_subject)} subject(s). "
                "Unvoid any in the admin if needed."
            ))
        else:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                f"Report only — {total} topic(s) across {len(by_subject)} subject(s) "
                "would be voided. Run again with --commit to apply."
            ))
        self.stdout.write("")
