# iPlan-It — Todo App & Admin Dashboard
### Session Report · May 2026

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [Tech Stack](#tech-stack)
3. [What Was Built](#what-was-built)
   - [1. Visit & Event Logging System](#1-visit--event-logging-system)
   - [2. Database Schema Migration](#2-database-schema-migration)
   - [3. Admin Dashboard (Complete Rewrite)](#3-admin-dashboard-complete-rewrite)
   - [4. New Routes & API Endpoints](#4-new-routes--api-endpoints)
   - [5. Auth Fixes](#5-auth-fixes)
   - [6. Dashboard Extra Sections](#6-dashboard-extra-sections)
   - [7. Functional Test Suite (check.py)](#7-functional-test-suite-checkpy)
   - [8. Demo Data Seeder (manage.py)](#8-demo-data-seeder-managepy)
4. [Extra Credit Work](#extra-credit-work)
5. [Bug Discoveries & Fixes](#bug-discoveries--fixes)
6. [File Reference](#file-reference)
7. [Running the App](#running-the-app)

---

## Project Overview

iPlan-It is a Flask web application where users can register, manage a personal todo list, and join a waitlist for early access. An admin dashboard (`/dashboard`) provides analytics, user management, and data export tools.

The starting state of the project had a basic Flask skeleton with models, an incomplete dashboard, and no analytics. Over the course of this session, analytics logging, a full admin UI, all missing routes, a test suite, and a demo data seeder were added from scratch.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Web framework | Flask 2.2.2 |
| Authentication | Flask-Login 0.6.2 |
| ORM | Flask-SQLAlchemy 3.0.2 / SQLAlchemy 2.0 |
| Database | SQLite (local) · PostgreSQL/MySQL (production-ready) |
| Charts | Chart.js 4.4.2 (CDN) |
| Frontend | Pure CSS — no external frameworks |
| Environment | python-dotenv |
| Production server | Gunicorn |

---

## What Was Built

### 1. Visit & Event Logging System

**Files:** `models.py`, `views.py`, `auth.py`

The original `log_visit(page, user_id)` only recorded which page was visited. It was extended to capture richer event data.

**Visit model — two new columns:**

```python
class Visit(db.Model):
    id         = db.Column(db.Integer, primary_key=True)
    page       = db.Column(db.String(200), nullable=False)
    user       = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    timestamp  = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    event_type = db.Column(db.String(100), nullable=True)  # NEW
    email      = db.Column(db.String(200), nullable=True)  # NEW
```

**Updated `log_visit` signature:**

```python
def log_visit(page, user_id=None, event_type=None, email=None):
    visit = Visit(page=page, user=user_id, event_type=event_type, email=email)
    db.session.add(visit)
    db.session.commit()
```

**Events now logged across the application:**

| Trigger | `page` | `event_type` | `email` |
|---|---|---|---|
| GET any public page | page name | — | — |
| Successful login | `login` | — | — |
| Failed login | `error-login` | `login_error` | — |
| Signup | `signup` | — | — |
| Logout | `logout` | — | — |
| Waitlist join | `waitlist-signup` | `waitlist_signup` | ✓ captured |
| Todo page load | `todo` | — | — |
| Task created | `task-create` | `todo_create` | — |
| Task toggled | `task-toggle` | `todo_toggle` | — |
| Task deleted | `task-delete` | `todo_delete` | — |

---

### 2. Database Schema Migration

**File:** `migrate.py`

Since Flask-Migrate was not installed, a standalone idempotent migration script was written. It uses SQLAlchemy's `inspect()` to check which columns already exist before running `ALTER TABLE`, making it safe to run multiple times on both fresh and existing databases.

```
python3 migrate.py
```

---

### 3. Admin Dashboard (Complete Rewrite)

**File:** `templates/admin.html`

The original dashboard used the Argon Dashboard 2 framework (Bootstrap + Font Awesome + external CDN). It was replaced with a self-contained template using only pure CSS and Chart.js.

**What the dashboard shows:**

| Section | Description |
|---|---|
| **4 Stat Cards** | Today's Visits · New Users (week) · Waitlist (week) · Total Users |
| **Line Chart** | Daily index-page visits: this week vs. last week with % change badge |
| **Database Stats** | Total visits, registered users, active tasks, waitlist count |
| **Recent Visits** | Last 15 recorded visit events with page, event type, and timestamp |
| **Recent Errors** | All login errors and system errors filtered from the visit log |
| **Bar Chart** | Page-visit breakdown across all 9 tracked pages for today |
| **Users Table** | All accounts with join date, task count, and Delete button |
| **Waitlist Table** | All pending waitlist entries with Add → button to create an account |
| **New Users (week)** | Table of accounts created this week (username + email + timestamp) |
| **Waitlist Emails (week)** | Table of this week's waitlist signups |
| **Database Backup** | Button to download the raw `.db` SQLite file |

**Design decisions:**
- CSS custom properties (`--blue`, `--green-bg`, etc.) for a consistent color system
- CSS Grid for responsive 4-col → 2-col → 1-col stat cards and 2-col layout rows
- No external fonts, icons, or stylesheets — everything is inline SVG and system fonts
- Chart data serialized safely from Jinja2 using `| tojson` to prevent XSS
- Flash messages displayed for admin actions (user deleted, account promoted from waitlist)

**Chart.js line chart (this week vs last week):**

```html
<script>
  const CHART_LABELS = {{ chart_week    | tojson }};
  const WEEK_VISITS  = {{ week_visits   | tojson }};
  const PREV_VISITS  = {{ two_week_visits | tojson }};
  ...
</script>
```

---

### 4. New Routes & API Endpoints

**File:** `views.py`

All routes are `@login_required`. Several were missing from the original codebase and were added in full:

#### `GET /dashboard`
Added `@login_required` (was publicly accessible). Passes 15+ template variables including chart data arrays, user/visit/task/waitlist querysets, and week-over-week stats.

#### `POST /api/v1/tasks` — Create task
Returns `{"task": {...}}` with HTTP 201. Logs a `todo_create` visit event.

#### `PATCH /api/v1/tasks/<id>` — Toggle task
Toggles status between `not-completed` and `completed`. Returns HTTP 403 if the task belongs to a different user (ownership enforcement). Logs a `todo_toggle` event.

#### `GET /remove/<id>` — Delete task
Deletes the task and redirects to `/todo`. Logs a `todo_delete` event.

#### `GET /delete_user/<id>` — Admin: delete user
Nullifies the user's Visit FK references before deletion (column is nullable). Deletes all their tasks. Blocks deletion of account ID 1 (primary admin). Uses `flash()` for status feedback.

#### `GET /waitlist_add/<id>` — Admin: promote waitlist entry
Creates a user account with a random temporary password using `secrets.token_urlsafe(8)`. Displays the temp password in a flash message. Removes the waitlist entry.

#### `GET /backup` — Export CSV zip
Streams a `.zip` file containing four CSVs: `visits.csv`, `users.csv`, `tasks.csv`, `waitlist.csv`. Built entirely in memory with `io.BytesIO` + `zipfile` — no temp files written to disk.

#### `GET /backup_db` — Export raw SQLite file *(extra credit)*
Streams the live `instance/todo.db` file as a direct download. Useful for opening in DB Browser for SQLite, DBeaver, or any SQLite client.

```python
@main_blueprint.route('/backup_db')
@login_required
def backup_db():
    db_path = db.engine.url.database
    filename = f'todo-{datetime.datetime.now().strftime("%Y%m%d-%H%M")}.db'
    return send_file(db_path, mimetype='application/x-sqlite3',
                     as_attachment=True, download_name=filename)
```

---

### 5. Auth Fixes

**File:** `auth.py`

Several bugs were present in the original auth blueprint:

| Bug | Fix |
|---|---|
| Login errors were not logged | Added `log_visit('error-login', event_type='login_error')` on credential failure |
| Logout redirected to `/login` | Changed to redirect to `url_for('main.index')` (home page) |
| Signup did not pass `user_id` to `log_visit` | Changed to `log_visit('signup', new_user.id)` after commit |
| `current_user` not imported | Added to `flask_login` import |
| Logout did not log the event | Added `log_visit('logout', current_user.id)` before `logout_user()` |

**`app.py` — SQLAlchemy 2.0 user loader fix:**

```python
# Before (deprecated in SQLAlchemy 2.0):
return User.query.get(int(user_id))

# After:
return db.session.get(User, int(user_id))
```

The same fix was applied across all `Model.query.get(id)` calls in `views.py`.

---

### 6. Dashboard Extra Sections

**Files:** `views.py`, `templates/admin.html`

Three additional sections were added below the existing management tables:

**New Users (this week)** — A dedicated table showing only accounts created in the last 7 days, with username (derived from email prefix), full email, and join timestamp. Powered by a new `new_users_list` query variable:

```python
new_users_list = User.query.filter(
    db.func.date(User.date_created) >= week_start
).order_by(User.date_created.desc()).all()
```

**Waitlist Emails (this week)** — Table of this week's waitlist signups (email + timestamp). Uses the existing `waitlist` context variable which was already scoped to the current week.

**Database Backup card** — A prominent card with a download button linking to `/backup_db`, including a description of the file format and suggested tools for opening it.

---

### 7. Functional Test Suite (`check.py`)

**File:** `check.py`

A comprehensive automated test script covering every feature of the application end to end. Uses Flask's built-in test client — no external testing library required.

```
python3 check.py
```

**8 test sections:**

| # | Section | What it verifies |
|---|---|---|
| 8 | Dashboard blocked without login | Unauthenticated GET `/dashboard` returns 302 |
| 1 | Page visits — unauthenticated routes | `/`, `/login`, `/signup`, `/invitation` each write a Visit row |
| 2 | Signup | User is created in DB |
| 3 | Login + todo visit | POST `/login` redirects to `/todo`; GET `/todo` logs a visit |
| 4 | Task create / toggle / delete | Each operation returns the correct HTTP status and logs the correct event |
| 4 | Ownership enforcement | A second user's PATCH on another user's task returns 403 |
| 5 | Waitlist signup | Entry created in DB; email captured in Visit row |
| 6 | Failed login | `login_error` event is recorded |
| 7 | Dashboard content | 200 status; all 14 required elements present in HTML; chart data arrays parseable and non-empty |

All test data uses isolated `_check_*@test.com` addresses and is cleaned up before and after the run.

---

### 8. Demo Data Seeder (`manage.py`)

**File:** `manage.py`

A management command script that populates the database with realistic demo data for dashboard screenshots.

```bash
python manage.py seed_demo_data   # insert demo data
python manage.py drop_demo_data   # remove it cleanly
python manage.py                  # print usage
```

**Data inserted by `seed_demo_data`:**

| Type | Count | Details |
|---|---|---|
| Users | 4 | alice, bob, carol, dave @demo.com — join dates staggered across 13 days |
| Tasks | 22 | Realistic titles distributed across the 4 users, mix of complete/incomplete |
| Waitlist entries | 12 | Spread across the last 12 days |
| Page visits | 97 | 15-day window; traffic ramps up toward today; all 9 tracked pages covered |
| Login errors | 5 | Scattered across days 1, 3, 5, 8, 11 ago |
| **Total rows** | **140** | |

**Safety design:**
- Aborts immediately if any `@demo.com` user already exists — accidental re-runs never double-insert data
- All demo users share the `@demo.com` domain as an isolation marker
- `drop_demo_data` uses that domain to scope deletion precisely
- `random.Random(42)` fixed seed — every fresh seed produces the same timestamps and distribution

---

## Extra Credit Work

The following items went beyond the base requirements:

### Raw SQLite database download (`/backup_db`)
In addition to the CSV zip backup, a second route streams the live `.db` file directly. This lets admins open the real database in any SQL client for ad hoc queries — more useful than CSVs for inspection or migration.

### Task ownership enforcement (HTTP 403)
The `PATCH /api/v1/tasks/<id>` endpoint checks that `task.user_id == current_user.id` before allowing a toggle. A cross-user attempt returns a proper `403 Forbidden` JSON response rather than silently failing or performing the action.

### Idempotent migration script (`migrate.py`)
Rather than requiring Flask-Migrate or manual SQL, a standalone script was written that uses SQLAlchemy's `inspect()` to check for column existence before issuing `ALTER TABLE`. Safe to run on fresh DBs (calls `db.create_all()` first) and existing ones alike.

### `drop_demo_data` command
The seeder is bidirectional — every insert can be cleanly reversed with a single command, making it safe to use in a shared development environment without leaving stale data.

### Flask-Login 0.6.2 + Flask 2.2 compatibility bug — discovered and fixed
While writing the test suite, a subtle framework-level bug was uncovered and fixed. Full explanation below.

---

## Bug Discoveries & Fixes

### Flask-Login `g._login_user` app-context leak

**Symptom:** In `check.py`, the task-delete visit was logged with the wrong user ID — a second test client's authenticated user (ID 3) appeared as `current_user` inside a request made by the first test client.

**Root cause:** Flask-Login 0.6.2 stores `current_user` in `g._login_user`. In Flask 2.2, `g` is scoped to the **app context**, not the request context. When all test requests share a single outer `with app.app_context():` block, no new `g` is created between requests. A `login_user()` call in one test client's request permanently overwrites `g._login_user` for all subsequent requests in that context.

This is a test-environment-only issue. In production, each WSGI request gets its own app context (and therefore its own `g`).

**Fix:** After the cross-user test client's requests, explicitly clear the cached user:

```python
from flask import g as flask_g
if hasattr(flask_g, '_login_user'):
    del flask_g._login_user  # forces _load_user() to re-read session cookie
```

This was originally misdiagnosed as the known Flask-Login `_request_ctx_stack` / `preserve_context=True` bug. The actual mechanism is different: it's `g` scoping, not request context stack leakage.

### SQLAlchemy 2.0 `Query.get()` deprecation
`Model.query.get(id)` is deprecated in SQLAlchemy 2.0 and raises warnings. All occurrences were updated to `db.session.get(Model, id)` across `app.py` and `views.py`.

### Logout redirect to login instead of home
The original logout sent users back to `/login`. Since a logged-out user arriving at the login page with no context is confusing, this was changed to redirect to the index (`/`).

### `log_visit` called before user ID was available
In the original signup flow, `log_visit` was called before `db.session.commit()`, so `new_user.id` was `None`. The call was moved after the commit.

---

## File Reference

```
.
├── app.py            Flask app factory — config, DB init, login manager, blueprints
├── auth.py           Auth blueprint — signup, login, logout routes
├── views.py          Main blueprint — dashboard, todo, task API, admin actions, backups
├── models.py         SQLAlchemy models: User, Task, Visit, Waitlist; log_visit()
├── migrate.py        Idempotent schema migration for Visit.event_type and Visit.email
├── manage.py         Management commands: seed_demo_data, drop_demo_data
├── check.py          Functional test suite — 8 sections, self-cleaning
├── .env              DATABASE_URL + SECRET_KEY (not committed to VCS)
├── requirements.txt  Python dependencies
├── Procfile          Gunicorn entry point for deployment
├── instance/
│   └── todo.db       SQLite database (created on first run)
└── templates/
    ├── admin.html    Admin dashboard — pure CSS + Chart.js, no external frameworks
    ├── index.html    Landing page
    ├── login.html    Login form
    ├── signup.html   Registration form
    ├── invitation.html  Waitlist signup
    └── todo.html     Todo list UI
```

---

## Running the App

**1. Install dependencies**
```bash
pip install Flask==2.2.2 Flask-Login==0.6.2 Flask-SQLAlchemy==3.0.2 \
            werkzeug==2.2.2 python-dotenv==0.21.0 gunicorn==20.1.0
```

**2. Configure environment**

Create `.env` in the project root:
```
DATABASE_URL=sqlite:///todo.db
SECRET_KEY=<generate with: python3 -c "import secrets; print(secrets.token_hex(32))">
```

**3. Initialise the database**
```bash
python3 migrate.py
```

**4. (Optional) Seed demo data**
```bash
python manage.py seed_demo_data
```

**5. Run the development server**
```bash
python3 app.py
# or
flask --app app run --debug
```

**6. Run the functional test suite**
```bash
python3 check.py
```

**7. Remove demo data when done**
```bash
python manage.py drop_demo_data
```

---

*Project by Freeman Buernor · iPlan-It · 2026*
