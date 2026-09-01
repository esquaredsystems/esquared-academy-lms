"""
API routes for the assessment app.

Every resource is a standard DRF router registration, so each gets
list / create / retrieve / update / partial_update, plus `void` and
`unvoid`. DELETE voids rather than deletes.

Extra actions worth knowing about:
    POST /api/paper-versions/{id}/lock/    freeze a version, pin its prompts
    POST /api/paper-versions/{id}/clone/   next version, items carried over
    GET  /api/students/{id}/enrolments/
    GET  /api/syllabi/{id}/topics/
    GET  /api/questions/{id}/group_parts/
    GET  /api/attempts/{id}/answers/
    GET  /api/answers/{id}/evaluations/
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

# identity
router.register("users", views.AppUserViewSet, basename="appuser")

# people & placement
router.register("grades", views.GradeViewSet, basename="grade")
router.register("students", views.StudentViewSet, basename="student")
router.register("teachers", views.TeacherViewSet, basename="teacher")
router.register("enrolments", views.EnrolmentViewSet, basename="enrolment")

# curriculum
router.register("subjects", views.SubjectViewSet, basename="subject")
router.register("topics", views.TopicViewSet, basename="topic")
router.register("syllabi", views.SyllabusViewSet, basename="syllabus")
router.register("syllabus-topics", views.SyllabusTopicViewSet, basename="syllabustopic")
router.register("student-subjects", views.StudentSubjectViewSet, basename="studentsubject")
router.register(
    "teaching-assignments", views.TeachingAssignmentViewSet, basename="teachingassignment"
)

# prompt library
router.register("prompts", views.EvaluationPromptViewSet, basename="evaluationprompt")
router.register("prompt-versions", views.PromptVersionViewSet, basename="promptversion")

# question bank
router.register("questions", views.QuestionViewSet, basename="question")
router.register("binary-configs", views.BinaryConfigViewSet, basename="binaryconfig")
router.register("numeric-configs", views.NumericConfigViewSet, basename="numericconfig")

# papers & delivery
router.register("question-papers", views.QuestionPaperViewSet, basename="questionpaper")
router.register("paper-versions", views.PaperVersionViewSet, basename="paperversion")
router.register("paper-items", views.PaperItemViewSet, basename="paperitem")
router.register("cohorts", views.StudentCohortViewSet, basename="studentcohort")
router.register(
    "cohort-memberships", views.CohortMembershipViewSet, basename="cohortmembership"
)
router.register(
    "paper-assignments", views.PaperAssignmentViewSet, basename="paperassignment"
)

# assessment & marking
router.register("attempts", views.AttemptViewSet, basename="attempt")
router.register("answers", views.AnswerViewSet, basename="answer")
router.register("evaluations", views.EvaluationViewSet, basename="evaluation")

# retention
router.register(
    "retention-policies", views.RetentionPolicyViewSet, basename="retentionpolicy"
)
router.register("purge-runs", views.PurgeRunViewSet, basename="purgerun")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
]
