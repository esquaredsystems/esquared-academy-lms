"""
Turn the weekly timetable into real lessons.

    python manage.py generate_lessons                      # this week
    python manage.py generate_lessons --weeks 2            # this week and next
    python manage.py generate_lessons --from 2026-09-14 --to 2026-09-18
    python manage.py generate_lessons --grade S2 --dry-run

`TimetableSlot` is the pattern — one subject, one grade, one day, one
period, set once a year. `Lesson` is the class that actually happens on a
date, and it is what everything else hangs off: the teaching timer, the
lecture table, the log, and the assignments set from it.

Nothing created these before, so a teacher opening My day saw an empty
screen no matter how complete the timetable was. This walks the slots
across a range of dates and creates the missing lessons.

Safe to run again. A lesson already there — however much a teacher has
since written on it — is left exactly as it is, so the honest way to
extend the term is simply to run it again with a later date.

Lessons are created as DRAFT, unteached and unlogged. It creates the slot
in the day, not the content: the plan, the material and the assignment are
the teacher's.
"""

from datetime import date as date_cls, datetime, timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from app import models


def current_academic_year():
    """
    The session as the school writes it: 1 July 2026 – 30 June 2027 is 2627.

    Derived from the clock rather than stored in a setting, so nobody has
    to remember to change it in July.
    """
    today = date_cls.today()
    start = today.year if today.month >= 7 else today.year - 1
    return int(f"{start % 100:02d}{(start + 1) % 100:02d}")


def parse_date(value, label):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        raise CommandError(f"--{label} should look like 2026-09-14, not {value!r}.")


class Command(BaseCommand):
    help = "Create Lesson rows from the weekly TimetableSlot pattern."

    def add_arguments(self, parser):
        parser.add_argument("--from", dest="start", help="First date, YYYY-MM-DD. Defaults to this Monday.")
        parser.add_argument("--to", dest="end", help="Last date, YYYY-MM-DD. Defaults to the Sunday of the last week.")
        parser.add_argument("--weeks", type=int, default=1,
                            help="How many weeks from the start date. Ignored when --to is given. Default 1.")
        parser.add_argument("--year", type=int, default=None,
                            help=f"Academic year to take slots from. Defaults to {current_academic_year()}.")
        parser.add_argument("--grade", default=None, help="Only this class, e.g. S2.")
        parser.add_argument("--dry-run", action="store_true", help="Report what would happen, write nothing.")

    def handle(self, *args, **options):
        year = options["year"] or current_academic_year()
        dry = options["dry_run"]

        today = date_cls.today()
        start = parse_date(options["start"], "from") if options["start"] else today - timedelta(days=today.weekday())
        if options["end"]:
            end = parse_date(options["end"], "to")
        else:
            end = start + timedelta(days=7 * max(1, options["weeks"]) - 1)
        if end < start:
            raise CommandError("The end date is before the start date.")

        slots = (
            models.TimetableSlot.objects
            .filter(voided=False, syllabus__academic_year=year, syllabus__voided=False)
            .select_related("syllabus", "syllabus__grade", "syllabus__subject", "teacher")
            .order_by("day_of_week", "period")
        )
        if options["grade"]:
            slots = slots.filter(syllabus__grade__short_name=options["grade"])

        by_day = {}
        for slot in slots:
            by_day.setdefault(slot.day_of_week, []).append(slot)

        if not by_day:
            raise CommandError(
                f"No timetable slots for academic year {year}"
                + (f" and class {options['grade']}" if options["grade"] else "")
                + ".\nImport the timetable first:  manage.py import_setup docs/setup_data.json"
            )

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING(
            f"Lessons for {start:%d %b %Y} – {end:%d %b %Y}  (year {year})"
            + ("   DRY RUN — nothing will be written" if dry else "")
        ))

        created = existing = 0
        per_day = []

        with transaction.atomic():
            day = start
            while day <= end:
                todays = by_day.get(day.weekday(), [])
                made = found = 0
                for slot in todays:
                    lesson = models.Lesson.objects.filter(
                        syllabus=slot.syllabus, date=day, period=slot.period
                    ).first()
                    if lesson is not None:
                        found += 1
                        continue
                    if not dry:
                        models.Lesson.objects.create(
                            syllabus=slot.syllabus,
                            slot=slot,
                            teacher=slot.teacher,
                            date=day,
                            period=slot.period,
                            status=models.LessonStatus.DRAFT,
                        )
                    made += 1
                if todays:
                    per_day.append((day, made, found))
                created += made
                existing += found
                day += timedelta(days=1)

            if dry:
                transaction.set_rollback(True)

        for day, made, found in per_day:
            note = f"{made} created" if made else "nothing to do"
            if found:
                note += f", {found} already there"
            self.stdout.write(f"  {day:%a %d %b}   {note}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"{created} lesson(s) created, {existing} already existed."
        ))
        if dry:
            self.stdout.write(self.style.WARNING("Dry run — nothing was written."))
        elif created:
            self.stdout.write("A teacher's My day will now show these. The plan, the "
                              "material and the assignments are theirs to add.")
        self.stdout.write("")
