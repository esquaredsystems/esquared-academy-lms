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

## Seeding the curriculum

```bash
python manage.py seed_curriculum              # current calendar year
python manage.py seed_curriculum --year 2027
python manage.py seed_curriculum --dry-run
```

Loads the Cambridge curriculum as taught in Pakistan: five grades (E1, E2 =
Lower Secondary stages 7–8; S1–S3 = the O Level programme, S3 terminal), 18
subjects, 156 topics and 48 syllabi for the year — 348 syllabus/topic links.

Topic titles are verbatim from the Cambridge syllabus or curriculum framework
in force for the 2026 series; `app/seed_data.py` records the source document
against every list, and each topic's `description` carries it too. A subject
holds both its Lower Secondary strands (`LS-…`) and its O Level sections
(`OL-…`), and the syllabus for a grade picks the right set.

The command is idempotent: it matches on natural keys, updates titles in
place, and never deletes. A topic dropped from a later syllabus revision
stays in the catalogue and simply leaves that year's syllabus.

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

`AttendanceSession` is one register: a grade, a date, a period. Leave
`syllabus` empty for a whole-day register or set it for a single lesson —
both can exist for the same day. `AttendanceRecord` is one student's mark:
present, absent, late, excused or leave, with optional minutes late and a
note.

`POST /api/attendance-sessions/{id}/mark/` marks a whole register in one
call: everyone in the grade defaults to present and the request carries only
the exceptions. Re-marking updates rather than duplicating.

## Roles

Six roles, created by `python manage.py seed_roles` as Django groups, so they
work in the admin natively and in the API through `app.access.RolePermission`:

| Role | Reach |
|---|---|
| Admin | Everything. |
| Teaching Staff | Curriculum, questions, papers, marking, registers, attachments, and student profiles. |
| Non-academic Staff | Attendance, plus read access to the student, grade and cohort lists it needs. |
| Student | Read the catalogue; read and write their own attempts and answers. |
| Guardian | Read-only, and only for the students linked to them by `GuardianLink`. |
| Guest | Read-only list of grades, subjects and topics. Nothing else. |

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

The data model follows the published ERD: grades are classes, question
papers are versioned and immutable once locked, and every row is audited
and soft-deleted rather than destroyed.
