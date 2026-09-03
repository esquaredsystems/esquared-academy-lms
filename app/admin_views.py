"""
Admin pages that are not tied to one model.

Currently just the Demo page, reached from the "Demo" entry in the side
menu. It runs the same `seed_demo` management command the terminal does,
so the button and the command can never behave differently.
"""

from datetime import date
from io import StringIO

from django.contrib import messages
from django.core.management import call_command
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import reverse

from . import demo_data, models


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


def demo_view(request, admin_site):
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
