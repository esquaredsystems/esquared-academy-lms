"""
Django admin.
"""

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from . import entity_help as help_text
from .columns import TruncatedColumnsMixin, shorten
from . import files as app_files
from . import models

# Everything the audit block carries, in the order it is shown.
AUDIT_FIELDS = (
    "voided", "void_reason", "date_voided", "voided_by",
    "uuid", "created_by", "date_created", "changed_by", "date_changed",
)

# Voiding is the one audit decision a person makes; the rest stamps itself
# and is shown read-only.
AUDIT_EDITABLE = ("voided", "void_reason")
AUDIT_READONLY = tuple(f for f in AUDIT_FIELDS if f not in AUDIT_EDITABLE)


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


class AuditAdmin(TruncatedColumnsMixin, admin.ModelAdmin):
    """Shared behaviour for every audited model."""

    readonly_fields = AUDIT_READONLY
    list_filter = (VoidedFilter,)
    actions = ("void_selected",)
    save_on_top = True
    change_list_template = "admin/academy_change_list.html"

    def changelist_view(self, request, extra_context=None):
        """Hand the template this entity's help text for the "?" button."""
        extra_context = {
            **(extra_context or {}),
            "entity_help": help_text.help_for(self.model),
        }
        return super().changelist_view(request, extra_context=extra_context)

    def get_fieldsets(self, request, obj=None):
        """
        Main fields first, the audit block last in its own collapsed
        section — on every model, without each ModelAdmin repeating it.
        """
        fieldsets = super().get_fieldsets(request, obj)
        audit_present, cleaned = [], []
        for name, opts in fieldsets:
            fields = []
            for field in opts.get("fields", ()):
                target = audit_present if field in AUDIT_FIELDS else fields
                target.append(field)
            if fields:
                cleaned.append((name, {**opts, "fields": fields}))
        if not audit_present:
            return tuple(cleaned)
        ordered = [f for f in AUDIT_FIELDS if f in audit_present]
        return tuple(cleaned) + (
            ("Audit", {"fields": ordered, "classes": ("collapse",),
                       "description": "Stamped automatically. Only voiding is set by hand."}),
        )

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


class AttachmentLinkInline(GenericTabularInline):
    """Files attached to whatever row is being edited."""

    model = models.AttachmentLink
    extra = 0
    fields = ("attachment", "role", "sort_order", "voided")
    raw_id_fields = ("attachment",)


@admin.register(models.AppUser)
class AppUserAdmin(UserAdmin, AuditAdmin):
    list_display = ("username", "first_name", "last_name", "email", "suspended", "is_staff")
    list_filter = UserAdmin.list_filter + ("suspended", VoidedFilter)
    fieldsets = UserAdmin.fieldsets + (
        ("Academy", {"fields": ("id_number", "suspended")}),
        ("Audit", {"fields": AUDIT_FIELDS, "classes": ("collapse",),
                   "description": "Stamped automatically. Only voiding is set by hand."}),
    )
    readonly_fields = AUDIT_READONLY


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
    list_display = ("indented_name", "subject", "short_name", "child_count",
                    "sort_order", "visible", "live")
    list_filter = ("subject", "depth", "visible", VoidedFilter)
    search_fields = ("short_name", "full_name", "id_number")
    list_select_related = ("subject", "parent")
    # Server-side search rather than a raw id box. app/static/js narrows it
    # to the same subject and cuts the keystroke delay to 200 ms.
    autocomplete_fields = ("parent",)

    class Media:
        js = ("js/topic-autocomplete.js",)
        css = {"all": ("css/topic-autocomplete.css",)}

    change_list_template = "admin/app/topic/change_list.html"

    def get_urls(self):
        return [
            path(
                "graph/",
                self.admin_site.admin_view(self.knowledge_graph_view),
                name="app_topic_graph",
            ),
        ] + super().get_urls()

    def knowledge_graph_view(self, request):
        """
        The knowledge graph: a subject and its topic tree, drawn with D3.

        The page only picks the subject and draws; the tree itself comes
        from /api/topics/tree/, so the same data feeds anything else that
        wants it.
        """
        subjects = models.Subject.objects.order_by("sort_order", "short_name")
        selected = request.GET.get("subject")
        context = {
            **self.admin_site.each_context(request),
            "title": "Knowledge graph",
            "opts": self.model._meta,
            "subjects": subjects,
            "selected_id": int(selected) if selected and selected.isdigit()
                           else (subjects.first().pk if subjects.exists() else None),
            "tree_url": reverse("api:topic-tree"),
        }
        return TemplateResponse(request, "admin/knowledge_graph.html", context)

    def get_search_results(self, request, queryset, search_term):
        """
        Also serves the parent picker's autocomplete requests.

        The picker sends the form's current subject and the topic being
        edited, so the results can only ever contain valid parents: same
        subject, and never the topic itself or anything below it.
        """
        queryset, may_have_duplicates = super().get_search_results(
            request, queryset, search_term
        )

        subject_id = request.GET.get("subject")
        if subject_id:
            queryset = queryset.filter(subject_id=subject_id)

        exclude_id = request.GET.get("exclude_topic")
        if exclude_id:
            current = models.Topic.objects.filter(pk=exclude_id).first()
            if current:
                queryset = queryset.exclude(pk=current.pk).exclude(
                    path__startswith=f"{current.path}/"
                )

        # Only sensible parents: a topic already at the depth limit cannot
        # take children.
        queryset = queryset.filter(depth__lt=models.Topic.MAX_DEPTH)
        return queryset, may_have_duplicates

    @admin.display(description="Topic", ordering="path")
    def indented_name(self, obj):
        """
        Nesting shown by indentation, so the tree reads in the list. This
        column builds its own markup, so it truncates its own text.
        """
        name = shorten(obj.full_name)
        if not obj.depth:
            return format_html('<strong title="{}">{}</strong>', obj.full_name, name)
        return format_html(
            '<span style="opacity:.6">{}</span><span title="{}">{}</span>',
            "\u00a0" * (obj.depth * 4) + "└ ", obj.full_name, name,
        )

    @admin.display(description="Children")
    def child_count(self, obj):
        count = obj.children.count()
        return count or ""


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
    inlines = (BinaryConfigInline, NumericConfigInline, AttachmentLinkInline)


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
                f.name for f in obj._meta.fields if f.name not in AUDIT_EDITABLE
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
    inlines = (EvaluationInline, AttachmentLinkInline)


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
class PurgeRunAdmin(TruncatedColumnsMixin, admin.ModelAdmin):
    list_display = ("target_table", "rows_purged", "ran_by", "date_run")
    list_filter = ("target_table",)
    readonly_fields = ("target_table", "criteria", "row_ids", "rows_purged", "ran_by", "date_run")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.site_header = "Esquared Academy"
admin.site.site_title = "Esquared Academy"
admin.site.index_title = "Assessment platform"


# ---------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------
@admin.register(models.Attachment)
class AttachmentAdmin(AuditAdmin):
    list_display = ("preview", "original_filename", "kind", "size_display", "mime_type",
                    "date_created", "live")
    list_filter = ("kind", VoidedFilter)
    search_fields = ("original_filename", "title", "caption", "checksum")
    readonly_fields = AUDIT_READONLY + (
        "preview_large", "original_filename", "kind", "mime_type",
        "size_display", "checksum", "file",
    )
    change_list_template = "admin/app/attachment/change_list.html"

    def get_urls(self):
        return [
            path(
                "upload/",
                self.admin_site.admin_view(self.upload_view),
                name="app_attachment_upload",
            ),
        ] + super().get_urls()

    def upload_view(self, request):
        """Drag-and-drop uploader. Sends files in chunks through /api/uploads/."""
        context = {
            **self.admin_site.each_context(request),
            "title": "Upload files",
            "opts": self.model._meta,
            "chunk_size": settings.UPLOAD_CHUNK_SIZE,
            "chunk_size_display": app_files.human_size(settings.UPLOAD_CHUNK_SIZE),
        }
        return TemplateResponse(request, "admin/app/attachment/upload.html", context)

    @admin.display(description="")
    def preview(self, obj):
        if obj.kind == app_files.FileKind.PICTURE and obj.file:
            return format_html(
                '<img src="{}" style="height:36px;border-radius:3px" alt="">', obj.file.url
            )
        icons = {"text": "📄", "audio": "🎵", "video": "🎬", "other": "📦"}
        return icons.get(obj.kind, "📦")

    @admin.display(description="Preview")
    def preview_large(self, obj):
        if not obj.file:
            return "—"
        if obj.kind == app_files.FileKind.PICTURE:
            return format_html('<img src="{}" style="max-width:420px" alt="">', obj.file.url)
        if obj.kind == app_files.FileKind.VIDEO:
            return format_html('<video src="{}" controls style="max-width:420px"></video>', obj.file.url)
        if obj.kind == app_files.FileKind.AUDIO:
            return format_html('<audio src="{}" controls></audio>', obj.file.url)
        return format_html('<a href="{}" target="_blank" rel="noopener">Download</a>', obj.file.url)

    @admin.display(description="Size", ordering="size_bytes")
    def size_display(self, obj):
        return obj.size_display


@admin.register(models.AttachmentLink)
class AttachmentLinkAdmin(AuditAdmin):
    list_display = ("attachment", "content_type", "object_id", "role", "sort_order", "live")
    list_filter = ("role", "content_type", VoidedFilter)
    raw_id_fields = ("attachment",)


@admin.register(models.UploadSession)
class UploadSessionAdmin(AuditAdmin):
    list_display = ("filename", "state", "received", "declared_size", "attachment", "date_created")
    list_filter = ("state", VoidedFilter)
    readonly_fields = AUDIT_READONLY + ("filename", "mime_type", "declared_size", "received", "attachment")

    def has_add_permission(self, request):
        return False


# ---------------------------------------------------------------------
# Guardians and attendance
# ---------------------------------------------------------------------
@admin.register(models.GuardianLink)
class GuardianLinkAdmin(AuditAdmin):
    list_display = ("student", "user", "relationship", "is_primary", "can_view_marks", "live")
    list_filter = ("relationship", "is_primary", VoidedFilter)
    search_fields = ("student__first_name", "student__last_name", "user__username", "user__email")
    raw_id_fields = ("user", "student")


class AttendanceRecordInline(admin.TabularInline):
    model = models.AttendanceRecord
    extra = 0
    fields = ("enrolment", "status", "minutes_late", "note", "voided")
    raw_id_fields = ("enrolment",)


@admin.register(models.AttendanceSession)
class AttendanceSessionAdmin(AuditAdmin):
    list_display = ("date", "grade", "period", "syllabus", "academic_year",
                    "marked", "is_finalised", "live")
    list_filter = ("grade", "academic_year", "period", "is_finalised", VoidedFilter)
    date_hierarchy = "date"
    raw_id_fields = ("syllabus",)
    inlines = (AttendanceRecordInline,)

    @admin.display(description="Marked")
    def marked(self, obj):
        counts = obj.summary
        if not counts:
            return "—"
        return shorten(", ".join(f"{s}: {c}" for s, c in sorted(counts.items())))


@admin.register(models.AttendanceRecord)
class AttendanceRecordAdmin(AuditAdmin):
    list_display = ("session", "student_name", "status", "minutes_late", "live")
    list_filter = ("status", "session__grade", "session__academic_year", VoidedFilter)
    search_fields = ("enrolment__student__first_name", "enrolment__student__last_name")
    raw_id_fields = ("session", "enrolment")

    @admin.display(description="Student", ordering="enrolment__student__last_name")
    def student_name(self, obj):
        return shorten(str(obj.enrolment.student))
