"""
Seed the subject and topic catalogue from app/seed_data.py.

    python manage.py seed_subjects                # apply
    python manage.py seed_subjects --dry-run       # report, change nothing

app/seed_data.py's SUBJECTS and TOPICS lists are themselves generated from
docs/seed.xlsx (its Subjects and Topics sheets) — that workbook is the
source of truth for the catalogue; this command is what loads it into the
database.

Idempotent: every row is matched on its natural key (Subject.short_name,
or (Subject, Topic.short_name) for a topic), so running it twice changes
nothing and running it again after the catalogue changes updates titles,
descriptions and ordering in place. Nothing is ever deleted — a subject or
topic dropped from seed_data stays in the catalogue until pruned by
prune_subjects / prune_topics.

Rows are attributed to the user named by --created-by (default: the first
superuser), so the audit trail says who loaded the catalogue.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import models, seed_data


class Command(BaseCommand):
    help = "Seed the Subject and Topic catalogue from app/seed_data.py (sourced from docs/seed.xlsx)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--created-by", type=str, default=None,
            help="Username to attribute the rows to. Defaults to the first superuser.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        user = self._resolve_user(options["created_by"])

        self.counts = {k: [0, 0] for k in ("subject", "topic")}

        try:
            with transaction.atomic():
                self._seed(user)
                if dry_run:
                    raise _Rollback()
        except _Rollback:
            self.stdout.write(self.style.WARNING("\nDry run — nothing was written.\n"))

        self._report(dry_run)

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

    # -- the seed --------------------------------------------------------
    def _seed(self, user):
        subjects = {}
        for row in seed_data.SUBJECTS:
            subjects[row["short_name"]] = self._upsert(
                models.Subject, "subject",
                {
                    "full_name": row["full_name"],
                    "id_number": row["id_number"],
                    "description": row["description"],
                    "sort_order": row["sort_order"],
                    "created_by": user,
                },
                short_name=row["short_name"],
            )

        # Topics reference their subject and (optionally) their parent by
        # short_name. A topic can only be created once its parent exists,
        # so resolve them in dependency order: repeatedly sweep the rows,
        # creating whatever is ready, until nothing changes. This works
        # for any nesting depth, not just the flat two-level sheet in use
        # today.
        remaining = list(seed_data.TOPICS)
        created_topics = {}  # (subject_short_name, topic_short_name) -> Topic
        while remaining:
            progressed = False
            still_remaining = []
            for row in remaining:
                subject_code = row["subject"]
                parent_code = row["parent"]
                if subject_code not in subjects:
                    raise CommandError(
                        f"Topic {row['short_name']!r} references unknown subject "
                        f"{subject_code!r}. Check seed_data.SUBJECTS."
                    )
                if parent_code and (subject_code, parent_code) not in created_topics:
                    still_remaining.append(row)
                    continue

                subject = subjects[subject_code]
                parent = created_topics.get((subject_code, parent_code)) if parent_code else None
                topic = self._upsert(
                    models.Topic, "topic",
                    {
                        "full_name": row["full_name"],
                        "id_number": row["id_number"],
                        "description": row["description"],
                        "sort_order": row["sort_order"],
                        "parent": parent,
                        "created_by": user,
                    },
                    subject=subject, short_name=row["short_name"],
                )
                created_topics[(subject_code, row["short_name"])] = topic
                progressed = True

            if not progressed:
                unresolved = ", ".join(
                    f"{r['subject']}/{r['short_name']} (parent {r['parent']!r})"
                    for r in still_remaining
                )
                raise CommandError(f"Topics with unresolved parents: {unresolved}")
            remaining = still_remaining

    # -- output --------------------------------------------------------
    def _report(self, dry_run):
        verb = "would create" if dry_run else "created"
        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("Subject/topic catalogue seed"))
        for kind, (created, updated) in self.counts.items():
            self.stdout.write(f"  {kind:8} {verb} {created:4}   updated {updated:4}")
        self.stdout.write("")


class _Rollback(Exception):
    """Aborts the transaction on --dry-run."""
