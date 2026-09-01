"""
Unit tests for the rules the schema promises but a foreign key cannot.

Run with `python manage.py test`, which uses an in-memory database — no
server, no files left behind.
"""

from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from . import models


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

    def test_schema_and_docs_are_served(self):
        self.assertEqual(self.client.get("/api/schema/").status_code, 200)
        self.assertEqual(self.client.get("/api/docs/").status_code, 200)
