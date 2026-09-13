"""
Void the subjects the academy no longer teaches, and everything under them,
so they disappear from every list — Subjects, Topics and Syllabus Topics.

    venv\\Scripts\\python.exe manage.py prune_subjects            # report only
    venv\\Scripts\\python.exe manage.py prune_subjects --commit   # void them

The academy keeps twelve subjects (KEEP below, with Pakistan Studies split
into PST1 History and PST2 Environment). Any other subject — Biology,
Science, the auto-added Activity, or anything else — is voided along with:
its topics and subtopics, its syllabus-topic links, and its (untaught)
syllabus, timetable and teaching rows.

Voiding is the system's soft delete: the rows stay in the database for the
audit trail but never appear in any normal list, dropdown or picker — you
will not see them. A mistake is undone by unvoiding in the admin. A surplus
subject that a class is actually studying (a live syllabus) is reported and
left alone unless you pass --force.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from app import models

KEEP = {"ENG", "MATH", "PHY", "CHEM", "ISL", "PST1", "PST2",
        "CS", "BUS", "ACC", "ECON", "URDU"}


class Command(BaseCommand):
    help = "Void surplus subjects and everything under them (topics, links, syllabi)."

    def add_arguments(self, parser):
        parser.add_argument("--commit", action="store_true",
                            help="Apply it. Without this it only reports.")
        parser.add_argument("--force", action="store_true",
                            help="Also void a surplus subject a class is studying.")

    @staticmethod
    def _void_all(queryset, reason):
        """Void rows one at a time so active_flag is cleared on each."""
        n = 0
        for row in queryset:
            if not row.voided:
                row.void(reason=reason)
                n += 1
        return n

    def handle(self, *args, **options):
        commit = options["commit"]
        force = options["force"]
        reason = "subject not taught by the academy"

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            "Subjects to void" + ("" if commit else "   — REPORT ONLY, nothing written")
        ))

        surplus = models.Subject.objects.exclude(short_name__in=KEEP).order_by("sort_order")
        if not surplus.exists():
            self.stdout.write("\n" + self.style.SUCCESS(
                "Nothing to void — only the twelve kept subjects remain.") + "\n")
            return

        going, held = [], []
        for s in surplus:
            live_syllabi = models.Syllabus.objects.filter(subject=s).count()
            row = {
                "subject": s,
                "topics": models.Topic.objects.filter(subject=s).count(),
                "links": models.SyllabusTopic.objects.filter(topic__subject=s).count()
                       + models.SyllabusTopic.objects.filter(syllabus__subject=s).count(),
                "syllabi": live_syllabi,
                "taught": models.StudentSubject.objects.filter(syllabus__subject=s).exists()
                          or models.LessonTopic.objects.filter(topic__subject=s).exists(),
            }
            (held if row["taught"] and not force else going).append(row)

        self.stdout.write("")
        for row in going:
            s = row["subject"]
            bits = [f"{row['topics']} topics"] if row["topics"] else []
            if row["links"]: bits.append(f"{row['links']} syllabus-topic link(s)")
            if row["syllabi"]: bits.append(f"{row['syllabi']} syllabus row(s)")
            self.stdout.write(f"  {s.short_name} — {s.full_name}" + (f"  ({', '.join(bits)})" if bits else ""))
        for row in held:
            s = row["subject"]
            self.stdout.write(self.style.WARNING(
                f"  {s.short_name} — {s.full_name}: a class is studying this — skipped (use --force)."))

        if commit and going:
            counts = {"subjects": 0, "topics": 0, "links": 0, "syllabi": 0, "other": 0}
            with transaction.atomic():
                for row in going:
                    s = row["subject"]
                    counts["links"] += self._void_all(
                        models.SyllabusTopic.objects.filter(topic__subject=s), reason)
                    counts["links"] += self._void_all(
                        models.SyllabusTopic.objects.filter(syllabus__subject=s), reason)
                    counts["topics"] += self._void_all(
                        models.Topic.objects.filter(subject=s), reason)
                    counts["other"] += self._void_all(
                        models.TeachingAssignment.objects.filter(syllabus__subject=s), reason)
                    counts["other"] += self._void_all(
                        models.TimetableSlot.objects.filter(syllabus__subject=s), reason)
                    counts["syllabi"] += self._void_all(
                        models.Syllabus.objects.filter(subject=s), reason)
                    if not s.voided:
                        s.void(reason=reason)
                        counts["subjects"] += 1
            self.stdout.write("\n" + self.style.SUCCESS(
                f"Voided {counts['subjects']} subject(s), {counts['topics']} topic(s), "
                f"{counts['links']} syllabus-topic link(s), {counts['syllabi']} syllabus row(s). "
                "They will not appear in any list now. Unvoid in the admin if needed.") + "\n")
        elif not commit:
            self.stdout.write("\n" + self.style.WARNING(
                f"Report only — {len(going)} subject(s) and everything under them would be "
                "voided. Run again with --commit to apply.") + "\n")
        else:
            self.stdout.write("")
