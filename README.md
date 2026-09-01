# esquared-academy-lms
Knwoledge and Learning management system for Esquared Academy

## Running

```bash
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # then fill in the MySQL credentials
mysql -e "CREATE DATABASE esquared_lms CHARACTER SET utf8mb4"   # or: docker compose up -d db
python manage.py migrate      # also creates the admin / admin superuser
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

| Path            | What it is                        |
|-----------------|-----------------------------------|
| `/admin/`       | Django admin                      |
| `/api/`         | REST API (browsable)              |
| `/api/docs/`    | Swagger UI                        |
| `/api/redoc/`   | ReDoc                             |
| `/api/schema/`  | OpenAPI 3 schema (YAML)           |

The data model follows the published ERD: grades are classes, question
papers are versioned and immutable once locked, and every row is audited
and soft-deleted rather than destroyed.
