"""
Put a realistic lesson on today's date, so My day has something in it.

    python manage.py seed_today
    python manage.py seed_today --date 2026-09-07
    python manage.py seed_today --remove

An empty screen teaches nobody anything. This creates one lesson for
today with two topics, a lecture note on each, and a handout with its
sheet — enough to see the Lecture, Assignments and Logging sections
doing their jobs.

Everything it makes is prefixed `TODAY-` or titled "Sample", so
`--remove` can find it again. It is sample data: do not run it on a
database that holds real records.
"""

from datetime import date as date_cls

from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from app import files as app_files, models

MARK = "Sample"


def _pdf(title, lines):
    """A minimal one-page PDF, so the links open in a real viewer."""
    body = "BT /F1 18 Tf 60 760 Td (%s) Tj ET\n" % title.replace("(", "").replace(")", "")
    y = 730
    for line in lines:
        body += "BT /F1 11 Tf 60 %d Td (%s) Tj ET\n" % (
            y, line.replace("(", "").replace(")", "")
        )
        y -= 18
    stream = body.encode("latin-1", "replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
        b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, obj in enumerate(objects, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + obj + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n" % (len(objects) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objects) + 1, xref
    )
    return bytes(out)


class Command(BaseCommand):
    help = "Create a sample lesson for today, with topics, notes and a handout."

    def add_arguments(self, parser):
        parser.add_argument("--date", help="YYYY-MM-DD. Default: today.")
        parser.add_argument("--remove", action="store_true",
                            help="Delete what this command created.")

    def handle(self, *args, **options):
        day = (
            date_cls.fromisoformat(options["date"])
            if options.get("date") else timezone.localdate()
        )

        if options["remove"]:
            return self._remove()

        syllabus = models.Syllabus.objects.filter(voided=False).first()
        if syllabus is None:
            self.stdout.write(self.style.ERROR(
                "No syllabus exists yet. Run `manage.py seed_subjects` and "
                "`manage.py set_syllabi` first."
            ))
            return

        with transaction.atomic():
            lesson, made = models.Lesson.objects.get_or_create(
                syllabus=syllabus, date=day, period="1", voided=False,
                defaults={
                    "title": f"{MARK} lesson",
                    "plan": "Recap last week, then two new topics with a worked "
                            "example each. Hand out the worksheet at the end.",
                    "status": models.LessonStatus.APPROVED,
                },
            )
            self.stdout.write(
                ("Created " if made else "Reusing ") + f"lesson: {lesson}"
            )

            topics = list(
                models.Topic.objects.filter(
                    subject=syllabus.subject, voided=False, parent__isnull=True
                )[:2]
            )
            if not topics:
                topics = [
                    models.Topic.objects.create(
                        subject=syllabus.subject,
                        short_name=f"{MARK} topic {n}",
                        full_name=f"{MARK} topic {n}",
                    )
                    for n in (1, 2)
                ]

            lesson_ct = ContentType.objects.get_for_model(models.Lesson)
            topic_ct = ContentType.objects.get_for_model(models.LessonTopic)
            handout_ct = ContentType.objects.get_for_model(models.Handout)

            for order, topic in enumerate(topics):
                entry, _ = models.LessonTopic.objects.get_or_create(
                    lesson=lesson, topic=topic, voided=False,
                    defaults={"planned": True, "sort_order": order},
                )
                self._attach(
                    entry, topic_ct,
                    f"{MARK} notes — {topic.short_name}.pdf",
                    _pdf(f"Lecture notes: {topic.full_name}", [
                        "1. What it is, and why it matters.",
                        "2. A worked example.",
                        "3. Two for the class to try.",
                        "",
                        "(Sample file created by manage.py seed_today.)",
                    ]),
                    role="notes",
                )

            self._attach(
                lesson, lesson_ct, f"{MARK} slides.pdf",
                _pdf("Slides for today", ["Title slide", "Recap", "New material"]),
                role="material",
            )

            handout, made = models.Handout.objects.get_or_create(
                syllabus=syllabus, title=f"{MARK} worksheet", voided=False,
                defaults={
                    "topic": topics[0],
                    "instructions": "Answer every question. Show your working. "
                                    "Scan and upload under this code.",
                    "due_date": day,
                    "max_marks": 20,
                    "status": models.HandoutStatus.ACTIVE,
                    "date_activated": timezone.now(),
                },
            )
            models.HandoutLesson.objects.get_or_create(
                handout=handout, lesson=lesson, voided=False
            )
            self._attach(
                handout, handout_ct, f"{MARK} worksheet.pdf",
                _pdf(f"Worksheet — {handout.code}", [
                    "Name: ______________________  Admission no: ____________",
                    "",
                    "1. ...", "2. ...", "3. ...",
                    "",
                    "Scan this sheet and upload it under " + handout.code + ".",
                ]),
                role="handout",
            )
            self.stdout.write(f"Handout: {handout.code} — {handout.title}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Done. Open /admin/my-day/{'' if day == timezone.localdate() else ' and move to ' + day.isoformat()}"
        ))
        self.stdout.write("Remove it again with: manage.py seed_today --remove")
        self.stdout.write("")

    # -- helpers -------------------------------------------------------
    def _attach(self, obj, content_type, filename, payload, role):
        checksum = app_files.sha256_of(ContentFile(payload))
        attachment = models.Attachment.objects.filter(
            checksum=checksum, voided=False
        ).first()
        if attachment is None:
            attachment = models.Attachment(
                original_filename=filename, mime_type="application/pdf",
                kind=app_files.classify("application/pdf", filename),
                size_bytes=len(payload), checksum=checksum, title=filename,
            )
            attachment.file.save(filename, ContentFile(payload), save=False)
            attachment.save()
        models.AttachmentLink.objects.get_or_create(
            attachment=attachment, content_type=content_type,
            object_id=obj.pk, voided=False, defaults={"role": role},
        )
        self.stdout.write(f"  attached {filename}")

    def _remove(self):
        counts = []
        for model in (models.HandoutLesson, models.Submission, models.Handout,
                      models.LessonTopic, models.Lesson):
            if model is models.Handout:
                rows = model.all_objects.filter(title__startswith=MARK)
            elif model in (models.Lesson,):
                rows = model.all_objects.filter(title__startswith=MARK)
            elif model is models.HandoutLesson:
                rows = model.all_objects.filter(handout__title__startswith=MARK)
            elif model is models.Submission:
                rows = model.all_objects.filter(handout__title__startswith=MARK)
            else:
                rows = model.all_objects.filter(lesson__title__startswith=MARK)
            counts.append((model.__name__, rows.count()))
            rows.delete()
        attachments = models.Attachment.all_objects.filter(title__startswith=MARK)
        counts.append(("Attachment", attachments.count()))
        attachments.delete()
        for name, n in counts:
            self.stdout.write(f"  removed {n} {name}")
        self.stdout.write(self.style.WARNING("Sample data removed."))
