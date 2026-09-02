"""
Unit tests for the rules the schema promises but a foreign key cannot.

Run with `python manage.py test`, which uses an in-memory database — no
server, no files left behind.
"""

import tempfile
import uuid
from datetime import date, timedelta
from io import StringIO

from django.contrib.admin import site
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.test import Client, RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from . import access, audit, entity_help, files, models


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
        self.assertEqual(models.Topic.objects.count(), 156)
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
            models.Topic.objects.filter(subject=maths, short_name__startswith="LS-").count(), 4
        )
        self.assertEqual(
            models.Topic.objects.filter(subject=maths, short_name__startswith="OL-").count(), 9
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

    def test_the_six_roles_exist(self):
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

        self.assertEqual(client.get("/api/questions/").status_code, 200)
        self.assertEqual(client.get("/api/students/").status_code, 200)
        self.assertEqual(client.get("/api/answers/").status_code, 200)
        self.assertEqual(client.get("/api/attendance-sessions/").status_code, 200)

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
