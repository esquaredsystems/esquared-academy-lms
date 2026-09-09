"""
How a student's marks add up.

The problem this solves
-----------------------
A minor topic may carry a fifty-mark sheet while a major topic carries a
ten-mark one. If raw marks were added up, the minor topic would count for
five times more — not because anyone decided it should, but because of how
many questions happened to fit on the page. And if every assignment counted
equally, a topic that took three weeks and six sheets would drown out a
topic that took one week and two, again by accident.

Two separate ideas, kept apart
------------------------------
1. **Marks measure performance.** Every piece of work is reduced to a
   percentage the moment it is scored, so a sheet out of 50 and a sheet out
   of 10 are on the same scale and neither dominates by size.

2. **Importance is a property of the topic, not of the paper.** It is set
   once on the syllabus, when planning the year — a curriculum judgement
   made calmly, rather than a number invented the night a test is written.
   Teachers never weigh an individual paper.

The arithmetic, in two levels
-----------------------------
    topic score    = mean of the percentages of that topic's papers
    subject score  = Σ(topic score × topic importance) / Σ(topic importance)

Averaging within a topic first is what stops frequency from distorting the
result: six sheets on quadratics average to one quadratics score, two sheets
on trigonometry average to one trigonometry score, and only then does
importance decide how much each says about the student. Importance ends up
being the single deliberate signal, which is what makes it defensible to a
parent.

Coursework and exams are aggregated separately and reported side by side.
Combining them means choosing a ratio, and that is a decision for the
school, not an arithmetic convenience.
"""

from collections import defaultdict
from decimal import Decimal

from django.db.models import Prefetch

from .models import (
    Enrolment,
    Handout,
    HandoutKind,
    MarkLine,
    Submission,
    SubmissionState,
    SyllabusTopic,
    TopicImportance,
)

#: Marks are only counted once a teacher has released them. Work that is
#: still with the examiner is not a result yet, and a student's average
#: should never move because of something they cannot see.
COUNTED_STATES = {SubmissionState.APPROVED, SubmissionState.ACCEPTED}

TWO_PLACES = Decimal("0.01")


def _q(value):
    return None if value is None else Decimal(value).quantize(TWO_PLACES)


# ---------------------------------------------------------------------
# Topic importance
# ---------------------------------------------------------------------
def topic_weights(syllabus):
    """
    Every topic's importance for one syllabus, keyed by topic id.

    Only the ratios matter, so a school allocating a true percentage
    across its topics and a school picking Core / Standard / Supporting
    get the same behaviour from the same field.
    """
    rows = SyllabusTopic.objects.filter(syllabus=syllabus, voided=False)
    return {
        row.topic_id: Decimal(row.weight_pct)
        for row in rows
        if row.weight_pct is not None
    }


def resolve_weight(handout, weights=None):
    """
    What one paper counts for.

    An override on the paper wins; failing that the topic's importance;
    failing that Standard. A paper flagged as practice-only counts zero,
    so it stays visible in the list and out of the average.
    """
    if not handout.counts_toward_grade:
        return Decimal("0")
    if handout.weight_override is not None:
        return Decimal(handout.weight_override)
    if weights is not None and handout.topic_id in weights:
        return weights[handout.topic_id]
    inherited = handout.topic_importance
    if inherited is not None:
        return Decimal(inherited)
    return Decimal(TopicImportance.STANDARD.value)


# ---------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------
def _live_submissions(enrolment, syllabus=None):
    """
    The submissions that count: released, not voided, latest round only.

    Rounds are kept rather than overwritten, so a redo produces a second
    row. The last round is the one that stands — a student who was asked
    to do the work again is judged on the work they did again.
    """
    qs = (
        Submission.objects
        .filter(enrolment=enrolment, voided=False, state__in=COUNTED_STATES)
        .select_related("handout", "handout__syllabus", "handout__topic")
        .prefetch_related(
            Prefetch("mark_lines", queryset=MarkLine.objects.filter(voided=False))
        )
    )
    if syllabus is not None:
        qs = qs.filter(handout__syllabus=syllabus)

    latest = {}
    for sub in qs:
        key = sub.handout_id
        if key not in latest or sub.round_no > latest[key].round_no:
            latest[key] = sub
    return list(latest.values())


def topic_scores(enrolment, syllabus, kinds=None):
    """
    One score per topic: the mean of that topic's papers, as percentages.

    Averaging here is the step that keeps a heavily-taught topic from
    drowning out a lightly-taught one purely by producing more sheets.
    Papers not tied to a catalogued topic are grouped under None, which
    keeps them in the subject average without inventing a topic for them.
    """
    buckets = defaultdict(list)
    for sub in _live_submissions(enrolment, syllabus):
        if kinds is not None and sub.handout.kind not in kinds:
            continue
        pct = sub.percentage
        if pct is None:
            continue
        buckets[sub.handout.topic_id].append((pct, sub))

    out = {}
    for topic_id, entries in buckets.items():
        scores = [pct for pct, _ in entries]
        out[topic_id] = {
            "topic_id": topic_id,
            "topic": entries[0][1].handout.topic,
            "score_pct": _q(sum(scores) / len(scores)),
            "papers": len(scores),
            "submissions": [sub for _, sub in entries],
        }
    return out


def subject_score(enrolment, syllabus, kinds=None):
    """
    One subject mark, weighting each topic score by that topic's importance.

    Returns None when nothing has been released yet — which is not the
    same as zero, and must not be displayed as one.
    """
    weights = topic_weights(syllabus)
    topics = topic_scores(enrolment, syllabus, kinds=kinds)
    if not topics:
        return None

    default = Decimal(TopicImportance.STANDARD.value)
    numerator = Decimal("0")
    denominator = Decimal("0")
    for topic_id, row in topics.items():
        weight = weights.get(topic_id, default) if topic_id else default
        if weight <= 0:
            continue
        numerator += row["score_pct"] * weight
        denominator += weight

    if denominator == 0:
        return None
    return _q(numerator / denominator)


def subject_summary(enrolment, syllabus):
    """
    Everything a report line needs for one subject, computed in one pass.

    Coursework and exams are reported separately on purpose. Rolling them
    into a single figure means picking a ratio — 30/70, 40/60 — and that
    is a policy the school sets, not something this function should decide
    quietly on its behalf.
    """
    coursework_kinds = {HandoutKind.ASSIGNMENT}
    exam_kinds = {HandoutKind.ASSESSMENT, HandoutKind.MOCK, HandoutKind.QUARTERLY}

    weights = topic_weights(syllabus)
    all_topics = topic_scores(enrolment, syllabus)

    rows = []
    for topic_id, row in sorted(
        all_topics.items(),
        key=lambda kv: (kv[1]["topic"].sort_order if kv[1]["topic"] else 0),
    ):
        weight = weights.get(topic_id, Decimal(TopicImportance.STANDARD.value))
        label = min(
            TopicImportance.choices, key=lambda c: abs(Decimal(c[0]) - weight)
        )[1]
        rows.append({
            "topic": row["topic"],
            "topic_name": row["topic"].full_name if row["topic"] else "Not on a topic",
            "score_pct": row["score_pct"],
            "papers": row["papers"],
            "weight": weight,
            "weight_label": label,
        })

    return {
        "syllabus": syllabus,
        "subject": syllabus.subject,
        "coursework_pct": subject_score(enrolment, syllabus, kinds=coursework_kinds),
        "exam_pct": subject_score(enrolment, syllabus, kinds=exam_kinds),
        "overall_pct": subject_score(enrolment, syllabus),
        "topics": rows,
        "pass_mark_pct": syllabus.pass_mark_pct,
    }


def student_report(enrolment):
    """Every subject this enrolment carries, each summarised."""
    from .models import StudentSubject

    subjects = (
        StudentSubject.objects
        .filter(enrolment=enrolment, voided=False)
        .select_related("syllabus", "syllabus__subject")
    )
    return [subject_summary(enrolment, ss.syllabus) for ss in subjects]
