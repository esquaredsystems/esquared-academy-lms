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

    POST /api/handouts/{id}/activate/          hand a sheet out to the class\n    POST /api/handouts/{id}/close/             stop accepting work\n    GET  /api/handouts/{id}/completion/        who has handed in\n\n    POST /api/lessons/{id}/submit/             hand a lesson to a head for review\n    POST /api/lessons/{id}/approve/            approve it; from here it is content\n    POST /api/lessons/{id}/return_for_changes/ send it back, with a reason\n\n    POST /api/attendance-sessions/{id}/mark/   mark a whole register at once

    POST /api/uploads/                  start a chunked upload
    PUT  /api/uploads/{uuid}/chunk/     append bytes
    POST /api/uploads/{uuid}/complete/  store the assembled file
"""

from django.urls import include, path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()

# identity
router.register("users", views.AppUserViewSet, basename="appuser")

# people & placement
router.register("academy-classes", views.AcademyClassViewSet, basename="academyclass")
router.register("students", views.StudentViewSet, basename="student")
router.register(
    "student-attribute-types", views.StudentAttributeTypeViewSet, basename="studentattributetype"
)
router.register(
    "student-attributes", views.StudentAttributeViewSet, basename="studentattribute"
)
router.register("teachers", views.TeacherViewSet, basename="teacher")
router.register("enrolments", views.EnrolmentViewSet, basename="enrolment")

# curriculum
router.register("subjects", views.SubjectViewSet, basename="subject")
router.register("topics", views.TopicViewSet, basename="topic")
router.register("syllabi", views.SyllabusViewSet, basename="syllabus")
router.register("syllabus-topics", views.SyllabusTopicViewSet, basename="syllabustopic")
router.register("student-subjects", views.StudentSubjectViewSet, basename="studentsubject")
router.register("topic-results", views.TopicResultViewSet, basename="topicresult")
router.register(
    "teaching-assignments", views.TeachingAssignmentViewSet, basename="teachingassignment"
)

# timetable and lessons
router.register("timetable-slots", views.TimetableSlotViewSet, basename="timetableslot")
router.register("lessons", views.LessonViewSet, basename="lesson")
router.register("lesson-topics", views.LessonTopicViewSet, basename="lessontopic")
router.register("lecture-items", views.LectureItemViewSet, basename="lectureitem")

# handouts and what students hand back
router.register("handouts", views.HandoutViewSet, basename="handout")
router.register("handout-lessons", views.HandoutLessonViewSet, basename="handoutlesson")
router.register("submissions", views.SubmissionViewSet, basename="submission")
router.register(
    "handout-extensions", views.HandoutExtensionViewSet,
    basename="handoutextension",
)
router.register("handout-sheets", views.HandoutSheetViewSet, basename="handoutsheet")

# prompt library
router.register("prompts", views.EvaluationPromptViewSet, basename="evaluationprompt")
router.register("prompt-versions", views.PromptVersionViewSet, basename="promptversion")

# question bank
router.register("questions", views.QuestionViewSet, basename="question")
router.register(
    "question-attribute-types", views.QuestionAttributeTypeViewSet, basename="questionattributetype"
)
router.register(
    "question-attributes", views.QuestionAttributeViewSet, basename="questionattribute"
)

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

# attendance and guardians
router.register("attendance-sessions", views.AttendanceSessionViewSet, basename="attendancesession")
router.register("attendance-records", views.AttendanceRecordViewSet, basename="attendancerecord")
router.register("guardian-links", views.GuardianLinkViewSet, basename="guardianlink")

# files
router.register("attachments", views.AttachmentViewSet, basename="attachment")
router.register("attachment-links", views.AttachmentLinkViewSet, basename="attachmentlink")
router.register("uploads", views.UploadSessionViewSet, basename="upload")

# retention
router.register(
    "retention-policies", views.RetentionPolicyViewSet, basename="retentionpolicy"
)
router.register("purge-runs", views.PurgeRunViewSet, basename="purgerun")

app_name = "api"

urlpatterns = [
    path("", include(router.urls)),
]
