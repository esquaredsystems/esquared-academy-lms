---
doc: agent-knowledge-graph
project: esquared-academy-lms
repo: esquaredsystems/esquared-academy-lms (private)
generated: 2026-09-13
generated_by: claude (assessment from scratch, ast-based structural extraction + manual read of every non-generated module; updated same day after the attribute-type refactor, then again after the Grade→AcademyClass rename, the 12→6 role consolidation, and the curriculum-widget admin reorg below)
covers_commit: 163833b "Adding instructions and knowledge graph for AI agents" + uncommitted attribute-type refactor (Question config + Student optional fields → attribute types; see §5.8) + uncommitted Grade→AcademyClass rename, role consolidation, and admin UI reorg (see §4.2, §5.1, §5.3, §8)
freshness_contract: see .agents/instructions.md — this file must be updated in the same turn/commit that changes the code it describes
NOTE: do not confuse this file with the *in-app* feature also called "knowledge graph"/"knowledge map"
      (templates/admin/knowledge_graph.html, TopicViewSet.tree(), student subject_panel/knowledge_map_panel,
      static/js/student-knowledge-map.js). That is a product feature for visualizing a student's topic mastery.
      This file is meta: it is about the codebase, for an AI agent's own use.
---

# 0. What this system is

Esquared Academy LMS — a Django 5.2 monolith (single app called `app`) that is
simultaneously: student information system, curriculum/syllabus manager,
timetable + lesson log, online assessment engine (papers/attempts/AI-or-rule
autograding), coursework handout/submission/marking workflow, attendance
register, and a role-scoped REST API. There is no separate frontend — the
UI *is* the Django admin (skinned with django-jet-reboot) plus a set of
custom function-based "admin_views" pages bolted on for teacher/student/
examiner workflows that don't fit the generic admin changelist/changeform.

Real-world deployment: a single Windows PC at the school (see README.md's
"Running it day to day" section, setup_academy.bat, start_server.bat). MySQL runs in Docker on that PC;
`runserver` runs in a foreground PowerShell window — not a service. This is
intentionally small-scale, not a cloud SaaS.

Author's voice/style note (relevant when generating new code to match house
style): every module and most non-trivial functions carry a prose docstring
explaining *why*, not just what — "the problem this solves" style, plaintext,
no jargon. New code in this repo should keep that convention.

# 1. Stack

- Django 5.2.17, DRF 3.18 (+ drf-spectacular 0.30 for OpenAPI/Swagger/ReDoc,
  django-filter 26.1), django-jet-reboot 1.3.10 (admin skin, unmaintained
  since Sep 2024 — migration path if it blocks an upgrade: django-unfold or
  django-jazzmin; nothing in admin.py depends on Jet specifically).
- DB: MySQL 8.0.16+/MariaDB 10.5+ in every real env (CHECK constraints need
  8.0.16+; Django 5.2 refuses <8.0.11). Driver: PyMySQL (pure python, shimmed
  as MySQLdb in lms/__init__.py); mysqlclient supported as a faster opt-in.
  Tests run on in-memory SQLite unless DJANGO_TEST_ON_MYSQL=true — SQLite is
  lenient about column types and ignores CHECK constraints, so pre-release
  testing should also run on MySQL.
- Auth: custom user model `app.AppUser` (extends AbstractUser + AuditModel).
  Django's own admin handles accounts/groups/permissions/passwords.
- Media: local filesystem under MEDIA_ROOT, flat-by-kind (see §6).
- No Celery/task queue, no cache backend configured, no frontend build step,
  no JS framework — vanilla templates + a few hand-written JS files under
  static/js/.

# 2. Repo layout (non-generated, non-vendor files only)

```
manage.py
lms/                    # Django project package
  settings.py           # see §3
  urls.py               # see §7 (root URLconf; wires custom admin_views + DRF router)
  asgi.py, wsgi.py, __init__.py (PyMySQL shim)
app/                     # the one Django app — everything lives here
  models.py     (3363 lines) # ALL 46 concrete models + enums. See §4/§5.
  admin.py      (1555 lines) # ModelAdmin registration for every model. See §8.
  admin_views.py (2888 lines) # ~40 function-based views: teacher/student/examiner
                              # workflow pages that are not generic changelist/changeform.
                              # See §9 for the full list + purpose.
  views.py       (995 lines) # DRF ViewSets — one per model, mostly declarative
                              # (serializer_class/filterset_fields/search/ordering),
                              # plus @action endpoints for workflow verbs. See §7.
  serializers.py (280 lines) # `build_serializer()` factory auto-generates most
                              # ModelSerializers; a dozen hand-written ones for
                              # trees/actions/uploads. See §7.
  urls.py        (113 lines) # DRF router registrations -> /api/*
  access.py      (280 lines) # ROLE DEFINITIONS + row-scoping. THE security model. See §5.1.
  audit.py       (48 lines)  # contextvar carrying "current acting user" for AuditModel.save().
  middleware.py  (63 lines)  # TeacherLandingMiddleware: routes /admin/ index by role.
  grading.py     (249 lines) # topic-importance-weighted subject score algorithm. See §5.6.
  files.py       (209 lines) # upload storage paths, MIME/ext classification, photo validation.
  columns.py     (118 lines) # admin changelist column value truncation.
  dashboard.py   (244 lines) # per-role Jet dashboard panels (what each role sees on /admin/).
  entity_help.py (600 lines) # ENTITY_HELP dict: summary/role/context/fields prose per model,
                              # shown behind the "?" button on every admin changelist.
                              # A test enforces every named field actually exists on the model.
  demo_data.py   (133 lines) # deterministic fake school (3 teachers, 20 students, Karachi
                              # names) for the /admin/demo/ page. Void-tagged with "DEMO-" prefix.
  seed_data.py   (951 lines) # static data used by seed_curriculum: the whole Cambridge
                              # O Level/Lower-Secondary curriculum (classes/subjects/topics).
  check_row_scoping.py (120) # standalone security smoke test (NOT test*.py — see §11 for why).
  tests.py      (2213 lines) # Django TestCase suite. See §11.
  templatetags/academy.py    # custom template tags for the admin templates.
  management/commands/*.py   # ops tooling — see §10.
  migrations/0001..0030      # see §4.1 for the notable ones.
templates/admin/*.html       # ~30 templates for admin_views.py pages + admin overrides
static/{css,js}/             # academy-admin.css (WCAG contrast fix for Jet), a few JS files
docs/                        # non-code: syllabi PDFs, setup spreadsheets, a bulk-reset script
setup_academy.bat, start_server.bat, setup_log.txt   # Windows ops scripts (see README.md)
docker-compose.yml           # MySQL 8.4 on port 3307 (for machines already running 5.7 on 3306)
```

# 3. Settings highlights (lms/settings.py)

- `AUTH_USER_MODEL = "app.AppUser"` — every audit FK and every ForeignKey to
  "the user" resolves here.
- `MIDDLEWARE` order matters: `AuthenticationMiddleware` → `app.audit.
  CurrentUserMiddleware` (must be after auth) → ... → `app.middleware.
  TeacherLandingMiddleware` (last, needs auth resolved).
- `RUNNING_TESTS` flag (`"test" in sys.argv`) swaps DATABASES to sqlite
  `:memory:` unless `DJANGO_TEST_ON_MYSQL=true`.
- `REST_FRAMEWORK`: session auth only (`SessionAuthentication`), permission
  classes `[IsAuthenticated, app.access.RolePermission]`, DjangoFilterBackend
  + Search + Ordering, PageNumberPagination @ 50/page.
- `SPECTACULAR_SETTINGS`: title "Esquared Academy API", version "2.0.0",
  schema served at /api/schema/, Swagger at /api/docs/, ReDoc at /api/redoc/.
- `JET_INDEX_DASHBOARD = "app.dashboard.AcademyDashboard"`,
  `JET_APP_INDEX_DASHBOARD = "app.dashboard.AcademyAppIndexDashboard"` —
  both needed or the "App" breadcrumb reverts to Jet's default model-list.
- `JET_SIDE_MENU_ITEMS` — manually grouped to mirror the ERD's 10 domains.
- Upload limits: `FILE_UPLOAD_MAX_MEMORY_SIZE=5MB`, `DATA_UPLOAD_MAX_MEMORY_
  SIZE=20MB`, `UPLOAD_CHUNK_SIZE=5MB` (client-side slicing size for the
  chunked uploader — see §6).
- `TIME_ZONE = "Asia/Karachi"`.
- Secrets/DB creds via `.env` (python-dotenv), `.env.example` documents every
  key, `.env` is gitignored (but exists un-ignored-looking in the working
  tree checked here — treat as local/dev only, never echo its contents).

# 4. Data model

46 concrete models, all inheriting `AuditModel` (abstract) except `PurgeRun`
(deliberately un-audited, immutable log) and `AppUser` (inherits AuditModel
via AbstractUser + AuditModel). Full ER diagram already produced and stored
in the claude.ai Project doc `claude/lms-schema-erd.md` and as
`academy-lms-erd.drawio` in this repo — **read that file for the visual /
field-by-field version**; this section gives the relationships and the
*behavioral* facts a diagram can't show.

## 4.0 AuditModel (abstract base, every table)

Fields: `uuid` (unique, immutable after insert), `created_by`/`date_created`
(stamped once, immutable), `changed_by`/`date_changed` (stamped every
update), `voided` (bool, indexed — soft-delete flag), `active_flag`
(nullable bool, `True` while live / `NULL` once voided — see §4.1 unique-
active pattern), `voided_by`, `date_voided`, `void_reason`.
Managers: `objects` = `ActiveManager` (filters `voided=False` — the default
everywhere), `all_objects` = plain `Manager` (used explicitly where voided
rows must be reachable, e.g. `AuditAdmin.get_queryset` before row-scoping).
Methods: `save()` (re-stamps created_by/date_created from DB on update so
they truly can't change; sets changed_by/date_changed on update via
`app.audit.get_current_user()`), `void(user, reason, save=True)`,
`unvoid(user, save=True)`, `is_voided` (property).
**Nothing is ever hard-deleted.** `has_delete_permission` is False everywhere
in the admin; DRF's `destroy()` calls `void()` instead of deleting.

## 4.1 The soft-delete unique-constraint trick

MySQL has no partial/filtered unique index (`UniqueConstraint(condition=...)`
is a Postgres-only feature Django exposes but MySQL silently can't enforce).
Workaround: helper `unique_active(fields, name)` in models.py builds
`UniqueConstraint(fields=[*fields, "active_flag"])`. Because NULL is
"distinct from every other NULL" in a unique index on MySQL/Postgres/SQLite,
any number of voided rows (`active_flag=NULL`) can share a key while at most
one live row (`active_flag=True`) holds it. **28 constraints** use this
pattern; `active_flag`/`counted_flag` (Attempt's version of the same trick,
for "one counted attempt per student per assignment") are maintained only in
`save()` — never set by hand. A couple of unique constraints (e.g.
`Attempt.attempt_one_counted_uix`) are plain UniqueConstraints that
deliberately DO bind voided rows too — check the model before assuming the
pattern is universal.
Migration history for this: 0002 bootstrap admin → 0003 "mysql_portable_
unique_flags" → 0004-0006 added/populated/finalized `uuid`.

## 4.2 Domains and models (10 groups, matches JET_SIDE_MENU_ITEMS / the ERD)

1. **Identity & people**: `AppUser` (AUTH_USER_MODEL), `Student` (national ID
   type and a second guardian contact are NOT columns — they're
   `StudentAttribute` rows, see §5.8; a `GuardianLinkInline` on `StudentAdmin`
   shows a student's guardians without leaving the page), `Teacher`,
   `GuardianLink` (user ↔ student, `relationship`, `is_primary`,
   `can_view_marks`; still separately registered in admin for its
   `raw_id_fields` lookup, but removed from `JET_SIDE_MENU_ITEMS`/the
   dashboard so it is reached only via the Student inline or by URL).
2. **Curriculum**: `AcademyClass` (renamed from `Grade` on 2026-09-13 —
   same table shape, `db_table="academy_class"`; `level` int, `is_terminal`
   bool — S3 is the only class where students choose subjects; still
   colloquially "grade" in speech, never in code/schema), `Subject`
   (`TopicInline` on `SubjectAdmin` shows its topics without leaving the
   page), `Topic` (self-FK tree, `MAX_DEPTH=4`, materialized `path`/
   `depth`, `clean()` enforces real ancestor not just any Topic id,
   `_reparent_descendants()` rewrites path/depth for the whole subtree on
   move; still separately registered in admin for its own change list and
   the parent-picker autocomplete, but reached day-to-day via the Subject
   inline — removed from `JET_SIDE_MENU_ITEMS`/the dashboard "Curriculum"
   widget), `Syllabus` (one subject+class+year, `status`
   draft/published/retired, `assessable_sections()`/`assessable_topics()`;
   `SyllabusTopicInline` shows its topics), `SyllabusTopic` (syllabus×topic
   join, `weight_pct` — the importance number grading.py uses; also
   separately registered but removed from the menu/dashboard for the same
   reason as Topic).
3. **Enrolment & cohorts**: `Enrolment` (student×class×year, "one class at
   a time" invariant enforced in app code not DB; FK field is
   `academy_class`), `StudentSubject` (enrolment×syllabus — auto-filled
   from core syllabi, chosen only in terminal class; `progress()`),
   `StudentCohort` (temp/permanent group *within one class*),
   `CohortMembership`, `TopicResult` (student's mark on one topic; `status`
   property feeds the in-app "knowledge map" feature — not this file).
4. **Teaching & timetable**: `TeachingAssignment` (teacher×syllabus, `role`),
   `TimetableSlot` (weekly pattern: syllabus/teacher/day/period — Lessons
   are generated FROM this, never edited directly), `Lesson` (one class on
   one date — carries an actual class-timer: `timer_start/pause/stop`,
   `elapsed_seconds`, review workflow `draft→submitted→approved|returned→
   retired` via `submit()/approve()/return_for_changes()`; `carry_forward()`
   pushes unfinished LessonTopics to `next_lesson()`), `LessonTopic`
   (planned vs `covered`, `carried` flag), `LectureItem` (one row of the
   in-lesson lecture table: unit/chapter/topic + an Attachment).
5. **Assessment bank** (question authoring, reusable across papers):
   `EvaluationPrompt` (reusable AI/rule marking instruction) →
   `PromptVersion` (immutable once active; reword = new version_no),
   `Question` (supports multi-part groups via `group`+`order_in_group`+
   `group_stem`). The old 1:1 `BinaryConfig`/`NumericConfig` supertype
   tables are gone — a binary or numeric question's answer-key fields
   (`expected_value`, `tolerance`, `true_label`...) are now
   `QuestionAttribute` rows against `QuestionAttributeType`s filtered by
   `applies_to`, see §5.8. `TEXT` type questions carry no attributes of
   this kind and are AI/teacher marked via prompts.
6. **Papers & attempts** (the online exam engine): `QuestionPaper` (stable
   identity only — holds no questions) → `PaperVersion` (the actual
   editable-while-draft/frozen-once-locked question set; `lock(user)`
   freezes it + pins each item's PromptVersion + totals marks; `clone(user)`
   makes version_no+1 carrying items across) → `PaperItem` (question in a
   slot/page/section, `max_mark`, optionally its own pinned
   `prompt_version`) → `PaperAssignment` (issues a locked version to a
   class or one cohort inside it: time_open/close, time_limit, attempts cap,
   `marking_method` highest/average/first/last, shuffle, is_practice) →
   `Attempt` (one sitting; `is_counted`/`counted_flag` recomputed from
   marking_method) → `Answer` (per paper-item response; boolean/numeric/text
   fields, one used per question type) → `Evaluation` (**append-only**: a
   teacher override inserts a NEW row with `supersedes` pointing at the old
   one rather than editing it — full audit trail of every marking pass,
   method = rule|ai|teacher).
7. **Handouts & submissions** (the coursework/homework workflow — the
   busiest part of the codebase behaviorally): `Handout` (a sheet given out;
   `code` = "SUBJECT-CLASS-YEAR-Hnnn" auto-generated in `save()`/
   `_next_code()`; `kind` assignment/assessment/mock/quarterly;
   `is_exam` property = never shown in advance; weight resolution chain —
   `effective_weight` = weight_override → topic's importance → Standard
   default, implemented in grading.py's `resolve_weight`; deadline logic:
   `deadline_for(enrolment)` checks `HandoutExtension` first, `accepts_
   submission()`/`is_past_due`/`late_window_open`/`lateness()`) →
   `HandoutLesson` (which lessons it belongs to) → `HandoutSheet`
   (versioned file — `add_sheet()` bumps version_no, `is_current` property)
   → `HandoutExtension` (per-student later deadline) → `Submission` (one
   student's hand-in for one round; **state machine**: `submitted →
   grading → marked → (approved|sent_back) `, or `returned` (teacher asks
   for a redo) / `accepted`/`rejected` (unreadable) — see §5.5 for the full
   transition map and who triggers each edge) → `MarkLine` (one row of a
   marks breakdown: label/out_of/awarded/comment/source
   auto|examiner|teacher) → `AutogradeJob` (queued/running/done/failed/
   skipped request to an external autograder; keeps `raw_response` verbatim
   for disputes).
8. **Attachments & comms**: `Attachment` (real stored file; kind
   text/audio/video/picture/other via `files.classify()`; `checksum` SHA-256
   dedupes uploads), `AttachmentLink` (generic FK — content_type+object_id
   — attaches a file to ANY row: question/answer/topic/paper/lesson/
   handout/submission/notice; `role` free text e.g. figure/mark_scheme/
   submission), `UploadSession` (chunked-upload in-progress state:
   open/completed/aborted; `append(data, offset)` guards out-of-order
   chunks; `complete()` turns the assembled part file into an Attachment,
   dedupe-checking SHA-256 first), `Notice` (school noticeboard item;
   `is_live` computed from published_from/until, not a flag).
9. **Attendance**: `AttendanceSession` (one register: academy_class+date+
   period, optional `syllabus` for a single-lesson register vs whole-day;
   `summary` property = counts by status), `AttendanceRecord` (one
   student's mark: present/absent/late/excused/leave, minutes_late).
10. **Ops & retention**: `RetentionPolicy` (one row per table name;
    `purge_enabled` stays False for assessment evidence by policy),
    `PurgeRun` (immutable append-only log of an actual purge — the one
    model with NO AuditModel base and never itself purged).

## 4.3 Enums (models.TextChoices/IntegerChoices) worth knowing by name

`TextFormat` (plain/html/markdown — used on every rich-text field's paired
`_format` column), `QuestionType` (binary/numeric/text),
`ToleranceType` (absolute/relative/geometric — now unused as a model field;
kept alive only as the source of `numeric_tolerance_type`'s
`datatype_config` allow-list in `seed_attribute_types`), `SyllabusStatus`,
`PromptStatus`, `LessonStatus`, `HandoutStatus`, `SubmissionState`,
`TimerStatus`, `DayOfWeek` (Monday=0), `PaperPurpose` (quiz/assignment/exam/
mock), `PaperStatus` (draft/locked/retired), `CohortPurpose`,
`MarkingMethod`, `AttemptState`, `EvalMethod` (rule/ai/teacher),
`HandoutKind`, `MarkSource` (auto/examiner/teacher), `TopicImportance` (INT:
supporting=30, standard=60, core=100 — these numeric values ARE the weights
grading.py uses when a syllabus doesn't set an explicit `weight_pct`),
`NoticeCategory`, `AutogradeStatus`, `SubjectStatus` (studying/passed/
not_taken — feeds Student.subject_history()), `AttendanceStatus`,
`UploadState`, `AttributeDatatype` (text/boolean/integer/decimal/date/
datetime — app/attributes.py, see §5.8; `NationalIdType` is gone, replaced
by a `StudentAttributeType` whose `datatype_config` is the
`"cnic|b_form|passport"` allow-list).

# 5. Core cross-cutting systems

## 5.1 Roles & access control (app/access.py) — READ THIS BEFORE CHANGING PERMISSIONS

Two independent layers:
- **Model permissions** (Django's `add/change/delete/view_<model>`, held by
  Groups, seeded by `manage.py seed_roles`) decide if a role may touch a
  *table* at all. Enforced natively in the admin, and in the API by
  `RolePermission(DjangoModelPermissions)` — note DRF's stock class lets ANY
  authenticated user GET; this subclass requires `view_<model>` even for
  GET/HEAD/OPTIONS (needed because Guest/Guardian are read-only-by-role).
- **Row scoping** (`access.scope_queryset(user, queryset)`) decides *which
  rows* of a permitted table are visible. Called by every DRF list/detail
  AND (since commit f3693ec) by `AuditAdmin.get_queryset` too — this was a
  real fixed bug: the admin used to leak every student's full record to any
  authenticated student because `view_student` had to be granted for a
  student to see their OWN row.

Six roles as of 2026-09-13 (constants `access.ADMINISTRATOR`, `TEACHER`,
`EXAMINER`, `STUDENT`, `GUARDIAN`, `GUEST`) — consolidated from twelve
(`Admin`, `Academic Admin`, `IT Administrator`, `Head of Department`,
`Teaching Staff`, `Paper Setter`, `Marking Reviewer`, `Exam Operations`,
`Non-academic Staff`, `Student`, `Guardian`, `Guest`). The merge:
`Administrator` = the old Admin + Academic Admin + IT Administrator +
Head of Department + Non-academic Staff, given `"all"` permissions in
`seed_roles.ROLE_PERMISSIONS` (a strict superset of what any of the merged
roles had); `Teacher` = old Teaching Staff + Paper Setter (classroom
teaching AND the question bank/draft papers — no longer two roles for one
person); `Examiner` = old Marking Reviewer + Exam Operations (marking
review AND script scanning/upload). Student/Guardian/Guest are unchanged.
`STAFF_ROLES` (`ADMINISTRATOR`, `TEACHER`, `EXAMINER`) are unrestricted by
row scoping — `is_unrestricted(user)` is true for any of them or a
superuser. One person may hold several roles (normal for a small academy),
though the merge means that matters less now than it used to.
`scope_queryset` logic: Guest with no other role → only academyclass/
subject/topic (`GUEST_VISIBLE_MODELS`), else none. Student → own rows via
`_scope_to_students`'s per-model-name lookup-path table (a model missing
from that dict silently gets `queryset.none()` — a common bug source when
adding a new model students should see; the dict is the single source of
truth, in `_scope_to_students`). Guardian → same shape via `_ward_ids`
(GuardianLink rows). Lesson is special-cased for both (only
`status="approved"` visible — course content isn't released until an
Administrator approves it). Notice is special-cased to unfiltered (board is
scoped by class in the view layer, not here).
`may_approve_papers(user)` / `may_approve_lessons(user)` gate the lock/
approve actions — both now keyed to `PAPER_APPROVAL_ROLES =
LESSON_APPROVAL_ROLES = [ADMINISTRATOR]` only: composing (Teacher) and
approving (Administrator) stay two different roles even after the merge —
this was a deliberate design call during the consolidation, not an
oversight, so a Teacher still cannot self-approve their own lesson or
paper.
**Known limitation, stated in the docstring**: department-level scoping was
never implemented (there is no "who heads which subject" table), and is
moot now that the role it would have narrowed (Head of Department) is
folded into Administrator, which is unrestricted by design anyway.

## 5.2 Audit trail plumbing (app/audit.py + app/middleware.py + AuditModel.save())

`app.audit._current_user` is a `contextvars.ContextVar` (not thread-local —
works under async views too). `CurrentUserMiddleware` sets it for the
request's lifetime; `AuditModel.save()` reads `get_current_user()` to stamp
changed_by/date_changed (and created_by on insert if not already set).
Outside a request (management command, shell, tests) it's empty and callers
must pass `created_by=` explicitly. Middleware order requirement: must run
AFTER `AuthenticationMiddleware`.

## 5.3 Teacher/role landing (app/middleware.py)

`TeacherLandingMiddleware` (last in MIDDLEWARE) intercepts GET /admin/ (no
`?home=1` override) for authenticated non-superusers whose roles don't
intersect `DASHBOARD_ROLES = {ADMINISTRATOR}`: Teacher → `/admin/home/`
(teacher_home_view), Student → `/admin/my-work/`, Examiner →
`/admin/checking/`.

## 5.4 File storage (app/files.py)

One MEDIA_ROOT, flat per-kind subfolders (`text/audio/video/picture/other/
_incoming/`). Stored filename = `<uuid><ext>` (never the original name —
avoids collisions and leaks nothing about content). `classify(mime, ext)`
prefers MIME, falls back to extension (browsers send wrong/empty MIME often).
Person photos (Student.photo, Teacher.photo): two-stage validation in strict
order — **must be square** (`validate_person_photo` checks width==height
FIRST, raises `not_square` before ever checking size — the rationale in the
docstring: telling someone to crop AND compress at once is confusing when
cropping changes the size anyway), then **must be ≤100KB**
(`PHOTO_MAX_BYTES`). `sha256_of()` streams in 1MiB blocks for dedup
checksums (used by both direct-upload `AttachmentViewSet.create` and
chunked `UploadSession.complete`).

## 5.5 Handout/Submission state machine (models.py Handout + Submission)

Handout: `draft → active` (`activate()`, stamps date_activated/activated_by)
`→ closed` (`close()`) `→ retired`. `can_unpost` only while `has_submissions`
is False. Submission (per round): `submitted → grading` (`start_checking()`
— examiner opens it, file becomes immutable) `→ marked` (`mark()`) then
either `→ approved` (`approve()` — class teacher releases to student,
COUNTS toward grading.py) or `→ sent_back` (`send_back_to_examiner()` —
teacher disputes the mark, back to examiner) or the approved/marked result
can become `→ returned` (`request_redo()` — teacher asks student to redo;
next round_no submission supersedes). Also `accepted`/`rejected` terminal
states for exam-operations intake (unreadable scripts etc — see
EXAM_OPERATIONS role). Only `SubmissionState.APPROVED` and `.ACCEPTED` are
`COUNTED_STATES` in grading.py — a mark sitting with the examiner never
moves a student's visible average.

## 5.6 Grading algorithm (app/grading.py) — the most conceptually dense module

Two-level weighted average, deliberately NOT a flat sum of raw marks:
```
topic score    = mean(percentage of each of that topic's counted submissions)
subject score  = Σ(topic score × topic importance) / Σ(topic importance)
```
Averaging within-topic first stops a heavily-taught topic (many sheets) from
drowning out a lightly-taught one purely by volume; importance (`weight_pct`
on SyllabusTopic, else `Handout.topic_importance` inherited from the topic's
own field, else `TopicImportance.STANDARD=60`) is the one deliberate,
curriculum-level signal — set when planning the year, never invented per-
paper. `resolve_weight(handout)`: `weight_override` on the handout wins,
else the syllabus's per-topic `weight_pct`, else inherited topic importance,
else Standard(60); a handout with `counts_toward_grade=False` (practice
work) always resolves to weight 0 (visible, but excluded from the average).
Coursework (`HandoutKind.ASSIGNMENT`) and exams (`ASSESSMENT|MOCK|
QUARTERLY`) are aggregated and reported SEPARATELY — deliberately never
blended into one number, because the ratio is a school policy decision, not
an arithmetic default this code should make quietly. `_live_submissions()`
takes the LATEST round per handout among counted-state submissions (a redo
supersedes, doesn't average with, the original). `subject_score()` returns
`None` (not 0) when nothing is released yet — callers must not render None
as zero. Entry points: `topic_weights`, `topic_scores`, `subject_score`,
`subject_summary` (one report line, with topic breakdown for a UI),
`student_report(enrolment)` (every subject for one enrolment).

## 5.7 Admin plumbing shared by every model (app/columns.py, entity_help.py)

`TruncatedColumnsMixin` (mixed into `AuditAdmin`): wraps every
`list_display` string column so long text doesn't blow out the changelist
table — `shorten()` truncates with an ellipsis. `entity_help.ENTITY_HELP`
dict (keyed by `model._meta.model_name`) supplies the summary/role/context/
field-notes shown behind the "?" on every changelist
(`AuditAdmin.changelist_view` injects it); `EntityHelpFieldTests` in
tests.py asserts every field named there actually exists on the model, so
this cannot silently drift from models.py.

## 5.8 Attribute-type/attribute pattern (app/attributes.py) — how optional fields are added now

Modeled on OpenMRS's `location`/`location_attribute_type`/
`location_attribute`. `app/attributes.py` (imports nothing from
`models.py`, to avoid a circular import) defines: `AttributeDatatype`
(closed TextChoices set: text/boolean/integer/decimal/date/datetime —
narrower than OpenMRS's pluggable datatype classes, deliberately, since
this codebase doesn't need that generality); `to_python`/`to_storage`
(text ⇄ real value conversion); `validate_raw(datatype, raw,
datatype_config=None)` (raises `ValidationError`; for TEXT with a
non-empty `datatype_config`, the config is read as a `|`-separated
choice allow-list — this is how a closed choice set like the old
`national_id_type` is expressed, since there's no dedicated CHOICE
datatype); abstract `BaseAttributeType(models.Model)` (fields: `name`,
`short_name` [the stable lookup key — changing it orphans existing
values], `description`, `datatype`, `datatype_config`, `min_occurs`,
`max_occurs`, `sort_order`, `visible`; methods `python_value`/
`storage_value`); abstract `BaseAttribute(models.Model)` (field:
`value_reference` TextField; methods `get_value()`/`set_value(v)` that
resolve through `self.attribute_type`; `clean()` calls `validate_raw`).

Both base classes are plain `models.Model`, NOT `AuditModel` — concrete
pairs in `models.py` use multiple inheritance to add the audit block:
`class QuestionAttributeType(AuditModel, BaseAttributeType)`. Two pairs
exist so far, both per-entity (OpenMRS-exact, not one shared generic
pair, per an explicit design decision):

- `QuestionAttributeType`/`QuestionAttribute` — replaces the old
  `BinaryConfig`/`NumericConfig` tables. `QuestionAttributeType` adds
  `applies_to` (nullable `QuestionType` choice; null = any type).
  `QuestionAttribute` FKs `question`+`attribute_type`, unique together
  (live rows). Seeded by `seed_attribute_types` with 12 types (4 binary:
  `binary_expected_value`/`binary_true_label`/`binary_false_label`/
  `binary_true_feedback`; 8 numeric: `numeric_expected_value`/
  `numeric_tolerance_type`/`numeric_tolerance`/`numeric_partial_band`/
  `numeric_partial_fraction`/`numeric_unit`/`numeric_unit_penalty`/
  `numeric_significant_figures`).
- `StudentAttributeType`/`StudentAttribute` — replaces
  `Student.national_id_type`/`Student.guardian_contact_2`. No
  entity-specific extra field on the type. Seeded with 2 types:
  `national_id_type` (TEXT, `datatype_config="cnic|b_form|passport"`),
  `guardian_contact_2` (TEXT).

Both admin forms have a `TabularInline` for the attribute (
`QuestionAttributeInline` on `QuestionAdmin`, `StudentAttributeInline` on
`StudentAdmin`); both `<Entity>AttributeType` models get their own plain
`AuditAdmin` registration so staff can add a new type without a
migration. `app/management/commands/import_setup.py` sets Student
attributes through a `set_student_attribute(student, short_name,
raw_value)` helper (creates/updates/voids a `StudentAttribute` row)
rather than direct field assignment — the student row must already be
saved (has a pk) before this is called.

**Adding a new optional/descriptive field to Question or Student from
here on is a new attribute type (admin, or a `seed_attribute_types.py`
entry), not a migration.** The same recipe is intended for other
entities' descriptive fields (`AcademyClass`/`Subject`/`Topic.description`,
`Handout`'s free-text fields) as later follow-ups — not done yet, so
those are still plain columns as of this writing. Structural fields
(FKs, workflow state, anything `access.py`/`grading.py` reads) are
deliberately NOT candidates for this pattern — only descriptive/optional
fields move.

# 6. Uploads

Two paths, same storage/dedup logic underneath: (a) small file → `POST
/api/attachments/` multipart, straight to `AttachmentViewSet.create`; (b)
large file → chunked: `POST /api/uploads/` (returns uuid+chunk_size) → `PUT
/api/uploads/{uuid}/chunk/` (raw bytes, `X-Chunk-Offset` header, must equal
`received` so far) repeated → `POST /api/uploads/{uuid}/complete/` (assembles
part file into an Attachment; SHA-256 dedup — same content returns the
EXISTING Attachment rather than storing twice). Admin also has a drag-drop
uploader at `/admin/app/attachment/upload/` using the same chunk size
(`UPLOAD_CHUNK_SIZE`, default 5MB) client-side.

# 7. URL / API surface

Root URLconf `lms/urls.py`: `/` → redirect to admin index; `/admin/*` →
Django admin (Jet-skinned) PLUS ~20 hand-wired custom paths (all wrapped in
`admin.site.admin_view(...)`, i.e. staff-login-required, defined via lambdas
importing from `app/admin_views.py` — see §9 for what each does);
`/api/*` → DRF router (`app/urls.py`, one `register()` per model, standard
list/create/retrieve/update/partial_update/destroy(=void)/void/unvoid on
every viewset, PLUS resource-specific `@action` endpoints — full list is in
the app/urls.py module docstring, reproduced here since it's the fastest
reference:
```
POST /api/paper-versions/{id}/lock/ | /clone/
GET  /api/students/{id}/enrolments/
GET  /api/syllabi/{id}/topics/
GET  /api/questions/{id}/group_parts/
GET  /api/attempts/{id}/answers/
GET  /api/answers/{id}/evaluations/
POST /api/handouts/{id}/activate/ | /close/     GET .../completion/
POST /api/lessons/{id}/submit/ | /approve/ | /return_for_changes/
POST /api/attendance-sessions/{id}/mark/
POST /api/uploads/  PUT /api/uploads/{uuid}/chunk/  POST .../complete/
GET  /api/topics/tree/?subject=<id>   (whole nested topic tree in one query)
GET  /api/topics/{id}/children/ | /subtree/ | /ancestors/
GET  /api/cohorts/{id}/members/
```
`/api/schema/` (OpenAPI YAML), `/api/docs/` (Swagger), `/api/redoc/`,
`/api-auth/` (DRF browsable-API session login).
ViewSet base class `AuditedModelViewSet(viewsets.ModelViewSet)`
(app/views.py): `get_queryset()` runs `access.scope_queryset`; `destroy()`
voids instead of deleting; `void`/`unvoid` `@action`s; permission_classes
`[IsAuthenticated, access.RolePermission]`. Every concrete ViewSet is a thin
subclass declaring `serializer_class` + `filterset_fields`/`search_fields`/
`ordering_fields` — genuinely boilerplate, safe to pattern-match when adding
a model. Serializers: most are produced at import time by
`serializers.build_serializer(model, name=None, depth=0)` (locks audit
fields read-only); ~14 are hand-written for trees, void/lock payloads,
uploads, and attendance bulk-marking.

# 8. Django admin (app/admin.py)

`AuditAdmin(TruncatedColumnsMixin, admin.ModelAdmin)` is the base for every
ModelAdmin: read-only audit fields (`AUDIT_READONLY` = all audit fields
except `voided`/`void_reason`), `IncludeVoidedFilter` (a checkbox, not a
dropdown — unticked = live rows only, ticked = live+voided together, no
"voided only" mode by design), `void_selected` bulk action,
`has_delete_permission` hard-wired False, `get_fieldsets` auto-moves the
audit fields into a collapsed "Audit" fieldset last on every form,
`get_queryset` = `access.scope_queryset` applied over `all_objects` (this is
the row-scoping fix mentioned in §5.1), `changelist_view` injects
`entity_help.help_for(self.model)` into context for the "?" popover,
`save_model` stamps changed_by/created_by. `PhotoAdmin(AuditAdmin)` is a
second-level base for Student/Teacher (avatar thumbnail column + photo
validation UI). Every model has its own registered `<Model>Admin` (list at
grep `^class.*Admin` in app/admin.py — 44 registrations, unchanged by the
2026-09-13 curriculum-widget reorg below since nothing was unregistered,
only removed from menus); inlines used heavily for parent/child pairs
(SyllabusTopicInline on Syllabus, TopicInline on Subject and
GuardianLinkInline on Student — both added 2026-09-13 so a subject's topics
and a student's guardians edit in place instead of needing their own
changelist visit, TopicResultInline on StudentSubject, PromptVersionInline
on EvaluationPrompt, QuestionAttributeInline + AttachmentLinkInline on
Question, StudentAttributeInline on Student (see §5.8), PaperItemInline on
PaperVersion, Lecture/LessonTopicInline on Lesson, HandoutLessonInline on
Handout, CohortMembershipInline on StudentCohort, Answer/EvaluationInline
on Attempt/Answer, AttendanceRecordInline on AttendanceSession, generic
`AttachmentLinkInline` reused across most content models). Topic,
SyllabusTopic and GuardianLink stay independently registered (an inline's
`raw_id_fields`/`autocomplete_fields` lookup needs the target model's own
`ModelAdmin` to exist) but were removed from `JET_SIDE_MENU_ITEMS` (lms/
settings.py) and from the dashboard "Curriculum"/"People" `ModelList`
widgets (app/dashboard.py) — reachable by URL and via the inline, not from
the menu or the homepage cards.

# 9. Custom admin pages (app/admin_views.py, wired in lms/urls.py)

All are plain function views `(request, admin_site)` (or with an extra id
arg), wrapped by `admin.site.admin_view` in urls.py — i.e. staff-login-
required but NOT tied to one model's changelist/changeform. Grouped by who
uses them:

- **Teacher**: `teacher_home_view` (/admin/home/, the one landing page —
  "six ways in and nothing else"), `my_day_view` (/admin/my-day/ — today +
  rest of week + needs-attention, with `_decorate`/`_decorate_full` building
  the lesson-card view model, timer start/pause/stop posted via
  `_my_day_post`), `calendar_view` (/admin/calendar/, month grid),
  `my_subjects_view` (/admin/my-subjects/, one row per subject×class
  taught, via `_syllabi_for`), `lesson_materials_view` (upload straight onto
  a lesson — the generic admin inline can only link an existing file),
  `assignments_view` (/admin/assignments/, one card per class), `browse_view`
  (/admin/browse/, class→subject→topic→lectures/assignments drill-down).
- **Handouts**: `new_handout_view` (set a sheet for a lesson in one screen,
  `_set_sheet`/`_link_file`/`_detach_file` helpers), `handout_view`
  (/admin/handout/{id}/ — the sheet, print count, who's handed in),
  `handout_print_view` (cover sheet for photocopying),
  `handout_extend_view` (grant named students a later deadline).
- **Examiner role**: `checking_browse_view`
  (/admin/checking/, class→subject→assignment drill-down),
  `checking_queue_view` (/admin/checking/waiting/, oldest-first flat queue),
  `checking_assignment_view` (one assignment, every hand-in + status via
  `_submission_status`), `check_submission_view` (the actual marking
  screen — reads work, writes MarkLine rows via `_apply_mark_edits`,
  handles PDF detection via `_is_pdf` for inline preview).
- **Teacher sign-off**: `approvals_view` (/admin/approvals/ — examiner-
  checked marks awaiting teacher release; gated by `_may_approve`).
- **Student**: `my_work_view` (/admin/my-work/ — what's open + hand-in
  form).
- **Notices**: `notice_board_view` (student-facing board),
  `post_notice_view` (Teacher/Administrator posting, gated by
  `_may_post_notices`).
- **Ops/demo**: `demo_view` (/admin/demo/ — load/remove the fictional demo
  school via `demo_data.py`, `_plan`/`_counts` build the preview before
  committing).

Helper naming convention: leading-underscore functions are private view-
model builders local to one screen; none are imported elsewhere except
`grading` module functions and `access` role checks.

# 10. Management commands (app/management/commands/)

| command | purpose |
|---|---|
| seed_roles | create the 6 role Groups + their model permissions (run once per fresh DB) |
| seed_attribute_types | create the initial QuestionAttributeType/StudentAttributeType rows (12 + 2) — see §5.8; idempotent on `short_name` |
| seed_curriculum | load the full Cambridge curriculum from seed_data.py: classes/subjects/topics/syllabi for a year (`--year`, `--dry-run`) |
| seed_demo | load/remove the fictional demo school |
| seed_today | put one realistic lesson on today's date (so My Day isn't empty in dev) |
| seed_test_users | one test account per role for manual browser testing |
| seed_student_logins | create login accounts for imported students |
| import_setup | load the filled-in `Esquared_LMS_Setup` Excel workbook (docs/Esquared_LMS_Setup.xlsx) — the real onboarding path |
| load_syllabus_content | load O-Level syllabus content (docs/syllabus_content.json) into subjects/topics |
| generate_lessons | turn the weekly TimetableSlot pattern into real dated Lesson rows |
| backfill_sheets | give pre-existing handouts a version-1 HandoutSheet retroactively |
| set_subject_names, set_syllabi, set_syllabus_topics | one-off/data-fix commands for subject naming, per-year syllabus assignment, and syllabus↔topic linking |
| prune_students, prune_subjects, prune_topics | VOID (never delete) rows no longer on the school's current list |
| account_status | report who can log in / still needs a password |
| reset_login | show + optionally set one account's password |
| reset_dashboards | clear saved Jet dashboard layouts so they rebuild from current code |
| role_audit | print what each role can actually see, for manual review |

Windows ops wrapper: `setup_academy.bat` runs migrate → seed_roles →
seed_attribute_types → import_setup → seed_student_logins →
generate_lessons → account_status in order, logs to setup_log.txt, is safe
to re-run (idempotent by design of each command). `start_server.bat`
starts the Docker MySQL container then `runserver` in the foreground.

# 11. Tests

`app/tests.py` (2213 lines, ~30 TestCase classes, in-memory SQLite by
default). Notable classes: `Fixture` (shared base building a minimal
class/subject/syllabus/enrolment set), `PaperVersioningTests`,
`CountedAttemptTests`, `VoidingTests`, `ApiTests`, `SeedCurriculumTests`
(asserts the real curriculum numbers — 618 topics etc, see README), `Audit*
Tests` (block/api/admin), `AttachmentTests`, `AttendanceTests`, `RoleTests`,
`EntityHelp*Tests` (field-existence enforcement, see §5.7),
`TopicHierarchyTests`/`TopicParentPickerTests`, `KnowledgeGraphTests` (this
is the IN-APP topic-tree feature, not this .agents/ file — see the note at
top), `IncludeVoided*Tests`, `DemoData/DemoPageTests`, `PhotoRuleTests`,
`StudentSubjectHistoryTests`/`StudentPageTests`,
`AssessableTopicTests`/`CompletionTests`/`MarkingGridTests`/
`KnowledgeMapDataTests` (grading.py + Handout.completion() coverage),
`DemoMarkTests`, `AttributeTests` (app/attributes.py: datatype round-trip
for each `AttributeDatatype`, blank→None, the TEXT+`datatype_config`
choice allow-list, the one-value-per-entity-per-type uniqueness
constraint, `applies_to` filtering — see §5.8).

`app/check_row_scoping.py` is a **standalone** security smoke test, run
directly (`python -m app.check_row_scoping`), NOT via `manage.py test` — its
filename deliberately avoids the `test*.py` glob because it builds its own
test database at import time via `DiscoverRunner`, and being auto-collected
made it run twice inside an already-started suite and crash it. It logs in
as a student and a teacher and asserts the student can't see another
student's identity fields/marks anywhere (list or direct object access) and
that the teacher's own access wasn't accidentally narrowed by the same fix.
Treat this file as the canonical regression test for any change to
`access.scope_queryset` or `AuditAdmin.get_queryset` — run it whenever
either changes, in addition to `manage.py test`.

Run tests: `python manage.py test` (sqlite) or
`DJANGO_TEST_ON_MYSQL=true python manage.py test` (before any release).

# 12. Notable design decisions / gotchas an agent should not "fix"

- Soft-delete-only, everywhere. Never add a hard delete path; add `void()`.
- `active_flag`/`counted_flag` are derived/maintained columns — never set
  them directly in new code; they're recomputed in `save()`.
- Versioned-immutable pattern appears three times with the same shape
  (draft→locked/active, clone-to-next-version-on-edit): `PaperVersion`,
  `PromptVersion`, `HandoutSheet`. If adding a fourth versioned entity,
  follow this shape rather than inventing a new one.
- `Evaluation` is append-only by design (audit trail of every marking pass)
  — never update an Evaluation row in place; insert a new one with
  `supersedes` set.
- Row-scoping's `_scope_to_students` lookup-path dict in access.py is the
  single source of truth for "can a student/guardian see this model at
  all" — a new student/guardian-visible model MUST be added there or it
  silently becomes invisible (`queryset.none()`), which reads as "working"
  (empty list, no error) rather than failing loudly.
- `entity_help.ENTITY_HELP` field names are tested against the live model —
  keep them in sync or `EntityHelpFieldTests` fails.
- Department-level admin scoping was never implemented (no schema support)
  and is now moot: the role it would have narrowed (Head of Department) is
  folded into Administrator, which is unrestricted by design — documented
  in access.py's module docstring.
- `.env` holds real local secrets in this working tree; never print/commit
  its contents, and don't assume `.env.example`'s defaults are what's
  actually configured.
- The bootstrap superuser (`admin`/`admin`, migration 0002) is a known
  first-run-only credential; production must override
  `DJANGO_BOOTSTRAP_ADMIN_PASSWORD` or disable it — flag it if you ever see
  it still active in something that looks like a live deployment.
- Optional/descriptive fields are attribute-type/attribute pairs
  (app/attributes.py, §5.8), not new columns — this is the reference
  pattern now, following OpenMRS's location/location_attribute_type/
  location_attribute shape. Only `Question` and `Student` have been
  converted; `AcademyClass`/`Subject`/`Topic`'s `description` fields and
  `Handout`'s free-text fields are known follow-up candidates using the
  exact same recipe, not yet done. Structural fields (FKs, workflow
  state, anything `access.py`/`grading.py` reads) stay real columns —
  don't attributize those.
- `Grade` was renamed to `AcademyClass` on 2026-09-13 (model class, every
  FK and attribute — `enrolment.grade` is now `enrolment.academy_class`,
  etc — table `academy_class`, API resource `/api/academy-classes/`,
  admin URL `/admin/app/academyclass/`). "Grade" survives only where it
  means a mark/score (`Handout.counts_toward_grade`, `app/grading.py`,
  `AutogradeJob`) — those are a different, colloquial sense of the word
  and were deliberately left alone. If you see a bare `grade` identifier
  anywhere else in this codebase going forward, it is a bug, not a
  pre-existing pattern to match.
- All migrations were squashed to a fresh `0001_initial` + `0002_
  bootstrap_admin` on 2026-09-13, twice in the same day (no real
  production data existed yet, by design): once after the attribute-type
  refactor, again after the Grade→AcademyClass rename + role consolidation
  + admin UI reorg landed together. Don't assume old migration
  numbers/names from before that date mean anything; the dev database
  must be dropped and recreated once, after which normal incremental
  migrations resume.

# 13. Related artifacts (already produced, don't regenerate blindly)

- ERD (visual, field-level): claude.ai Project doc
  `claude/lms-schema-erd.md` describes an `academy-lms-erd.drawio` meant
  to live at the repo root — but as of 2026-09-13 that file is NOT
  actually present in this repo (it seems to have only ever been
  delivered as a chat attachment, never committed). The write-up text has
  been kept current (attribute-type refactor, then the Grade→AcademyClass
  rename + 6-role model + admin UI reorg), but the diagram itself has
  never been regenerated to match — the "where's the file" gap and the
  "diagram not regenerated" gap are both still open. If you (or Uzair)
  need the actual diagram, it has to be built fresh against the current
  `models.py`, not "updated" from a prior file, and should be saved into
  the repo this time so this gap doesn't repeat.
- This file + `.agents/instructions.md` are new as of 2026-09-13.
