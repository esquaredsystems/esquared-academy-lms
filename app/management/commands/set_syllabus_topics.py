"""
Put every subject's topics onto its syllabus for the year.

    venv\\Scripts\\python.exe manage.py set_syllabus_topics            # report only
    venv\\Scripts\\python.exe manage.py set_syllabus_topics --commit   # apply it

A syllabus lists which of a subject's catalogue topics that class studies
this year — those are the "syllabus topics". This links every top-level
topic of each subject to that subject's syllabus for the given year (2627
by default), in order. The subtopics come along automatically: they sit
under their parent topic, so listing the parent brings the whole branch.

Runs against the syllabi that already exist for the year — so run
set_syllabi first. Safe to run again: a topic already on a syllabus is
left as it is, never duplicated.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app import models

YEAR = 2627


class Command(BaseCommand):
    help = "Link each subject's top-level topics to its syllabus for the year."

    def add_arguments(self, parser):
        parser.add_argument("--year", type=int, default=YEAR,
                            help=f"Academic year. Default {YEAR}.")
        parser.add_argument("--commit", action="store_true",
                            help="Apply it. Without this it only reports.")

    def handle(self, *args, **options):
        year = options["year"]
        commit = options["commit"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Syllabus topics for {year}"
            + ("" if commit else "   — REPORT ONLY, nothing written")
        ))

        syllabi = (
            models.Syllabus.objects
            .filter(academic_year=year, voided=False)
            .select_related("subject", "grade")
            .order_by("grade__sort_order", "subject__sort_order", "subject__short_name")
        )
        if not syllabi:
            self.stdout.write("\n" + self.style.WARNING(
                f"No syllabi for {year}. Run set_syllabi first.") + "\n")
            return

        self.stdout.write("")
        total_linked = total_have = 0
        with transaction.atomic():
            for syl in syllabi:
                topics = list(
                    models.Topic.objects
                    .filter(subject=syl.subject, voided=False, parent__isnull=True)
                    .order_by("sort_order", "short_name")
                )
                # where to start numbering, so we never collide with links
                # already on this syllabus
                existing = {
                    st.topic_id: st
                    for st in models.SyllabusTopic.objects.filter(syllabus=syl, voided=False)
                }
                order = len(existing)
                linked = have = 0
                for topic in topics:
                    if topic.pk in existing:
                        have += 1
                        continue
                    linked += 1
                    if commit:
                        models.SyllabusTopic.objects.create(
                            syllabus=syl, topic=topic, sort_order=order,
                        )
                        order += 1

                total_linked += linked
                total_have += have
                self.stdout.write(
                    f"  {syl.grade.short_name:3} {syl.subject.short_name:5} "
                    f"{len(topics):2} topic(s): +{linked} linked"
                    + (f", {have} already there" if have else "")
                )

            if not commit:
                transaction.set_rollback(True)

        self.stdout.write("")
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Done — {total_linked} topic(s) linked to their syllabi "
                f"({total_have} already present)."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Report only — would link {total_linked} topic(s) "
                f"({total_have} already present). Run again with --commit to apply."
            ))
        self.stdout.write("")
