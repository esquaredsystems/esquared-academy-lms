# How to run Esquared Academy LMS

Everything you need, in the order you need it. Nothing here assumes you
remember anything from last time.

---

## The one thing to understand

Two programs have to be running for the site to work:

| What | Where it runs | How you start it |
|---|---|---|
| **The database** (MySQL) | Inside Docker | Docker Desktop, container `esquared-mysql` |
| **The web server** (Django) | A PowerShell window | `start_server.bat` |

The web server is **not** a service. It runs only while its window is
open. Close the window, restart the PC, or let the machine sleep, and the
site stops — and the browser then says the page cannot be reached. That is
normal, and starting it again is the whole fix.

---

## Every day: starting the site

**Double-click `start_server.bat`.**

It starts the database, then the web server, and leaves the window open.
Then go to:

```
http://127.0.0.1:8000/admin/
```

Leave that black window open while anyone is using the site. To stop the
site, close it or press Ctrl+C.

If you would rather type it:

```powershell
cd C:\Users\uzair\OneDrive\Documents\GitHub\esquared-academy-lms
venv\Scripts\python.exe manage.py runserver
```

---

## After the code changes: setting everything up

**Double-click `setup_academy.bat`.**

It runs, in order: database migrations, the twelve roles, the import of
staff, students, subjects and the timetable, student logins, this
fortnight's lessons, and an account report — then asks you to set the
teacher's password.

Everything in it is safe to run again. Each step checks what is already
there and updates rather than duplicating. It writes `setup_log.txt`
beside itself, so the result survives the window closing.

Run it when: you have just pulled new code, rebuilt the database, or
changed `docs/setup_data.json`.

---

## Passwords

Accounts are created **without** a password and cannot be used until one
is set. That is deliberate — no script ever invents a password.

Set one account's password (it prompts twice; nothing appears as you
type, which is normal):

```powershell
venv\Scripts\python.exe manage.py reset_login uxair.ahm --set
```

See who can actually log in and who is still waiting:

```powershell
venv\Scripts\python.exe manage.py account_status
venv\Scripts\python.exe manage.py account_status --pending
venv\Scripts\python.exe manage.py account_status --role Student
```

Create an account that does not exist yet, with a role, and set its
password in one go:

```powershell
venv\Scripts\python.exe manage.py reset_login someone --set --create --role "Teaching Staff"
```

**Logins.** Teachers sign in with a name (`uxair.ahm`, `samyanconsole`,
`sid.marium`, `adan.salahuddin`, `rabia.basaria`, `usama.khan`).
Students sign in with their **admission number** (`26070108` and up).
The full list is in `docs\Esquared_Academy_Logins.xlsx`.

---

## Lessons and the timetable

Lessons are built from the weekly timetable. Without them a teacher's
**My day** is empty.

```powershell
venv\Scripts\python.exe manage.py generate_lessons --weeks 2
venv\Scripts\python.exe manage.py generate_lessons --from 2026-09-21 --to 2026-10-02
venv\Scripts\python.exe manage.py generate_lessons --weeks 2 --dry-run
```

Run it every couple of weeks to extend the term. It never touches a
lesson a teacher has already written on.

If a class has no lessons, the timetable itself is probably missing rows —
fill in the **Timetable** sheet of `docs\Esquared_LMS_Setup.xlsx`, re-run
`setup_academy.bat`, then `generate_lessons` again.

---

## Tidying the roll

The academy's roll is `docs\keep_students.txt` — 99 admission numbers.
Anything else with a student login (demo data, test accounts) is surplus.

```powershell
venv\Scripts\python.exe manage.py prune_students
venv\Scripts\python.exe manage.py prune_students --commit
```

The first reports and writes nothing. The second retires the surplus.
Nothing is ever deleted — accounts are voided, so they can be brought
back by unvoiding them in the admin.

---

## When something goes wrong

**"This site can't be reached" / the page never loads.**
The web server is not running. Double-click `start_server.bat`.

**The page loads but shows a database error.**
The web server is fine; MySQL is not. Start Docker Desktop, wait for it
to settle, then run `start_server.bat` again.

**"No account called ..."**
That account does not exist yet. Run `account_status` to see what does.

**A password is refused even though you just set it.**
The account has no role, so the admin login refuses it. Give it one:
`reset_login <name> --set --role "Teaching Staff"`.

**A yellow Django error page.**
Read the black PowerShell window — the real error is printed there, and
the last few lines are the part that matters.

---

## Two rules

Never put anything in `.env` into a message, a screenshot or a commit —
the database password lives there.

The black PowerShell window is the truth. Every page request appears in
it, and every error prints there in full. When something behaves oddly,
that window says why.
