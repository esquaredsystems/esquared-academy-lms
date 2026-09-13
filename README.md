# esquared-academy-lms
Knwoledge and Learning management system for Esquared Academy

## Running

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the MySQL credentials
mysql -e "CREATE DATABASE esquared_lms CHARACTER SET utf8mb4"   # or: docker compose up -d db
python manage.py migrate      # also creates the admin / admin superuser
python manage.py seed_roles   # the six roles
python manage.py seed_attribute_types   # the optional-field/answer-key attribute types
python manage.py seed_curriculum
python manage.py runserver
```

Migration `0002_bootstrap_admin` creates a superuser on a fresh database —
`admin` / `admin` by default — so `/admin/` is reachable straight after
`migrate`. **Change that password before the database is reachable by
anyone but you.** Set `DJANGO_BOOTSTRAP_ADMIN_PASSWORD` (or
`DJANGO_BOOTSTRAP_ADMIN=false`, and use `manage.py createsuperuser`) in
any deployed environment. The migration is a no-op if a superuser already
exists.

User management itself is Django's own: accounts, groups, permissions and
password changes all live in `/admin/`, and `AppUser` extends
`AbstractUser`, so nothing about that had to be rebuilt.

Configuration is read from `.env` via python-dotenv. `.env` is git-ignored;
`.env.example` lists every key and is committed.

MySQL 8.0.16+ (or MariaDB 10.5+) is the database in every real environment.
Django 5.2 refuses to start on anything below 8.0.11, and CHECK constraints
only became real in 8.0.16 — older servers parse them and silently ignore
them, which would turn several of the model constraints into decoration.
MySQL 5.7 will not work.

If your machine already runs MySQL 5.7 for other projects, `docker-compose.yml`
starts an 8.4 server on port **3307** beside it, leaving 3306 alone:

```bash
docker compose up -d db
# then set MYSQL_PORT=3307 in .env
```

The driver is `PyMySQL`, a pure-Python implementation of the `MySQLdb`
interface — nothing to compile, no Homebrew prerequisites. `lms/__init__.py`
registers it under the `MySQLdb` name that Django expects.

`mysqlclient` is faster and is Django's reference driver; if you want it
instead, install the client library first and the shim will step aside:

```bash
brew install mysql-client pkg-config
export PKG_CONFIG_PATH="$(brew --prefix mysql-client)/lib/pkgconfig"
pip install mysqlclient
```

## Running it day to day (the school's deployment)

The academy runs this on one Windows PC, not a server. Two programs have to
be running for the site to work:

| What | Where it runs | How you start it |
|---|---|---|
| **The database** (MySQL) | Inside Docker | Docker Desktop, container `esquared-mysql` |
| **The web server** (Django) | A PowerShell window | `start_server.bat` |

The web server is **not** a service. It runs only while its window is open.
Close the window, restart the PC, or let the machine sleep, and the site
stops — and the browser then says the page cannot be reached. That is
normal, and starting it again is the whole fix.

**Every day: starting the site.** Double-click `start_server.bat`. It
starts the database, then the web server, and leaves the window open. Then
go to `http://127.0.0.1:8000/admin/`. Leave that black window open while
anyone is using the site; close it or press Ctrl+C to stop. Typed out
instead:

```powershell
cd C:\Users\uzair\OneDrive\Documents\GitHub\esquared-academy-lms
venv\Scripts\python.exe manage.py runserver
```

**After the code changes: `setup_academy.bat`.** Double-click it. It runs,
in order: database migrations, the six roles, the attribute types
(the answer-key fields on a question, and a student's optional fields —
see "Attribute types" below), the import of staff, students, subjects and
the timetable, student logins, this fortnight's lessons, and an account
report — then asks you to set the teacher's password. Everything in it is safe to run again: each step checks what is
already there and updates rather than duplicating. It writes
`setup_log.txt` beside itself, so the result survives the window closing.
Run it when you have just pulled new code, rebuilt the database, or
changed `docs/setup_data.json`.

**Passwords.** Accounts are created **without** a password and cannot be
used until one is set — deliberately; no script ever invents a password.

```powershell
# set one account's password (prompts twice; nothing appears as you type)
venv\Scripts\python.exe manage.py reset_login uxair.ahm --set

# see who can actually log in and who is still waiting
venv\Scripts\python.exe manage.py account_status
venv\Scripts\python.exe manage.py account_status --pending
venv\Scripts\python.exe manage.py account_status --role Student

# create an account that doesn't exist yet, with a role, password in one go
venv\Scripts\python.exe manage.py reset_login someone --set --create --role "Teacher"
```

Teachers sign in with a name (`uxair.ahm`, `samyanconsole`, `sid.marium`,
`adan.salahuddin`, `rabia.basaria`, `usama.khan`). Students sign in with
their **admission number** (`26070108` and up). The full list is in
`docs/Esquared_Academy_Logins.xlsx`.

**Lessons and the timetable.** Lessons are built from the weekly timetable
by `generate_lessons` — without them a teacher's **My day** is empty:

```powershell
venv\Scripts\python.exe manage.py generate_lessons --weeks 2
venv\Scripts\python.exe manage.py generate_lessons --from 2026-09-21 --to 2026-10-02
venv\Scripts\python.exe manage.py generate_lessons --weeks 2 --dry-run
```

Run it every couple of weeks to extend the term. It never touches a lesson
a teacher has already written on. If a class has no lessons, the timetable
itself is probably missing rows — fill in the **Timetable** sheet of
`docs/Esquared_LMS_Setup.xlsx`, re-run `setup_academy.bat`, then
`generate_lessons` again.

**Tidying the roll.** The academy's roll is `docs/keep_students.txt` — 99
admission numbers. Anything else with a student login (demo data, test
accounts) is surplus:

```powershell
venv\Scripts\python.exe manage.py prune_students             # reports only
venv\Scripts\python.exe manage.py prune_students --commit     # retires the surplus
```

Nothing is ever deleted — accounts are voided, so they can be brought back
by unvoiding them in the admin.

**When something goes wrong.**

- *"This site can't be reached" / the page never loads* — the web server
  isn't running. Double-click `start_server.bat`.
- *The page loads but shows a database error* — the web server is fine;
  MySQL isn't. Start Docker Desktop, wait for it to settle, then run
  `start_server.bat` again.
- *"No account called ..."* — that account doesn't exist yet. Run
  `account_status` to see what does.
- *A password is refused even though you just set it* — the account has
  no role, so the admin login refuses it. Give it one:
  `reset_login <name> --set --role "Teacher"`.
- *A yellow Django error page* — read the black PowerShell window; the
  real error is printed there, and the last few lines are the part that
  matters.

Two rules worth keeping in mind: never put anything from `.env` into a
message, a screenshot or a commit — the database password lives there —
and treat the black PowerShell window as the source of truth: every page
request appears in it, and every error prints there in full.

## Seeding the curriculum

```bash
python manage.py seed_curriculum              # current calendar year
python manage.py seed_curriculum --year 2027
python manage.py seed_curriculum --dry-run
```

Loads the Cambridge curriculum as taught in Pakistan: five classes (E1, E2 =
Lower Secondary stages 7–8; S1–S3 = the O Level programme, S3 terminal), 18
subjects, 618 topics and 48 syllabi for the year — 348 syllabus/topic links.

156 of those topics are top-level syllabus sections; the other 462 are
sub-topics, seeded wherever Cambridge publishes a second level:

| Subject | Second level | Count |
|---|---|---|
| Mathematics D 4024 | numbered sub-topics | 68 |
| Biology 5090 | numbered sub-topics | 52 |
| Chemistry 5070 | numbered sub-topics | 49 |
| Pakistan Studies 2059 | 16 Key Questions + 25 Paper 2 headings | 41 |
| Economics 2281 | numbered sub-topics | 39 |
| Accounting 7707 | numbered sub-topics | 27 |
| History 2147 | focus points under the six Key Questions | 26 |
| Physics 5054 | numbered sub-topics | 25 |
| Business Studies 7115 | numbered sub-topics | 25 |
| Computer Science 2210 | numbered sub-topics | 21 |
| Geography 2217 | numbered sub-topics | 19 |
| Global Perspectives 1129 (LS) | framework sub-strands | 18 |
| English 0861 (LS) | framework sub-strands | 17 |
| Science 0893 (LS) | framework sub-strands | 16 |
| English 1123 | assessment objectives R1–R5, W1–W5 | 10 |
| Mathematics 0862 (LS) | framework sub-strands | 9 |

Four subjects stay flat, deliberately, and the note on each seed entry says
why:

- **Additional Mathematics 4037** prints no titled sub-topics — its second
  level is full-sentence learning outcomes.
- **Art & Design 6090** repeats two rubric headings under every area of study
  rather than naming distinct content.
- **Islamiyat 2058** publishes named sub-headings for only three of its eight
  sections, and the research pass read those inconsistently. Scripture
  references are not something to seed on a shaky reading.
- **Urdu 3247** already sits at its published second level; below it are set
  texts that change by series and are printed in Urdu script.
- **Computing 0860 (LS)** publishes no sub-strands at all — objectives hang
  straight off the five strands.

Physics also numbers a third level (1.5.1, 4.5.1 …). Only the second level is
seeded, matching every other subject.

## Attribute types

```bash
python manage.py seed_attribute_types
python manage.py seed_attribute_types --dry-run
```

Two entities carry optional fields as attributes rather than columns, on the
model OpenMRS uses for `location`/`location_attribute_type`/
`location_attribute`: `Question` (the true/false and numeric answer-key
fields that used to be the separate `BinaryConfig`/`NumericConfig` tables)
and `Student` (national ID type, second guardian contact). Each has an
`<Entity>AttributeType` table naming the property and its datatype
(text, yes/no, whole number, decimal, date, or date+time — a closed set,
narrower than OpenMRS's pluggable datatype classes) and an `<Entity>Attribute`
table holding one value per entity per type, stored as text and resolved to
a real Python value through the type's datatype (`app/attributes.py`).

`seed_attribute_types` creates the initial types — the ones a fresh install
needs to behave like the old fixed-column schema. It is idempotent, matched
on each type's `short_name`, so editing a label or a `datatype_config` in
`app/management/commands/seed_attribute_types.py` and re-running it updates
the existing row rather than duplicating it.

Adding a new optional field to Question or Student from here on is a new
attribute type — a row added through the admin (Question attribute types /
Student attribute types) or a new entry in that command — not a migration.
The same recipe applies to any other entity's descriptive fields; Question
and Student are the two done so far.

## Files and attachments

All uploads live under one root — `MEDIA_ROOT` in `.env`, defaulting to
`<project>/media` — in a flat folder per kind:

```
media/
  picture/   images
  video/
  audio/
  text/      documents, PDFs included
  other/
  _incoming/ chunks of uploads in progress, never served
```

Stored names are the attachment's uuid plus the original extension, so two
files called `diagram.png` never collide and a filename on disk gives nothing
away. The original name is kept on the row. A file's kind comes from its MIME
type, falling back to its extension, because browsers get the MIME type wrong
often enough to matter.

`AttachmentLink` attaches a file to any row — a question, an answer, a topic,
a paper — with a `role` (`figure`, `mark_scheme`, `submission`), so no model
grows its own file columns.

**Uploading.** The admin has a drag-and-drop uploader at
`/admin/app/attachment/upload/`, linked from the attachment list. It slices
files into 5 MB chunks (`UPLOAD_CHUNK_SIZE`) and sends them one at a time, so
file size is bounded by disk rather than by the request body limit, and an
interrupted upload can resume from the byte count the server reports. The same
thing is available over the API:

```
POST /api/uploads/                    → {uuid, chunk_size}
PUT  /api/uploads/{uuid}/chunk/       raw bytes, X-Chunk-Offset header
POST /api/uploads/{uuid}/complete/    → the stored attachment
```

Small files can go straight to `POST /api/attachments/` as multipart. Either
way, a file whose SHA-256 already exists returns the existing attachment
rather than storing a second copy.

In production the web server (or object storage) serves `MEDIA_ROOT`;
`runserver` only serves it because `DEBUG` is on.

## Attendance

`AttendanceSession` is one register: a class, a date, a period. Leave
`syllabus` empty for a whole-day register or set it for a single lesson —
both can exist for the same day. `AttendanceRecord` is one student's mark:
present, absent, late, excused or leave, with optional minutes late and a
note.

`POST /api/attendance-sessions/{id}/mark/` marks a whole register in one
call: everyone in the class defaults to present and the request carries only
the exceptions. Re-marking updates rather than duplicating.

## Roles

Six roles, created by `python manage.py seed_roles` as Django groups, so they
work in the admin natively and in the API through `app.access.RolePermission`:

| Role | Reach |
|---|---|
| Administrator | Everything: permissions, passwords, academic authority, accounts and office administration. |
| Teacher | Curriculum, the question bank, draft papers, marking, registers, attachments, and student profiles. |
| Examiner | Confirms or overrides marks, and scans and uploads exam scripts. |
| Student | Read the catalogue; read and write their own attempts and answers. |
| Guardian | Read-only, and only for the students linked to them by `GuardianLink`. |
| Guest | Read-only list of classes, subjects and topics. Nothing else. |

Permissions decide which *tables* a role may touch; they cannot express "their
own" or "their ward's". That second question is answered by
`app.access.scope_queryset`, which every API list and detail lookup runs
through — a student sees one student record, a guardian sees their wards, a
guest sees no student rows at all.

## The audit block

Self-controlled, on every table:

| Field | Who sets it |
|---|---|
| `uuid` | Assigned at insert. Restored from the database on every later save — it cannot be changed. |
| `created_by`, `date_created` | Stamped once at insert, from the request user. Also restored on every later save. |
| `changed_by`, `date_changed` | Stamped automatically on each update. |
| `voided`, `void_reason` | **The only audit fields a person sets**, through the admin, the API, or `void()`. |
| `voided_by`, `date_voided` | Stamped when voiding happens. |

The acting user comes from `app.audit.CurrentUserMiddleware`, which publishes
`request.user` in a context variable that `AuditModel.save()` reads — so
nothing has to pass a user around. Outside a request (a management command,
the shell) it is empty and `created_by` may be passed explicitly.

In the admin, the audit block is the last fieldset on every change form,
collapsed, with everything read-only except voiding.

## Tests

```bash
python manage.py test
```

The suite runs against an in-memory SQLite database — no server, nothing
written to disk. Before a release, run it against MySQL too, since SQLite is
lenient about column types and ignores CHECK constraints:

```bash
DJANGO_TEST_ON_MYSQL=true python manage.py test
```

### Soft deletion without partial indexes

MySQL has no partial (filtered) indexes, so "unique among live rows" cannot
be written as `UniqueConstraint(condition=Q(voided=False))` the way it would
be on PostgreSQL. Every such constraint instead includes `active_flag`,
which is `True` on a live row and `NULL` once voided. A unique index treats
`NULL`s as distinct on MySQL, PostgreSQL and SQLite alike, so any number of
voided rows may share a key while only one live row can hold it. `Attempt`
carries the same trick as `counted_flag` for "one counted attempt per
student per assignment". Both columns are maintained in `save()` — never set
them by hand.

## Admin theme

The admin is skinned with [Django JET Reboot](https://github.com/assem-ch/django-jet-reboot),
the maintained fork of the abandoned `django-jet` (the original stopped at
Django 2.x in 2018). The left menu is grouped the way the ERD is — placement,
curriculum, question bank, papers, marking, administration — via
`JET_SIDE_MENU_ITEMS` in `lms/settings.py`. Set `JET_THEME` in `.env` to
switch skins: `default`, `light-violet`, `light-green`, `light-blue`,
`light-gray`, `green`.

All six skins share the same low-contrast greys for text — measured against
white, JET's body text is 2.89:1 and its links 2.51:1, where WCAG AA wants
4.5:1 — so changing skin only changes the accent. `static/css/academy-admin.css`
fixes the text itself: same hues, darkened until they pass, loaded after the
theme by `templates/admin/base_site.html`. The measured ratios are in the
comments at the top of that file.

Its last release is from September 2024, so treat it as stable-but-quiet
rather than actively developed. If it ever blocks a Django upgrade, the
migration path is `django-unfold` or `django-jazzmin`; nothing in `admin.py`
depends on JET, so swapping the theme means changing `INSTALLED_APPS`, two
URL lines and this settings block.

| Path            | What it is                        |
|-----------------|-----------------------------------|
| `/`             | Redirects to the admin — the login page when signed out |
| `/admin/`       | Django admin (JET theme)          |
| `/api/`         | REST API (browsable)              |
| `/api/docs/`    | Swagger UI                        |
| `/api/redoc/`   | ReDoc                             |
| `/api/schema/`  | OpenAPI 3 schema (YAML)           |

The data model follows the published ERD: question papers are versioned
and immutable once locked, and every row is audited and soft-deleted
rather than destroyed.
