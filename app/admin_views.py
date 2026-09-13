"""
Admin pages that are not tied to one model.

  * Demo      — loads or removes the demo school. It runs the same
                `seed_demo` management command the terminal does, so the
                button and the command can never behave differently.
  * My day    — a teacher's own screen: today's lessons and what to do
                with them. The model lists are a filing cabinet; this is
                the page someone actually opens at 7.40am.
  * Materials — upload lecture material straight onto a lesson. The
                admin's own inline only *links* to a file that already
                exists, which is no use to someone holding a slide deck.
  * Handout   — print it, hand it out, and watch the work come back.
  * My work   — the student's side: what is open, and handing it in.
  * Subjects  — everything a teacher teaches, in one list, with what is
                prepared ahead of today.
  * Checking  — the examiner's side: work waiting to be checked, and the
                screen for handing back the checked version.
"""

from datetime import date, datetime, timedelta
from io import StringIO

from django.contrib import messages
from decimal import Decimal, InvalidOperation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.core.management import call_command
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils import timezone

from . import access, demo_data, files as app_files, grading, models


def _current_year():
    """
    The academic year as the school writes it.

    The session runs 1 July to 30 June and is named for both calendar
    years it touches: 2026-27 is 2627. Derived from the clock rather than
    stored in a setting, so nobody has to remember to change it in July.
    """
    today = timezone.localdate()
    start = today.year if today.month >= 7 else today.year - 1
    return int(f"{start % 100:02d}{(start + 1) % 100:02d}")


def _counts(year):
    prefix = demo_data.PREFIX
    students = models.Student.objects.filter(admission_no__startswith=prefix)
    teachers = models.Teacher.objects.filter(staff_no__startswith=prefix)
    return {
        "teachers": teachers.count(),
        "students": students.count(),
        "enrolments": models.Enrolment.objects.filter(
            student__in=students, academic_year=year
        ).count(),
        "choices": models.StudentSubject.objects.filter(
            enrolment__student__in=students
        ).count(),
        "assignments": models.TeachingAssignment.objects.filter(
            teacher__in=teachers
        ).count(),
        "marks": models.TopicResult.objects.filter(
            student_subject__enrolment__student__in=students
        ).count(),
    }


def _plan(year):
    """What the demo will look like, grade by grade."""
    rows = []
    for grade in models.Grade.objects.order_by("sort_order"):
        students = [s for s in demo_data.STUDENTS if s["grade"] == grade.short_name]
        syllabi = models.Syllabus.objects.filter(grade=grade, academic_year=year)
        core = syllabi.filter(is_core=True).count()
        if grade.is_terminal:
            spread = sorted({core + len(s.get("electives", [])) for s in students})
            subjects = f"{core} core + electives ({'–'.join(str(n) for n in (spread[0], spread[-1]))} total)"
        else:
            subjects = f"{core} core"
        rows.append({
            "grade": f"{grade.short_name} — {grade.full_name}",
            "students": len(students),
            "subjects": subjects,
        })
    return rows


# ---------------------------------------------------------------------
# Who may open the staff screens
# ---------------------------------------------------------------------
def _may_open_teaching_screens(user):
    """
    Whether this account may open the teacher-facing pages.

    Every account in the system carries `is_staff`, students included:
    the whole interface lives under /admin/ and Django's admin login
    refuses anyone without it. So `admin.site.admin_view()` is a door
    key, not a rank — it lets any signed-in account reach these URLs by
    typing them, and these pages show a whole class's lessons, its
    answer schemes and every student's hand-in.

    What holds a student to their own rows on the model lists is
    `access.scope_queryset`; these pages are not model lists, so the
    same job is done here, by role.
    """
    return (
        user.is_superuser
        or access.has_role(
            user, access.TEACHING_STAFF, access.HEAD_OF_DEPARTMENT,
            access.ACADEMIC_ADMIN, access.ADMIN,
        )
    )


def demo_view(request, admin_site):
    # Loading or removing the demo school rewrites data. Held to the
    # accounts that may create students in the first place.
    if not request.user.has_perm("app.add_student"):
        raise PermissionDenied

    year = int(request.POST.get("year") or request.GET.get("year") or date.today().year)

    if request.method == "POST":
        action = request.POST.get("action")
        output = StringIO()
        try:
            if action == "remove":
                call_command("seed_demo", year=year, remove=True, stdout=output)
                messages.success(request, "Demo data removed. " + _summarise(output))
            else:
                call_command("seed_demo", year=year, stdout=output)
                messages.success(request, "Demo data loaded. " + _summarise(output))
        except Exception as exc:                      # surfaced, not swallowed
            messages.error(request, str(exc))
        return redirect("{}?year={}".format(reverse("demo"), year))

    context = {
        **admin_site.each_context(request),
        "title": "Demo data",
        "year": year,
        "counts": _counts(year),
        "loaded": _counts(year)["students"] > 0,
        "curriculum_ready": models.Syllabus.objects.filter(academic_year=year).exists(),
        "plan": _plan(year),
        "demo_password": demo_data.DEMO_PASSWORD,
    }
    return TemplateResponse(request, "admin/demo.html", context)


def _summarise(output):
    lines = [line.strip() for line in output.getvalue().splitlines() if line.strip()]
    return ", ".join(" ".join(line.split()) for line in lines) or "nothing to do."


# ---------------------------------------------------------------------
# My day
# ---------------------------------------------------------------------
def _teacher_for(user):
    return models.Teacher.objects.filter(user=user, voided=False).first()


def _lessons_for(user, teacher, start, end):
    """
    A teacher's lessons between two dates.

    Matched on the lesson's own teacher, or on the slot's usual teacher
    when the lesson does not name one — which is the ordinary case, since
    a lesson only names a teacher when someone is covering.

    A user with no Teacher record (an owner looking at the page, say) sees
    every lesson rather than an empty screen.
    """
    lessons = (
        models.Lesson.objects
        .filter(voided=False, date__gte=start, date__lte=end)
        .select_related("syllabus", "syllabus__subject", "syllabus__grade",
                        "teacher", "slot", "slot__teacher")
        .prefetch_related(
            "topics__topic", "attachments__attachment",
            "handouts__handout__syllabus", "lecture_items__attachment",
        )
        .order_by("date", "period")
    )
    if teacher is None:
        return lessons
    from django.db.models import Q
    return lessons.filter(
        # Theirs by name, or theirs because the weekly slot is theirs...
        Q(teacher=teacher)
        | Q(teacher__isnull=True, slot__teacher=teacher)
        # ...or nobody's yet. A lesson with no teacher and no slot would
        # otherwise be invisible to everyone, which is worse than showing
        # it to whoever is looking: it is exactly the lesson someone needs
        # to notice and claim.
        | Q(teacher__isnull=True, slot__isnull=True)
        | Q(teacher__isnull=True, slot__teacher__isnull=True)
    )


def _covered_topic_ids(lesson):
    """Topics already ticked on this lesson, parents and children alike."""
    return {
        entry.topic_id for entry in lesson.topics.all()
        if entry.covered and not entry.voided
    }


def _topic_rows(lesson, handouts):
    """
    One row per planned topic: its notes, its handouts, and its children.

    Topics nest already, so a topic with children offers them as ticks and
    a topic without one just takes a percentage. Nothing forces sub-topics
    on anyone, and starting to use them later needs no change here.
    """
    rows = []
    done = _covered_topic_ids(lesson)
    for entry in lesson.topics.all():
        if entry.voided or not entry.planned:
            continue
        topic = entry.topic
        rows.append({
            "entry": entry,
            "topic": topic,
            "materials": [
                {
                    "name": a.title or a.original_filename,
                    "url": a.file.url if a.file else "",
                    "kind": a.get_kind_display(),
                    "size": a.size_display,
                }
                for a in entry.materials()
            ],
            "handouts": [h for h in handouts if h["handout"].topic_id == topic.id],
            "children": [
                {"topic": child, "done": child.id in done}
                for child in topic.children.filter(voided=False)
                                   .order_by("sort_order", "short_name")
            ],
            "summary": topic.teaching_summary(lesson.syllabus),
            "add_url": "{}?topic={}".format(
                reverse("lesson-materials", args=[lesson.pk]), entry.pk
            ),
            "carried": entry.carried,
        })
    return rows


def _lecture_rows(lesson):
    """The lecture table: one dict per row, ready to render or edit."""
    rows = []
    for item in lesson.lecture_items.filter(voided=False).select_related("attachment"):
        attachment = item.attachment
        rows.append({
            "item": item,
            "file_name": (
                attachment.title or attachment.original_filename
            ) if attachment else "",
            "file_url": attachment.file.url if attachment and attachment.file else "",
            "file_size": attachment.size_display if attachment else "",
        })
    return rows


def _assignment_rows(lesson):
    """The assignment table: one row per handout set for this lesson."""
    rows = []
    for link in lesson.handouts.filter(voided=False).select_related("handout"):
        handout = link.handout
        if handout is None or handout.voided:
            continue
        sheet = _handout_files(handout, "handout")
        scheme = _handout_files(handout, "scheme")
        # Three states, and the time decides the third one. A handout is
        # posted until its due date passes, at which point it reads as
        # closed without anyone having to remember to close it.
        # Four states. Past the due date the handout is closed, unless the
        # teacher deliberately left a late window open — which reads as
        # "overridden", because that is what it is: the deadline stood, and
        # someone chose to keep taking work anyway.
        if handout.status != models.HandoutStatus.ACTIVE:
            post_state = "closed" if handout.status == models.HandoutStatus.CLOSED \
                else "unposted"
        elif not handout.is_past_due:
            post_state = "posted"
        elif handout.late_window_open:
            post_state = "overridden"
        else:
            post_state = "closed"

        rows.append({
            "handout": handout,
            "post_state": post_state,
            "can_unpost": handout.can_unpost,
            "late_open": handout.late_window_open,
            "sheet_version": handout.sheet_version_no,
            "sheets": handout.sheets.filter(voided=False).count(),
            "extensions": handout.extensions.filter(voided=False).count(),
            "extend_url": reverse("handout-extend", args=[handout.pk]),
            "url": reverse("handout", args=[handout.pk]),
            "sheet": sheet,
            "scheme": scheme,
            "scheme_name": scheme[0]["name"] if scheme else "",
            "scheme_url": scheme[0]["url"] if scheme else "",
            "file_name": sheet[0]["name"] if sheet else "",
            "file_url": sheet[0]["url"] if sheet else "",
            "file_size": sheet[0]["size"] if sheet else "",
            "completion": handout.completion(),
        })
    return rows


def _lecture_defaults(lesson):
    """
    What a new assignment should start with.

    A handout almost always belongs to whatever the lecture table's first
    line says, and the teacher has already typed it once. Carrying it over
    is the difference between filling a form in and confirming it.
    """
    first = lesson.lecture_items.filter(voided=False).first()
    if first is None:
        return {"unit": "", "chapter": "", "topic": ""}
    return {
        "unit": first.unit,
        # The assignment table's Chapter column takes whichever of the two
        # is filled in, because a teacher who only wrote a unit means that
        # to be the heading.
        "chapter": first.chapter or first.unit,
        "topic": first.topic,
    }


def _decorate(lesson):
    """Everything the template needs about one lesson, worked out here."""
    topics = [t for t in lesson.topics.all() if not t.voided]
    return {
        "lesson": lesson,
        "url": reverse("admin:app_lesson_change", args=[lesson.pk]),
        "materials_url": reverse("lesson-materials", args=[lesson.pk]),
        "new_handout_url": reverse("new-handout", args=[lesson.pk]),
        "handouts": [
            {
                "handout": hl.handout,
                "url": reverse("handout", args=[hl.handout_id]),
                "completion": hl.handout.completion(),
                "sheet": _handout_files(hl.handout, "handout"),
            }
            for hl in lesson.handouts.all()
            if not hl.voided and hl.handout_id and not hl.handout.voided
        ],
        "subject": lesson.syllabus.subject,
        "grade": lesson.syllabus.grade,
        "topics": topics,
        "planned": [t for t in topics if t.planned],
        "uncovered": [t for t in topics if t.planned and not t.covered],
        # Lecture material, ready to open. `file.url` is served by
        # MEDIA_URL, so a PDF opens in the browser and a PowerPoint or Word
        # file downloads and opens in whatever the teacher has installed.
        "materials": [
            {
                "attachment": link.attachment,
                "name": link.attachment.title or link.attachment.original_filename,
                "url": link.attachment.file.url if link.attachment.file else "",
                "kind": link.attachment.get_kind_display(),
                "size": link.attachment.size_display,
                "role": link.role,
            }
            for link in lesson.attachments.all()
            if not link.voided and link.attachment is not None
        ],
        "lecture_rows": _lecture_rows(lesson),
        "assignment_rows": _assignment_rows(lesson),
        "defaults": _lecture_defaults(lesson),
        "topic_rows": None,          # filled in below, once handouts are known
        "unfinished": lesson.unfinished_topics(),
        "next_lesson": lesson.next_lesson(),
        "timer_running": lesson.timer_running,
        "elapsed": lesson.elapsed_display,
        "elapsed_seconds": lesson.elapsed_seconds,
        # Read from the lesson rather than deduced. Deducing it made a
        # pause after an ended class look like an end.
        "timer_state": lesson.timer_status,
        "counts": lesson.topic_counts,
        # Taught and written up: it folds away, so the day's remaining
        # work stays prominent. Everything else stays open.
        "finished": bool(lesson.date_taught) and lesson.timer_status == "ended",
        "needs_plan": not lesson.plan.strip(),
        "needs_log": lesson.date <= timezone.localdate() and not lesson.date_taught,
        "awaiting_review": lesson.status == models.LessonStatus.SUBMITTED,
        "returned": lesson.status == models.LessonStatus.RETURNED,
    }


def _decorate_full(lesson):
    """A lesson card with its topic rows filled in."""
    row = _decorate(lesson)
    row["topic_rows"] = _topic_rows(lesson, row["handouts"])
    return row


def my_day_view(request, admin_site):
    """
    Today, then the rest of this week, then what needs attention.

    Deliberately not a filterable list. A teacher arriving in the morning
    wants their day and the three things they have not done, not a table
    of every lesson in the school.

    The timer and the log are posted back here rather than living on a
    separate page, because both happen with the class in front of you.
    """
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    if request.method == "POST":
        return _my_day_post(request)

    today = timezone.localdate()
    day_offset = int(request.GET.get("offset") or 0)
    day = today + timedelta(days=day_offset)

    teacher = _teacher_for(request.user)
    week_start = day - timedelta(days=day.weekday())
    week_end = week_start + timedelta(days=6)

    week = list(_lessons_for(request.user, teacher, week_start, week_end))
    today_rows = [_decorate_full(l) for l in week if l.date == day]

    upcoming = [_decorate(l) for l in week if l.date > day]

    # Anything still to do, looking back a fortnight as well as forward.
    window = _lessons_for(
        request.user, teacher, today - timedelta(days=14), today + timedelta(days=14)
    )
    attention = []
    for lesson in window:
        row = _decorate(lesson)
        if row["needs_log"] or row["returned"] or (
            lesson.date > today and row["needs_plan"]
        ):
            attention.append(row)

    context = {
        **admin_site.each_context(request),
        "title": "My day",
        "day": day,
        "today": today,
        "is_today": day == today,
        "offset": day_offset,
        "prev_offset": day_offset - 1,
        "next_offset": day_offset + 1,
        "teacher": teacher,
        "no_teacher_record": teacher is None,
        "today_rows": today_rows,
        "upcoming": upcoming,
        "now": timezone.now(),
        # Which card just had something happen, and what. The banner is
        # drawn inside that card: a confirmation at the top of the page is
        # no use to someone looking at a button near the bottom.
        "flash_lesson": request.GET.get("done"),
        "flash_kind": request.GET.get("kind", ""),
        "attention": attention,
        "may_approve": access.may_approve_lessons(request.user),
        # A teaching-only account is sent here from /admin/, so this page
        # *is* their home. Showing a "Home" crumb that lands them back on
        # the same page is a link that does nothing.
        "is_home": (
            access.TEACHING_STAFF in access.role_names(request.user)
            and not request.user.is_superuser
            and not (access.role_names(request.user) & {
                access.ADMIN, access.ACADEMIC_ADMIN,
                access.IT_ADMIN, access.HEAD_OF_DEPARTMENT,
            })
        ),
        "lesson_list_url": reverse("admin:app_lesson_changelist"),
        "add_lesson_url": reverse("admin:app_lesson_add"),
        "add_handout_url": reverse("admin:app_handout_add"),
    }
    return TemplateResponse(request, "admin/my_day.html", context)


# ---------------------------------------------------------------------
# Lesson materials
# ---------------------------------------------------------------------
def lesson_materials_view(request, lesson_id, admin_site):
    """
    Upload lecture material onto one lesson, or onto one of its topics.

    The admin's attachment inline asks for the id of a file that already
    exists, so attaching a slide deck means creating it on another screen
    first and coming back. A teacher holding a PowerPoint should choose it
    and be done, which is all this page is.

    `?topic=<lesson topic id>` narrows it to one topic, so notes can sit
    with the topic they explain rather than in one pile on the lesson.

    Storing a file twice is avoided by checksum, the same way the API
    does it: the same bytes reuse the row already there.
    """
    lesson = get_object_or_404(models.Lesson, pk=lesson_id)

    if not request.user.has_perm("app.change_lesson"):
        raise PermissionDenied

    entry_id = request.POST.get("entry") or request.GET.get("topic")
    entry = None
    if entry_id:
        entry = lesson.topics.filter(pk=entry_id, voided=False).first()

    target = entry or lesson
    back = reverse("lesson-materials", args=[lesson.pk])
    if entry:
        back = f"{back}?topic={entry.pk}"

    if request.method == "POST":
        uploads = request.FILES.getlist("files")
        if not uploads:
            messages.error(request, "No file was chosen.")
            return redirect(back)

        content_type = ContentType.objects.get_for_model(type(target))
        added = 0
        for upload in uploads:
            checksum = app_files.sha256_of(upload)
            attachment = models.Attachment.objects.filter(
                checksum=checksum, voided=False
            ).first()

            if attachment is None:
                mime = getattr(upload, "content_type", "") or ""
                attachment = models.Attachment(
                    original_filename=upload.name,
                    mime_type=mime,
                    kind=app_files.classify(mime, upload.name),
                    size_bytes=upload.size,
                    checksum=checksum,
                    title=request.POST.get("title", "") or "",
                )
                attachment.file.save(upload.name, upload, save=False)
                attachment.save()

            link, created = models.AttachmentLink.objects.get_or_create(
                attachment=attachment,
                content_type=content_type,
                object_id=target.pk,
                voided=False,
                defaults={"role": request.POST.get("role") or "material"},
            )
            if created:
                added += 1

        where = f"“{entry.topic}”" if entry else "this lesson"
        messages.success(
            request,
            f"{added} file(s) attached to {where}."
            if added else "That file was already attached.",
        )
        return redirect(back)

    content_type = ContentType.objects.get_for_model(type(target))
    links = (
        models.AttachmentLink.objects
        .filter(content_type=content_type, object_id=target.pk, voided=False)
        .select_related("attachment")
        .order_by("sort_order", "id")
    )
    context = {
        **admin_site.each_context(request),
        "title": f"Materials — {lesson}",
        "lesson": lesson,
        "entry": entry,
        "topics": [
            {
                "entry": e,
                "count": len(e.materials()),
                "url": "{}?topic={}".format(
                    reverse("lesson-materials", args=[lesson.pk]), e.pk
                ),
            }
            for e in lesson.topics.filter(voided=False).select_related("topic")
        ],
        "lesson_only_url": reverse("lesson-materials", args=[lesson.pk]),
        "lesson_url": reverse("admin:app_lesson_change", args=[lesson.pk]),
        "materials": [
            {
                "link": link,
                "attachment": link.attachment,
                "name": link.attachment.title or link.attachment.original_filename,
                "url": link.attachment.file.url if link.attachment.file else "",
                "kind": link.attachment.get_kind_display(),
                "size": link.attachment.size_display,
            }
            for link in links if link.attachment is not None
        ],
        "my_day_url": reverse("my-day"),
    }
    return TemplateResponse(request, "admin/lesson_materials.html", context)


# ---------------------------------------------------------------------
# Handouts — printing, handing out, and watching work come back
# ---------------------------------------------------------------------
def _moment(raw):
    """Read a datetime-local field, or None."""
    raw = (raw or "").strip()
    if not raw:
        return None
    try:
        return timezone.make_aware(
            datetime.fromisoformat(raw), timezone.get_current_timezone()
        )
    except ValueError:
        return None


def _link_file(handout, attachment, role):
    """
    Attach one file to a handout in one role, and say whether that is new.

    The role belongs in the lookup. Without it, a file already attached as
    the answer scheme counted as "already linked" when the same file was
    then added as the sheet, so the sheet silently stayed empty. A file may
    legitimately hold both roles, and the two are found separately.

    A link that was removed earlier is revived rather than duplicated,
    which also restores `active_flag` — the column the unique constraint
    relies on.
    """
    content_type = ContentType.objects.get_for_model(models.Handout)
    link = models.AttachmentLink.all_objects.filter(
        attachment=attachment, content_type=content_type,
        object_id=handout.pk, role=role,
    ).order_by("-id").first()
    if link is None:
        models.AttachmentLink.objects.create(
            attachment=attachment, content_type=content_type,
            object_id=handout.pk, role=role,
        )
        return True
    if link.voided:
        link.unvoid()
        return True
    return False


def _set_sheet(handout, attachment, note=""):
    """
    Make this file the handout's sheet, as a new version.

    The link students follow always points at the current version; the
    one it replaced is kept, so a submission that answered version 1
    still refers to the paper it was actually given.
    """
    handout.add_sheet(attachment, note=note)
    content_type = ContentType.objects.get_for_model(models.Handout)
    # Voided one row at a time on purpose. A bulk update() skips save(),
    # which is where active_flag is cleared, and a voided row that keeps
    # its active_flag still occupies the unique key — so the same file
    # could never be attached again.
    for link in models.AttachmentLink.objects.filter(
        content_type=content_type, object_id=handout.pk,
        role="handout", voided=False,
    ).exclude(attachment=attachment):
        link.void(reason="replaced by a newer sheet")
    _link_file(handout, attachment, "handout")


def _detach_file(handout, attachment_id, role):
    """
    Take one file off a handout.

    The file itself is kept — it may be attached elsewhere, and a
    submission may point at the sheet version that used it. Only the link
    goes, and with the sheet, the version record that named it.
    """
    content_type = ContentType.objects.get_for_model(models.Handout)
    link = models.AttachmentLink.objects.filter(
        attachment_id=attachment_id, content_type=content_type,
        object_id=handout.pk, role=role, voided=False,
    ).first()
    if link is None:
        return None
    name = link.attachment.title or link.attachment.original_filename
    link.void(reason="removed by a teacher")
    if role == "handout":
        for sheet in handout.sheets.filter(
            attachment_id=attachment_id, voided=False, replaced_on__isnull=True
        ):
            sheet.void(reason="sheet removed")
    return name


def _viewable(attachment):
    """
    One file, described well enough to be *shown* rather than only linked.

    The checking screen puts the script and the mark scheme in panes side
    by side, which means knowing whether a file is a PDF the browser can
    render or a picture that needs an <img>. Judged from the MIME type with
    the extension as a fallback, the same way app/files.py classifies
    everything else — browsers send an empty or wrong MIME type often
    enough that the extension has to be a real fallback.
    """
    name = attachment.title or attachment.original_filename
    lower = (attachment.original_filename or "").lower()
    mime = (attachment.mime_type or "").lower()
    return {
        "attachment": attachment,
        "name": name,
        "url": attachment.file.url if attachment.file else "",
        "kind": attachment.get_kind_display(),
        "size": attachment.size_display,
        "is_pdf": mime == "application/pdf" or lower.endswith(".pdf"),
        "is_image": (
            mime.startswith("image/") or attachment.kind == app_files.FileKind.PICTURE
        ),
    }


def _handout_files(handout, role="handout"):
    return [
        _viewable(link.attachment)
        for link in handout.attachments.all()
        if not link.voided and link.attachment_id and link.role == role
    ]


def handout_view(request, handout_id, admin_site):
    """
    One handout: its sheet, how many copies to print, and who has handed in.

    Copies are identical — nothing on the page names a student — so the
    print step is only "how many". Whose work it is comes from the
    submission's own code, stamped when it arrives.
    """
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    handout = get_object_or_404(models.Handout, pk=handout_id)

    if request.method == "POST":
        action = request.POST.get("action")

        if action == "request_redo":
            # Resubmission happens only when a teacher asks for it on one
            # student's work. Nothing returns automatically.
            submission = models.Submission.objects.filter(
                pk=request.POST.get("submission"), voided=False
            ).first()
            if submission is None:
                messages.error(request, "That submission could not be found.")
            elif not request.user.has_perm("app.change_submission"):
                raise PermissionDenied
            else:
                submission.request_redo(
                    user=request.user,
                    reason=(request.POST.get("reason") or "").strip()[:255],
                )
                messages.success(
                    request,
                    f"{submission.enrolment.student.full_name} has been asked to "
                    "do this again. It is back in their My work.",
                )
            return redirect(reverse("handout", args=[handout.pk]))

        if action == "detach":
            if not request.user.has_perm("app.change_handout"):
                raise PermissionDenied
            role = request.POST.get("role") or "handout"
            name = _detach_file(handout, request.POST.get("attachment"), role)
            if name is None:
                messages.error(request, "That file is not attached to this handout.")
            elif role == "handout":
                messages.success(
                    request,
                    f"{name} removed. There is no sheet on this handout now — "
                    "attach one before handing it out.",
                )
            else:
                messages.success(request, f"{name} removed from the mark scheme.")
            return redirect(reverse("handout", args=[handout.pk]))

        if action == "activate":
            if not request.user.has_perm("app.change_handout"):
                raise PermissionDenied
            handout.activate(user=request.user)
            messages.success(
                request,
                f"{handout.code} handed out. It is now open in the students' accounts.",
            )
        elif action == "close":
            if not request.user.has_perm("app.change_handout"):
                raise PermissionDenied
            handout.close(user=request.user)
            messages.success(request, f"{handout.code} closed. No more work accepted.")
        elif action == "upload":
            if not request.user.has_perm("app.change_handout"):
                raise PermissionDenied
            role = request.POST.get("role") or "handout"
            uploads = request.FILES.getlist("files")
            content_type = ContentType.objects.get_for_model(models.Handout)
            names = []
            for upload in uploads:
                checksum = app_files.sha256_of(upload)
                attachment = models.Attachment.objects.filter(
                    checksum=checksum, voided=False
                ).first()
                if attachment is None:
                    mime = getattr(upload, "content_type", "") or ""
                    attachment = models.Attachment(
                        original_filename=upload.name, mime_type=mime,
                        kind=app_files.classify(mime, upload.name),
                        size_bytes=upload.size, checksum=checksum,
                    )
                    attachment.file.save(upload.name, upload, save=False)
                    attachment.save()
                if role == "handout":
                    _set_sheet(handout, attachment,
                               note=(request.POST.get("note") or "").strip()[:255])
                    names.append(attachment.title or attachment.original_filename)
                else:
                    _link_file(handout, attachment, role)
                    names.append(attachment.title or attachment.original_filename)
            if names and role == "handout":
                messages.success(
                    request,
                    "{} is now the sheet students get (version {}).".format(
                        names[-1], handout.sheet_version_no
                    ),
                )
            elif names:
                messages.success(
                    request,
                    "{} attached as the mark scheme. Students never see it.".format(
                        ", ".join(names)
                    ),
                )
            else:
                messages.error(request, "No file was chosen, so nothing was attached.")
        return redirect(reverse("handout", args=[handout.pk]))

    submissions = (
        models.Submission.objects
        .filter(handout=handout, voided=False)
        .select_related("enrolment", "enrolment__student")
        .order_by("enrolment__student__last_name", "round_no")
    )
    by_enrolment = {}
    for submission in submissions:
        by_enrolment.setdefault(submission.enrolment_id, []).append(submission)

    extensions = {
        e.enrolment_id: e for e in handout.extensions.filter(voided=False)
    }

    roll = []
    for enrolment in handout.enrolments().order_by(
        "student__last_name", "student__first_name"
    ):
        rounds = by_enrolment.get(enrolment.id, [])
        latest = rounds[-1] if rounds else None
        extension = extensions.get(enrolment.id)

        # On time, late, or nothing yet. Late only ever appears where the
        # teacher left a late window open or granted an extension — with a
        # hard close, work is simply refused rather than accepted late.
        if latest is None:
            timing = "missing"
        elif latest.is_late:
            timing = "late"
        else:
            timing = "ontime"

        roll.append({
            "enrolment": enrolment,
            "student": enrolment.student,
            "rounds": rounds,
            "latest": latest,
            "handed_in": bool(rounds),
            "timing": timing,
            "extension": extension,
            "checked": [
                {
                    "name": a.title or a.original_filename,
                    "url": a.file.url if a.file else "",
                }
                for a in (latest.checked_files() if latest else [])
            ],
        })

    context = {
        **admin_site.each_context(request),
        "title": f"{handout.code} — {handout.title}",
        "handout": handout,
        "sheet": _handout_files(handout, "handout"),
        "scheme": _handout_files(handout, "scheme"),
        "versions": [
            {
                "sheet": sheet,
                "name": sheet.attachment.title or sheet.attachment.original_filename,
                "url": sheet.attachment.file.url if sheet.attachment.file else "",
            }
            for sheet in handout.sheets.filter(voided=False).order_by("-version_no")
        ],
        "completion": handout.completion(),
        "roll": roll,
        "may_change": request.user.has_perm("app.change_handout"),
        "admin_url": reverse("admin:app_handout_change", args=[handout.pk]),
        "print_url": reverse("handout-print", args=[handout.pk]),
        "my_day_url": reverse("my-day"),
    }
    return TemplateResponse(request, "admin/handout.html", context)


def handout_print_view(request, handout_id, admin_site):
    """
    A cover sheet to print with the copies.

    The sheet itself is whatever file the teacher attached, printed from
    whatever opens it. This page carries the handout's code, the class,
    the due date and the instructions — the things a student needs in
    order to hand the right work back.
    """
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    handout = get_object_or_404(models.Handout, pk=handout_id)
    copies = handout.completion()["total"] or 0
    context = {
        **admin_site.each_context(request),
        "title": f"Print — {handout.code}",
        "handout": handout,
        "sheet": _handout_files(handout, "handout"),
        "copies": copies,
        "back_url": reverse("handout", args=[handout.pk]),
    }
    return TemplateResponse(request, "admin/handout_print.html", context)


# ---------------------------------------------------------------------
# My work — the student's side
# ---------------------------------------------------------------------
def _decimal(value):
    """A number from a form field, or zero. Never an exception."""
    try:
        return Decimal(str(value).strip() or "0")
    except (InvalidOperation, ValueError, AttributeError):
        return Decimal("0")


def _is_pdf(upload):
    """
    A PDF, judged by its first bytes rather than its name.

    A file renamed to .pdf is still a photo, and the examiner is the one
    who would find out. The signature check costs five bytes.
    """
    if upload is None:
        return False
    name = (upload.name or "").lower()
    head = b""
    try:
        upload.seek(0)
        head = upload.read(5)
        upload.seek(0)
    except Exception:
        pass
    return name.endswith(".pdf") and head == b"%PDF-"


def my_work_view(request, admin_site):
    """
    What is open for this student, and handing it in.

    Row scoping already limits what a student may read; this is the page
    that makes it usable — the open sheets, what they have handed in, and
    one button to upload.
    """
    student = models.Student.objects.filter(user=request.user, voided=False).first()
    enrolments = (
        models.Enrolment.objects
        .filter(student=student, voided=False)
        .select_related("grade") if student else models.Enrolment.objects.none()
    )
    enrolment = enrolments.order_by("-academic_year").first()

    if request.method == "POST":
        handout = get_object_or_404(models.Handout, pk=request.POST.get("handout"))
        # One file, and it must be a PDF. A single paper as a single file is
        # the whole rule, so there is nothing to explain about page order and
        # nothing for the examiner to piece together.
        picked = request.FILES.get("file")
        uploads = [picked] if picked else []

        # It must be one of this student's own sheets: their class, their
        # year, and work meant to be handed back. The handout id arrives
        # in the form, so without this check a posted id from another
        # class would be accepted and the hand-in would land against a
        # gradebook the student is not in.
        if enrolment is None:
            allowed, why = False, "Your account is not linked to a student record."
        elif not (
            handout.is_assignment
            and handout.syllabus.grade_id == enrolment.grade_id
            and handout.syllabus.academic_year == enrolment.academic_year
        ):
            allowed, why = False, "That handout is not one of yours."
        else:
            allowed, why = handout.accepts_submission(enrolment)
        if not allowed:
            messages.error(request, why)
        elif not uploads:
            messages.error(request, "No file was chosen.")
        elif not _is_pdf(picked):
            messages.error(
                request,
                "Only a PDF can be handed in. If you have photos of your pages, "
                "turn them into one PDF first — the scanning app on your phone "
                "does this — then upload that.",
            )
        else:
            previous = list(
                models.Submission.objects
                .filter(handout=handout, enrolment=enrolment, voided=False)
                .order_by("round_no")
            )
            done = len(previous)
            latest = previous[-1] if previous else None

            # Three cases, and only the first two write anything.
            #
            #   * a redo the teacher asked for  -> the next round
            #   * their own hand-in, still theirs to change -> replace it
            #   * anything else -> refused, and the reason says which
            #
            # Replacing keeps the round number: it is the same attempt at
            # the same work, not a second one. The file it replaces is
            # voided rather than deleted, so what was handed in first is
            # still on the record.
            replacing = latest is not None and latest.replaceable()
            if latest is not None and not latest.awaits_redo and not replacing:
                messages.error(
                    request,
                    "Your work is being checked now, so it can no longer be "
                    "replaced. Your teacher can ask you to do it again if "
                    "something needs putting right."
                    if latest.state != models.SubmissionState.SUBMITTED else
                    "The window for this one has closed, so it can no longer "
                    "be replaced. Ask your teacher if you need it reopened.",
                )
            else:
                minutes = handout.lateness(enrolment)
                round_no = latest.round_no if replacing else done + 1
                if replacing:
                    latest.void(
                        user=request.user,
                        reason="replaced by the student before checking began",
                    )
                submission = models.Submission.objects.create(
                    handout=handout, enrolment=enrolment, round_no=round_no,
                    is_late=bool(minutes), minutes_late=minutes,
                    sheet_version=handout.sheet_version_no,
                )
                content_type = ContentType.objects.get_for_model(models.Submission)
                stored = 0
                for upload in uploads:
                    # Only what nothing could read is turned away. CamScanner
                    # has usually done the work already, so there is no
                    # quality scoring here and no warnings.
                    if upload.size < 1024:
                        messages.error(
                            request,
                            f"{upload.name} looks empty. Take it again and re-upload.",
                        )
                        continue
                    checksum = app_files.sha256_of(upload)
                    attachment = models.Attachment.objects.filter(
                        checksum=checksum, voided=False
                    ).first()
                    if attachment is None:
                        mime = getattr(upload, "content_type", "") or ""
                        attachment = models.Attachment(
                            original_filename=upload.name, mime_type=mime,
                            kind=app_files.classify(mime, upload.name),
                            size_bytes=upload.size, checksum=checksum,
                        )
                        attachment.file.save(upload.name, upload, save=False)
                        attachment.save()
                    models.AttachmentLink.objects.get_or_create(
                        attachment=attachment, content_type=content_type,
                        object_id=submission.pk, voided=False,
                        defaults={"role": "work"},
                    )
                    stored += 1

                if stored:
                    note = (
                        f"Replaced. Your new reference is {submission.code}."
                        if replacing else
                        f"Handed in. Your reference is {submission.code}."
                    )
                    if submission.is_late:
                        hours, mins = divmod(submission.minutes_late, 60)
                        late = f"{hours}h {mins:02d}m" if hours else f"{mins}m"
                        note += f" It is marked {late} late."
                    messages.success(request, note)
                else:
                    submission.delete()
                    messages.error(request, "Nothing was stored. Try again.")
        return redirect(reverse("my-work"))

    open_rows, done_rows = [], []
    if enrolment is not None:
        handouts = (
            models.Handout.objects
            .filter(
                voided=False,
                is_assignment=True,
                syllabus__grade=enrolment.grade,
                syllabus__academic_year=enrolment.academic_year,
                status=models.HandoutStatus.ACTIVE,
            )
            # An assignment scheduled for tomorrow is not the student's
            # business today. Nothing is visible before its opening moment,
            # which is read from the clock at query time — no scheduler, no
            # job to miss a firing, and it survives the server being off
            # overnight.
            .filter(Q(open_from__isnull=True) | Q(open_from__lte=timezone.now()))
            .select_related("syllabus", "syllabus__subject")
            .order_by("due_date", "code")
        )
        for handout in handouts:
            mine = list(
                models.Submission.objects
                .filter(handout=handout, enrolment=enrolment, voided=False)
                .order_by("round_no")
            )
            allowed, why = handout.accepts_submission(enrolment)
            latest = mine[-1] if mine else None
            # Nothing about the marking reaches the student until the class
            # teacher has approved it. Until then it is simply "being
            # checked" — the examiner and the approval step are the
            # school's business, not the student's.
            released = bool(latest and latest.is_released)
            # Still theirs to change: the window is open and nobody has
            # started checking it.
            replacing = bool(latest and latest.replaceable())
            if latest is not None and not latest.awaits_redo and not replacing:
                allowed = False
                why = (
                    "Checked — see below."
                    if released else
                    "Handed in. It is being checked; your mark will appear "
                    "here once it is ready."
                )
            dates = handout.deadline_for(enrolment)
            row = {
                "handout": handout,
                "sheet": _handout_files(handout, "handout"),
                "can_submit": allowed,
                "why_not": why,
                "due": dates["due"],
                "cutoff": dates["cutoff"],
                "extended": dates["due"] != handout.due_moment,
                "submissions": mine,
                "latest": latest,
                "released": released,
                "rounds_left": handout.max_rounds - len(mine),
                "needs_redo": bool(latest and latest.awaits_redo),
                "replacing": replacing,
                # Only shown once released. A held mark shows nothing.
                "checked": [
                    {
                        "name": a.title or a.original_filename,
                        "url": a.file.url if a.file else "",
                        "size": a.size_display,
                    }
                    for a in (latest.checked_files() if released else [])
                ],
                "lines": latest.lines() if released else [],
                "totals": latest.line_totals() if released else None,
                # The percentage is what aggregates, so it is what the
                # student is shown. Raw marks out of an arbitrary total
                # tell them nothing about where they stand.
                "percentage": latest.percentage if released else None,
                "weight_label": handout.weight_label,
                "kind_label": handout.get_kind_display(),
                "is_exam": handout.is_exam,
            }
            still_open = row["needs_redo"] or replacing
            (open_rows if (not mine or still_open) else done_rows).append(row)

    context = {
        **admin_site.each_context(request),
        "title": "My work",
        "student": student,
        "enrolment": enrolment,
        "open_rows": open_rows,
        "done_rows": done_rows,
        "standing": grading.student_report(enrolment) if enrolment else [],
        "today": timezone.localdate(),
        "now": timezone.now(),
    }
    return TemplateResponse(request, "admin/my_work.html", context)


# ---------------------------------------------------------------------
# The notice board
# ---------------------------------------------------------------------
def _may_post_notices(user):
    """Teachers and heads of department put things on the board."""
    if user.is_superuser:
        return True
    return user.groups.filter(
        name__in=["Teaching Staff", "Head of Department", "Academic Admin", "Admin"]
    ).exists()


def _notice_rows(grade=None, academic_year=None):
    """
    What is on the board, grouped by what it is.

    Whether a notice is live is decided from the clock rather than from a
    flag anyone has to remember to clear, so last term's timetable falls
    off by itself.
    """
    qs = (
        models.Notice.objects
        .filter(voided=False)
        .select_related("grade", "posted_by")
        .prefetch_related("attachments__attachment")
    )
    if grade is not None:
        qs = qs.filter(Q(grade=grade) | Q(grade__isnull=True))
    if academic_year is not None:
        qs = qs.filter(Q(academic_year=academic_year) | Q(academic_year__isnull=True))

    groups = {c.value: [] for c in models.NoticeCategory}
    for notice in qs:
        if not notice.is_live:
            continue
        groups[notice.category].append({
            "notice": notice,
            "files": [
                {
                    "name": a.title or a.original_filename,
                    "url": a.file.url if a.file else "",
                    "size": a.size_display,
                    "is_image": (a.mime_type or "").startswith("image/"),
                }
                for a in notice.files()
            ],
        })
    return groups


def notice_board_view(request, admin_site):
    """
    The board a student sees: what is due, and what the school has posted.

    Assignments are listed here as well as on My Work because a student
    looking for "what is coming" and a student sitting down to hand
    something in are two different moments, and making the first one
    require the second is how deadlines get missed.
    """
    student = models.Student.objects.filter(user=request.user, voided=False).first()
    enrolment = (
        models.Enrolment.objects
        .filter(student=student, voided=False)
        .select_related("grade")
        .order_by("-academic_year")
        .first()
        if student else None
    )

    assignments = []
    if enrolment is not None:
        handouts = (
            models.Handout.objects
            .filter(
                voided=False,
                is_assignment=True,
                syllabus__grade=enrolment.grade,
                syllabus__academic_year=enrolment.academic_year,
                status=models.HandoutStatus.ACTIVE,
            )
            # An assignment scheduled for tomorrow is not the student's
            # business today. Nothing is visible before its opening moment,
            # which is read from the clock at query time — no scheduler, no
            # job to miss a firing, and it survives the server being off
            # overnight.
            .filter(Q(open_from__isnull=True) | Q(open_from__lte=timezone.now()))
            .select_related("syllabus", "syllabus__subject", "topic")
            .order_by("due_date", "code")
        )
        for handout in handouts:
            handed_in = models.Submission.objects.filter(
                handout=handout, enrolment=enrolment, voided=False
            ).exists()
            dates = handout.deadline_for(enrolment)
            assignments.append({
                "handout": handout,
                "subject": handout.syllabus.subject,
                "due": dates["due"],
                "handed_in": handed_in,
                "kind_label": handout.get_kind_display(),
            })

    groups = _notice_rows(
        grade=enrolment.grade if enrolment else None,
        academic_year=enrolment.academic_year if enrolment else None,
    )

    context = {
        **admin_site.each_context(request),
        "title": "Notice board",
        "student": student,
        "enrolment": enrolment,
        "assignments": assignments,
        "timetables": groups[models.NoticeCategory.EXAM_TIMETABLE],
        "syllabi": groups[models.NoticeCategory.EXAM_SYLLABUS],
        "general": groups[models.NoticeCategory.GENERAL],
        "now": timezone.now(),
    }
    return TemplateResponse(request, "admin/notice_board.html", context)


def post_notice_view(request, admin_site):
    """
    Where a teacher puts an exam timetable or syllabus on the board.

    A file and a heading, because that is what a quarterly timetable
    actually is. Re-typing it into structured rows would be work with no
    reader — nobody queries a timetable, they look at it.
    """
    if not _may_post_notices(request.user):
        raise PermissionDenied("Only teaching staff can post to the notice board.")

    teacher = _teacher_for(request.user)

    if request.method == "POST":
        action = request.POST.get("action", "post")

        if action == "remove":
            notice = get_object_or_404(models.Notice, pk=request.POST.get("notice"))
            notice.void(reason="taken off the board")
            messages.success(request, f"Removed “{notice.title}”.")
            return redirect(reverse("post-notice"))

        title = (request.POST.get("title") or "").strip()
        category = request.POST.get("category") or models.NoticeCategory.GENERAL
        grade_id = request.POST.get("grade") or None
        body = (request.POST.get("body") or "").strip()
        upload = request.FILES.get("file")

        if not title:
            messages.error(request, "Give it a heading so people know what it is.")
            return redirect(reverse("post-notice"))
        if category != models.NoticeCategory.GENERAL and not upload:
            messages.error(
                request,
                "A timetable or syllabus needs a file — that is the notice. "
                "Use a general notice if you only want to say something.",
            )
            return redirect(reverse("post-notice"))

        notice = models.Notice.objects.create(
            title=title,
            category=category,
            grade_id=int(grade_id) if grade_id else None,
            academic_year=_current_year(),
            body=body,
            posted_by=request.user,
        )

        if upload:
            checksum = app_files.sha256_of(upload)
            attachment = models.Attachment.objects.filter(
                checksum=checksum, voided=False
            ).first()
            if attachment is None:
                mime = getattr(upload, "content_type", "") or ""
                attachment = models.Attachment(
                    original_filename=upload.name, mime_type=mime,
                    kind=app_files.classify(mime, upload.name),
                    size_bytes=upload.size, checksum=checksum,
                )
                attachment.file.save(upload.name, upload, save=False)
                attachment.save()
            models.AttachmentLink.objects.create(
                attachment=attachment,
                content_type=ContentType.objects.get_for_model(models.Notice),
                object_id=notice.pk,
                role="notice",
            )

        where = notice.grade.short_name if notice.grade else "every class"
        messages.success(request, f"Posted “{title}” to {where}.")
        return redirect(reverse("post-notice"))

    mine = (
        models.Notice.objects
        .filter(voided=False)
        .select_related("grade", "posted_by")
        .prefetch_related("attachments__attachment")
        .order_by("-date_posted")[:40]
    )
    rows = [
        {
            "notice": n,
            "files": [
                {"name": a.title or a.original_filename,
                 "url": a.file.url if a.file else ""}
                for a in n.files()
            ],
            "live": n.is_live,
        }
        for n in mine
    ]

    context = {
        **admin_site.each_context(request),
        "title": "Post a notice",
        "teacher": teacher,
        "grades": models.Grade.objects.filter(voided=False).order_by("sort_order", "level"),
        "categories": models.NoticeCategory.choices,
        "rows": rows,
    }
    return TemplateResponse(request, "admin/post_notice.html", context)


def _my_day_post(request):
    """
    The timer and the log, posted from a lesson card.

    Four things arrive here: start, pause and stop for the timer, and the
    log itself — a percentage for each topic, an optional note on any that
    fell short, and a comment on the class as a whole.
    """
    lesson = get_object_or_404(models.Lesson, pk=request.POST.get("lesson"))
    if not request.user.has_perm("app.change_lesson"):
        raise PermissionDenied

    back = reverse("my-day")
    offset = request.POST.get("offset") or "0"
    if offset not in ("", "0"):
        back = f"{back}?offset={offset}"
    # Land back on the lesson that was acted on. Without the anchor the
    # browser keeps the old scroll position, the message renders off-screen
    # at the top, and a save that worked perfectly looks like a dead button.
    def _back(kind):
        joiner = "&" if "?" in back else "?"
        return f"{back}{joiner}done={lesson.pk}&kind={kind}#lesson-{lesson.pk}"

    action = request.POST.get("action")

    if action == "timer_start":
        lesson.timer_start()
        return redirect(_back("started"))

    elif action == "timer_pause":
        lesson.timer_pause()
        return redirect(_back("paused"))

    elif action == "timer_stop":
        lesson.timer_stop()
        return redirect(_back("ended"))

    elif action == "carry":
        # Moving leftovers to the next class is now an explicit decision,
        # not something that happens quietly when the log is saved. A
        # teacher may well intend to drop a topic rather than carry it.
        moved = lesson.carry_forward()
        return redirect(_back("carried" if moved else "nothing_to_carry"))

    elif action in ("lecture_save", "lecture_delete"):
        item = None
        if request.POST.get("item"):
            item = lesson.lecture_items.filter(
                pk=request.POST["item"], voided=False
            ).first()

        if action == "lecture_delete":
            if item:
                item.void(reason="Removed from the lecture table.")
            return redirect(_back("lecture"))

        if item is None:
            item = models.LectureItem(lesson=lesson)
            item.sort_order = lesson.lecture_items.filter(voided=False).count()

        item.unit = (request.POST.get("unit") or "").strip()[:128]
        item.chapter = (request.POST.get("chapter") or "").strip()[:128]
        item.topic = (request.POST.get("topic") or "").strip()[:255]

        upload = request.FILES.get("file")
        if upload:
            checksum = app_files.sha256_of(upload)
            attachment = models.Attachment.objects.filter(
                checksum=checksum, voided=False
            ).first()
            if attachment is None:
                mime = getattr(upload, "content_type", "") or ""
                attachment = models.Attachment(
                    original_filename=upload.name, mime_type=mime,
                    kind=app_files.classify(mime, upload.name),
                    size_bytes=upload.size, checksum=checksum,
                    title=upload.name,
                )
                attachment.file.save(upload.name, upload, save=False)
                attachment.save()
            item.attachment = attachment

        if item.is_empty:
            return redirect(_back("lecture_empty"))

        item.save()
        return redirect(_back("lecture"))

    elif action in ("assign_save", "assign_delete", "assign_post", "assign_unpost"):
        handout = None
        if request.POST.get("handout"):
            handout = models.Handout.objects.filter(
                pk=request.POST["handout"], voided=False
            ).first()

        if action == "assign_delete":
            if handout:
                handout.void(reason="Removed from the assignment table.")
            return redirect(_back("assign"))

        if action == "assign_post":
            if handout:
                handout.activate(user=request.user)
                return redirect(_back("posted"))
            return redirect(_back(""))

        if action == "assign_unpost":
            # Back to where it was before posting: out of the students'
            # accounts, and ready to be posted again. Refused once anyone
            # has handed in — see Handout.can_unpost.
            if handout and not handout.can_unpost:
                return redirect(_back("locked"))
            if handout:
                handout.status = models.HandoutStatus.DRAFT
                handout.date_activated = None
                handout.activated_by = None
                handout.save()
                return redirect(_back("unposted"))
            return redirect(_back(""))

        chapter = (request.POST.get("chapter") or "").strip()[:128]
        topic_text = (request.POST.get("topic_text") or "").strip()[:255]
        upload = request.FILES.get("file")
        open_from = _moment(request.POST.get("open_from"))
        due_date = (request.POST.get("due_date") or "").strip() or None
        cutoff_at = _moment(request.POST.get("cutoff_at"))
        allow_late = "allow_late" in request.POST

        if handout is None:
            if not (chapter or topic_text or upload):
                return redirect(_back("assign_empty"))
            handout = models.Handout(
                syllabus=lesson.syllabus,
                title=topic_text or chapter or "Handout",
            )

        handout.chapter = chapter
        handout.topic_text = topic_text
        if topic_text or chapter:
            handout.title = topic_text or chapter
        if "open_from" in request.POST:
            handout.open_from = open_from
        if "due_date" in request.POST:
            handout.due_date = due_date
        if "due_date" in request.POST:          # the dates were on this form
            handout.allow_late = allow_late
            handout.cutoff_at = cutoff_at if allow_late else None
        handout.save()

        models.HandoutLesson.objects.get_or_create(
            handout=handout, lesson=lesson, voided=False
        )

        # The sheet the class gets, and — kept apart from it — the answer
        # scheme, which no student ever sees. Both can be set from here, so
        # the handout page is somewhere to go, not somewhere you must go.
        for field, role in (("file", "handout"), ("scheme", "scheme")):
            picked = request.FILES.get(field)
            if not picked:
                continue
            checksum = app_files.sha256_of(picked)
            attachment = models.Attachment.objects.filter(
                checksum=checksum, voided=False
            ).first()
            if attachment is None:
                mime = getattr(picked, "content_type", "") or ""
                attachment = models.Attachment(
                    original_filename=picked.name, mime_type=mime,
                    kind=app_files.classify(mime, picked.name),
                    size_bytes=picked.size, checksum=checksum, title=picked.name,
                )
                attachment.file.save(picked.name, picked, save=False)
                attachment.save()
            if role == "handout":
                _set_sheet(handout, attachment)
            else:
                _link_file(handout, attachment, role)

        return redirect(_back("assign"))

    elif action == "log_fetch":
        # Pull the topics written on the lecture table into the log.
        # A teacher has already typed them once; typing them again is the
        # kind of duplication that makes people stop filling forms in.
        subject = lesson.syllabus.subject
        existing = {
            (e.topic.short_name or "").strip().lower()
            for e in lesson.topics.filter(voided=False).select_related("topic")
        }
        added = 0
        for item in lesson.lecture_items.filter(voided=False):
            name = (item.topic or "").strip()
            if not name or name.lower() in existing:
                continue
            topic = models.Topic.objects.filter(
                subject=subject, short_name__iexact=name, voided=False
            ).first()
            if topic is None:
                topic = models.Topic.objects.create(
                    subject=subject, short_name=name[:64], full_name=name[:256],
                )
            models.LessonTopic.objects.get_or_create(
                lesson=lesson, topic=topic, voided=False,
                defaults={"planned": True},
            )
            existing.add(name.lower())
            added += 1
        return redirect(_back("fetched" if added else "nothing_fetched"))

    elif action == "topic_save":
        # The whole panel arrives at once: the topic's name, and every
        # sub-topic row still on screen. Adding and removing rows is done
        # in the browser, so a teacher can lay the list out and then save
        # once, rather than reloading the page on every change.
        topic = models.Topic.objects.filter(pk=request.POST.get("topic")).first()
        if topic is None:
            return redirect(_back(""))

        name = (request.POST.get("name") or "").strip()
        if name and name != topic.short_name:
            topic.short_name = name[:64]
            topic.full_name = name[:256]
            topic.save()

        ids = request.POST.getlist("child_id")
        names = request.POST.getlist("child_name")
        kept, order = set(), 0

        for child_id, child_name in zip(ids, names):
            child_name = (child_name or "").strip()
            if not child_name:
                continue                       # a row left blank is not a part
            child = None
            if child_id:
                child = models.Topic.objects.filter(
                    pk=child_id, parent=topic, voided=False
                ).first()
            if child is None:
                child = models.Topic.objects.filter(
                    parent=topic, short_name__iexact=child_name, voided=False
                ).first()
            if child is None:
                child = models.Topic(subject=topic.subject, parent=topic)
            child.short_name = child_name[:64]
            child.full_name = child_name[:256]
            child.sort_order = order
            child.save()
            kept.add(child.pk)
            order += 1

        # Anything taken off the list with the minus button.
        for child in topic.children.filter(voided=False):
            if child.pk not in kept:
                child.void(reason="Removed from the log checklist.")

        return redirect(_back("topic_saved"))

    elif action == "log":
        # Done or not finished, one tick each. No percentage: a number
        # invented at the end of a class is not comparable between two
        # teachers, and the questions worth asking are answered by
        # counting lessons and minutes instead.
        done = set(request.POST.getlist("topic_done"))
        for entry in lesson.topics.filter(voided=False, planned=True):
            entry.covered = str(entry.pk) in done
            entry.save()

        # A ticked child topic is recorded as a covered topic of its own,
        # so a part-taught parent can still say which parts were done.
        done_children = set(request.POST.getlist("child_done"))
        for child_id in done_children:
            child = models.Topic.objects.filter(pk=child_id, voided=False).first()
            if child is None:
                continue
            entry, _ = models.LessonTopic.objects.get_or_create(
                lesson=lesson, topic=child, voided=False,
                defaults={"planned": False},
            )
            entry.covered = True
            entry.save()

        # One optional comment for the whole class, not one per topic —
        # reached by "+ comment" so it never asks for anything. The ticks
        # already say what was covered; this is only for the rest.
        if "log_comment" in request.POST:
            lesson.log = (request.POST.get("log_comment") or "").strip()
        if not lesson.date_taught:
            lesson.date_taught = timezone.now()
        lesson.save()

        return redirect(_back("logged"))

    return redirect(_back(""))


# ---------------------------------------------------------------------
# My subjects — what a teacher teaches, and how far ahead it is prepared
# ---------------------------------------------------------------------
def my_subjects_view(request, admin_site):
    """
    One row per subject-and-grade this teacher takes.

    The counts that matter are lessons and handouts, and how much of it
    exists *ahead of today*. A week ahead is the standing requirement now;
    next year the whole year is planned in advance, and the same column
    answers that too — it is just a bigger number.
    """
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    teacher = _teacher_for(request.user)
    today = timezone.localdate()
    horizon = today + timedelta(days=7)

    lessons = models.Lesson.objects.filter(voided=False)
    if teacher is not None:
        from django.db.models import Q
        lessons = lessons.filter(
            Q(teacher=teacher)
            | Q(teacher__isnull=True, slot__teacher=teacher)
            | Q(teacher__isnull=True, slot__isnull=True)
            | Q(teacher__isnull=True, slot__teacher__isnull=True)
        )
    lessons = lessons.select_related(
        "syllabus", "syllabus__subject", "syllabus__grade"
    )

    by_syllabus = {}
    for lesson in lessons:
        row = by_syllabus.setdefault(lesson.syllabus_id, {
            "syllabus": lesson.syllabus,
            "lessons": 0, "ahead": 0, "unlogged": 0, "seconds": 0,
        })
        row["lessons"] += 1
        row["seconds"] += lesson.teaching_seconds
        if lesson.date > today:
            if lesson.date <= horizon:
                row["ahead"] += 1
        elif not lesson.date_taught:
            row["unlogged"] += 1

    handouts = (
        models.Handout.objects
        .filter(voided=False, syllabus_id__in=by_syllabus.keys())
        .select_related("syllabus")
    )
    for handout in handouts:
        row = by_syllabus[handout.syllabus_id]
        row.setdefault("handouts", 0)
        row.setdefault("open", 0)
        row["handouts"] += 1
        if handout.status == models.HandoutStatus.ACTIVE:
            row["open"] += 1

    rows = []
    for row in by_syllabus.values():
        seconds = row["seconds"]
        row["handouts"] = row.get("handouts", 0)
        row["open"] = row.get("open", 0)
        row["hours"] = f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m" if seconds else "—"
        row["url"] = "{}?syllabus__id__exact={}".format(
            reverse("admin:app_lesson_changelist"), row["syllabus"].pk
        )
        row["handouts_url"] = "{}?syllabus__id__exact={}".format(
            reverse("admin:app_handout_changelist"), row["syllabus"].pk
        )
        rows.append(row)
    rows.sort(key=lambda r: (str(r["syllabus"].grade), str(r["syllabus"].subject)))

    context = {
        **admin_site.each_context(request),
        "title": "My subjects",
        "teacher": teacher,
        "rows": rows,
        "today": today,
        "horizon": horizon,
        "my_day_url": reverse("my-day"),
    }
    return TemplateResponse(request, "admin/my_subjects.html", context)


# ---------------------------------------------------------------------
# A teacher's home, and the two ways in from it
# ---------------------------------------------------------------------
def _syllabi_for(teacher):
    """Every subject-and-grade this teacher takes, newest year first."""
    lessons = models.Lesson.objects.filter(voided=False)
    if teacher is not None:
        from django.db.models import Q
        lessons = lessons.filter(
            Q(teacher=teacher)
            | Q(teacher__isnull=True, slot__teacher=teacher)
            | Q(teacher__isnull=True, slot__isnull=True)
            | Q(teacher__isnull=True, slot__teacher__isnull=True)
        )
    ids = set(lessons.values_list("syllabus_id", flat=True))
    if teacher is not None:
        ids |= set(
            models.TeachingAssignment.objects
            .filter(teacher=teacher, voided=False)
            .values_list("syllabus_id", flat=True)
        )
        ids |= set(
            models.TimetableSlot.objects
            .filter(teacher=teacher, voided=False)
            .values_list("syllabus_id", flat=True)
        )
    return (
        models.Syllabus.objects
        .filter(pk__in=ids, voided=False)
        .select_related("subject", "grade")
        .order_by("-academic_year", "grade__sort_order", "subject__short_name")
    )


def teacher_home_view(request, admin_site):
    """
    The one page a teacher starts from.

    Six ways in, and nothing else. The dashboard's panels list database
    tables; these are the things a teacher actually looks for.
    """
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    teacher = _teacher_for(request.user)
    today = timezone.localdate()
    syllabi = list(_syllabi_for(teacher))

    lessons_today = _lessons_for(request.user, teacher, today, today).count()
    week_start = today - timedelta(days=today.weekday())
    lessons_week = _lessons_for(
        request.user, teacher, week_start, week_start + timedelta(days=6)
    ).count()
    unlogged = len([
        l for l in _lessons_for(request.user, teacher,
                                today - timedelta(days=30), today)
        if not l.date_taught
    ])
    grades = sorted({s.grade for s in syllabi}, key=lambda g: (g.sort_order, g.level))
    open_handouts_qs = models.Handout.objects.filter(
        voided=False, status=models.HandoutStatus.ACTIVE, syllabus__in=syllabi,
    )
    open_handouts = open_handouts_qs.count()
    outstanding_work = sum(
        h.completion()["outstanding"] for h in open_handouts_qs
    )
    # Marks the examiner has checked and left for this teacher to release.
    to_approve = models.Submission.objects.filter(
        voided=False, state=models.SubmissionState.MARKED,
        handout__syllabus__in=syllabi,
    ).count()
    students = models.Enrolment.objects.filter(
        voided=False, grade__in=grades,
        academic_year=max([s.academic_year for s in syllabi], default=today.year),
    ).count()

    context = {
        **admin_site.each_context(request),
        "title": "Home",
        "teacher": teacher,
        "today": today,
        "lessons_today": lessons_today,
        "lessons_week": lessons_week,
        "unlogged": unlogged,
        "syllabi_count": len(syllabi),
        "grades": grades,
        "students": students,
        "open_handouts": open_handouts,
        "outstanding_work": outstanding_work,
        "to_approve": to_approve,
    }
    return TemplateResponse(request, "admin/teacher_home.html", context)


def calendar_view(request, admin_site):
    """A month of this teacher's lessons, as a grid."""
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    teacher = _teacher_for(request.user)
    today = timezone.localdate()

    try:
        month = int(request.GET.get("month") or today.month)
        year = int(request.GET.get("year") or today.year)
    except ValueError:
        month, year = today.month, today.year

    first = date(year, month, 1)
    last = date(year + (month == 12), (month % 12) + 1, 1) - timedelta(days=1)
    start = first - timedelta(days=first.weekday())
    end = last + timedelta(days=6 - last.weekday())

    lessons = _lessons_for(request.user, teacher, start, end)
    by_day = {}
    for lesson in lessons:
        by_day.setdefault(lesson.date, []).append(lesson)

    weeks, day = [], start
    while day <= end:
        row = []
        for _ in range(7):
            row.append({
                "date": day,
                "in_month": day.month == month,
                "is_today": day == today,
                "lessons": [
                    {
                        "lesson": l,
                        # Straight to that class's section on My day, on that
                        # date — timer, materials, handouts and log all in
                        # reach. The edit form is for changing details, not
                        # for teaching from.
                        "url": "{}?offset={}#lesson-{}".format(
                            reverse("my-day"), (l.date - today).days, l.pk
                        ),
                        "subject": l.syllabus.subject,
                        "grade": l.syllabus.grade,
                    }
                    for l in by_day.get(day, [])
                ],
            })
            day += timedelta(days=1)
        weeks.append(row)

    prev_month = first - timedelta(days=1)
    next_month = last + timedelta(days=1)
    context = {
        **admin_site.each_context(request),
        "title": "Calendar",
        "teacher": teacher,
        "month_name": first.strftime("%B %Y"),
        "weeks": weeks,
        "prev": f"?year={prev_month.year}&month={prev_month.month}",
        "next": f"?year={next_month.year}&month={next_month.month}",
        "today": today,
    }
    return TemplateResponse(request, "admin/calendar.html", context)


def browse_view(request, admin_site):
    """
    Grades, then subjects, then topics, then what hangs off each topic.

    One page that narrows as you click, rather than five list screens with
    filters. `grade`, `syllabus` and `topic` in the querystring say how far
    down the reader has gone.
    """
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    teacher = _teacher_for(request.user)
    syllabi = list(_syllabi_for(teacher))

    grade_id = request.GET.get("grade")
    syllabus_id = request.GET.get("syllabus")
    topic_id = request.GET.get("topic")

    grades, seen = [], set()
    for syllabus in syllabi:
        if syllabus.grade_id in seen:
            continue
        seen.add(syllabus.grade_id)
        grades.append({
            "grade": syllabus.grade,
            "subjects": len([s for s in syllabi if s.grade_id == syllabus.grade_id]),
            "students": models.Enrolment.objects.filter(
                grade=syllabus.grade, academic_year=syllabus.academic_year,
                voided=False,
            ).count(),
        })

    grade = syllabus = topic = None
    subjects, topics, lessons, handouts, children = [], [], [], [], []

    if grade_id:
        grade = models.Grade.objects.filter(pk=grade_id).first()
        subjects = [s for s in syllabi if str(s.grade_id) == str(grade_id)]

    if syllabus_id:
        syllabus = models.Syllabus.objects.filter(pk=syllabus_id).first()
        if syllabus:
            grade = syllabus.grade
            subjects = [s for s in syllabi if s.grade_id == syllabus.grade_id]
            topics = list(
                models.Topic.objects
                .filter(subject=syllabus.subject, voided=False, parent__isnull=True)
                .order_by("sort_order", "short_name")
            )

    if topic_id:
        topic = models.Topic.objects.filter(pk=topic_id).first()
        if topic:
            children = list(
                topic.children.filter(voided=False).order_by("sort_order", "short_name")
            )
            entries = (
                models.LessonTopic.objects
                .filter(topic__in=[topic] + children, voided=False)
                .select_related("lesson", "lesson__syllabus")
            )
            seen_lessons = {}
            for entry in entries:
                if entry.lesson.voided:
                    continue
                if syllabus and entry.lesson.syllabus_id != syllabus.pk:
                    continue
                seen_lessons[entry.lesson_id] = entry.lesson
            lessons = sorted(seen_lessons.values(), key=lambda l: (l.date, l.period))
            handouts = list(
                models.Handout.objects
                .filter(topic__in=[topic] + children, voided=False)
                .order_by("code")
            )

    context = {
        **admin_site.each_context(request),
        "title": "All lessons",
        "teacher": teacher,
        "grades": grades,
        "grade": grade,
        "subjects": subjects,
        "syllabus": syllabus,
        "topics": topics,
        "topic": topic,
        "children": children,
        "lessons": [
            {"lesson": l, "url": reverse("admin:app_lesson_change", args=[l.pk])}
            for l in lessons
        ],
        "handouts": [
            {"handout": h, "url": reverse("handout", args=[h.pk])} for h in handouts
        ],
    }
    return TemplateResponse(request, "admin/browse.html", context)


# ---------------------------------------------------------------------
# Setting a handout, from the lesson it belongs to
# ---------------------------------------------------------------------
def new_handout_view(request, lesson_id, admin_site):
    """
    Set a sheet for one lesson, in one screen.

    The admin's own Add form asks for a syllabus by id, a topic by id, and
    explains that the code appears after saving — which is a database form,
    not a way to set homework. Coming from the lesson, the subject, grade
    and year are already known, so all that is left is a title, a file, and
    when it is due.
    """
    lesson = get_object_or_404(models.Lesson, pk=lesson_id)

    if not request.user.has_perm("app.add_handout"):
        raise PermissionDenied

    topics = [
        entry.topic for entry in
        lesson.topics.filter(voided=False).select_related("topic")
    ]

    if request.method == "POST":
        title = (request.POST.get("title") or "").strip()
        if not title:
            messages.error(request, "Give it a title.")
            return redirect(reverse("new-handout", args=[lesson.pk]))

        topic = None
        if request.POST.get("topic"):
            topic = models.Topic.objects.filter(pk=request.POST["topic"]).first()

        due = (request.POST.get("due_date") or "").strip() or None
        open_from = _moment(request.POST.get("open_from"))
        cutoff_at = _moment(request.POST.get("cutoff_at"))
        marks = (request.POST.get("max_marks") or "").strip() or None
        rounds = (request.POST.get("max_rounds") or "").strip() or 3

        handout = models.Handout.objects.create(
            syllabus=lesson.syllabus,
            topic=topic,
            chapter=(request.POST.get("chapter") or "").strip()[:128],
            topic_text=(request.POST.get("topic_text") or "").strip()[:255],
            title=title,
            instructions=(request.POST.get("instructions") or "").strip(),
            open_from=open_from,
            due_date=due,
            allow_late="allow_late" in request.POST,
            cutoff_at=cutoff_at if "allow_late" in request.POST else None,
            max_marks=marks,
            max_rounds=int(rounds),
            is_assignment="is_assignment" in request.POST,
            # An exam paper is set the same way as an assignment; what
            # differs is that it is never shown to the class in advance
            # and its marks aggregate separately.
            kind=(request.POST.get("kind") or models.HandoutKind.ASSIGNMENT),
            counts_toward_grade="practice_only" not in request.POST,
        )
        models.HandoutLesson.objects.create(handout=handout, lesson=lesson)

        content_type = ContentType.objects.get_for_model(models.Handout)
        for role, field in (("handout", "sheet"), ("scheme", "scheme")):
            for upload in request.FILES.getlist(field):
                checksum = app_files.sha256_of(upload)
                attachment = models.Attachment.objects.filter(
                    checksum=checksum, voided=False
                ).first()
                if attachment is None:
                    mime = getattr(upload, "content_type", "") or ""
                    attachment = models.Attachment(
                        original_filename=upload.name, mime_type=mime,
                        kind=app_files.classify(mime, upload.name),
                        size_bytes=upload.size, checksum=checksum,
                    )
                    attachment.file.save(upload.name, upload, save=False)
                    attachment.save()
                if role == "handout":
                    _set_sheet(handout, attachment)
                else:
                    _link_file(handout, attachment, role)

        if "activate" in request.POST:
            handout.activate(user=request.user)
            messages.success(
                request,
                f"{handout.code} created and handed out to the class.",
            )
        else:
            messages.success(
                request,
                f"{handout.code} created as a draft. Hand it out when you are ready.",
            )
        return redirect(reverse("handout", args=[handout.pk]))

    context = {
        **admin_site.each_context(request),
        "kinds": models.HandoutKind.choices,
        "title": "New handout",
        "lesson": lesson,
        "topics": topics,
        "defaults": _lecture_defaults(lesson),
        "today": timezone.localdate(),
        "lesson_url": reverse("admin:app_lesson_change", args=[lesson.pk]),
        "my_day_url": reverse("my-day"),
    }
    return TemplateResponse(request, "admin/handout_new.html", context)


# ---------------------------------------------------------------------
# Extensions — a later deadline for the students who have not handed in
# ---------------------------------------------------------------------
def handout_extend_view(request, handout_id, admin_site):
    """
    Give named students longer on the same handout.

    Not a second handout: the same sheet, the same code, the same marks
    column, only the date moved for those students. Everyone who has not
    handed in is ticked to begin with, because that is almost always the
    list the teacher means.
    """
    handout = get_object_or_404(models.Handout, pk=handout_id)

    if not request.user.has_perm("app.change_handout"):
        raise PermissionDenied

    submitted = set(
        models.Submission.objects
        .filter(handout=handout, voided=False)
        .values_list("enrolment_id", flat=True)
    )
    existing = {
        e.enrolment_id: e for e in
        handout.extensions.filter(voided=False)
    }

    if request.method == "POST":
        raw = (request.POST.get("extended_to") or "").strip()
        if not raw:
            messages.error(request, "Choose a new deadline.")
            return redirect(reverse("handout-extend", args=[handout.pk]))
        try:
            moment = timezone.make_aware(
                datetime.fromisoformat(raw), timezone.get_current_timezone()
            )
        except ValueError:
            messages.error(request, "That date could not be read.")
            return redirect(reverse("handout-extend", args=[handout.pk]))

        reason = (request.POST.get("reason") or "").strip()[:255]
        chosen = set(request.POST.getlist("enrolment"))
        granted = 0
        for enrolment_id in chosen:
            enrolment = models.Enrolment.objects.filter(
                pk=enrolment_id, voided=False
            ).first()
            if enrolment is None:
                continue
            extension = existing.get(enrolment.pk)
            if extension is None:
                extension = models.HandoutExtension(
                    handout=handout, enrolment=enrolment
                )
            extension.extended_to = moment
            extension.reason = reason
            extension.granted_by = request.user
            extension.save()
            granted += 1

        # Unticking someone takes their extension away again.
        for enrolment_id, extension in existing.items():
            if str(enrolment_id) not in chosen:
                extension.void(reason="Extension withdrawn.")

        messages.success(
            request,
            f"{granted} student(s) now have until "
            f"{timezone.localtime(moment):%d %b, %H:%M}."
            if granted else "No students were given an extension.",
        )
        return redirect(reverse("handout", args=[handout.pk]))

    roll = []
    for enrolment in handout.enrolments().order_by(
        "student__last_name", "student__first_name"
    ):
        extension = existing.get(enrolment.pk)
        roll.append({
            "enrolment": enrolment,
            "student": enrolment.student,
            "handed_in": enrolment.pk in submitted,
            "extension": extension,
            # Ticked to begin with: everyone who has not handed in, plus
            # anyone who already has an extension.
            "checked": (enrolment.pk not in submitted) or bool(extension),
        })

    dates = handout.deadline_for()
    context = {
        **admin_site.each_context(request),
        "title": f"Extension — {handout.code}",
        "handout": handout,
        "roll": roll,
        "outstanding": len([r for r in roll if not r["handed_in"]]),
        "due": dates["due"],
        "cutoff": dates["cutoff"],
        "default_when": timezone.localtime(
            (dates["cutoff"] or dates["due"] or timezone.now()) + timedelta(days=2)
        ).strftime("%Y-%m-%dT%H:%M"),
        "back_url": reverse("handout", args=[handout.pk]),
    }
    return TemplateResponse(request, "admin/handout_extend.html", context)


# ---------------------------------------------------------------------
# Assignments — every handout this teacher has set, class by class
# ---------------------------------------------------------------------
def assignments_view(request, admin_site):
    """
    One collapsed card per class, newest assignment first inside each.

    A teacher takes several classes and wants to know, at a glance, which
    assignments are still waiting on work. Collapsed by default because
    four classes of twenty handouts is a wall of text otherwise.
    """
    if not _may_open_teaching_screens(request.user):
        raise PermissionDenied

    teacher = _teacher_for(request.user)
    syllabi = list(_syllabi_for(teacher))
    now = timezone.now()

    cards = []
    for syllabus in syllabi:
        handouts = (
            models.Handout.objects
            .filter(syllabus=syllabus, voided=False)
            .order_by("-date_created")
        )
        rows, outstanding_total = [], 0
        for handout in handouts:
            counts = handout.completion()
            outstanding_total += counts["outstanding"] if handout.is_open else 0

            if handout.status != models.HandoutStatus.ACTIVE:
                state = ("closed" if handout.status == models.HandoutStatus.CLOSED
                         else "unposted")
            elif not handout.is_past_due:
                state = "posted"
            elif handout.late_window_open:
                state = "overridden"
            else:
                state = "closed"

            rows.append({
                "handout": handout,
                "url": reverse("handout", args=[handout.pk]),
                "state": state,
                "counts": counts,
                "late_count": models.Submission.objects.filter(
                    handout=handout, voided=False, is_late=True
                ).count(),
            })

        if rows:
            cards.append({
                "syllabus": syllabus,
                "rows": rows,
                "total": len(rows),
                "outstanding": outstanding_total,
            })

    context = {
        **admin_site.each_context(request),
        "title": "Assignments",
        "teacher": teacher,
        "cards": cards,
        "now": now,
    }
    return TemplateResponse(request, "admin/assignments.html", context)


# ---------------------------------------------------------------------
# Checking — the examiner's queue, and one piece of work at a time
# ---------------------------------------------------------------------
def _may_approve(user):
    """
    Who may release an examiner's mark to the student.

    The class teacher signs off their own class's work; a head of
    department or an admin may sign off anyone's. An examiner may not
    approve their own marking — that is the whole point of the step.
    """
    return (
        user.is_superuser
        or access.has_role(
            user, access.TEACHING_STAFF, access.HEAD_OF_DEPARTMENT,
            access.ACADEMIC_ADMIN, access.ADMIN,
        )
    )


def _apply_mark_edits(request, submission):
    """
    The teacher's own corrections to the examiner's breakdown, if any.

    Only a line whose numbers or wording actually changed is written, and a
    line the teacher touches is re-attributed to them: the source column
    exists to say who stands behind each mark, and the examiner's original
    stays in the audit trail on the row.

    This is here so that a one-mark slip is fixed in three clicks rather
    than crossing a desk twice. Real disagreement still goes back to the
    examiner, with a reason.
    """
    ids = request.POST.getlist("line_id")
    if not ids:
        return 0

    out_ofs = request.POST.getlist("line_out_of")
    awardeds = request.POST.getlist("line_awarded")
    comments = request.POST.getlist("line_comment")

    changed = 0
    for i, raw_id in enumerate(ids):
        line = models.MarkLine.objects.filter(
            pk=raw_id, submission=submission, voided=False
        ).first()
        if line is None:
            continue
        out_of = _decimal(out_ofs[i]) if i < len(out_ofs) else line.out_of
        awarded = _decimal(awardeds[i]) if i < len(awardeds) else line.awarded
        comment = (comments[i] if i < len(comments) else line.comment).strip()[:255]
        if out_of == line.out_of and awarded == line.awarded and comment == line.comment:
            continue
        line.out_of = out_of
        line.awarded = awarded
        line.comment = comment
        line.source = models.MarkSource.TEACHER
        line.save()
        changed += 1

    if changed:
        # awarded_marks is the single number the rest of the system reads,
        # and once a breakdown exists it is the sum of the lines. Recompute
        # it here or the released mark disagrees with the table under it.
        submission.awarded_marks = submission.line_totals()["awarded"]
    return changed


def approvals_view(request, admin_site):
    """
    The teacher's sign-off list: marks the examiner has checked, waiting to
    be released to the student.

    Grouped by class so the eye lands on one lesson's worth at a time.
    Each row can be approved (the student sees it), sent back to the
    examiner to re-check, or sent back to the student to redo.
    """
    if not _may_approve(request.user):
        raise PermissionDenied

    teacher = _teacher_for(request.user)
    # An owner or admin with no Teacher record approves across the school;
    # a class teacher only their own subjects and grades.
    wide = teacher is None or access.has_role(
        request.user, access.HEAD_OF_DEPARTMENT, access.ACADEMIC_ADMIN, access.ADMIN,
    ) or request.user.is_superuser
    syllabus_ids = None if wide else set(
        _syllabi_for(teacher).values_list("pk", flat=True)
    )

    if request.method == "POST":
        submission = models.Submission.objects.filter(
            pk=request.POST.get("submission"), voided=False
        ).select_related("handout", "handout__syllabus", "enrolment",
                         "enrolment__student").first()
        action = request.POST.get("action")
        if submission is None:
            messages.error(request, "That submission could not be found.")
        elif syllabus_ids is not None and submission.handout.syllabus_id not in syllabus_ids:
            raise PermissionDenied
        elif action == "approve":
            edited = _apply_mark_edits(request, submission)
            submission.approve(user=request.user)
            messages.success(
                request,
                f"{submission.enrolment.student.full_name}'s work is approved and "
                "is now in their account."
                + (f" {edited} mark line(s) were changed by you first; the "
                   "examiner's originals are kept." if edited else ""),
            )
        elif action == "send_back":
            submission.send_back_to_examiner(
                user=request.user,
                reason=(request.POST.get("reason") or "").strip()[:255],
            )
            messages.success(
                request,
                f"Sent back to the examiner to look at again. It has left your list.",
            )
        elif action == "request_redo":
            submission.request_redo(
                user=request.user,
                reason=(request.POST.get("reason") or "").strip()[:255],
            )
            messages.success(
                request,
                f"{submission.enrolment.student.full_name} has been asked to do "
                "this again. It is back in their My work.",
            )
        return redirect(reverse("approvals"))

    waiting = (
        models.Submission.objects
        .filter(voided=False, state=models.SubmissionState.MARKED)
        .select_related("handout", "handout__syllabus", "handout__syllabus__grade",
                        "handout__syllabus__subject", "enrolment", "enrolment__student",
                        "marked_by")
        .order_by("handout__syllabus__grade__sort_order",
                  "handout__syllabus__subject__short_name", "date_marked")
    )
    if syllabus_ids is not None:
        waiting = waiting.filter(handout__syllabus_id__in=syllabus_ids)

    classes, index = [], {}
    for sub in waiting:
        syllabus = sub.handout.syllabus
        key = syllabus.pk
        if key not in index:
            index[key] = {"syllabus": syllabus, "rows": []}
            classes.append(index[key])
        totals = sub.line_totals()
        index[key]["rows"].append({
            "submission": sub,
            "student": sub.enrolment.student,
            "handout": sub.handout,
            "marked_by": sub.marked_by,
            # In a small academy the same person often teaches and examines
            # a subject. That is allowed, but it is not a second pair of
            # eyes, and the screen says so rather than pretending otherwise.
            "self_check": bool(sub.marked_by_id) and sub.marked_by_id == request.user.id,
            "marks": totals if totals["count"] else None,
            "lines": sub.lines(),
            "checked": [
                {"name": a.title or a.original_filename,
                 "url": a.file.url if a.file else ""}
                for a in sub.checked_files()
            ],
            "work": [
                {"name": a.title or a.original_filename,
                 "url": a.file.url if a.file else ""}
                for a in sub.work_files()
            ],
            "check_url": reverse("check-submission", args=[sub.pk]),
        })

    total = sum(len(c["rows"]) for c in classes)
    context = {
        **admin_site.each_context(request),
        "title": "To approve",
        "classes": classes,
        "total": total,
        # The checking screen belongs to the examiner. A class teacher who
        # does not also hold that role cannot open it, so the link to it is
        # only offered to someone it will actually work for — the work and
        # the checked file are on this page either way.
        "may_check": _may_check(request.user),
    }
    return TemplateResponse(request, "admin/approvals.html", context)


def _may_check(user):
    return (
        user.is_superuser
        or access.has_role(
            user, access.MARKING_REVIEWER, access.ACADEMIC_ADMIN,
            access.ADMIN, access.HEAD_OF_DEPARTMENT,
        )
    )


def _submission_status(sub):
    """
    Where one submission stands, in the examiner's terms.

    'waiting' is the only thing on their plate; 'redo' is back with the
    student; 'checked' is done. The queue works waiting; the browser
    shows all three so nothing looks lost.
    """
    if sub is None:
        return "missing"
    if sub.needs_examiner:               # never checked, or bounced back
        return "waiting"
    if sub.awaits_redo:
        return "redo"
    if sub.awaits_approval:              # checked, with the teacher now
        return "approval"
    if sub.is_released:
        return "released"
    return "waiting"


def checking_browse_view(request, admin_site):
    """
    The examiner's home: class, then subject, then assignment.

    The flat queue is the fastest way to clear a backlog, but it is no way
    to find one class's work or answer "how is E1 English doing". This
    walks the same submissions the other way round — down the structure a
    teacher thinks in — and every assignment carries how many are still
    waiting, so the eye goes straight to the ones with work on them.
    """
    if not _may_check(request.user):
        raise PermissionDenied

    # Every assignment that has been handed out at all. A draft nobody can
    # submit to has nothing to check, so it is left out.
    handouts = (
        models.Handout.objects
        .filter(voided=False, is_assignment=True)
        .exclude(status=models.HandoutStatus.DRAFT)
        .select_related("syllabus", "syllabus__grade", "syllabus__subject")
        .order_by("syllabus__grade__sort_order", "syllabus__grade__level",
                  "syllabus__subject__sort_order", "syllabus__subject__short_name",
                  "-date_created")
    )

    # counts in one query rather than one per handout
    S = models.SubmissionState
    counts = {}
    for row in (
        models.Submission.objects
        .filter(voided=False, handout__in=handouts)
        .values("handout_id", "state")
    ):
        bucket = counts.setdefault(row["handout_id"], {"waiting": 0, "checked": 0,
                                                       "redo": 0, "handed_in": 0})
        bucket["handed_in"] += 1
        state = row["state"]
        if state in (S.SUBMITTED, S.GRADING, S.SENT_BACK):
            bucket["waiting"] += 1        # examiner must act
        elif state == S.RETURNED:
            bucket["redo"] += 1           # back with the student
        else:
            bucket["checked"] += 1        # checked (awaiting approval or released)

    # group grade -> subject -> [assignments]
    classes = []
    grade_index = {}
    for handout in handouts:
        grade = handout.syllabus.grade
        subject = handout.syllabus.subject
        c = counts.get(handout.pk, {"waiting": 0, "checked": 0, "redo": 0, "handed_in": 0})

        gkey = grade.pk
        if gkey not in grade_index:
            grade_index[gkey] = {"grade": grade, "waiting": 0, "subjects": {},
                                 "sub_order": []}
            classes.append(grade_index[gkey])
        gentry = grade_index[gkey]
        gentry["waiting"] += c["waiting"]

        skey = subject.pk
        if skey not in gentry["subjects"]:
            gentry["subjects"][skey] = {"subject": subject, "waiting": 0, "rows": []}
            gentry["sub_order"].append(skey)
        sentry = gentry["subjects"][skey]
        sentry["waiting"] += c["waiting"]
        sentry["rows"].append({
            "handout": handout,
            "counts": c,
            "url": reverse("checking-assignment", args=[handout.pk]),
        })

    # flatten the subject dicts into ordered lists for the template
    for gentry in classes:
        gentry["subjects"] = [gentry["subjects"][k] for k in gentry["sub_order"]]

    total_waiting = sum(g["waiting"] for g in classes)

    context = {
        **admin_site.each_context(request),
        "title": "Checking",
        "classes": classes,
        "total_waiting": total_waiting,
        "queue_url": reverse("checking-queue"),
    }
    return TemplateResponse(request, "admin/checking_browse.html", context)


def checking_assignment_view(request, handout_id, admin_site):
    """
    One assignment: every student who handed it in, and where each stands.

    This is the checking equivalent of the teacher's handout roll, but
    turned to the checker's job: waiting work first, a Check button on
    each, and the mark once it is done.
    """
    if not _may_check(request.user):
        raise PermissionDenied

    handout = get_object_or_404(models.Handout, pk=handout_id)

    submissions = (
        models.Submission.objects
        .filter(handout=handout, voided=False)
        .select_related("enrolment", "enrolment__student", "marked_by")
        .order_by("enrolment__student__last_name", "enrolment__student__first_name",
                  "round_no")
    )
    # latest round per student — that is the one to act on
    latest = {}
    for sub in submissions:
        latest[sub.enrolment_id] = sub

    order = {"waiting": 0, "redo": 1, "checked": 2}
    rows = []
    for sub in latest.values():
        status = _submission_status(sub)
        totals = sub.line_totals()
        rows.append({
            "submission": sub,
            "student": sub.enrolment.student,
            "status": status,
            "url": reverse("check-submission", args=[sub.pk]),
            "marks": totals if totals["count"] else None,
            "sort": (order.get(status, 3),
                     sub.enrolment.student.last_name or "",
                     sub.enrolment.student.first_name or ""),
        })
    rows.sort(key=lambda r: r["sort"])

    waiting = sum(1 for r in rows if r["status"] == "waiting")

    context = {
        **admin_site.each_context(request),
        "title": f"{handout.code} — checking",
        "handout": handout,
        "rows": rows,
        "waiting": waiting,
        "handed_in": len(rows),
        "class_total": handout.completion()["total"],
        "sheet": _handout_files(handout, "handout"),
        "scheme": _handout_files(handout, "scheme"),
        "browse_url": reverse("checking-browse"),
    }
    return TemplateResponse(request, "admin/checking_assignment.html", context)


def checking_queue_view(request, admin_site):
    """
    Everything waiting to be checked, oldest first.

    Oldest first on purpose: a queue worked newest-first leaves the
    earliest submission waiting longest, which is the student most likely
    to have handed in on time.
    """
    if not _may_check(request.user):
        raise PermissionDenied

    waiting = (
        models.Submission.objects
        .filter(voided=False, state__in=[models.SubmissionState.SUBMITTED,
                                        models.SubmissionState.GRADING,
                                        models.SubmissionState.SENT_BACK])
        .select_related("handout", "handout__syllabus", "handout__syllabus__subject",
                        "handout__syllabus__grade", "enrolment", "enrolment__student")
        .order_by("time_submitted")
    )
    recent = (
        models.Submission.objects
        .filter(voided=False, marked_by=request.user)
        .select_related("handout", "enrolment", "enrolment__student")
        .order_by("-date_marked")[:10]
    )

    rows = [
        {
            "submission": submission,
            "url": reverse("check-submission", args=[submission.pk]),
            "student": submission.enrolment.student,
            "handout": submission.handout,
            "waiting_days": (timezone.now() - submission.time_submitted).days,
        }
        for submission in waiting
    ]

    context = {
        **admin_site.each_context(request),
        "title": "Checking",
        "rows": rows,
        "recent": recent,
        "waiting_count": len(rows),
    }
    return TemplateResponse(request, "admin/checking_queue.html", context)


def check_submission_view(request, submission_id, admin_site):
    """
    One piece of work: what the student handed in, and what goes back.

    The checked file is the feedback. Marks are entered against the
    handout's total; the rubric that decides how they are arrived at is
    the examiner's business, not this screen's.
    """
    submission = get_object_or_404(models.Submission, pk=submission_id)

    if not _may_check(request.user):
        raise PermissionDenied

    handout = submission.handout

    # Opening the script is what closes the student's window to replace it.
    # Marking a file that changes underneath you is worse than a late
    # correction, so the lock happens the moment someone looks — not when
    # they finish. It stays in the queue either way; see needs_examiner.
    if request.method == "GET":
        submission.start_checking(user=request.user)

    if request.method == "POST":
        marks = (request.POST.get("awarded_marks") or "").strip() or None
        feedback = (request.POST.get("feedback") or "").strip()

        # The breakdown arrives as parallel lists — the whole table is
        # posted at once, so rows can be added and removed in the browser
        # and saved in one go, the same way the lesson log works.
        ids = request.POST.getlist("line_id")
        labels = request.POST.getlist("line_label")
        out_ofs = request.POST.getlist("line_out_of")
        awardeds = request.POST.getlist("line_awarded")
        comments = request.POST.getlist("line_comment")
        kept, order = set(), 0
        for i, label in enumerate(labels):
            label = (label or "").strip()
            if not label:
                continue                        # a blank row is not a part
            line = None
            if i < len(ids) and ids[i]:
                line = models.MarkLine.objects.filter(
                    pk=ids[i], submission=submission, voided=False
                ).first()
            if line is None:
                line = models.MarkLine(submission=submission)
            line.label = label[:64]
            line.out_of = _decimal(out_ofs[i] if i < len(out_ofs) else 0)
            line.awarded = _decimal(awardeds[i] if i < len(awardeds) else 0)
            line.comment = (comments[i] if i < len(comments) else "").strip()[:255]
            line.sort_order = order
            line.save()
            kept.add(line.pk)
            order += 1
        if labels:                              # the table was on this form
            for line in submission.mark_lines.filter(voided=False):
                if line.pk not in kept:
                    line.void(reason="Removed from the breakdown.")

        content_type = ContentType.objects.get_for_model(models.Submission)
        stored = 0
        for upload in request.FILES.getlist("checked"):
            checksum = app_files.sha256_of(upload)
            attachment = models.Attachment.objects.filter(
                checksum=checksum, voided=False
            ).first()
            if attachment is None:
                mime = getattr(upload, "content_type", "") or ""
                attachment = models.Attachment(
                    original_filename=upload.name, mime_type=mime,
                    kind=app_files.classify(mime, upload.name),
                    size_bytes=upload.size, checksum=checksum, title=upload.name,
                )
                attachment.file.save(upload.name, upload, save=False)
                attachment.save()
            models.AttachmentLink.objects.get_or_create(
                attachment=attachment, content_type=content_type,
                object_id=submission.pk, voided=False,
                defaults={"role": "checked"},
            )
            stored += 1

        if not stored and not submission.checked_files():
            messages.error(
                request,
                "Attach the checked version — that is what the student reads.",
            )
            return redirect(reverse("check-submission", args=[submission.pk]))

        submission.mark(user=request.user, marks=marks, feedback=feedback)
        messages.success(
            request,
            f"{submission.code} checked and sent to the class teacher for approval. "
            "The student sees nothing until the teacher releases it.",
        )
        return redirect(reverse("checking-queue"))

    context = {
        **admin_site.each_context(request),
        "title": f"Checking — {submission.code}",
        "submission": submission,
        "handout": handout,
        "student": submission.enrolment.student,
        "work": [_viewable(a) for a in submission.work_files()],
        "checked": [_viewable(a) for a in submission.checked_files()],
        "scheme": _handout_files(handout, "scheme"),
        "sheet": _handout_files(handout, "handout"),
        "lines": submission.lines(),
        "totals": submission.line_totals(),
        # If the teacher bounced this back, show why, right at the top.
        "sent_back_reason": submission.sent_back_reason if submission.sent_back else "",
        "queue_url": reverse("checking-queue"),
    }
    return TemplateResponse(request, "admin/check_submission.html", context)
