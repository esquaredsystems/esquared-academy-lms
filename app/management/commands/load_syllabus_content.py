"""
Load the O Level syllabus content into subjects and the topic catalogue.

    venv\\Scripts\\python.exe manage.py load_syllabus_content            # report only
    venv\\Scripts\\python.exe manage.py load_syllabus_content --commit   # apply it

For each subject it writes a student-friendly description, and builds the
topic catalogue: each syllabus topic as a top-level topic, with its
subtopics as children beneath it. The content comes from
docs/syllabus_content.json, extracted from the Cambridge syllabuses that
are valid for 2027 examinations.

Safe to run again: a topic is matched by its name within the subject and
updated rather than duplicated, so re-running corrects rather than repeats.
It never voids topics — anything a teacher added by hand is left alone.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import models

DEFAULT_PATH = "docs/syllabus_content.json"


class Command(BaseCommand):
    help = "Write subject descriptions and build the topic/subtopic catalogue."

    def add_arguments(self, parser):
        parser.add_argument("--path", default=DEFAULT_PATH,
                            help=f"The content file. Default {DEFAULT_PATH}.")
        parser.add_argument("--commit", action="store_true",
                            help="Apply it. Without this it only reports.")

    def handle(self, *args, **options):
        path = Path(options["path"])
        if not path.exists():
            raise CommandError(f"No content file at {path}.")
        data = json.loads(path.read_text(encoding="utf-8"))
        commit = options["commit"]

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Syllabus content" + ("" if commit else "   — REPORT ONLY, nothing written")
        ))

        subj_done = topics_done = subs_done = missing = 0

        with transaction.atomic():
            for short_name, spec in data.items():
                subject = models.Subject.objects.filter(short_name=short_name).first()
                if subject is None:
                    self.stdout.write(self.style.WARNING(f"  {short_name:5} subject not found — skipped"))
                    missing += 1
                    continue

                used = set()   # short_names already taken within this subject

                def short_of(name):
                    base = name[:64].strip()
                    label, n = base, 1
                    while label.lower() in used:
                        n += 1
                        suffix = f" ({n})"
                        label = base[:64 - len(suffix)] + suffix
                    used.add(label.lower())
                    return label

                # description on the subject
                if commit:
                    subject.description = spec["description"]
                    subject.save()
                subj_done += 1

                t_count = s_count = 0
                for order, topic in enumerate(spec["topics"]):
                    t_short = short_of(topic["name"])
                    if commit:
                        row = models.Topic.objects.filter(
                            subject=subject, short_name=t_short, voided=False
                        ).first()
                        if row is None:
                            row = models.Topic(subject=subject, short_name=t_short)
                        row.full_name = topic["name"][:256]
                        row.parent = None
                        row.id_number = topic.get("code") or None
                        row.sort_order = order
                        row.save()
                    t_count += 1

                    for s_order, sub in enumerate(topic.get("subtopics", [])):
                        s_short = short_of(sub)
                        if commit:
                            child = models.Topic.objects.filter(
                                subject=subject, short_name=s_short, voided=False
                            ).first()
                            if child is None:
                                child = models.Topic(subject=subject, short_name=s_short)
                            child.full_name = sub[:256]
                            child.parent = row
                            child.sort_order = s_order
                            child.save()
                        s_count += 1

                topics_done += t_count
                subs_done += s_count
                self.stdout.write(
                    f"  {short_name:5} description + {t_count} topics, {s_count} subtopics"
                )

            if not commit:
                transaction.set_rollback(True)

        self.stdout.write("")
        if commit:
            self.stdout.write(self.style.SUCCESS(
                f"Done — {subj_done} subjects, {topics_done} topics, {subs_done} subtopics written."
                + (f" {missing} subjects not found." if missing else "")
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"Report only — would write {subj_done} subjects, {topics_done} topics, "
                f"{subs_done} subtopics. Run again with --commit to apply."
            ))
        self.stdout.write("")
