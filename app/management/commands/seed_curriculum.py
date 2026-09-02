"""
Seed the curriculum: grades, subjects, topics and the year's syllabi.

    python manage.py seed_curriculum                # current calendar year
    python manage.py seed_curriculum --year 2027
    python manage.py seed_curriculum --dry-run      # report, change nothing

Idempotent: every row is matched on its natural key, so running it twice
changes nothing and running it after a syllabus revision updates titles in
place. Nothing is ever deleted — a topic dropped from `seed_data` stays in
the catalogue and simply leaves that year's syllabus, which is the whole
point of separating `topic` from `syllabus_topic`.

Rows are attributed to the user named by --created-by (default: the first
superuser), so the audit trail says who loaded the curriculum.
"""

from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import models, seed_data


class Command(BaseCommand):
    help = "Seed Cambridge grades, subjects, topics and syllabi for an academic year."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year", type=int, default=date.today().year,
            help="Academic year to build syllabi for. Defaults to the current year.",
        )
        parser.add_argument(
            "--created-by", type=str, default=None,
            help="Username to attribute the rows to. Defaults to the first superuser.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        year = options["year"]
        dry_run = options["dry_run"]
        user = self._resolve_user(options["created_by"])

        self.counts = {k: [0, 0] for k in ("grade", "subject", "topic", "syllabus", "syllabus_topic")}

        try:
            with transaction.atomic():
                self._seed(user, year)
                if dry_run:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING("\nDry run — nothing was written.\n"))

        self._report(year, dry_run)

    # -- helpers -------------------------------------------------------
    def _resolve_user(self, username):
        if username:
            try:
                return models.AppUser.objects.get(username=username)
            except models.AppUser.DoesNotExist:
                raise CommandError(f"No user named {username!r}.")
        user = models.AppUser.objects.filter(is_superuser=True).order_by("id").first()
        if not user:
            raise CommandError(
                "No superuser to attribute the seed to. Run migrate (which creates "
                "one) or pass --created-by."
            )
        return user

    def _track(self, kind, created):
        self.counts[kind][0 if created else 1] += 1

    def _upsert(self, model, kind, defaults, **lookup):
        """update_or_create against the live (non-voided) rows."""
        obj = model.objects.filter(**lookup).first()
        if obj is None:
            obj = model.objects.create(**lookup, **defaults)
            self._track(kind, True)
        else:
            for field, value in defaults.items():
                setattr(obj, field, value)
            obj.save()
            self._track(kind, False)
        return obj

    # -- the seed ------------------------------------------------------
    def _seed(self, user, year):
        grades = {}
        for order, row in enumerate(seed_data.GRADES, start=1):
            grades[row["short_name"]] = self._upsert(
                models.Grade, "grade",
                {
                    "full_name": row["full_name"],
                    "level": row["level"],
                    "is_terminal": row["is_terminal"],
                    "sort_order": order,
                    "created_by": user,
                },
                short_name=row["short_name"],
            )

        subjects = {}
        for order, row in enumerate(seed_data.SUBJECTS, start=1):
            subjects[row["short_name"]] = self._upsert(
                models.Subject, "subject",
                {
                    "full_name": row["full_name"],
                    "id_number": row["id_number"],
                    "description": row["description"],
                    "sort_order": order,
                    "created_by": user,
                },
                short_name=row["short_name"],
            )

        # Topics are catalogue entries: one row per syllabus section, keyed
        # by "<stage>-<section>" so a subject can hold both its Lower
        # Secondary strands and its O Level sections without collision.
        topics = {}
        for (subject_code, stage), entry in seed_data.TOPICS.items():
            subject = subjects[subject_code]
            for order, (code, title) in enumerate(entry["topics"], start=1):
                short_name = f"{stage}-{code}"
                description = entry["source"]
                if entry.get("note"):
                    description = f"{description}\n\n{entry['note']}"
                topics[(subject_code, stage, code)] = self._upsert(
                    models.Topic, "topic",
                    {
                        "full_name": title,
                        "id_number": f"{subject.id_number}-{stage}-{code}",
                        "description": description,
                        "sort_order": order,
                        "created_by": user,
                    },
                    subject=subject, short_name=short_name,
                )

        # One syllabus per subject per grade per year, carrying that stage's
        # topics in teaching order.
        for grade_code, entries in seed_data.CURRICULUM.items():
            grade = grades[grade_code]
            for subject_code, stage, is_core in entries:
                subject = subjects[subject_code]
                syllabus = self._upsert(
                    models.Syllabus, "syllabus",
                    {
                        "full_name": f"{subject.full_name} — {grade.full_name} ({year})",
                        "is_core": is_core,
                        "status": models.SyllabusStatus.PUBLISHED,
                        "date_published": models.timezone.now(),
                        "created_by": user,
                    },
                    subject=subject, grade=grade, academic_year=year,
                )

                entry = seed_data.TOPICS.get((subject_code, stage))
                if not entry:
                    continue  # e.g. Islamiyat and Urdu at Lower Secondary
                for order, (code, _title) in enumerate(entry["topics"], start=1):
                    self._upsert(
                        models.SyllabusTopic, "syllabus_topic",
                        {"sort_order": order, "created_by": user},
                        syllabus=syllabus, topic=topics[(subject_code, stage, code)],
                    )

    # -- output --------------------------------------------------------
    def _report(self, year, dry_run):
        verb = "would create" if dry_run else "created"
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(f"Curriculum seed — academic year {year}"))
        for kind, (created, updated) in self.counts.items():
            self.stdout.write(f"  {kind:16} {verb} {created:4}   updated {updated:4}")

        empty = [
            f"{s.subject.short_name} {s.grade.short_name}"
            for s in models.Syllabus.objects.filter(academic_year=year)
            if not s.topics.exists()
        ]
        if empty:
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(
                "Syllabi with no topics (no Cambridge framework exists at this stage — "
                "the department defines them): " + ", ".join(empty)
            ))
        self.stdout.write("")


class _Rollback(Exception):
    """Aborts the transaction on --dry-run."""
