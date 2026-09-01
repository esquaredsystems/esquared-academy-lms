"""
Django admin.

Voided rows stay visible here — the admin is the audit surface — but they
are filtered out by default and marked in the list. Deleting is replaced
by a "void" action, so nothing leaves the database through the admin.
"""

from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.utils import timezone

from . import models

AUDIT_FIELDS = (
    "created_by", "date_created", "changed_by", "date_changed",
    "voided", "voided_by", "date_voided", "void_reason",
)


class VoidedFilter(admin.SimpleListFilter):
    title = "voided"
    parameter_name = "voided"

    def lookups(self, request, model_admin):
        return (("0", "Live only"), ("1", "Voided only"), ("all", "Both"))

    def queryset(self, request, queryset):
        value = self.value()
        if value == "1":
            return queryset.filter(voided=True)
        if value == "all":
            return queryset
        return queryset.filter(voided=False)


class AuditAdmin(admin.ModelAdmin):
    """Shared behaviour for every audited model."""

    readonly_fields = ("date_created", "date_changed", "date_voided", "voided_by")
    list_filter = (VoidedFilter,)
    actions = ("void_selected",)
    save_on_top = True

    def get_queryset(self, request):
        model = self.model
        manager = getattr(model, "all_objects", model._default_manager)
        return manager.get_queryset()

    def save_model(self, request, obj, form, change):
        if change:
            obj.changed_by = request.user
            obj.date_changed = timezone.now()
        elif not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    def has_delete_permission(self, request, obj=None):
        """Nothing is deleted from the admin — it is voided instead."""
        return False

    @admin.action(description="Void selected rows (soft delete)")
    def void_selected(self, request, queryset):
        count = 0
        for obj in queryset:
            if not obj.voided:
                obj.void(user=request.user, reason="voided from admin")
                count += 1
        self.message_user(request, f"{count} row(s) voided.", messages.SUCCESS)

    @admin.display(boolean=True, description="live")
    def live(self, obj):
        return not obj.voided


@admin.register(models.AppUser)
class AppUserAdmin(UserAdmin, AuditAdmin):
    list_display = ("username", "first_name", "last_name", "email", "suspended", "is_staff")
    list_filter = UserAdmin.list_filter + ("suspended", VoidedFilter)
    fieldsets = UserAdmin.fieldsets + (
        ("Academy", {"fields": ("id_number", "suspended")}),
        ("Audit", {"fields": ("voided", "void_reason"), "classes": ("collapse",)}),
    )
    readonly_fields = ("date_voided", "voided_by")


@admin.register(models.Grade)
class GradeAdmin(AuditAdmin):
    list_display = ("full_name", "short_name", "level", "is_terminal", "capacity", "visible", "live")
    search_fields = ("short_name", "full_name", "id_number")
    list_filter = ("is_terminal", "visible", VoidedFilter)


@admin.register(models.Student)
class StudentAdmin(AuditAdmin):
    list_display = ("admission_no", "first_name", "last_name", "date_of_birth", "live")
    search_fields = ("admission_no", "first_name", "last_name", "id_number")
    raw_id_fields = ("user",)


@admin.register(models.Teacher)
class TeacherAdmin(AuditAdmin):
    list_display = ("staff_no", "user", "id_number", "live")
    search_fields = ("staff_no", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)


@admin.register(models.Enrolment)
class EnrolmentAdmin(AuditAdmin):
    list_display = ("student", "grade", "academic_year", "status", "started_on", "live")
    list_filter = ("academic_year", "grade", "status", VoidedFilter)
    search_fields = ("student__admission_no", "student__last_name")
    raw_id_fields = ("student",)


@admin.register(models.Subject)
class SubjectAdmin(AuditAdmin):
    list_display = ("short_name", "full_name", "sort_order", "visible", "live")
    search_fields = ("short_name", "full_name", "id_number")


class SyllabusTopicInline(admin.TabularInline):
    model = models.SyllabusTopic
    extra = 0
    fields = ("topic", "sort_order", "weight_pct", "voided")
    raw_id_fields = ("topic",)


@admin.register(models.Topic)
class TopicAdmin(AuditAdmin):
    list_display = ("full_name", "subject", "short_name", "sort_order", "visible", "live")
    list_filter = ("subject", "visible", VoidedFilter)
    search_fields = ("short_name", "full_name", "id_number")


@admin.register(models.Syllabus)
class SyllabusAdmin(AuditAdmin):
    list_display = ("subject", "grade", "academic_year", "is_core", "status", "live")
    list_filter = ("academic_year", "grade", "subject", "status", "is_core", VoidedFilter)
    inlines = (SyllabusTopicInline,)


@admin.register(models.SyllabusTopic)
class SyllabusTopicAdmin(AuditAdmin):
    list_display = ("syllabus", "topic", "sort_order", "weight_pct", "live")
    list_filter = ("syllabus__academic_year", VoidedFilter)


@admin.register(models.StudentSubject)
class StudentSubjectAdmin(AuditAdmin):
    list_display = ("enrolment", "syllabus", "live")
    raw_id_fields = ("enrolment", "syllabus")


@admin.register(models.TeachingAssignment)
class TeachingAssignmentAdmin(AuditAdmin):
    list_display = ("teacher", "syllabus", "role", "live")
    list_filter = ("role", "syllabus__academic_year", VoidedFilter)


class PromptVersionInline(admin.TabularInline):
    model = models.PromptVersion
    extra = 0
    fields = ("version_no", "status", "effective_from", "prompt_text", "voided")


@admin.register(models.EvaluationPrompt)
class EvaluationPromptAdmin(AuditAdmin):
    list_display = ("name", "applies_to", "subject", "visible", "live")
    list_filter = ("applies_to", "subject", "visible", VoidedFilter)
    search_fields = ("name", "description")
    inlines = (PromptVersionInline,)


@admin.register(models.PromptVersion)
class PromptVersionAdmin(AuditAdmin):
    list_display = ("evaluation_prompt", "version_no", "status", "effective_from", "live")
    list_filter = ("status", "evaluation_prompt", VoidedFilter)
    search_fields = ("prompt_text",)

    def get_readonly_fields(self, request, obj=None):
        base = super().get_readonly_fields(request, obj)
        if obj and obj.status == models.PromptStatus.ACTIVE:
            return base + ("prompt_text", "rubric_json", "version_no", "evaluation_prompt")
        return base


class BinaryConfigInline(admin.StackedInline):
    model = models.BinaryConfig
    extra = 0
    can_delete = False


class NumericConfigInline(admin.StackedInline):
    model = models.NumericConfig
    extra = 0
    can_delete = False


@admin.register(models.Question)
class QuestionAdmin(AuditAdmin):
    list_display = (
        "name", "topic", "question_type", "group", "order_in_group",
        "default_mark", "difficulty", "live",
    )
    list_filter = ("question_type", "topic__subject", "difficulty", "visible", VoidedFilter)
    search_fields = ("name", "question_text", "group", "id_number")
    raw_id_fields = ("topic", "default_prompt_version")
    inlines = (BinaryConfigInline, NumericConfigInline)


@admin.register(models.BinaryConfig)
class BinaryConfigAdmin(AuditAdmin):
    list_display = ("question", "expected_value", "live")


@admin.register(models.NumericConfig)
class NumericConfigAdmin(AuditAdmin):
    list_display = ("question", "expected_value", "tolerance_type", "tolerance", "unit", "live")
    list_filter = ("tolerance_type", VoidedFilter)


class PaperItemInline(admin.TabularInline):
    model = models.PaperItem
    extra = 0
    fields = ("slot", "page", "question", "section_label", "max_mark", "prompt_version", "voided")
    raw_id_fields = ("question", "prompt_version")


@admin.register(models.QuestionPaper)
class QuestionPaperAdmin(AuditAdmin):
    list_display = ("name", "subject", "grade", "purpose", "live")
    list_filter = ("purpose", "subject", "grade", VoidedFilter)
    search_fields = ("name", "id_number")


@admin.register(models.PaperVersion)
class PaperVersionAdmin(AuditAdmin):
    list_display = (
        "question_paper", "version_no", "status", "total_marks",
        "date_locked", "cloned_from_version", "live",
    )
    list_filter = ("status", VoidedFilter)
    inlines = (PaperItemInline,)
    actions = AuditAdmin.actions + ("lock_selected", "clone_selected")

    def get_readonly_fields(self, request, obj=None):
        base = super().get_readonly_fields(request, obj)
        if obj and obj.is_locked:
            return base + tuple(
                f.name for f in obj._meta.fields if f.name not in {"voided", "void_reason"}
            )
        return base

    @admin.action(description="Lock selected versions")
    def lock_selected(self, request, queryset):
        locked = 0
        for version in queryset:
            if not version.is_locked:
                version.lock(user=request.user)
                locked += 1
        self.message_user(request, f"{locked} version(s) locked.", messages.SUCCESS)

    @admin.action(description="Clone selected versions into a new draft")
    def clone_selected(self, request, queryset):
        for version in queryset:
            new = version.clone(user=request.user)
            self.message_user(request, f"Created {new}.", messages.SUCCESS)


@admin.register(models.PaperItem)
class PaperItemAdmin(AuditAdmin):
    list_display = ("paper_version", "slot", "question", "max_mark", "prompt_version", "live")
    list_filter = ("paper_version__status", VoidedFilter)
    raw_id_fields = ("paper_version", "question", "prompt_version")


class CohortMembershipInline(admin.TabularInline):
    model = models.CohortMembership
    extra = 0
    raw_id_fields = ("enrolment",)
    fields = ("enrolment", "voided")


@admin.register(models.StudentCohort)
class StudentCohortAdmin(AuditAdmin):
    list_display = ("name", "grade", "academic_year", "purpose", "is_temporary", "live")
    list_filter = ("purpose", "grade", "academic_year", "is_temporary", VoidedFilter)
    search_fields = ("name", "id_number")
    inlines = (CohortMembershipInline,)


@admin.register(models.CohortMembership)
class CohortMembershipAdmin(AuditAdmin):
    list_display = ("student_cohort", "enrolment", "live")
    raw_id_fields = ("student_cohort", "enrolment")


@admin.register(models.PaperAssignment)
class PaperAssignmentAdmin(AuditAdmin):
    list_display = (
        "paper_version", "grade", "academic_year", "student_cohort",
        "time_open", "time_close", "attempts", "marking_method", "live",
    )
    list_filter = ("grade", "academic_year", "marking_method", "is_practice", VoidedFilter)
    raw_id_fields = ("paper_version", "student_cohort")


class AnswerInline(admin.TabularInline):
    model = models.Answer
    extra = 0
    fields = ("paper_item", "boolean_response", "numeric_response", "text_response", "voided")
    raw_id_fields = ("paper_item",)


@admin.register(models.Attempt)
class AttemptAdmin(AuditAdmin):
    list_display = (
        "student", "paper_assignment", "attempt_no", "state",
        "is_counted", "total_marks", "time_start", "live",
    )
    list_filter = ("state", "is_counted", "preview", VoidedFilter)
    raw_id_fields = ("paper_assignment", "student")
    inlines = (AnswerInline,)


class EvaluationInline(admin.TabularInline):
    model = models.Evaluation
    extra = 0
    fields = ("method", "awarded_marks", "fraction", "is_correct", "confidence", "prompt_version")
    readonly_fields = fields
    can_delete = False
    show_change_link = True


@admin.register(models.Answer)
class AnswerAdmin(AuditAdmin):
    list_display = ("attempt", "paper_item", "date_answered", "live")
    raw_id_fields = ("attempt", "paper_item")
    inlines = (EvaluationInline,)


@admin.register(models.Evaluation)
class EvaluationAdmin(AuditAdmin):
    list_display = (
        "answer", "method", "awarded_marks", "fraction", "is_correct",
        "confidence", "evaluated_by", "supersedes", "live",
    )
    list_filter = ("method", "is_correct", VoidedFilter)
    raw_id_fields = ("answer", "prompt_version", "supersedes")

    def has_change_permission(self, request, obj=None):
        """Marking is append-only: corrections are new rows."""
        return obj is None


@admin.register(models.RetentionPolicy)
class RetentionPolicyAdmin(AuditAdmin):
    list_display = ("target_table", "void_retention_days", "purge_enabled", "live")
    list_filter = ("purge_enabled", VoidedFilter)
    search_fields = ("target_table",)


@admin.register(models.PurgeRun)
class PurgeRunAdmin(admin.ModelAdmin):
    list_display = ("target_table", "rows_purged", "ran_by", "date_run")
    list_filter = ("target_table",)
    readonly_fields = ("target_table", "criteria", "row_ids", "rows_purged", "ran_by", "date_run")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = "E Squared Academy"
admin.site.site_title = "E Squared Academy"
admin.site.index_title = "Assessment platform"
