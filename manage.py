"""
Management commands for the iPlan-It app.

Usage:
    python manage.py seed_demo_data    Insert demo data for dashboard screenshots.
    python manage.py drop_demo_data    Remove all demo data added by the seeder.
    python manage.py --help            List commands.

seed_demo_data inserts:
  • 4 users  (alice / bob / carol / dave @demo.com) with staggered join dates
  • 20+ tasks distributed across those users
  • 50+ visits spread over the last 14 days across all tracked pages
  •  5 login-error events
  • 12 waitlist signups
All demo identifiers use the @demo.com domain — drop_demo_data removes them cleanly.
The command aborts if any @demo.com user already exists, so re-runs are safe.
"""
import sys
import random
import datetime

from app import app
from models import db, User, Task, Visit, Waitlist

# ── Deterministic seed so every run produces the same shape ────────────────
RNG = random.Random(42)

# ── Demo identity markers ─────────────────────────────────────────────────
DEMO_DOMAIN     = "@demo.com"
DEMO_PASSWORD   = "DemoPass99!"     # shared password for all demo users

DEMO_USERS = [
    # (email,              days_ago_joined)
    ("alice@demo.com",    13),
    ("bob@demo.com",       9),
    ("carol@demo.com",     5),
    ("dave@demo.com",      1),
]

DEMO_WAITLIST = [
    ("eve@example.com",      12),
    ("frank@example.com",    11),
    ("grace@example.com",    10),
    ("heidi@example.com",     9),
    ("ivan@example.com",      8),
    ("judy@example.com",      7),
    ("karl@example.com",      6),
    ("lena@example.com",      5),
    ("mike@example.com",      4),
    ("nina@example.com",      3),
    ("oscar@example.com",     2),
    ("petra@example.com",     1),
]

DEMO_TASKS = [
    # (user_index 0-3, title, completed)
    (0, "Draft Q2 roadmap",             True),
    (0, "Renew SSL certificate",        True),
    (0, "Code review — auth module",    False),
    (0, "Write release notes",          False),
    (0, "Update dependencies",          True),
    (0, "Fix pagination bug",           False),
    (1, "Schedule team standup",        True),
    (1, "Reply to client feedback",     True),
    (1, "Design new landing page",      False),
    (1, "Migrate staging database",     False),
    (1, "Add dark mode toggle",         True),
    (2, "Book dentist appointment",     True),
    (2, "Grocery run",                  True),
    (2, "Call bank about charge",       False),
    (2, "Plan birthday dinner",         False),
    (2, "Return library books",         True),
    (3, "Set up local dev environment", True),
    (3, "Read onboarding docs",         True),
    (3, "Submit first PR",              False),
    (3, "Shadow alice on next feature", False),
    (3, "Add unit tests for task API",  False),
    (3, "Ask about deployment process", False),
]

# Visits per day bucket: (days_ago, count, pages_pool)
# Pages with higher frequency appear multiple times.
PAGES_ANON       = ["index", "index", "index", "login", "login",
                    "signup", "signup", "invitation"]
PAGES_AUTH       = ["todo", "todo", "todo",
                    "task-create", "task-create", "task-toggle",
                    "task-delete"]
PAGES_ALL        = PAGES_ANON + PAGES_AUTH

EVENT_MAP = {
    "task-create":  "todo_create",
    "task-toggle":  "todo_toggle",
    "task-delete":  "todo_delete",
}

# ── Helpers ────────────────────────────────────────────────────────────────

def _ts(days_ago: int, hour: int = None, minute: int = None) -> datetime.datetime:
    """Return a datetime `days_ago` days before today at a random or given time."""
    base = datetime.datetime.utcnow().replace(
        hour   = hour   if hour   is not None else RNG.randint(8, 22),
        minute = minute if minute is not None else RNG.randint(0, 59),
        second = RNG.randint(0, 59),
        microsecond = 0,
    )
    return base - datetime.timedelta(days=days_ago)


def _abort(msg: str):
    print(f"\n  ✗  {msg}")
    sys.exit(1)


def _ok(msg: str):
    print(f"  ✓  {msg}")

# ── Commands ───────────────────────────────────────────────────────────────

def seed_demo_data():
    """Insert all demo data. Aborts if any demo user already exists."""
    with app.app_context():
        # ── Safety guard ─────────────────────────────────────────────────
        existing = User.query.filter(
            User.email.like(f"%{DEMO_DOMAIN}")
        ).first()
        if existing:
            _abort(
                f"Demo data already present ({existing.email}). "
                "Run  python manage.py drop_demo_data  first."
            )

        print("\n  Seeding demo data…\n")

        # ── Users ─────────────────────────────────────────────────────────
        user_objects = []
        for email, days_ago in DEMO_USERS:
            u = User(email=email)
            u.set_password(DEMO_PASSWORD)
            u.date_created = _ts(days_ago, hour=RNG.randint(9, 17))
            db.session.add(u)
            user_objects.append(u)
        db.session.flush()   # populate .id without full commit
        _ok(f"Users: {len(user_objects)} inserted")

        # ── Tasks ─────────────────────────────────────────────────────────
        for u_idx, title, completed in DEMO_TASKS:
            owner = user_objects[u_idx]
            t = Task(
                title   = title,
                status  = "completed" if completed else "not-completed",
                user_id = owner.id,
            )
            db.session.add(t)
        db.session.flush()
        _ok(f"Tasks: {len(DEMO_TASKS)} inserted")

        # ── Waitlist ──────────────────────────────────────────────────────
        for email, days_ago in DEMO_WAITLIST:
            w = Waitlist(
                email      = email,
                ip_address = f"192.168.1.{RNG.randint(10, 254)}",
                timestamp  = _ts(days_ago),
            )
            db.session.add(w)
        db.session.flush()
        _ok(f"Waitlist: {len(DEMO_WAITLIST)} entries inserted")

        # ── Visits ────────────────────────────────────────────────────────
        visit_count = 0

        # Day buckets: (days_ago, anon_visits, auth_visits)
        # Heavier traffic on recent days to make charts interesting.
        day_buckets = [
            (14, 2, 1),
            (13, 2, 1),
            (12, 3, 1),
            (11, 2, 2),
            (10, 3, 2),
            (9,  3, 2),
            (8,  4, 2),
            (7,  3, 3),
            (6,  4, 3),
            (5,  4, 3),
            (4,  5, 3),
            (3,  5, 4),
            (2,  6, 4),
            (1,  5, 4),
            (0,  6, 5),
        ]

        for days_ago, n_anon, n_auth in day_buckets:
            # anonymous visits
            for _ in range(n_anon):
                page = RNG.choice(PAGES_ANON)
                v = Visit(
                    page       = page,
                    user       = None,
                    event_type = EVENT_MAP.get(page),
                    timestamp  = _ts(days_ago),
                )
                db.session.add(v)
                visit_count += 1

            # authenticated visits
            for _ in range(n_auth):
                page  = RNG.choice(PAGES_AUTH)
                owner = RNG.choice(user_objects)
                v = Visit(
                    page       = page,
                    user       = owner.id,
                    event_type = EVENT_MAP.get(page),
                    timestamp  = _ts(days_ago),
                )
                db.session.add(v)
                visit_count += 1

        _ok(f"Visits: {visit_count} inserted (across 15 days)")

        # ── Login errors ──────────────────────────────────────────────────
        error_days = [11, 8, 5, 3, 1]
        for days_ago in error_days:
            v = Visit(
                page       = "error-login",
                user       = None,
                event_type = "login_error",
                timestamp  = _ts(days_ago, hour=RNG.randint(10, 20)),
            )
            db.session.add(v)
        _ok(f"Login errors: {len(error_days)} inserted")

        # ── Commit ────────────────────────────────────────────────────────
        db.session.commit()

        total = len(user_objects) + len(DEMO_TASKS) + len(DEMO_WAITLIST) + visit_count + len(error_days)
        print(f"\n  Done — {total} rows inserted.\n"
              f"  Login with any @demo.com address using password: {DEMO_PASSWORD!r}\n"
              f"  To remove: python manage.py drop_demo_data\n")


def drop_demo_data():
    """Remove all rows seeded by seed_demo_data."""
    with app.app_context():
        demo_users = User.query.filter(
            User.email.like(f"%{DEMO_DOMAIN}")
        ).all()

        if not demo_users:
            print("\n  No demo data found — nothing to remove.\n")
            return

        user_ids = [u.id for u in demo_users]

        Visit.query.filter(Visit.user.in_(user_ids)).delete(synchronize_session=False)
        Task.query.filter(Task.user_id.in_(user_ids)).delete(synchronize_session=False)
        for u in demo_users:
            db.session.delete(u)

        # Waitlist entries from the seeder (known emails)
        wl_emails = [email for email, _ in DEMO_WAITLIST]
        deleted_wl = Waitlist.query.filter(
            Waitlist.email.in_(wl_emails)
        ).delete(synchronize_session=False)

        # Orphan error-login visits (no user FK) can't be isolated from real
        # ones, so we leave them — they're just Visit rows with no user.

        db.session.commit()
        print(f"\n  ✓  Removed {len(demo_users)} demo users, their tasks and visits, "
              f"and {deleted_wl} waitlist entries.\n")


# ── Entry point ────────────────────────────────────────────────────────────

COMMANDS = {
    "seed_demo_data": seed_demo_data,
    "drop_demo_data": drop_demo_data,
}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in COMMANDS:
        print(__doc__)
        print("Available commands:")
        for name in COMMANDS:
            print(f"  python manage.py {name}")
        print()
        sys.exit(0 if len(sys.argv) < 2 else 1)

    COMMANDS[sys.argv[1]]()
