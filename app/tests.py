"""
Unit tests for the rules the schema promises but a foreign key cannot.

Run with `python manage.py test`, which uses an in-memory database — no
server, no files left behind.
"""

import io
import os
import re
import tempfile
import uuid
from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.admin import site
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from . import access, audit, columns, demo_data, entity_help, files, models


class Fixture(TestCase):
    """Shared skeleton: one grade, one subject, one paper, two questions."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.AppUser.objects.create_superuser(
            "tester", "tester@example.com", "pw12345!"
        )
        cls.grade = models.Grade.objects.create(
            level=5, short_name="G5", full_name="Grade 5", is_terminal=True,
            created_by=cls.user,
        )
        cls.subject = models.Subject.objects.create(
            short_name="ENG", full_name="English Language", created_by=cls.user
        )
        cls.syllabus = models.Syllabus.objects.create(
            subject=cls.subject, grade=cls.grade, academic_year=2026, created_by=cls.user
        )
        cls.topic = models.Topic.objects.create(
            subject=cls.subject, short_name="COMP", full_name="Comprehension",
            created_by=cls.user,
        )
        cls.prompt = models.EvaluationPrompt.objects.create(
            name="Short explanation, 3 marks", created_by=cls.user
        )
        cls.prompt_v1 = models.PromptVersion.objects.create(
            evaluation_prompt=cls.prompt, version_no=1,
            prompt_text="Mark against {{mark_scheme}}.",
            required_variables=["mark_scheme"],
            status=models.PromptStatus.ACTIVE, created_by=cls.user,
        )
        cls.q_binary = models.Question.objects.create(
            topic=cls.topic, name="Q4a", question_text="True or false?",
            question_type=models.QuestionType.BINARY, group="Q4", order_in_group=1,
            created_by=cls.user,
        )
        cls.q_text = models.Question.objects.create(
            topic=cls.topic, name="Q4b", question_text="Explain why.",
            question_type=models.QuestionType.TEXT, group="Q4", order_in_group=2,
            mark_scheme="1 mark per point", default_prompt_version=cls.prompt_v1,
            created_by=cls.user,
        )
        cls.paper = models.QuestionPaper.objects.create(
            subject=cls.subject, grade=cls.grade, name="Mid-Term",
            purpose=models.PaperPurpose.EXAM, created_by=cls.user,
        )
        cls.student = models.Student.objects.create(
            admission_no="A-001", first_name="Ali", last_name="Khan", created_by=cls.user
        )

    def draft_version(self, version_no=1):
        version = models.PaperVersion.objects.create(
            question_paper=self.paper, version_no=version_no, created_by=self.user
        )
        models.PaperItem.objects.create(
            paper_version=version, question=self.q_binary, slot=1, max_mark=1,
            created_by=self.user,
        )
        models.PaperItem.objects.create(
            paper_version=version, question=self.q_text, slot=2, max_mark=3,
            created_by=self.user,
        )
        return version


class PaperVersioningTests(Fixture):
    def test_lock_pins_prompt_version_and_totals_marks(self):
        version = self.draft_version()
        self.assertIsNone(version.items.get(slot=2).prompt_version)

        version.lock(user=self.user)

        self.assertTrue(version.is_locked)
        self.assertEqual(version.total_marks, 4)
        self.assertEqual(version.items.get(slot=2).prompt_version, self.prompt_v1)

    def test_reworded_prompt_does_not_change_a_locked_paper(self):
        version = self.draft_version()
        version.lock(user=self.user)

        models.PromptVersion.objects.create(
            evaluation_prompt=self.prompt, version_no=2,
            prompt_text="Be stricter about {{mark_scheme}}.",
            status=models.PromptStatus.ACTIVE, created_by=self.user,
        )

        self.assertEqual(version.items.get(slot=2).prompt_version.version_no, 1)

    def test_clone_carries_items_and_links_back(self):
        version = self.draft_version()
        version.lock(user=self.user)

        clone = version.clone(user=self.user)

        self.assertEqual(clone.version_no, 2)
        self.assertEqual(clone.status, models.PaperStatus.DRAFT)
        self.assertEqual(clone.cloned_from_version, version)
        self.assertEqual(clone.items.count(), 2)

    def test_locking_twice_is_refused(self):
        version = self.draft_version()
        version.lock(user=self.user)
        with self.assertRaises(ValueError):
            version.lock(user=self.user)


class EnrolmentTests(Fixture):
    def test_one_live_enrolment_per_student_per_year(self):
        models.Enrolment.objects.create(
            student=self.student, grade=self.grade, academic_year=2026, created_by=self.user
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.Enrolment.objects.create(
                student=self.student, grade=self.grade, academic_year=2026,
                created_by=self.user,
            )

    def test_voided_enrolment_does_not_block_a_corrected_one(self):
        first = models.Enrolment.objects.create(
            student=self.student, grade=self.grade, academic_year=2026, created_by=self.user
        )
        first.void(user=self.user, reason="wrong grade")

        models.Enrolment.objects.create(
            student=self.student, grade=self.grade, academic_year=2026, created_by=self.user
        )

        self.assertEqual(models.Enrolment.objects.filter(student=self.student).count(), 1)
        self.assertEqual(models.Enrolment.all_objects.filter(student=self.student).count(), 2)


class CountedAttemptTests(Fixture):
    """`counted_flag` replaces a partial index, so it needs its own cover."""

    def setUp(self):
        version = self.draft_version()
        version.lock(user=self.user)
        self.assignment = models.PaperAssignment.objects.create(
            paper_version=version, grade=self.grade, academic_year=2026,
            attempts=0, created_by=self.user,
        )

    def _attempt(self, attempt_no, is_counted=True, preview=False):
        return models.Attempt.objects.create(
            paper_assignment=self.assignment, student=self.student,
            attempt_no=attempt_no, is_counted=is_counted, preview=preview,
            created_by=self.user,
        )

    def test_only_one_attempt_can_count(self):
        self._attempt(1)
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._attempt(2)

    def test_uncounted_and_preview_attempts_are_unlimited(self):
        self._attempt(1)
        self._attempt(2, is_counted=False)
        self._attempt(3, is_counted=False)
        self._attempt(4, preview=True)

        self.assertEqual(models.Attempt.objects.filter(student=self.student).count(), 4)
        self.assertEqual(
            models.Attempt.objects.filter(student=self.student, counted_flag=True).count(), 1
        )

    def test_voiding_the_counted_attempt_frees_the_slot(self):
        first = self._attempt(1)
        first.void(user=self.user, reason="mis-sat")

        second = self._attempt(2)

        self.assertIsNone(models.Attempt.all_objects.get(pk=first.pk).counted_flag)
        self.assertTrue(second.counted_flag)


class VoidingTests(Fixture):
    def test_void_records_who_and_why(self):
        self.student.void(user=self.user, reason="left school")

        row = models.Student.all_objects.get(pk=self.student.pk)
        self.assertTrue(row.voided)
        self.assertEqual(row.void_reason, "left school")
        self.assertEqual(row.voided_by, self.user)
        self.assertIsNotNone(row.date_voided)

    def test_voiding_clears_the_active_flag(self):
        self.assertTrue(self.student.active_flag)

        self.student.void(user=self.user, reason="left school")

        self.assertIsNone(models.Student.all_objects.get(pk=self.student.pk).active_flag)

    def test_unvoiding_restores_the_active_flag(self):
        self.student.void(user=self.user, reason="mistake")
        self.student.unvoid(user=self.user)

        row = models.Student.all_objects.get(pk=self.student.pk)
        self.assertTrue(row.active_flag)
        self.assertFalse(row.voided)

    def test_default_manager_hides_voided_rows(self):
        self.student.void(user=self.user, reason="left school")

        self.assertFalse(models.Student.objects.filter(pk=self.student.pk).exists())
        self.assertTrue(models.Student.all_objects.filter(pk=self.student.pk).exists())


class ApiTests(Fixture):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_delete_voids_rather_than_deletes(self):
        response = self.client.delete(
            f"/api/students/{self.student.pk}/",
            {"void_reason": "left school"},
            format="json",
        )

        self.assertEqual(response.status_code, 204)
        self.assertTrue(models.Student.all_objects.get(pk=self.student.pk).voided)

    def test_list_hides_voided_rows_unless_asked(self):
        self.student.void(user=self.user, reason="left school")

        self.assertEqual(self.client.get("/api/students/").data["count"], 0)
        self.assertEqual(
            self.client.get("/api/students/?include_voided=true").data["count"], 1
        )


    def test_locked_version_rejects_updates(self):
        version = self.draft_version()
        version.lock(user=self.user)

        response = self.client.patch(
            f"/api/paper-versions/{version.pk}/", {"duration_minutes": 90}, format="json"
        )

        self.assertEqual(response.status_code, 400)

    def test_lock_and_clone_actions(self):
        version = self.draft_version()

        locked = self.client.post(f"/api/paper-versions/{version.pk}/lock/", {}, format="json")
        cloned = self.client.post(f"/api/paper-versions/{version.pk}/clone/", {}, format="json")

        self.assertEqual(locked.status_code, 200)
        self.assertEqual(locked.data["status"], "locked")
        self.assertEqual(cloned.status_code, 201)
        self.assertEqual(cloned.data["version_no"], 2)

    def test_active_prompt_cannot_be_reworded(self):
        response = self.client.patch(
            f"/api/prompt-versions/{self.prompt_v1.pk}/",
            {"prompt_text": "Something else."},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_root_sends_visitors_to_the_login_page(self):
        anonymous = APIClient()

        response = anonymous.get("/", follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], "/admin/login/?next=/admin/")

    def test_root_sends_signed_in_staff_to_the_admin(self):
        # force_authenticate is DRF-level and leaves no session, so the
        # admin needs a real login here.
        self.client.force_login(self.user)

        response = self.client.get("/", follow=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.redirect_chain[-1][0], "/admin/")

    def test_schema_and_docs_are_served(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)


class SeedCurriculumTests(TestCase):
    """The curriculum seed must be safe to re-run against a live database."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.AppUser.objects.create_superuser(
            "seeder", "seeder@example.com", "pw12345!"
        )

    def seed(self, year=2026):
        out = StringIO()
        call_command("seed_curriculum", year=year, stdout=out)
        return out.getvalue()

    def test_seed_builds_the_expected_shape(self):
        self.seed()

        self.assertEqual(
            [g.short_name for g in models.Grade.objects.all()],
            ["E1", "E2", "S1", "S2", "S3"],
        )
        self.assertTrue(models.Grade.objects.get(short_name="S3").is_terminal)
        self.assertEqual(models.Subject.objects.count(), 18)
        # 156 syllabus sections plus 462 published sub-topics.
        self.assertEqual(models.Topic.objects.count(), 618)
        self.assertEqual(models.Topic.objects.filter(parent__isnull=False).count(), 462)
        self.assertEqual(models.Topic.objects.filter(parent__isnull=True).count(), 156)
        self.assertEqual(models.Syllabus.objects.filter(academic_year=2026).count(), 48)

    def test_seed_is_idempotent(self):
        self.seed()
        before = (
            models.Grade.objects.count(), models.Subject.objects.count(),
            models.Topic.objects.count(), models.Syllabus.objects.count(),
            models.SyllabusTopic.objects.count(),
        )

        output = self.seed()

        after = (
            models.Grade.objects.count(), models.Subject.objects.count(),
            models.Topic.objects.count(), models.Syllabus.objects.count(),
            models.SyllabusTopic.objects.count(),
        )
        self.assertEqual(before, after)
        self.assertIn("created    0", output)

    def test_a_subject_carries_both_stages_without_collision(self):
        self.seed()

        maths = models.Subject.objects.get(short_name="MATH")

        self.assertEqual(
            models.Topic.objects.filter(
                subject=maths, short_name__startswith="LS-", parent__isnull=True
            ).count(),
            4,
        )
        self.assertEqual(
            models.Topic.objects.filter(
                subject=maths, short_name__startswith="OL-", parent__isnull=True
            ).count(),
            9,
        )

    def test_terminal_grade_is_the_only_one_with_electives(self):
        self.seed()

        electives = models.Syllabus.objects.filter(academic_year=2026, is_core=False)

        self.assertEqual({s.grade.short_name for s in electives}, {"S3"})
        self.assertEqual(electives.count(), 11)

    def test_a_second_year_reuses_the_catalogue(self):
        self.seed(2026)
        subjects_before = models.Subject.objects.count()
        topics_before = models.Topic.objects.count()

        self.seed(2027)

        self.assertEqual(models.Subject.objects.count(), subjects_before)
        self.assertEqual(models.Topic.objects.count(), topics_before)
        self.assertEqual(models.Syllabus.objects.filter(academic_year=2027).count(), 48)


class AuditBlockTests(Fixture):
    """The audit block stamps itself and refuses to be rewritten."""

    def test_uuid_is_assigned_on_insert(self):
        self.assertIsNotNone(self.student.uuid)
        self.assertNotEqual(self.student.uuid, self.grade.uuid)

    def test_uuid_cannot_be_changed(self):
        original = self.student.uuid

        self.student.uuid = uuid.uuid4()
        self.student.save()

        self.student.refresh_from_db()
        self.assertEqual(self.student.uuid, original)

    def test_created_by_and_date_created_cannot_be_changed(self):
        original_by = self.student.created_by_id
        original_at = self.student.date_created
        other = models.AppUser.objects.create_user("intruder", "i@example.com", "pw12345!")

        self.student.created_by = other
        self.student.date_created = timezone.now() - timedelta(days=365)
        self.student.save()

        self.student.refresh_from_db()
        self.assertEqual(self.student.created_by_id, original_by)
        self.assertEqual(self.student.date_created, original_at)

    def test_date_changed_is_stamped_on_update_only(self):
        student = models.Student.objects.create(
            admission_no="A-002", first_name="Sara", last_name="Ahmed", created_by=self.user
        )
        self.assertIsNone(student.date_changed)

        student.first_name = "Sarah"
        student.save()

        self.assertIsNotNone(student.date_changed)

    def test_the_acting_user_is_stamped_without_being_passed(self):
        token = audit.set_current_user(self.user)
        try:
            grade = models.Grade.objects.create(
                level=9, short_name="S1", full_name="Senior 1"
            )
            self.assertEqual(grade.created_by, self.user)

            other = models.AppUser.objects.create_user("marker", "m@example.com", "pw12345!")
            audit.set_current_user(other)
            grade.room = "204"
            grade.save()

            self.assertEqual(grade.changed_by, other)
            self.assertEqual(grade.created_by, self.user)
        finally:
            audit.reset_current_user(token)

    def test_voiding_is_the_one_audit_field_a_person_sets(self):
        self.student.void(user=self.user, reason="left school")

        row = models.Student.all_objects.get(pk=self.student.pk)
        self.assertTrue(row.voided)
        self.assertEqual(row.void_reason, "left school")
        self.assertEqual(row.voided_by, self.user)


class AuditApiTests(Fixture):
    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_api_cannot_write_the_self_controlled_fields(self):
        original_uuid = str(self.student.uuid)
        original_created = self.student.date_created

        response = self.client.patch(
            f"/api/students/{self.student.pk}/",
            {
                "uuid": str(uuid.uuid4()),
                "date_created": "2001-01-01T00:00:00Z",
                "first_name": "Ali Raza",
            },
            format="json",
        )

        self.student.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.student.first_name, "Ali Raza")
        self.assertEqual(str(self.student.uuid), original_uuid)
        self.assertEqual(self.student.date_created, original_created)

    def test_api_can_void_with_a_reason(self):
        response = self.client.patch(
            f"/api/students/{self.student.pk}/",
            {"voided": True, "void_reason": "duplicate record"},
            format="json",
        )

        row = models.Student.all_objects.get(pk=self.student.pk)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(row.voided)
        self.assertEqual(row.void_reason, "duplicate record")


class AuditAdminTests(Fixture):
    """The admin shows the audit block last, and read-only apart from voiding."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def _fieldsets(self, model_admin, obj=None):
        request = RequestFactory().get("/")
        request.user = self.user
        return model_admin.get_fieldsets(request, obj)

    def test_audit_fieldset_is_last(self):
        for model in (models.Student, models.Question, models.Syllabus):
            with self.subTest(model=model.__name__):
                fieldsets = self._fieldsets(site._registry[model])

                self.assertEqual(fieldsets[-1][0], "Audit")
                self.assertNotIn(
                    "voided", [f for _, o in fieldsets[:-1] for f in o["fields"]]
                )

    def test_only_voiding_is_editable(self):
        model_admin = site._registry[models.Student]
        request = RequestFactory().get("/")
        request.user = self.user

        readonly = model_admin.get_readonly_fields(request, self.student)

        self.assertIn("uuid", readonly)
        self.assertIn("created_by", readonly)
        self.assertIn("date_created", readonly)
        self.assertNotIn("voided", readonly)
        self.assertNotIn("void_reason", readonly)

    def test_change_form_renders_with_the_audit_section(self):
        response = self.client.get(f"/admin/app/student/{self.student.pk}/change/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Audit", response.content.decode(errors="ignore"))


@override_settings(MEDIA_ROOT=tempfile.mkdtemp(prefix="lms-test-media-"))
class AttachmentTests(Fixture):
    """Files land in a flat folder per kind and are never stored twice."""

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def _upload(self, name, content, mime):
        return self.client.post(
            "/api/attachments/",
            {"file": SimpleUploadedFile(name, content, content_type=mime)},
            format="multipart",
        )

    def test_kind_is_decided_from_mime_then_extension(self):
        self.assertEqual(files.classify("image/png", "x.png"), files.FileKind.PICTURE)
        self.assertEqual(files.classify("video/mp4", "x.mp4"), files.FileKind.VIDEO)
        self.assertEqual(files.classify("audio/mpeg", "x.mp3"), files.FileKind.AUDIO)
        self.assertEqual(files.classify("application/pdf", "x.pdf"), files.FileKind.TEXT)
        self.assertEqual(files.classify("", "notes.docx"), files.FileKind.TEXT)
        self.assertEqual(files.classify("", "clip.mov"), files.FileKind.VIDEO)
        self.assertEqual(files.classify("application/zip", "bundle.zip"), files.FileKind.OTHER)

    def test_upload_files_by_kind(self):
        response = self._upload("diagram.png", b"\x89PNG fake", "image/png")

        self.assertEqual(response.status_code, 201)
        attachment = models.Attachment.objects.get(pk=response.data["id"])
        self.assertEqual(attachment.kind, "picture")
        self.assertTrue(attachment.file.name.startswith("picture/"))
        self.assertIn(str(attachment.uuid), attachment.file.name)
        self.assertEqual(attachment.original_filename, "diagram.png")

    def test_the_same_file_twice_reuses_one_row(self):
        first = self._upload("paper.pdf", b"%PDF-1.7 same bytes", "application/pdf")
        second = self._upload("paper-copy.pdf", b"%PDF-1.7 same bytes", "application/pdf")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)     # existing row handed back
        self.assertEqual(first.data["id"], second.data["id"])
        self.assertEqual(models.Attachment.objects.count(), 1)

    def test_a_large_file_uploads_in_chunks(self):
        payload = bytes(range(256)) * 400            # 102 400 bytes
        start = self.client.post(
            "/api/uploads/",
            {"filename": "lecture.mp4", "mime_type": "video/mp4", "size_bytes": len(payload)},
            format="json",
        )
        upload_id = start.data["uuid"]

        offset, chunk = 0, 30_000
        while offset < len(payload):
            piece = payload[offset:offset + chunk]
            response = self.client.put(
                f"/api/uploads/{upload_id}/chunk/",
                piece,
                content_type="application/octet-stream",
                HTTP_X_CHUNK_OFFSET=str(offset),
                HTTP_CONTENT_DISPOSITION='attachment; filename="chunk"',
            )
            self.assertEqual(response.status_code, 200, response.data)
            offset = response.data["received"]

        done = self.client.post(f"/api/uploads/{upload_id}/complete/", {}, format="json")

        self.assertEqual(done.status_code, 201)
        self.assertEqual(done.data["kind"], "video")
        self.assertEqual(done.data["size_bytes"], len(payload))
        attachment = models.Attachment.objects.get(pk=done.data["id"])
        self.assertTrue(attachment.file.name.startswith("video/"))
        self.assertEqual(attachment.file.read(), payload)

    def test_a_chunk_at_the_wrong_offset_is_refused(self):
        start = self.client.post(
            "/api/uploads/", {"filename": "a.bin", "size_bytes": 10}, format="json"
        )
        upload_id = start.data["uuid"]

        response = self.client.put(
            f"/api/uploads/{upload_id}/chunk/",
            b"0123456789",
            content_type="application/octet-stream",
            HTTP_X_CHUNK_OFFSET="500",
            HTTP_CONTENT_DISPOSITION='attachment; filename="chunk"',
        )

        self.assertEqual(response.status_code, 400)

    def test_a_file_can_be_attached_to_a_question(self):
        uploaded = self._upload("figure.png", b"png bytes", "image/png")
        models.AttachmentLink.objects.create(
            attachment_id=uploaded.data["id"],
            content_type=ContentType.objects.get_for_model(models.Question),
            object_id=self.q_binary.id,
            role="figure",
        )

        self.assertEqual(self.q_binary.attachments.count(), 1)
        self.assertEqual(self.q_binary.attachments.first().role, "figure")


class AttendanceTests(Fixture):
    def setUp(self):
        self.enrolment = models.Enrolment.objects.create(
            student=self.student, grade=self.grade, academic_year=2026, created_by=self.user
        )
        self.session = models.AttendanceSession.objects.create(
            grade=self.grade, academic_year=2026, date=date(2026, 9, 2), created_by=self.user
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_one_register_per_grade_date_period(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            models.AttendanceSession.objects.create(
                grade=self.grade, academic_year=2026, date=date(2026, 9, 2), created_by=self.user
            )

    def test_a_lesson_register_sits_beside_the_day_register(self):
        models.AttendanceSession.objects.create(
            grade=self.grade, academic_year=2026, date=date(2026, 9, 2),
            syllabus=self.syllabus, period="3", created_by=self.user,
        )

        self.assertEqual(models.AttendanceSession.objects.count(), 2)

    def test_marking_the_register_defaults_everyone_present(self):
        response = self.client.post(
            f"/api/attendance-sessions/{self.session.pk}/mark/",
            {"default_status": "present", "records": []},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["status"], "present")

    def test_marking_records_only_the_exceptions(self):
        response = self.client.post(
            f"/api/attendance-sessions/{self.session.pk}/mark/",
            {
                "default_status": "present",
                "records": [
                    {"enrolment": self.enrolment.id, "status": "late", "minutes_late": 12}
                ],
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        record = models.AttendanceRecord.objects.get(session=self.session, enrolment=self.enrolment)
        self.assertEqual(record.status, "late")
        self.assertEqual(record.minutes_late, 12)

    def test_marking_twice_updates_rather_than_duplicates(self):
        for status_value in ("absent", "excused"):
            self.client.post(
                f"/api/attendance-sessions/{self.session.pk}/mark/",
                {"records": [{"enrolment": self.enrolment.id, "status": status_value}]},
                format="json",
            )

        self.assertEqual(models.AttendanceRecord.objects.count(), 1)
        self.assertEqual(models.AttendanceRecord.objects.first().status, "excused")

    def test_summary_counts_by_status(self):
        models.AttendanceRecord.objects.create(
            session=self.session, enrolment=self.enrolment, status="absent", created_by=self.user
        )

        self.assertEqual(self.session.summary, {"absent": 1})


class RoleTests(Fixture):
    """Roles gate the tables; scoping gates the rows."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command("seed_roles", stdout=StringIO())

        cls.enrolment = models.Enrolment.objects.create(
            student=cls.student, grade=cls.grade, academic_year=2026, created_by=cls.user
        )
        cls.other_student = models.Student.objects.create(
            admission_no="A-999", first_name="Bilal", last_name="Iqbal", created_by=cls.user
        )

        cls.teacher_user = cls._member("teacher1", access.TEACHING_STAFF)
        cls.office_user = cls._member("office1", access.NON_ACADEMIC_STAFF)
        cls.guest_user = cls._member("guest1", access.GUEST)
        cls.student_user = cls._member("pupil1", access.STUDENT)
        cls.student.user = cls.student_user
        cls.student.save()
        cls.guardian_user = cls._member("parent1", access.GUARDIAN)
        models.GuardianLink.objects.create(
            user=cls.guardian_user, student=cls.student, relationship="father", created_by=cls.user
        )

    @classmethod
    def _member(cls, username, role):
        user = models.AppUser.objects.create_user(username, f"{username}@example.com", "pw12345!")
        user.groups.add(Group.objects.get(name=role))
        return user

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_every_role_exists(self):
        self.assertEqual(
            set(Group.objects.values_list("name", flat=True)), set(access.ROLES)
        )

    def test_guest_sees_the_catalogue_and_nothing_else(self):
        client = self.api(self.guest_user)

        self.assertEqual(client.get("/api/grades/").status_code, 200)
        self.assertEqual(client.get("/api/subjects/").status_code, 200)
        self.assertEqual(client.get("/api/topics/").status_code, 200)
        self.assertEqual(client.get("/api/students/").status_code, 403)
        self.assertEqual(client.get("/api/attempts/").status_code, 403)
        self.assertEqual(client.get("/api/attendance-records/").status_code, 403)

    def test_guest_cannot_write(self):
        response = self.api(self.guest_user).post(
            "/api/subjects/", {"short_name": "X", "full_name": "X"}, format="json"
        )

        self.assertEqual(response.status_code, 403)

    def test_teaching_staff_reach_teaching_tables(self):
        client = self.api(self.teacher_user)

        self.assertEqual(client.get("/api/students/").status_code, 200)
        self.assertEqual(client.get("/api/answers/").status_code, 200)
        self.assertEqual(client.get("/api/attendance-sessions/").status_code, 200)

    def test_the_question_bank_belongs_to_the_paper_setter(self):
        """
        A teacher's reach stops at the question bank.

        Paper setting is its own role, and a teacher who also sets papers
        is given that role as well rather than having it folded into this
        one — the reasoning is on TEACHING_STAFF in seed_roles.py. The
        assertion is here so the separation cannot quietly come undone.
        """
        self.assertEqual(
            self.api(self.teacher_user).get("/api/questions/").status_code, 403
        )
        setter = self._member("setter1", access.PAPER_SETTER)
        self.assertEqual(self.api(setter).get("/api/questions/").status_code, 200)

    def test_non_academic_staff_get_attendance_but_not_questions(self):
        client = self.api(self.office_user)

        self.assertEqual(client.get("/api/attendance-sessions/").status_code, 200)
        self.assertEqual(client.get("/api/attendance-records/").status_code, 200)
        self.assertEqual(client.get("/api/students/").status_code, 200)
        self.assertEqual(client.get("/api/questions/").status_code, 403)
        self.assertEqual(client.get("/api/evaluations/").status_code, 403)

    def test_a_student_sees_only_their_own_record(self):
        client = self.api(self.student_user)

        response = client.get("/api/students/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["admission_no"], self.student.admission_no)

    def test_a_guardian_sees_only_their_ward(self):
        client = self.api(self.guardian_user)

        response = client.get("/api/students/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 1)
        self.assertEqual(response.data["results"][0]["id"], self.student.id)

    def test_a_guardian_cannot_write(self):
        client = self.api(self.guardian_user)

        response = client.patch(
            f"/api/students/{self.student.pk}/", {"first_name": "Nope"}, format="json"
        )

        self.assertEqual(response.status_code, 403)

    def test_an_unlinked_guardian_sees_nothing(self):
        stranger = self._member("parent2", access.GUARDIAN)

        response = self.api(stranger).get("/api/students/")

        self.assertEqual(response.data["count"], 0)

    def test_anonymous_requests_are_refused(self):
        self.assertEqual(APIClient().get("/api/students/").status_code, 403)


class EntityHelpTests(Fixture):
    """Every change list explains its entity behind the "?" button."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_every_registered_model_has_help(self):
        missing = [
            model._meta.model_name
            for model in site._registry
            if model._meta.app_label == "app" and entity_help.help_for(model) is None
        ]

        self.assertEqual(missing, [])

    def test_help_entries_are_complete(self):
        for name, entry in entity_help.ENTITY_HELP.items():
            with self.subTest(entity=name):
                self.assertEqual(set(entry), {"summary", "role", "context", "fields"})
                self.assertTrue(all(entry.values()))

    def test_the_change_list_renders_the_help_panel(self):
        response = self.client.get("/admin/app/question/")
        body = response.content.decode(errors="ignore")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="entity-help-toggle"', body)
        self.assertIn("Never duplicate a question", body)

    def test_the_panel_starts_closed(self):
        body = self.client.get("/admin/app/grade/").content.decode(errors="ignore")

        self.assertIn('id="entity-help"', body)
        self.assertIn("hidden", body.split('id="entity-help"')[1][:120])

    def test_the_attachment_list_keeps_its_upload_button(self):
        body = self.client.get("/admin/app/attachment/").content.decode(errors="ignore")

        self.assertIn("Upload files", body)
        self.assertIn('id="entity-help-toggle"', body)


class EntityHelpFieldTests(TestCase):
    """Field names in the help must be real fields — this cannot drift."""

    def test_every_named_field_exists_on_its_model(self):
        from django.apps import apps

        problems = []
        for model_name, entry in entity_help.ENTITY_HELP.items():
            model = apps.get_model("app", model_name)
            known = {f.name for f in model._meta.get_fields()}
            known |= {f.attname for f in model._meta.fields}
            for name, _meaning in entry.get("fields", []):
                if name not in known:
                    problems.append(f"{model_name}.{name}")

        self.assertEqual(problems, [])

    def test_every_entity_documents_its_fields(self):
        thin = [
            name for name, entry in entity_help.ENTITY_HELP.items()
            if len(entry.get("fields", [])) < 2
        ]

        self.assertEqual(thin, [])


class TopicHierarchyTests(Fixture):
    """Topics nest, and the tree cannot be made invalid."""

    def setUp(self):
        self.programming = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8", full_name="Programming",
            created_by=self.user,
        )
        self.loops = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8.1", full_name="Loops",
            parent=self.programming, created_by=self.user,
        )

    def test_a_child_records_its_parent_depth_and_path(self):
        self.assertEqual(self.loops.parent, self.programming)
        self.assertEqual(self.programming.depth, 0)
        self.assertEqual(self.loops.depth, 1)
        self.assertEqual(self.loops.path, f"{self.programming.pk}/{self.loops.pk}")

    def test_full_path_reads_as_a_trail(self):
        self.assertEqual(self.loops.full_path, "Programming › Loops")

    def test_descendants_and_ancestors(self):
        counted = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8.1.1", full_name="Counted loops",
            parent=self.loops, created_by=self.user,
        )

        self.assertEqual(set(self.programming.descendants()), {self.loops, counted})
        self.assertEqual(counted.ancestors(), [self.programming, self.loops])
        self.assertEqual(counted.depth, 2)

    def test_moving_a_topic_rewrites_its_descendants(self):
        counted = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8.1.1", full_name="Counted loops",
            parent=self.loops, created_by=self.user,
        )
        other = models.Topic.objects.create(
            subject=self.subject, short_name="OL-9", full_name="Databases",
            created_by=self.user,
        )

        self.loops.parent = other
        self.loops.save()

        counted.refresh_from_db()
        self.assertEqual(counted.depth, 2)
        self.assertTrue(counted.path.startswith(f"{other.pk}/{self.loops.pk}/"))
        self.assertEqual(counted.ancestors(), [other, self.loops])

    def test_a_topic_cannot_be_its_own_parent(self):
        self.programming.parent = self.programming

        with self.assertRaises(ValueError):
            self.programming.save()

    def test_a_topic_cannot_sit_under_its_own_child(self):
        self.programming.parent = self.loops

        with self.assertRaises(ValueError):
            self.programming.save()

    def test_a_parent_must_be_in_the_same_subject(self):
        other_subject = models.Subject.objects.create(
            short_name="PHY", full_name="Physics", created_by=self.user
        )
        stray = models.Topic.objects.create(
            subject=other_subject, short_name="OL-1", full_name="Motion", created_by=self.user
        )

        self.loops.parent = stray
        with self.assertRaises(ValueError):
            self.loops.save()

    def test_nesting_stops_at_the_depth_limit(self):
        node = self.loops
        for level in range(2, models.Topic.MAX_DEPTH + 1):
            node = models.Topic.objects.create(
                subject=self.subject, short_name=f"OL-8.{level}", full_name=f"Level {level}",
                parent=node, created_by=self.user,
            )

        with self.assertRaises(ValueError):
            models.Topic.objects.create(
                subject=self.subject, short_name="OL-8.deep", full_name="Too deep",
                parent=node, created_by=self.user,
            )

    def test_the_api_walks_the_tree(self):
        client = APIClient()
        client.force_authenticate(self.user)

        children = client.get(f"/api/topics/{self.programming.pk}/children/")
        roots = client.get("/api/topics/?root_only=true")

        self.assertEqual(len(children.data), 1)
        self.assertEqual(children.data[0]["full_name"], "Loops")
        self.assertTrue(all(t["parent"] is None for t in roots.data["results"]))

    def test_the_seeded_maths_syllabus_is_complete(self):
        call_command("seed_curriculum", year=2026, stdout=StringIO())

        maths = models.Subject.objects.get(short_name="MATH")
        sections = models.Topic.objects.filter(
            subject=maths, short_name__startswith="OL-", parent__isnull=True
        ).order_by("sort_order")

        self.assertEqual(
            [s.full_name for s in sections],
            ["Number", "Algebra and graphs", "Coordinate geometry", "Geometry",
             "Mensuration", "Trigonometry", "Transformations and vectors",
             "Probability", "Statistics"],
        )
        self.assertEqual(
            [s.children.count() for s in sections], [18, 12, 7, 8, 5, 4, 4, 3, 7]
        )
        self.assertEqual(
            models.Topic.objects.filter(
                subject=maths, short_name__startswith="OL-", parent__isnull=False
            ).count(),
            68,
        )

    def test_maths_sub_topic_numbering_is_contiguous(self):
        call_command("seed_curriculum", year=2026, stdout=StringIO())

        maths = models.Subject.objects.get(short_name="MATH")
        for section in models.Topic.objects.filter(
            subject=maths, short_name__startswith="OL-", parent__isnull=True
        ):
            number = section.short_name.removeprefix("OL-")
            expected = [
                f"OL-{number}.{i}"
                for i in range(1, section.children.count() + 1)
            ]
            actual = [c.short_name for c in section.children.order_by("sort_order")]

            self.assertEqual(actual, expected, f"section {number}")

    def test_english_carries_both_stages_nested(self):
        call_command("seed_curriculum", year=2026, stdout=StringIO())

        english = models.Subject.objects.get(short_name="ENG")

        def section(short_name):
            return models.Topic.objects.get(subject=english, short_name=short_name)

        # O Level 1123 publishes no topic list; its assessment objectives are
        # the named breakdown.
        self.assertEqual(section("OL-1").children.count(), 5)   # AO1 Reading, R1-R5
        self.assertEqual(section("OL-2").children.count(), 5)   # AO2 Writing, W1-W5
        # Lower Secondary 0861 publishes sub-strands, by reporting code.
        self.assertEqual(section("LS-1").children.count(), 6)
        self.assertEqual(section("LS-2").children.count(), 6)
        self.assertEqual(section("LS-3").children.count(), 5)
        self.assertEqual(
            section("LS-3").children.order_by("sort_order").first().full_name,
            "Making yourself understood",
        )

    def test_the_seeded_geography_topics_are_nested(self):
        call_command("seed_curriculum", year=2026, stdout=StringIO())

        theme_two = models.Topic.objects.get(
            subject__short_name="GEO", short_name="OL-2"
        )
        rivers = models.Topic.objects.get(subject__short_name="GEO", short_name="OL-2.2")

        self.assertEqual(rivers.parent, theme_two)
        self.assertEqual(theme_two.children.count(), 5)
        self.assertEqual(rivers.full_path, "Theme 2: The natural environment › Rivers")


class TopicParentPickerTests(Fixture):
    """The parent picker only ever offers valid parents."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.programming = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8", full_name="Programming",
            created_by=self.user,
        )
        self.loops = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8.1", full_name="Loops",
            parent=self.programming, created_by=self.user,
        )
        self.other_subject = models.Subject.objects.create(
            short_name="PHY", full_name="Physics", created_by=self.user
        )
        self.elsewhere = models.Topic.objects.create(
            subject=self.other_subject, short_name="OL-1", full_name="Motion",
            created_by=self.user,
        )

    def _autocomplete(self, **params):
        query = {
            "app_label": "app",
            "model_name": "topic",
            "field_name": "parent",
            "term": "",
            **params,
        }
        response = self.client.get("/admin/autocomplete/", query)
        self.assertEqual(response.status_code, 200)
        return [r["text"] for r in response.json()["results"]]

    def test_results_are_limited_to_the_chosen_subject(self):
        names = self._autocomplete(subject=self.subject.pk)

        self.assertIn(str(self.programming), names)
        self.assertNotIn(str(self.elsewhere), names)

    def test_a_topic_is_not_offered_as_its_own_parent(self):
        names = self._autocomplete(subject=self.subject.pk, exclude_topic=self.programming.pk)

        self.assertNotIn(str(self.programming), names)

    def test_descendants_are_not_offered_as_parents(self):
        names = self._autocomplete(subject=self.subject.pk, exclude_topic=self.programming.pk)

        self.assertNotIn(str(self.loops), names)

    def test_search_narrows_by_term(self):
        names = self._autocomplete(subject=self.subject.pk, term="Loop")

        self.assertEqual(names, [str(self.loops)])

    def test_the_change_form_loads_the_picker_assets(self):
        body = self.client.get(
            f"/admin/app/topic/{self.loops.pk}/change/"
        ).content.decode(errors="ignore")

        self.assertIn("js/topic-autocomplete.js", body)
        self.assertIn("admin-autocomplete", body)

    def test_the_sort_column_is_headed_sort(self):
        body = self.client.get("/admin/app/topic/").content.decode(errors="ignore")

        self.assertIn(">Sort<", body)
        self.assertNotIn(">Sort order<", body)


class ColumnTruncationTests(Fixture):
    """Long text is cut in tables; everything else is left alone."""

    LONG = ("Relationships of organisms with one another and with the physical environment "
            "and the consequences for conservation")

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_shorten_keeps_short_values_whole(self):
        self.assertEqual(columns.shorten("Rivers"), "Rivers")

    def test_shorten_cuts_at_45_plus_an_ellipsis(self):
        result = columns.shorten(self.LONG)

        self.assertEqual(len(result), columns.MAX_LENGTH)
        self.assertTrue(result.endswith("..."))
        self.assertTrue(self.LONG.startswith(result[:-3].rstrip()))

    def test_a_value_of_exactly_the_limit_is_untouched(self):
        exact = "x" * columns.MAX_LENGTH

        self.assertEqual(columns.shorten(exact), exact)

    def test_non_text_passes_through(self):
        self.assertEqual(columns.shorten(42), 42)
        self.assertIs(columns.shorten(True), True)
        self.assertIsNone(columns.shorten(None))

    def test_the_change_list_truncates_long_names(self):
        models.Topic.objects.create(
            subject=self.subject, short_name="OL-19", full_name=self.LONG,
            created_by=self.user,
        )

        body = self.client.get("/admin/app/topic/").content.decode(errors="ignore")
        cells = re.findall(r'<th class="field-indented_name">(.*?)</th>', body, re.S)
        visible = " ".join(re.sub(r"<[^>]+>", "", cell) for cell in cells)

        self.assertNotIn(self.LONG, visible)          # the cell shows the short form
        self.assertIn(self.LONG[:columns.KEEP].rstrip() + "...", visible)
        self.assertIn(f'title="{self.LONG}"', body)   # the full value is on hover

    def test_the_full_value_is_on_hover(self):
        models.Topic.objects.create(
            subject=self.subject, short_name="OL-20", full_name=self.LONG,
            created_by=self.user,
        )

        body = self.client.get("/admin/app/topic/").content.decode(errors="ignore")

        self.assertIn(f'title="{self.LONG}"', body)

    def test_boolean_columns_keep_their_icon(self):
        body = self.client.get("/admin/app/topic/").content.decode(errors="ignore")

        self.assertIn("icon-yes", body)

    def test_html_columns_are_not_mangled(self):
        """The indented topic tree builds its own markup."""
        parent = models.Topic.objects.create(
            subject=self.subject, short_name="OL-21", full_name="Programming",
            created_by=self.user,
        )
        models.Topic.objects.create(
            subject=self.subject, short_name="OL-21.1", full_name="Loops",
            parent=parent, created_by=self.user,
        )

        body = self.client.get("/admin/app/topic/").content.decode(errors="ignore")

        self.assertIn('<strong title="Programming">Programming</strong>', body)
        self.assertIn("└", body)

    def test_dates_still_render_as_dates(self):
        models.Attachment.objects.create(
            original_filename="notes.pdf", mime_type="application/pdf",
            kind="text", size_bytes=10, checksum="abc", created_by=self.user,
        )

        body = self.client.get("/admin/app/attachment/").content.decode(errors="ignore")

        self.assertNotIn("datetime.datetime", body)


class KnowledgeGraphTests(Fixture):
    """The graph page and the tree endpoint behind it."""

    def setUp(self):
        self.programming = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8", full_name="Programming",
            sort_order=1, created_by=self.user,
        )
        self.loops = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8.1", full_name="Loops",
            parent=self.programming, sort_order=1, created_by=self.user,
        )
        self.counted = models.Topic.objects.create(
            subject=self.subject, short_name="OL-8.1.1", full_name="Counted loops",
            parent=self.loops, sort_order=1, created_by=self.user,
        )
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.client = Client()
        self.client.force_login(self.user)

    def tree(self):
        response = self.api.get(f"/api/topics/tree/?subject={self.subject.pk}")
        self.assertEqual(response.status_code, 200)
        return response.data

    def test_the_subject_is_the_root(self):
        payload = self.tree()

        self.assertEqual(payload["type"], "subject")
        self.assertEqual(payload["name"], self.subject.full_name)
        self.assertEqual(payload["depth"], 0)

    def test_topics_nest_to_any_depth(self):
        payload = self.tree()

        programming = next(c for c in payload["children"] if c["name"] == "Programming")
        loops = programming["children"][0]

        self.assertEqual(loops["name"], "Loops")
        self.assertEqual(loops["children"][0]["name"], "Counted loops")
        self.assertEqual(loops["children"][0]["depth"], 3)

    def test_leaves_have_no_children(self):
        payload = self.tree()
        comprehension = next(c for c in payload["children"] if c["name"] == "Comprehension")

        self.assertEqual(comprehension["children"], [])

    def test_question_counts_ride_along(self):
        models.Question.objects.create(
            topic=self.loops, name="Q1", question_text="?",
            question_type=models.QuestionType.BINARY, created_by=self.user,
        )

        payload = self.tree()
        programming = next(c for c in payload["children"] if c["name"] == "Programming")

        self.assertEqual(programming["children"][0]["question_count"], 1)
        self.assertEqual(programming["question_count"], 0)

    def test_voided_topics_are_left_out(self):
        self.loops.void(user=self.user, reason="merged")

        payload = self.tree()
        programming = next(c for c in payload["children"] if c["name"] == "Programming")

        self.assertEqual(programming["children"], [])

    def test_a_missing_subject_is_a_clear_error(self):
        self.assertEqual(self.api.get("/api/topics/tree/").status_code, 400)
        self.assertEqual(self.api.get("/api/topics/tree/?subject=99999").status_code, 404)

    def test_the_page_renders_with_a_subject_picker(self):
        response = self.client.get("/admin/app/subject/graph/")
        body = response.content.decode(errors="ignore")

        self.assertEqual(response.status_code, 200)
        self.assertIn('id="kg-subject"', body)
        self.assertIn("d3.min.js", body)
        self.assertIn("/api/topics/tree/", body)

    def test_the_subject_list_links_to_the_graph(self):
        body = self.client.get("/admin/app/subject/").content.decode(errors="ignore")

        self.assertIn("/admin/app/subject/graph/", body)
        self.assertIn('aria-label="Knowledge graph"', body)
        # icon only: no words, and not JET's plus
        anchor = body.split('/admin/app/subject/graph/"')[1].split("</a>")[0]
        self.assertIn("icon-grid", anchor)     # JET's icon font, not inline SVG
        self.assertNotIn("<svg", anchor)
        self.assertNotIn("addlink", anchor)    # not JET's plus
        self.assertNotIn("Knowledge graph<", anchor)

    def test_the_topic_list_does_not_carry_the_graph_button(self):
        body = self.client.get("/admin/app/topic/").content.decode(errors="ignore")

        self.assertNotIn("subject/graph/", body)

    def test_the_picker_is_bound_through_jquery_as_well(self):
        """JET's select2 fires change through jQuery, not natively."""
        body = self.client.get("/admin/app/subject/graph/").content.decode(errors="ignore")

        self.assertIn("addEventListener('change', onSubjectChange)", body)
        self.assertIn("jq(subjectPicker).on('change', onSubjectChange)", body)

    def test_the_page_needs_a_login(self):
        response = Client().get("/admin/app/subject/graph/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

class IncludeVoidedFilterTests(Fixture):
    """The admin's voided control is a checkbox: off = live only, on = both."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.gone = models.Student.objects.create(
            admission_no="A-777", first_name="Zara", last_name="Malik", created_by=self.user
        )
        self.gone.void(user=self.user, reason="left school")

    def rows(self, query=""):
        response = self.client.get(f"/admin/app/student/{query}")
        body = response.content.decode(errors="ignore")
        table = body.split('id="result_list"')[1].split("</table>")[0]
        return table

    def test_unticked_shows_live_rows_only(self):
        table = self.rows()

        self.assertIn("Khan", table)          # the live student
        self.assertNotIn("Malik", table)      # the voided one

    def test_ticked_shows_voided_alongside_live(self):
        table = self.rows("?include_voided=1")

        self.assertIn("Khan", table)
        self.assertIn("Malik", table)

    def test_the_control_renders_as_a_checkbox(self):
        body = self.client.get("/admin/app/student/").content.decode(errors="ignore")

        self.assertIn('id="include-voided-toggle"', body)
        self.assertIn("Include voided", body)
        self.assertNotIn("Voided only", body)     # the old three-way dropdown
        self.assertNotIn("Live only", body)

    def test_the_checkbox_reflects_the_current_state(self):
        off = self.client.get("/admin/app/student/").content.decode(errors="ignore")
        on = self.client.get(
            "/admin/app/student/?include_voided=1"
        ).content.decode(errors="ignore")

        off_input = off.split('id="include-voided-toggle"')[1].split(">")[0]
        on_input = on.split('id="include-voided-toggle"')[1].split(">")[0]

        self.assertNotIn("checked", off_input)
        self.assertIn("checked", on_input)

    def test_it_keeps_other_query_parameters(self):
        body = self.client.get(
            "/admin/app/student/?q=Khan"
        ).content.decode(errors="ignore")
        on_url = body.split('data-on-url="')[1].split('"')[0]

        self.assertIn("q=Khan", on_url)
        self.assertIn("include_voided=1", on_url)


class IncludeVoidedEverywhereTests(Fixture):
    """The voided checkbox belongs to every audited entity, not just some."""

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def audited_admins(self):
        from app.admin import IncludeVoidedFilter

        return [
            (model, model_admin, IncludeVoidedFilter)
            for model, model_admin in site._registry.items()
            if model._meta.app_label == "app" and hasattr(model, "voided")
        ]

    def test_every_audited_admin_declares_the_filter(self):
        missing = [
            model._meta.model_name
            for model, model_admin, filter_class in self.audited_admins()
            if not any(f is filter_class for f in (model_admin.list_filter or ()))
        ]

        self.assertEqual(missing, [])

    def test_every_audited_change_list_renders_the_checkbox(self):
        missing = []
        for model, _model_admin, _f in self.audited_admins():
            url = f"/admin/app/{model._meta.model_name}/"
            body = self.client.get(url).content.decode(errors="ignore")
            if 'id="include-voided-toggle"' not in body:
                missing.append(model._meta.model_name)

        self.assertEqual(missing, [])

    def test_the_unaudited_purge_log_does_not_offer_it(self):
        """PurgeRun carries no audit block, so there is nothing to include."""
        body = self.client.get("/admin/app/purgerun/").content.decode(errors="ignore")

        self.assertNotIn('id="include-voided-toggle"', body)


class DemoDataTests(TestCase):
    """The demo school: three teachers, twenty students, the school's rules."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.AppUser.objects.create_superuser(
            "demoadmin", "demo@example.com", "pw12345!"
        )
        call_command("seed_roles", stdout=StringIO())
        call_command("seed_curriculum", year=2026, stdout=StringIO())

    def load(self):
        out = StringIO()
        call_command("seed_demo", year=2026, stdout=out)
        return out.getvalue()

    def demo_students(self):
        return models.Student.objects.filter(admission_no__startswith=demo_data.PREFIX)

    def test_it_loads_three_teachers_and_twenty_students(self):
        self.load()

        self.assertEqual(
            models.Teacher.objects.filter(
                staff_no__startswith=demo_data.PREFIX
            ).count(),
            3,
        )
        self.assertEqual(self.demo_students().count(), 20)
        self.assertEqual(
            models.Enrolment.objects.filter(student__in=self.demo_students()).count(), 20
        )

    def test_every_student_is_in_exactly_one_grade(self):
        self.load()

        for student in self.demo_students():
            with self.subTest(student=student.admission_no):
                self.assertEqual(student.enrolments.count(), 1)

    def test_a_teacher_covers_several_subjects(self):
        self.load()

        for teacher in models.Teacher.objects.filter(
            staff_no__startswith=demo_data.PREFIX
        ):
            subjects = {a.syllabus.subject.short_name for a in teacher.assignments.all()}
            with self.subTest(teacher=teacher.staff_no):
                self.assertGreater(len(subjects), 1)

    def test_below_the_terminal_grade_everyone_takes_the_same_subjects(self):
        self.load()

        for code in ("E1", "E2", "S1", "S2"):
            enrolments = models.Enrolment.objects.filter(
                grade__short_name=code, student__in=self.demo_students()
            )
            taken = {
                frozenset(s.syllabus_id for s in e.subjects.all()) for e in enrolments
            }
            with self.subTest(grade=code):
                self.assertEqual(len(taken), 1, "subjects should be identical")

    def test_only_the_terminal_grade_has_electives(self):
        self.load()

        electives = models.StudentSubject.objects.filter(
            enrolment__student__in=self.demo_students(), syllabus__is_core=False
        )

        self.assertTrue(electives.exists())
        self.assertEqual(
            {e.enrolment.grade.short_name for e in electives}, {"S3"}
        )

    def test_terminal_students_choose_differently(self):
        self.load()

        chosen = {
            frozenset(
                s.syllabus.subject.short_name
                for s in e.subjects.all()
                if not s.syllabus.is_core
            )
            for e in models.Enrolment.objects.filter(
                grade__short_name="S3", student__in=self.demo_students()
            )
        }

        self.assertEqual(len(chosen), 4, "each S3 student picked a different set")

    def test_loading_twice_changes_nothing(self):
        self.load()
        before = (
            models.Student.objects.count(),
            models.Enrolment.objects.count(),
            models.StudentSubject.objects.count(),
            models.TeachingAssignment.objects.count(),
        )

        self.load()

        after = (
            models.Student.objects.count(),
            models.Enrolment.objects.count(),
            models.StudentSubject.objects.count(),
            models.TeachingAssignment.objects.count(),
        )
        self.assertEqual(before, after)

    def test_removing_voids_the_demo_and_leaves_the_curriculum(self):
        self.load()
        subjects_before = models.Subject.objects.count()
        topics_before = models.Topic.objects.count()

        call_command("seed_demo", year=2026, remove=True, stdout=StringIO())

        self.assertEqual(self.demo_students().count(), 0)           # live view
        self.assertEqual(
            models.Student.all_objects.filter(
                admission_no__startswith=demo_data.PREFIX
            ).count(),
            20,                                                      # still there
        )
        self.assertEqual(models.Subject.objects.count(), subjects_before)
        self.assertEqual(models.Topic.objects.count(), topics_before)

    def test_removing_suspends_the_teacher_logins(self):
        self.load()

        call_command("seed_demo", year=2026, remove=True, stdout=StringIO())

        for row in demo_data.TEACHERS:
            account = models.AppUser.objects.get(username=row["username"])
            with self.subTest(teacher=row["username"]):
                self.assertTrue(account.suspended)
                self.assertFalse(account.is_active)

    def test_it_refuses_without_a_curriculum(self):
        # Nothing is ever deleted here, so void the year's syllabi instead —
        # which is also what an actual empty year looks like.
        for syllabus in models.Syllabus.objects.filter(academic_year=2026):
            syllabus.void(user=self.user, reason="test")

        with self.assertRaises(CommandError):
            call_command("seed_demo", year=2026, stdout=StringIO())


class DemoPageTests(TestCase):
    """The Demo entry in the side menu, and the page behind it."""

    @classmethod
    def setUpTestData(cls):
        cls.user = models.AppUser.objects.create_superuser(
            "pageadmin", "page@example.com", "pw12345!"
        )
        call_command("seed_curriculum", year=2026, stdout=StringIO())

    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def test_the_page_is_reachable_and_named(self):
        self.assertEqual(reverse("demo"), "/admin/demo/")
        self.assertEqual(self.client.get("/admin/demo/").status_code, 200)

    def test_it_needs_a_login(self):
        response = Client().get("/admin/demo/")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_the_button_loads_the_demo(self):
        response = self.client.post(
            "/admin/demo/", {"action": "load", "year": 2026}, follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            models.Student.objects.filter(
                admission_no__startswith=demo_data.PREFIX
            ).count(),
            20,
        )

    def test_the_button_removes_it_again(self):
        self.client.post("/admin/demo/", {"action": "load", "year": 2026})

        self.client.post("/admin/demo/", {"action": "remove", "year": 2026}, follow=True)

        self.assertEqual(
            models.Student.objects.filter(
                admission_no__startswith=demo_data.PREFIX
            ).count(),
            0,
        )

    def test_the_page_reports_what_is_loaded(self):
        self.client.post("/admin/demo/", {"action": "load", "year": 2026})

        body = self.client.get("/admin/demo/").content.decode(errors="ignore")

        self.assertIn("Remove demo data", body)
        self.assertIn("Reload demo data", body)


# ---------------------------------------------------------------------
# Portraits
# ---------------------------------------------------------------------
def _png(width, height, noisy=False):
    """A PNG of the given shape. `noisy` makes it incompressible, so it
    comfortably exceeds the 100 KB ceiling."""
    from PIL import Image

    if noisy:
        image = Image.frombytes("RGB", (width, height), os.urandom(width * height * 3))
    else:
        image = Image.new("RGB", (width, height), (200, 210, 190))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _upload(name, data):
    return SimpleUploadedFile(name, data, content_type="image/png")


class PhotoRuleTests(Fixture):
    """Square first, under 100 KB second — in that order."""

    def test_a_small_square_picture_is_accepted(self):
        files.validate_person_photo(_upload("ok.png", _png(240, 240)))

    def test_a_rectangle_is_rejected_for_its_shape(self):
        with self.assertRaises(ValidationError) as caught:
            files.validate_person_photo(_upload("wide.png", _png(400, 300)))

        self.assertEqual(caught.exception.code, "not_square")
        self.assertIn("400 by 300", str(caught.exception.messages[0]))

    def test_a_square_picture_over_the_ceiling_is_rejected_for_its_size(self):
        big = _png(400, 400, noisy=True)
        self.assertGreater(len(big), files.PHOTO_MAX_BYTES)

        with self.assertRaises(ValidationError) as caught:
            files.validate_person_photo(_upload("big.png", big))

        self.assertEqual(caught.exception.code, "too_large")

    def test_shape_is_reported_before_size(self):
        """A picture that breaks both rules is told to crop, not compress."""
        both = _png(600, 400, noisy=True)
        self.assertGreater(len(both), files.PHOTO_MAX_BYTES)

        with self.assertRaises(ValidationError) as caught:
            files.validate_person_photo(_upload("both.png", both))

        self.assertEqual(caught.exception.code, "not_square")

    def test_a_file_that_is_not_an_image_is_rejected(self):
        with self.assertRaises(ValidationError):
            files.validate_person_photo(_upload("notes.png", b"this is not a picture"))

    def test_the_model_enforces_the_rules_on_clean(self):
        self.student.photo = _upload("wide.png", _png(300, 200))

        with self.assertRaises(ValidationError) as caught:
            self.student.full_clean()

        self.assertIn("photo", caught.exception.error_dict)

    def test_a_portrait_is_stored_with_the_other_pictures(self):
        with tempfile.TemporaryDirectory() as media:
            with override_settings(MEDIA_ROOT=media):
                self.student.photo = _upload("me.png", _png(120, 120))
                self.student.save()

                self.assertEqual(
                    self.student.photo.name,
                    f"{files.FileKind.PICTURE}/{self.student.uuid}.png",
                )

    def test_teachers_carry_one_too(self):
        self.assertIn("photo", [f.name for f in models.Teacher._meta.get_fields()])


# ---------------------------------------------------------------------
# The student page: Subjects and Knowledge map
# ---------------------------------------------------------------------
class StudentSubjectHistoryTests(Fixture):
    """Studying now beats passed earlier; anything untouched is untaken."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.maths = models.Subject.objects.create(
            short_name="MATH", full_name="Mathematics", created_by=cls.user
        )
        cls.art = models.Subject.objects.create(
            short_name="ART", full_name="Art and Design", created_by=cls.user
        )
        cls.maths_2025 = models.Syllabus.objects.create(
            subject=cls.maths, grade=cls.grade, academic_year=2025, created_by=cls.user
        )
        cls.english_2026 = cls.syllabus

    def enrol(self, year, ended=None):
        return models.Enrolment.objects.create(
            student=self.student, grade=self.grade, academic_year=year,
            ended_on=ended, created_by=self.user,
        )

    def take(self, enrolment, syllabus):
        return models.StudentSubject.objects.create(
            enrolment=enrolment, syllabus=syllabus, created_by=self.user
        )

    def test_a_finished_year_counts_as_passed(self):
        self.take(self.enrol(2025), self.maths_2025)

        history = self.student.subject_history(year=2026)

        self.assertEqual(history[self.maths.pk], models.SubjectStatus.PASSED)

    def test_the_open_year_counts_as_studying(self):
        self.take(self.enrol(2026), self.english_2026)

        history = self.student.subject_history(year=2026)

        self.assertEqual(history[self.subject.pk], models.SubjectStatus.STUDYING)

    def test_an_enrolment_closed_early_counts_as_passed(self):
        self.take(self.enrol(2026, ended=date(2026, 3, 1)), self.english_2026)

        history = self.student.subject_history(year=2026)

        self.assertEqual(history[self.subject.pk], models.SubjectStatus.PASSED)

    def test_a_subject_continued_this_year_outranks_last_year(self):
        maths_2026 = models.Syllabus.objects.create(
            subject=self.maths, grade=self.grade, academic_year=2026,
            created_by=self.user,
        )
        self.take(self.enrol(2025), self.maths_2025)
        self.take(self.enrol(2026), maths_2026)

        history = self.student.subject_history(year=2026)

        self.assertEqual(history[self.maths.pk], models.SubjectStatus.STUDYING)

    def test_a_subject_never_taken_is_absent(self):
        self.assertNotIn(self.art.pk, self.student.subject_history(year=2026))


class StudentPageTests(StudentSubjectHistoryTests):
    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)

    def map_url(self):
        return reverse("admin:app_student_knowledge_map", args=[self.student.pk])

    def test_the_change_page_has_a_subjects_and_a_knowledge_map_section(self):
        body = self.client.get(
            reverse("admin:app_student_change", args=[self.student.pk])
        ).content.decode(errors="ignore")

        self.assertIn("Subjects", body)
        self.assertIn("Knowledge map", body)
        self.assertIn('id="skm"', body)

    def test_the_subjects_panel_lists_what_was_taken(self):
        self.take(self.enrol(2026), self.english_2026)

        body = self.client.get(
            reverse("admin:app_student_change", args=[self.student.pk])
        ).content.decode(errors="ignore")

        self.assertIn("English Language", body)
        self.assertIn("currently studying", body)

    def test_the_map_marks_every_subject(self):
        self.take(self.enrol(2025), self.maths_2025)
        self.take(self.enrol(2026), self.english_2026)

        payload = self.client.get(self.map_url(), {"year": 2026}).json()
        status = {s["short_name"]: s["status"] for s in payload["subjects"]}

        self.assertEqual(status["MATH"], "passed")
        self.assertEqual(status["ENG"], "studying")
        self.assertEqual(status["ART"], "not_taken")
        self.assertEqual(payload["counts"]["not_taken"], 1)

    def test_the_map_carries_the_topic_tree(self):
        child = models.Topic.objects.create(
            subject=self.subject, parent=self.topic, short_name="SKIM",
            full_name="Skimming", created_by=self.user,
        )

        payload = self.client.get(self.map_url()).json()
        english = next(s for s in payload["subjects"] if s["short_name"] == "ENG")

        self.assertEqual(english["children"][0]["name"], "Comprehension")
        self.assertEqual(
            [c["id"] for c in english["children"][0]["children"]], [child.pk]
        )

    def test_the_map_needs_a_login(self):
        self.client.logout()

        response = self.client.get(self.map_url())

        self.assertEqual(response.status_code, 302)

    def test_the_list_links_the_admission_number_as_well_as_the_portrait(self):
        body = self.client.get(
            reverse("admin:app_student_changelist")
        ).content.decode(errors="ignore")

        self.assertIn(
            f'href="/admin/app/student/{self.student.pk}/change/">A-001</a>', body
        )
        self.assertIn("ac-avatar", body)


# ---------------------------------------------------------------------
# Topic results, completion and the marking grid
# ---------------------------------------------------------------------
class TopicResultFixture(Fixture):
    """
    English with two sections, three leaves between them.

        Comprehension  ->  Skimming, Inference
        Writing        ->  (a leaf itself)
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.skimming = models.Topic.objects.create(
            subject=cls.subject, parent=cls.topic, short_name="SKIM",
            full_name="Skimming", sort_order=1, created_by=cls.user,
        )
        cls.inference = models.Topic.objects.create(
            subject=cls.subject, parent=cls.topic, short_name="INF",
            full_name="Inference", sort_order=2, created_by=cls.user,
        )
        cls.writing = models.Topic.objects.create(
            subject=cls.subject, short_name="WRIT", full_name="Writing",
            sort_order=2, created_by=cls.user,
        )
        models.SyllabusTopic.objects.create(
            syllabus=cls.syllabus, topic=cls.topic, sort_order=1, created_by=cls.user
        )
        models.SyllabusTopic.objects.create(
            syllabus=cls.syllabus, topic=cls.writing, sort_order=2, created_by=cls.user
        )
        cls.enrolment = models.Enrolment.objects.create(
            student=cls.student, grade=cls.grade, academic_year=2026,
            created_by=cls.user,
        )
        cls.taking = models.StudentSubject.objects.create(
            enrolment=cls.enrolment, syllabus=cls.syllabus, created_by=cls.user
        )

    def mark(self, topic, score):
        return models.TopicResult.objects.create(
            student_subject=self.taking, topic=topic, score_pct=Decimal(str(score)),
            assessed_on=date(2026, 4, 1), created_by=self.user,
        )


class AssessableTopicTests(TopicResultFixture):
    def test_a_syllabus_is_assessed_at_its_leaves(self):
        leaves = self.syllabus.assessable_topics()

        self.assertEqual(
            [t.short_name for t in leaves], ["SKIM", "INF", "WRIT"]
        )

    def test_sections_keep_their_leaves_together(self):
        sections = self.syllabus.assessable_sections()

        self.assertEqual([s.short_name for s, _ in sections], ["COMP", "WRIT"])
        self.assertEqual([t.short_name for t in sections[0][1]], ["SKIM", "INF"])

    def test_a_voided_topic_drops_out(self):
        self.inference.void(user=self.user, reason="merged")

        self.assertEqual(
            [t.short_name for t in self.syllabus.assessable_topics()],
            ["SKIM", "WRIT"],
        )


class CompletionTests(TopicResultFixture):
    def test_completion_counts_passed_topics_over_assessable_ones(self):
        self.mark(self.skimming, 70)
        self.mark(self.inference, 30)

        progress = self.taking.progress()

        self.assertEqual(progress["total"], 3)
        self.assertEqual(progress["assessed"], 2)
        self.assertEqual(progress["passed"], 1)
        self.assertEqual(progress["percent"], 33)

    def test_the_pass_mark_lives_on_the_syllabus(self):
        self.mark(self.skimming, 55)
        self.assertEqual(self.taking.progress()["passed"], 1)

        self.syllabus.pass_mark_pct = Decimal("60")
        self.syllabus.save()

        self.assertEqual(self.taking.progress()["passed"], 0)

    def test_an_unassessed_topic_is_not_a_failure(self):
        result = models.TopicResult.objects.create(
            student_subject=self.taking, topic=self.skimming, created_by=self.user
        )

        self.assertIsNone(result.passed)
        self.assertEqual(self.taking.progress()["assessed"], 0)

    def test_a_result_must_belong_to_the_subject(self):
        other = models.Subject.objects.create(
            short_name="BIO", full_name="Biology", created_by=self.user
        )
        stray = models.Topic.objects.create(
            subject=other, short_name="CELL", full_name="Cells", created_by=self.user
        )

        with self.assertRaises(ValidationError):
            models.TopicResult(
                student_subject=self.taking, topic=stray, score_pct=Decimal("80")
            ).full_clean()

    def test_one_live_result_per_topic(self):
        self.mark(self.skimming, 70)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self.mark(self.skimming, 80)

    def test_a_voided_result_stops_competing(self):
        first = self.mark(self.skimming, 70)
        first.void(user=self.user, reason="marked the wrong paper")

        second = self.mark(self.skimming, 40)

        self.assertEqual(self.taking.progress()["passed"], 0)
        self.assertEqual(second.score_pct, Decimal("40"))


class MarkingGridTests(TopicResultFixture):
    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("admin:app_studentsubject_results", args=[self.taking.pk])

    def test_the_grid_lists_every_leaf_under_its_section(self):
        body = self.client.get(self.url).content.decode(errors="ignore")

        self.assertIn("Skimming", body)
        self.assertIn("Inference", body)
        self.assertIn("Writing", body)
        self.assertIn(f'name="score_{self.skimming.pk}"', body)
        # Sections are headings, not markable rows of their own.
        self.assertNotIn(f'name="score_{self.topic.pk}"', body)

    def test_saving_records_the_marks(self):
        self.client.post(self.url, {
            f"score_{self.skimming.pk}": "72",
            f"score_{self.inference.pk}": "48",
            f"score_{self.writing.pk}": "",
        })

        results = {r.topic_id: r.score_pct for r in self.taking.topic_results.all()}
        self.assertEqual(results[self.skimming.pk], Decimal("72.00"))
        self.assertEqual(results[self.inference.pk], Decimal("48.00"))
        self.assertNotIn(self.writing.pk, results)
        self.assertEqual(self.taking.progress()["percent"], 33)

    def test_saving_again_updates_rather_than_duplicates(self):
        self.client.post(self.url, {f"score_{self.skimming.pk}": "40"})
        self.client.post(self.url, {f"score_{self.skimming.pk}": "90"})

        rows = self.taking.topic_results.filter(topic=self.skimming)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().score_pct, Decimal("90.00"))

    def test_clearing_a_box_clears_the_mark_without_losing_the_row(self):
        self.client.post(self.url, {f"score_{self.skimming.pk}": "90"})

        self.client.post(self.url, {f"score_{self.skimming.pk}": ""})

        row = self.taking.topic_results.get(topic=self.skimming)
        self.assertIsNone(row.score_pct)
        self.assertIsNone(row.assessed_on)

    def test_a_mark_is_dated_and_attributed(self):
        self.client.post(self.url, {f"score_{self.skimming.pk}": "65"})

        row = self.taking.topic_results.get(topic=self.skimming)
        self.assertEqual(row.assessed_on, timezone.localdate())
        self.assertEqual(row.created_by, self.user)
        self.assertEqual(row.method, models.EvalMethod.TEACHER)

    def test_the_student_subject_page_links_to_the_grid(self):
        body = self.client.get(
            reverse("admin:app_studentsubject_change", args=[self.taking.pk])
        ).content.decode(errors="ignore")

        self.assertIn(self.url, body)


class KnowledgeMapDataTests(TopicResultFixture):
    def setUp(self):
        self.client = Client()
        self.client.force_login(self.user)
        self.url = reverse("admin:app_student_knowledge_map", args=[self.student.pk])

    def english(self, payload):
        return next(s for s in payload["subjects"] if s["short_name"] == "ENG")

    def test_a_subject_carries_its_completion(self):
        self.mark(self.skimming, 70)
        self.mark(self.writing, 80)

        english = self.english(self.client.get(self.url, {"year": 2026}).json())

        self.assertEqual(english["topics"], 3)
        self.assertEqual(english["passed"], 2)
        self.assertEqual(english["percent"], 67)

    def test_topics_are_marked_one_by_one(self):
        self.mark(self.skimming, 70)
        self.mark(self.inference, 20)

        english = self.english(self.client.get(self.url).json())
        marks = {}

        def walk(nodes):
            for node in nodes:
                marks[node["name"]] = node["status"]
                walk(node["children"])

        walk(english["children"])

        self.assertEqual(marks["Skimming"], "passed")
        self.assertEqual(marks["Inference"], "studying")
        self.assertEqual(marks["Writing"], "studying")

    def test_a_section_is_passed_only_when_all_of_it_is(self):
        self.mark(self.skimming, 70)

        english = self.english(self.client.get(self.url).json())
        comprehension = english["children"][0]

        self.assertEqual(comprehension["status"], "studying")
        self.assertEqual(comprehension["passed_leaves"], 1)
        self.assertEqual(comprehension["leaves"], 2)

        self.mark(self.inference, 90)
        english = self.english(self.client.get(self.url).json())

        self.assertEqual(english["children"][0]["status"], "passed")

    def test_a_subject_never_taken_marks_its_topics_with_crosses(self):
        biology = models.Subject.objects.create(
            short_name="BIO", full_name="Biology", created_by=self.user
        )
        models.Topic.objects.create(
            subject=biology, short_name="CELL", full_name="Cells", created_by=self.user
        )

        payload = self.client.get(self.url).json()
        bio = next(s for s in payload["subjects"] if s["short_name"] == "BIO")

        self.assertEqual(bio["status"], "not_taken")
        self.assertEqual(bio["children"][0]["status"], "not_taken")
        self.assertEqual(bio["percent"], 0)

    def test_the_subjects_tab_shows_the_percentage(self):
        self.mark(self.skimming, 70)

        body = self.client.get(
            reverse("admin:app_student_change", args=[self.student.pk])
        ).content.decode(errors="ignore")

        self.assertIn("33%", body)
        self.assertIn("record marks", body)


class DemoMarkTests(DemoDataTests):
    """The demo fills in topic marks, so the maps are not blank."""

    def test_loading_records_marks_against_topics(self):
        self.load()

        marks = models.TopicResult.objects.filter(
            student_subject__enrolment__student__in=self.demo_students()
        )

        self.assertGreater(marks.count(), 200)
        self.assertTrue(all(m.score_pct is not None for m in marks[:50]))

    def test_every_demo_subject_is_partly_done_and_partly_open(self):
        self.load()

        percents = [
            taking.progress()["percent"]
            for taking in models.StudentSubject.objects.filter(
                enrolment__student__in=self.demo_students()
            ).select_related("syllabus__subject")[:12]
        ]

        self.assertTrue(any(p > 0 for p in percents))
        self.assertTrue(all(p < 100 for p in percents))

    def test_the_marks_are_the_same_every_time(self):
        self.load()
        first = list(
            models.TopicResult.objects
            .filter(student_subject__enrolment__student__in=self.demo_students())
            .order_by("id").values_list("topic_id", "score_pct")[:40]
        )

        call_command("seed_demo", year=2026, remove=True, stdout=StringIO())
        call_command("seed_demo", year=2026, stdout=StringIO())

        second = list(
            models.TopicResult.objects
            .filter(student_subject__enrolment__student__in=self.demo_students())
            .order_by("id").values_list("topic_id", "score_pct")[:40]
        )
        self.assertEqual(first, second)

    def test_removing_voids_the_marks_too(self):
        self.load()

        call_command("seed_demo", year=2026, remove=True, stdout=StringIO())

        self.assertEqual(
            models.TopicResult.objects.filter(
                student_subject__enrolment__student__in=
                models.Student.all_objects.filter(
                    admission_no__startswith=demo_data.PREFIX
                )
            ).count(),
            0,
        )
