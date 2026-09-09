"""
Django admin.
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.contenttypes.admin import GenericTabularInline
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.template.loader import render_to_string
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from . import access
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


class IncludeVoidedFilter(admin.SimpleListFilter):
    """
    A checkbox, not a dropdown.

    Unticked — the default — lists live rows only. Ticked lists the voided
    ones alongside them, which is what the audit trail is for. There is no
    "voided only" option: seeing a voided row in its place among the live
    ones is more useful than seeing it in isolation.
    """

    title = "voided"
    parameter_name = "include_voided"
    template = "admin/include_voided_filter.html"

    def lookups(self, request, model_admin):
        return (("1", "Include voided"),)

    def queryset(self, request, queryset):
        if self.value() == "1":
            return queryset
        return queryset.filter(voided=False)

    def choices(self, changelist):
        """
        One "choice", carrying the two URLs the checkbox flips between.

        Django's filter contract expects an iterable of choices; the
        template reads choices.0 rather than looping, because there is
        only ever the one control.
        """
        return [{
            "selected": self.value() == "1",
            "on_url": changelist.get_query_string({self.parameter_name: "1"}),
            "off_url": changelist.get_query_string(remove=[self.parameter_name]),
        }]


class AuditAdmin(TruncatedColumnsMixin, admin.ModelAdmin):
    """Shared behaviour for every audited model."""

    readonly_fields = AUDIT_READONLY
    list_filter = (IncludeVoidedFilter,)
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
    list_filter = UserAdmin.list_filter + ("suspended", IncludeVoidedFilter)
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
    list_filter = ("is_terminal", "visible", IncludeVoidedFilter)


class PhotoAdmin(AuditAdmin):
    """
    Shared portrait handling for the two models that carry one.

    The picture is square by validation, so both the list thumbnail and
    the form preview can be drawn in a circle without cropping anything.
    """

    def get_list_display_links(self, request, list_display):
        """
        The portrait and the identifier next to it both open the record.

        Django matches these by identity against the columns the
        truncation wrapper produced, so they are taken by position rather
        than by name.
        """
        return list(list_display[:2])

    @admin.display(description="")
    def avatar(self, obj):
        """Small round thumbnail for the list; initials when there is none."""
        if obj.photo:
            return format_html(
                '<img src="{}" class="ac-avatar ac-avatar-sm" alt="">', obj.photo.url
            )
        return format_html('<span class="ac-avatar ac-avatar-sm is-empty">{}</span>',
                           self._initials(obj))

    @admin.display(description="Photo")
    def photo_preview(self, obj):
        if obj.photo:
            return format_html(
                '<img src="{}" class="ac-avatar ac-avatar-lg" alt="">', obj.photo.url
            )
        return format_html(
            '<span class="ac-avatar ac-avatar-lg is-empty">{}</span>'
            '<p class="help">{}</p>',
            self._initials(obj), app_files.PHOTO_HELP,
        )

    @staticmethod
    def _initials(obj):
        name = str(obj) or ""
        parts = [p for p in name.replace("(", " ").split() if p[:1].isalpha()]
        return "".join(p[0].upper() for p in parts[:2]) or "?"


@admin.register(models.Student)
class StudentAdmin(PhotoAdmin):
    list_display = ("avatar", "admission_no", "first_name", "last_name",
                    "date_of_birth", "live")
    search_fields = ("admission_no", "first_name", "last_name", "id_number",
                     "national_id", "email", "mobile")
    raw_id_fields = ("user",)
    fieldsets = (
        (None, {"fields": (
            "photo_preview", "photo", "user", "admission_no", "id_number",
            "first_name", "last_name", "date_of_birth",
        )}),
        ("Contact", {
            "fields": ("email", "mobile", "address"),
            "description": "Optional at admission. All of it is needed to enter "
                           "a candidate for a Cambridge examination.",
        }),
        ("Identity document", {
            "fields": ("national_id_type", "national_id"),
            "description": "The name above must match this document exactly.",
        }),
        ("Guardian", {"fields": (
            "guardian_name", "guardian_contact", "guardian_contact_2",
        )}),
        ("Subjects", {"fields": ("subject_panel",)}),
        ("Knowledge map", {"fields": ("knowledge_map_panel",)}),
        ("Audit", {"fields": AUDIT_FIELDS}),
    )
    readonly_fields = AUDIT_READONLY + (
        "photo_preview", "subject_panel", "knowledge_map_panel",
    )

    class Media:
        css = {"all": ("css/student-page.css",)}
        js = (
            "https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js",
            "js/student-knowledge-map.js",
        )

    # -- extra pages ---------------------------------------------------
    def get_urls(self):
        return [
            path(
                "<int:student_id>/knowledge-map/",
                self.admin_site.admin_view(self.knowledge_map_json),
                name="app_student_knowledge_map",
            ),
        ] + super().get_urls()

    def knowledge_map_json(self, request, student_id):
        """
        The student's map as one tree: the student, every subject, and the
        topics under each one.

        Every subject in the catalogue appears, so the crosses — subjects
        never taken — are as visible as the ticks. Inside a subject the
        marks come from the topic results: a tick once the topic is passed
        against the syllabus's pass mark, a question mark while it is
        still being studied. A parent topic is passed when everything
        under it is.
        """
        student = get_object_or_404(models.Student.all_objects, pk=student_id)
        year = int(request.GET.get("year") or timezone.localdate().year)
        records = student.subject_records(year=year)

        passed_topics = self._passed_topics(records)
        trees = self._subject_topic_trees()

        counts = {status: 0 for status, _ in models.SubjectStatus.choices}
        subjects = []
        for subject in models.Subject.objects.filter(voided=False).order_by(
            "sort_order", "short_name"
        ):
            record = records.get(subject.pk)
            status = record["status"] if record else models.SubjectStatus.NOT_TAKEN
            counts[status] = counts.get(status, 0) + 1

            taken = record is not None
            passed = passed_topics.get(subject.pk, set())
            children = [
                self._mark(node, taken, passed)
                for node in trees.get(subject.pk, [])
            ]

            progress = record["student_subject"].progress() if record else None
            subjects.append({
                "id": subject.pk,
                "name": subject.full_name,
                "short_name": subject.short_name,
                "type": "subject",
                "status": str(status),
                "status_label": models.SubjectStatus(status).label,
                "year": record["year"] if record else None,
                "percent": progress["percent"] if progress else 0,
                "passed": progress["passed"] if progress else 0,
                "assessed": progress["assessed"] if progress else 0,
                "topics": progress["total"] if progress else 0,
                "children": children,
            })

        return JsonResponse({
            "student": {
                "id": student.pk,
                "name": student.full_name,
                "admission_no": student.admission_no,
            },
            "year": year,
            "counts": counts,
            "subjects": subjects,
        })

    @staticmethod
    def _passed_topics(records):
        """{subject id: {topic ids passed}} — one query for every subject."""
        by_subject = {}
        if not records:
            return by_subject

        marks = {
            record["student_subject"].pk: record["syllabus"].pass_mark_pct
            for record in records.values()
        }
        subject_of = {
            record["student_subject"].pk: subject_id
            for subject_id, record in records.items()
        }
        rows = models.TopicResult.objects.filter(
            student_subject_id__in=marks, voided=False
        ).values("student_subject_id", "topic_id", "score_pct")

        for row in rows:
            score = row["score_pct"]
            if score is None or score < marks[row["student_subject_id"]]:
                continue
            subject_id = subject_of[row["student_subject_id"]]
            by_subject.setdefault(subject_id, set()).add(row["topic_id"])
        return by_subject

    @staticmethod
    def _subject_topic_trees():
        """{subject id: [nested topic nodes]} — the whole catalogue, one query."""
        topics = (
            models.Topic.objects.filter(voided=False)
            .order_by("subject_id", "depth", "sort_order", "short_name")
            .values("id", "subject_id", "parent_id", "full_name")
        )
        trees, nodes = {}, {}
        for topic in topics:
            node = {
                "id": topic["id"],
                "name": topic["full_name"],
                "type": "topic",
                "children": [],
            }
            nodes[topic["id"]] = node
            parent = nodes.get(topic["parent_id"])
            if parent is not None:
                parent["children"].append(node)
            else:
                trees.setdefault(topic["subject_id"], []).append(node)
        return trees

    @classmethod
    def _mark(cls, node, taken, passed_ids):
        """
        Copy a topic node with its mark on it.

        A leaf is passed when its result says so. A parent is passed when
        every leaf under it is, and carries the tally either way, so a
        folded section still says how much of it is done.
        """
        children = [cls._mark(child, taken, passed_ids) for child in node["children"]]

        if children:
            leaves = sum(child["leaves"] for child in children)
            done = sum(child["passed_leaves"] for child in children)
        else:
            leaves = 1
            done = 1 if node["id"] in passed_ids else 0

        if not taken:
            status = models.SubjectStatus.NOT_TAKEN
        elif leaves and done == leaves:
            status = models.SubjectStatus.PASSED
        else:
            status = models.SubjectStatus.STUDYING

        return {
            "id": node["id"],
            "name": node["name"],
            "type": "topic",
            "status": str(status),
            "leaves": leaves,
            "passed_leaves": done,
            "children": children,
        }

    # -- panels --------------------------------------------------------
    @admin.display(description="")
    def subject_panel(self, obj):
        """Every enrolment, what was taken in it, and how far through it is."""
        if obj.pk is None:
            return "Save the student first."

        year = timezone.localdate().year
        enrolments = (
            models.Enrolment.all_objects.filter(student=obj)
            .select_related("grade")
            .prefetch_related(
                "subjects__syllabus__subject", "subjects__topic_results"
            )
            .order_by("-academic_year")
        )

        rows = []
        for enrolment in enrolments:
            taken = sorted(
                (s for s in enrolment.subjects.all() if not s.voided),
                key=lambda ss: (not ss.syllabus.is_core, ss.syllabus.subject.short_name),
            )
            rows.append({
                "enrolment": enrolment,
                "current": not enrolment.ended_on and enrolment.academic_year >= year,
                "subjects": [
                    {"student_subject": ss, "syllabus": ss.syllabus,
                     "progress": ss.progress()}
                    for ss in taken
                ],
            })

        return render_to_string("admin/app/student/subject_panel.html", {
            "rows": rows,
            "student": obj,
            "total": sum(len(row["subjects"]) for row in rows),
        })

    @admin.display(description="")
    def knowledge_map_panel(self, obj):
        if obj.pk is None:
            return "Save the student first."
        return render_to_string("admin/app/student/knowledge_map_panel.html", {
            "student": obj,
            "year": timezone.localdate().year,
            "map_url": reverse("admin:app_student_knowledge_map", args=[obj.pk]),
        })


@admin.register(models.Teacher)
class TeacherAdmin(PhotoAdmin):
    list_display = ("avatar", "staff_no", "user", "id_number", "live")
    search_fields = ("staff_no", "user__first_name", "user__last_name")
    raw_id_fields = ("user",)
    fieldsets = (
        (None, {"fields": ("photo_preview", "photo", "user", "staff_no", "id_number")}),
        ("Audit", {"fields": AUDIT_FIELDS}),
    )
    readonly_fields = AUDIT_READONLY + ("photo_preview",)

    class Media:
        css = {"all": ("css/student-page.css",)}


@admin.register(models.Enrolment)
class EnrolmentAdmin(AuditAdmin):
    list_display = ("student", "grade", "academic_year", "status", "started_on", "live")
    list_filter = ("academic_year", "grade", "status", IncludeVoidedFilter)
    search_fields = ("student__admission_no", "student__last_name")
    raw_id_fields = ("student",)


@admin.register(models.Subject)
class SubjectAdmin(AuditAdmin):
    list_display = ("short_name", "full_name", "topic_count", "sort_order", "visible", "live")
    search_fields = ("short_name", "full_name", "id_number")

    change_list_template = "admin/app/subject/change_list.html"

    def get_urls(self):
        return [
            path(
                "graph/",
                self.admin_site.admin_view(self.knowledge_graph_view),
                name="app_subject_graph",
            ),
        ] + super().get_urls()

    def knowledge_graph_view(self, request):
        """
        The knowledge graph: a subject and its topic tree, drawn with D3.

        It lives on the subject list because a subject is what it draws —
        pick one from the dropdown on the page. The tree itself comes from
        /api/topics/tree/, so the same data feeds anything else.
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

    @admin.display(description="Topics")
    def topic_count(self, obj):
        total = obj.topics.count()
        sections = obj.topics.filter(parent__isnull=True).count()
        if not total:
            return "—"
        return f"{sections} + {total - sections}" if total > sections else str(sections)


class SyllabusTopicInline(admin.TabularInline):
    model = models.SyllabusTopic
    extra = 0
    fields = ("topic", "sort_order", "weight_pct", "voided")
    raw_id_fields = ("topic",)


@admin.register(models.Topic)
class TopicAdmin(AuditAdmin):
    list_display = ("indented_name", "subject", "short_name", "child_count",
                    "sort_order", "visible", "live")
    list_filter = ("subject", "depth", "visible", IncludeVoidedFilter)
    search_fields = ("short_name", "full_name", "id_number")
    list_select_related = ("subject", "parent")
    # Server-side search rather than a raw id box. app/static/js narrows it
    # to the same subject and cuts the keystroke delay to 200 ms.
    autocomplete_fields = ("parent",)

    class Media:
        js = ("js/topic-autocomplete.js",)
        css = {"all": ("css/topic-autocomplete.css",)}


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
    list_filter = ("academic_year", "grade", "subject", "status", "is_core", IncludeVoidedFilter)
    inlines = (SyllabusTopicInline,)


@admin.register(models.SyllabusTopic)
class SyllabusTopicAdmin(AuditAdmin):
    list_display = ("syllabus", "topic", "sort_order", "weight_pct", "live")
    list_filter = ("syllabus__academic_year", IncludeVoidedFilter)


class TopicResultInline(admin.TabularInline):
    """Marks already recorded. The grid behind "Record marks" adds them."""

    model = models.TopicResult
    extra = 0
    fields = ("topic", "score_pct", "assessed_on", "method", "note", "voided")
    raw_id_fields = ("topic",)


@admin.register(models.StudentSubject)
class StudentSubjectAdmin(AuditAdmin):
    list_display = ("enrolment", "syllabus", "completion", "live")
    list_filter = ("syllabus__academic_year", "syllabus__grade",
                   "syllabus__subject", IncludeVoidedFilter)
    search_fields = ("enrolment__student__admission_no",
                     "enrolment__student__last_name")
    raw_id_fields = ("enrolment", "syllabus")
    inlines = (TopicResultInline,)
    change_form_template = "admin/app/studentsubject/change_form.html"

    def get_urls(self):
        return [
            path(
                "<int:pk>/results/",
                self.admin_site.admin_view(self.results_view),
                name="app_studentsubject_results",
            ),
        ] + super().get_urls()

    @admin.display(description="Completion")
    def completion(self, obj):
        progress = obj.progress()
        if not progress["total"]:
            return "—"
        return format_html(
            '<span class="ac-bar"><i style="width:{}%"></i></span> {}% '
            '<span class="ac-bar-note">{} of {}</span>',
            progress["percent"], progress["percent"],
            progress["passed"], progress["total"],
        )

    def results_view(self, request, pk):
        """
        The marking grid: every assessable topic of this student's subject,
        with the mark against it.

        One page per student per subject, grouped by syllabus section. A
        blank box clears the mark rather than deleting the row, so the note
        and the audit trail on it survive.
        """
        student_subject = get_object_or_404(models.StudentSubject.all_objects, pk=pk)
        sections = student_subject.syllabus.assessable_sections()
        saved = 0

        if request.method == "POST":
            saved = self._save_results(request, student_subject, sections)
            self.message_user(
                request,
                f"{saved} topic mark(s) recorded." if saved else "Nothing changed.",
                messages.SUCCESS if saved else messages.INFO,
            )
            return redirect(
                reverse("admin:app_studentsubject_results", args=[student_subject.pk])
            )

        results = {
            row.topic_id: row
            for row in student_subject.topic_results.filter(voided=False)
        }
        pass_mark = student_subject.syllabus.pass_mark_pct

        groups = []
        for section, leaves in sections:
            rows = []
            for leaf in leaves:
                result = results.get(leaf.pk)
                score = result.score_pct if result else None
                rows.append({
                    "topic": leaf,
                    "score": "" if score is None else f"{score:g}",
                    "passed": score is not None and score >= pass_mark,
                    "assessed": score is not None,
                    "result": result,
                })
            groups.append({
                "section": section,
                "rows": rows,
                "passed": sum(1 for r in rows if r["passed"]),
                "total": len(rows),
            })

        context = {
            **self.admin_site.each_context(request),
            "title": f"Record marks · {student_subject}",
            "opts": self.model._meta,
            "student_subject": student_subject,
            "student": student_subject.enrolment.student,
            "syllabus": student_subject.syllabus,
            "pass_mark": pass_mark,
            "groups": groups,
            "progress": student_subject.progress(),
        }
        return TemplateResponse(
            request, "admin/app/studentsubject/results.html", context
        )

    def _save_results(self, request, student_subject, sections):
        """Read one number per topic out of the posted grid."""
        today = timezone.localdate()
        existing = {
            row.topic_id: row
            for row in student_subject.topic_results.filter(voided=False)
        }
        changed = 0

        for _section, leaves in sections:
            for leaf in leaves:
                raw = (request.POST.get(f"score_{leaf.pk}") or "").strip()
                score = None
                if raw:
                    try:
                        score = Decimal(raw)
                    except (InvalidOperation, ValueError):
                        continue
                    score = max(Decimal("0"), min(Decimal("100"), score))

                result = existing.get(leaf.pk)
                if result is None:
                    if score is None:
                        continue
                    models.TopicResult.objects.create(
                        student_subject=student_subject, topic=leaf,
                        score_pct=score, assessed_on=today,
                        method=models.EvalMethod.TEACHER, created_by=request.user,
                    )
                    changed += 1
                elif result.score_pct != score:
                    result.score_pct = score
                    result.assessed_on = today if score is not None else None
                    result.changed_by = request.user
                    result.save()
                    changed += 1
        return changed


@admin.register(models.TopicResult)
class TopicResultAdmin(AuditAdmin):
    """The marks themselves. Most are entered through the grid, not here."""

    list_display = ("student_name", "subject_name", "topic", "score_pct",
                    "outcome", "assessed_on", "method", "live")
    list_filter = ("method", "student_subject__syllabus__academic_year",
                   "student_subject__syllabus__subject", IncludeVoidedFilter)
    search_fields = ("student_subject__enrolment__student__admission_no",
                     "student_subject__enrolment__student__last_name",
                     "topic__full_name", "topic__short_name")
    raw_id_fields = ("student_subject", "topic")
    date_hierarchy = "assessed_on"
    list_select_related = (
        "student_subject__enrolment__student", "student_subject__syllabus__subject",
        "topic",
    )

    @admin.display(description="Student",
                   ordering="student_subject__enrolment__student__last_name")
    def student_name(self, obj):
        return shorten(str(obj.student_subject.enrolment.student))

    @admin.display(description="Subject",
                   ordering="student_subject__syllabus__subject__short_name")
    def subject_name(self, obj):
        return obj.student_subject.syllabus.subject.short_name

    @admin.display(description="Outcome")
    def outcome(self, obj):
        if obj.score_pct is None:
            return format_html('<span class="ac-mark is-studying">?</span> not assessed')
        if obj.passed:
            return format_html('<span class="ac-mark is-passed">&#10003;</span> passed')
        return format_html('<span class="ac-mark is-below">&#8722;</span> below the mark')


@admin.register(models.TeachingAssignment)
class TeachingAssignmentAdmin(AuditAdmin):
    list_display = ("teacher", "syllabus", "role", "live")
    list_filter = ("role", "syllabus__academic_year", IncludeVoidedFilter)


class PromptVersionInline(admin.TabularInline):
    model = models.PromptVersion
    extra = 0
    fields = ("version_no", "status", "effective_from", "prompt_text", "voided")


@admin.register(models.EvaluationPrompt)
class EvaluationPromptAdmin(AuditAdmin):
    list_display = ("name", "applies_to", "subject", "visible", "live")
    list_filter = ("applies_to", "subject", "visible", IncludeVoidedFilter)
    search_fields = ("name", "description")
    inlines = (PromptVersionInline,)


@admin.register(models.PromptVersion)
class PromptVersionAdmin(AuditAdmin):
    list_display = ("evaluation_prompt", "version_no", "status", "effective_from", "live")
    list_filter = ("status", "evaluation_prompt", IncludeVoidedFilter)
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
    list_filter = ("question_type", "topic__subject", "difficulty", "visible", IncludeVoidedFilter)
    search_fields = ("name", "question_text", "group", "id_number")
    raw_id_fields = ("topic", "default_prompt_version")
    inlines = (BinaryConfigInline, NumericConfigInline, AttachmentLinkInline)


@admin.register(models.BinaryConfig)
class BinaryConfigAdmin(AuditAdmin):
    list_display = ("question", "expected_value", "live")


@admin.register(models.NumericConfig)
class NumericConfigAdmin(AuditAdmin):
    list_display = ("question", "expected_value", "tolerance_type", "tolerance", "unit", "live")
    list_filter = ("tolerance_type", IncludeVoidedFilter)


class PaperItemInline(admin.TabularInline):
    model = models.PaperItem
    extra = 0
    fields = ("slot", "page", "question", "section_label", "max_mark", "prompt_version", "voided")
    raw_id_fields = ("question", "prompt_version")


@admin.register(models.QuestionPaper)
class QuestionPaperAdmin(AuditAdmin):
    list_display = ("name", "subject", "grade", "purpose", "live")
    list_filter = ("purpose", "subject", "grade", IncludeVoidedFilter)
    search_fields = ("name", "id_number")


@admin.register(models.PaperVersion)
class PaperVersionAdmin(AuditAdmin):
    list_display = (
        "question_paper", "version_no", "status", "total_marks",
        "date_locked", "cloned_from_version", "live",
    )
    list_filter = ("status", IncludeVoidedFilter)
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
        if not access.may_approve_papers(request.user):
            self.message_user(
                request,
                "Locking a paper is an approval, not an edit. It is reserved "
                "for Head of Department, Academic Admin and Admin.",
                messages.ERROR,
            )
            return
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


# ---------------------------------------------------------------------
# Timetable and lessons
# ---------------------------------------------------------------------
@admin.register(models.TimetableSlot)
class TimetableSlotAdmin(AuditAdmin):
    """The weekly pattern. Set once; a swapped day edits the lesson, not this."""

    list_display = ("syllabus", "day_of_week", "period", "start_time", "end_time",
                    "teacher", "live")
    list_filter = ("day_of_week", "syllabus__academic_year", "syllabus__grade",
                   IncludeVoidedFilter)
    search_fields = ("period", "syllabus__subject__short_name")
    raw_id_fields = ("syllabus", "teacher")


class LectureItemInline(admin.TabularInline):
    """The lecture table, for anyone who prefers the admin to My day."""

    model = models.LectureItem
    extra = 0
    fields = ("unit", "chapter", "topic", "attachment", "sort_order", "voided")
    raw_id_fields = ("attachment",)


class LessonTopicInline(admin.TabularInline):
    """What the lesson plans to cover, and what it actually did."""

    model = models.LessonTopic
    extra = 0
    fields = ("topic", "planned", "covered", "carried", "note",
              "sort_order", "voided")
    raw_id_fields = ("topic",)


@admin.register(models.Lesson)
class LessonAdmin(AuditAdmin):
    """
    One class on one date. Drafted by its teacher, approved by a head.

    The two actions below are the review queue: approving is a separate
    act from editing, so a teacher cannot publish their own material.
    """

    list_display = ("date", "period", "syllabus", "teacher", "title",
                    "status", "logged", "time_taught", "covered_pct", "live")
    list_filter = ("status", "date", "syllabus__grade", "syllabus__subject",
                   IncludeVoidedFilter)
    search_fields = ("title", "plan", "log")
    raw_id_fields = ("syllabus", "slot", "teacher", "submitted_by", "reviewed_by")
    date_hierarchy = "date"
    inlines = (LectureItemInline, LessonTopicInline, AttachmentLinkInline)
    actions = AuditAdmin.actions + ("submit_selected", "approve_selected",
                                    "return_selected")
    fieldsets = (
        (None, {"fields": ("syllabus", "slot", "teacher", "date", "period", "title")}),
        ("Plan", {
            "fields": ("plan", "plan_format", "materials_link"),
            "description": "Prepared in advance. This is what the head reviews.",
        }),
        ("After the lesson", {
            "fields": ("log", "log_format", "date_taught",
                       "teaching_seconds", "timer_started_at"),
            "description": "Written up after teaching. An empty date_taught means "
                           "the lesson was never logged.",
        }),
        ("Review", {
            "fields": ("status", "date_submitted", "submitted_by",
                       "date_reviewed", "reviewed_by", "review_comment"),
        }),
        ("Audit", {"fields": AUDIT_FIELDS}),
    )
    readonly_fields = AUDIT_READONLY + (
        "date_submitted", "submitted_by", "date_reviewed", "reviewed_by",
        "materials_link",
    )

    @admin.display(boolean=True, description="Logged")
    def logged(self, obj):
        return obj.is_logged

    @admin.display(description="Time")
    def time_taught(self, obj):
        return obj.elapsed_display if obj.elapsed_seconds else "—"

    @admin.display(description="Topics done")
    def covered_pct(self, obj):
        counts = obj.topic_counts
        return f"{counts['done']}/{counts['total']}" if counts["total"] else "—"

    @admin.display(description="Lecture material")
    def materials_link(self, obj):
        """
        A way out of this form to the upload page.

        The inline below only links to a file that already exists, so it
        is no help to someone holding a slide deck.
        """
        if obj is None or obj.pk is None:
            return "Save the lesson first, then attach files."
        url = reverse("lesson-materials", args=[obj.pk])
        count = obj.attachments.filter(voided=False).count()
        label = f"{count} attached — add or open" if count else "Upload a file"
        return format_html('<a class="button" href="{}">{}</a>', url, label)

    @admin.action(description="Submit selected lessons for review")
    def submit_selected(self, request, queryset):
        count = 0
        for lesson in queryset:
            if lesson.status in (models.LessonStatus.DRAFT,
                                 models.LessonStatus.RETURNED):
                lesson.submit(user=request.user)
                count += 1
        self.message_user(request, f"{count} lesson(s) submitted.", messages.SUCCESS)

    @admin.action(description="Approve selected lessons")
    def approve_selected(self, request, queryset):
        if not access.may_approve_lessons(request.user):
            self.message_user(
                request,
                "Approving a lesson is reserved for Head of Department, "
                "Academic Admin and Admin. A teacher may submit, not approve.",
                messages.ERROR,
            )
            return
        count = 0
        for lesson in queryset:
            if lesson.status != models.LessonStatus.APPROVED:
                lesson.approve(user=request.user)
                count += 1
        self.message_user(request, f"{count} lesson(s) approved.", messages.SUCCESS)

    @admin.action(description="Return selected lessons for changes")
    def return_selected(self, request, queryset):
        if not access.may_approve_lessons(request.user):
            self.message_user(
                request,
                "Returning a lesson is reserved for Head of Department, "
                "Academic Admin and Admin.",
                messages.ERROR,
            )
            return
        count = 0
        for lesson in queryset:
            lesson.return_for_changes(user=request.user)
            count += 1
        self.message_user(
            request,
            f"{count} lesson(s) returned. Open each one to add a reason.",
            messages.SUCCESS,
        )


@admin.register(models.LessonTopic)
class LessonTopicAdmin(AuditAdmin):
    list_display = ("lesson", "topic", "planned", "covered", "carried",
                    "note", "sort_order", "live")
    list_filter = ("planned", "covered", "carried", IncludeVoidedFilter)
    raw_id_fields = ("lesson", "topic")


class HandoutLessonInline(admin.TabularInline):
    """Which lessons this sheet belongs to. Usually one; sometimes a week."""

    model = models.HandoutLesson
    extra = 0
    fields = ("lesson", "sort_order", "voided")
    raw_id_fields = ("lesson",)


@admin.register(models.Handout)
class HandoutAdmin(AuditAdmin):
    """
    A sheet given out in class, and the work handed back from it.

    Most of the work happens on its own page — printing, handing out and
    watching the class hand in — reached from the button below or from
    My day. This form is for the details behind it.
    """

    list_display = ("code", "title", "syllabus", "due_date", "status",
                    "handed_in", "live")
    list_filter = ("status", "is_assignment", "syllabus__grade",
                   "syllabus__subject", IncludeVoidedFilter)
    search_fields = ("code", "title", "instructions")
    raw_id_fields = ("syllabus", "topic", "activated_by")
    date_hierarchy = "due_date"
    inlines = (HandoutLessonInline, AttachmentLinkInline)
    actions = AuditAdmin.actions + ("activate_selected", "close_selected")
    fieldsets = (
        (None, {"fields": ("syllabus", "chapter", "topic_text", "topic",
                           "code", "title", "open_page")}),
        ("The work", {
            "fields": ("instructions", "instructions_format", "is_assignment",
                       "open_from", "due_date", "allow_late", "cutoff_at",
                       "max_marks", "max_rounds"),
            "description": "max_rounds counts the first hand-in. Three means "
                           "one attempt and two redoes.",
        }),
        ("Handing out", {"fields": ("status", "date_activated", "activated_by")}),
        ("Audit", {"fields": AUDIT_FIELDS}),
    )
    readonly_fields = AUDIT_READONLY + ("code", "date_activated", "activated_by",
                                        "open_page")

    @admin.display(description="Handed in")
    def handed_in(self, obj):
        counts = obj.completion()
        return f"{counts['submitted']} / {counts['total']}"

    @admin.display(description="Print, hand out, track")
    def open_page(self, obj):
        if obj is None or obj.pk is None:
            return "Save it first, then attach the sheet and hand it out."
        return format_html(
            '<a class="button" href="{}">Open the handout page</a>',
            reverse("handout", args=[obj.pk]),
        )

    @admin.action(description="Hand out to the class")
    def activate_selected(self, request, queryset):
        count = 0
        for handout in queryset:
            if handout.status != models.HandoutStatus.ACTIVE:
                handout.activate(user=request.user)
                count += 1
        self.message_user(
            request, f"{count} handout(s) are now open to students.", messages.SUCCESS
        )

    @admin.action(description="Close — no more work accepted")
    def close_selected(self, request, queryset):
        count = 0
        for handout in queryset:
            handout.close(user=request.user)
            count += 1
        self.message_user(request, f"{count} handout(s) closed.", messages.SUCCESS)


@admin.register(models.HandoutLesson)
class HandoutLessonAdmin(AuditAdmin):
    list_display = ("handout", "lesson", "sort_order", "live")
    raw_id_fields = ("handout", "lesson")


@admin.register(models.HandoutSheet)
class HandoutSheetAdmin(AuditAdmin):
    """Each version of a sheet, and when it was replaced."""

    list_display = ("handout", "version_no", "attachment", "replaced_on",
                    "note", "live")
    list_filter = (IncludeVoidedFilter,)
    raw_id_fields = ("handout", "attachment")
    readonly_fields = AUDIT_READONLY + ("replaced_on",)


@admin.register(models.HandoutExtension)
class HandoutExtensionAdmin(AuditAdmin):
    """A later deadline for one student. Same handout, same marks column."""

    list_display = ("handout", "student_name", "extended_to", "reason", "live")
    list_filter = (IncludeVoidedFilter,)
    search_fields = ("handout__code", "enrolment__student__first_name",
                     "enrolment__student__last_name")
    raw_id_fields = ("handout", "enrolment", "granted_by")

    @admin.display(description="Student")
    def student_name(self, obj):
        return obj.enrolment.student.full_name


@admin.register(models.Submission)
class SubmissionAdmin(AuditAdmin):
    """
    One student's work for one handout, in one round.

    Append-only in spirit: a redo is a new row, never an edit of the last
    one, so "right first time" survives as a fact about the student.
    """

    list_display = ("code", "student_name", "handout", "round_no", "sheet_version",
                    "state", "late", "awarded_marks", "time_submitted", "live")
    list_filter = ("state", "round_no", "handout__syllabus__grade",
                   IncludeVoidedFilter)
    search_fields = ("code", "enrolment__student__first_name",
                     "enrolment__student__last_name",
                     "enrolment__student__admission_no")
    raw_id_fields = ("handout", "enrolment", "marked_by")
    date_hierarchy = "time_submitted"
    inlines = (AttachmentLinkInline,)
    readonly_fields = AUDIT_READONLY + ("code", "time_submitted")

    @admin.display(description="Student", ordering="enrolment__student__last_name")
    def student_name(self, obj):
        return obj.enrolment.student.full_name

    @admin.display(description="Late")
    def late(self, obj):
        if not obj.is_late:
            return "—"
        hours, minutes = divmod(obj.minutes_late, 60)
        return f"{hours}h {minutes:02d}m" if hours else f"{minutes}m"


@admin.register(models.PaperItem)
class PaperItemAdmin(AuditAdmin):
    list_display = ("paper_version", "slot", "question", "max_mark", "prompt_version", "live")
    list_filter = ("paper_version__status", IncludeVoidedFilter)
    raw_id_fields = ("paper_version", "question", "prompt_version")


class CohortMembershipInline(admin.TabularInline):
    model = models.CohortMembership
    extra = 0
    raw_id_fields = ("enrolment",)
    fields = ("enrolment", "voided")


@admin.register(models.StudentCohort)
class StudentCohortAdmin(AuditAdmin):
    list_display = ("name", "grade", "academic_year", "purpose", "is_temporary", "live")
    list_filter = ("purpose", "grade", "academic_year", "is_temporary", IncludeVoidedFilter)
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
    list_filter = ("grade", "academic_year", "marking_method", "is_practice", IncludeVoidedFilter)
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
    list_filter = ("state", "is_counted", "preview", IncludeVoidedFilter)
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
    list_filter = ("method", "is_correct", IncludeVoidedFilter)
    raw_id_fields = ("answer", "prompt_version", "supersedes")

    def has_change_permission(self, request, obj=None):
        """Marking is append-only: corrections are new rows."""
        return obj is None


@admin.register(models.RetentionPolicy)
class RetentionPolicyAdmin(AuditAdmin):
    list_display = ("target_table", "void_retention_days", "purge_enabled", "live")
    list_filter = ("purge_enabled", IncludeVoidedFilter)
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
    list_filter = ("kind", IncludeVoidedFilter)
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
    list_filter = ("role", "content_type", IncludeVoidedFilter)
    raw_id_fields = ("attachment",)


@admin.register(models.UploadSession)
class UploadSessionAdmin(AuditAdmin):
    list_display = ("filename", "state", "received", "declared_size", "attachment", "date_created")
    list_filter = ("state", IncludeVoidedFilter)
    readonly_fields = AUDIT_READONLY + ("filename", "mime_type", "declared_size", "received", "attachment")

    def has_add_permission(self, request):
        return False


# ---------------------------------------------------------------------
# Guardians and attendance
# ---------------------------------------------------------------------
@admin.register(models.GuardianLink)
class GuardianLinkAdmin(AuditAdmin):
    list_display = ("student", "user", "relationship", "is_primary", "can_view_marks", "live")
    list_filter = ("relationship", "is_primary", IncludeVoidedFilter)
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
    list_filter = ("grade", "academic_year", "period", "is_finalised", IncludeVoidedFilter)
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
    list_filter = ("status", "session__grade", "session__academic_year", IncludeVoidedFilter)
    search_fields = ("enrolment__student__first_name", "enrolment__student__last_name")
    raw_id_fields = ("session", "enrolment")

    @admin.display(description="Student", ordering="enrolment__student__last_name")
    def student_name(self, obj):
        return shorten(str(obj.enrolment.student))


# ---------------------------------------------------------------------
# The notice board, and the marking service's record of its own work
# ---------------------------------------------------------------------
@admin.register(models.Notice)
class NoticeAdmin(AuditAdmin):
    list_display = ("title", "category", "grade", "academic_year",
                    "date_posted", "posted_by", "live")
    list_filter = ("category", "grade", "academic_year", IncludeVoidedFilter)
    search_fields = ("title", "body")
    raw_id_fields = ("posted_by",)
    date_hierarchy = "date_posted"

    fieldsets = (
        (None, {"fields": ("title", "category", "grade", "academic_year", "body")}),
        ("When it shows", {
            "fields": ("published_from", "published_until"),
            "description": "Both optional. Empty means from now, and forever.",
        }),
        ("Who posted it", {"fields": ("posted_by", "date_posted")}),
    )


@admin.register(models.AutogradeJob)
class AutogradeJobAdmin(AuditAdmin):
    """
    A record of what the marking service was asked and what it returned.

    Read-only on purpose. A mark is corrected by editing the mark line —
    which records the person who changed it — never by rewriting what the
    machine said it found. Keeping the two apart is what makes a disputed
    mark answerable months later.
    """

    list_display = ("submission", "status", "confidence", "requested_at",
                    "completed_at", "service_ref")
    list_filter = ("status", IncludeVoidedFilter)
    search_fields = ("submission__code", "service_ref")
    raw_id_fields = ("submission",)
    readonly_fields = AUDIT_READONLY + (
        "submission", "status", "service_ref", "requested_at", "completed_at",
        "confidence", "raw_response", "error",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
