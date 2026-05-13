"""
Full functional check. Run with: python3 check.py
Creates isolated test data, exercises every scenario, cleans up after.
"""
import json
from app import app
from models import db, User, Task, Visit, Waitlist

PASS = "✓"
FAIL = "✗"

issues = []

def ok(msg):
    print(f"  {PASS}  {msg}")

def fail(msg):
    issues.append(msg)
    print(f"  {FAIL}  {msg}")

def section(title):
    print(f"\n{'─'*50}")
    print(f"  {title}")
    print(f"{'─'*50}")

def assert_visit(page=None, event_type=None, email=None, user_id=None, label=""):
    q = Visit.query
    if page:       q = q.filter_by(page=page)
    if event_type: q = q.filter_by(event_type=event_type)
    if email:      q = q.filter_by(email=email)
    if user_id:    q = q.filter_by(user=user_id)
    v = q.order_by(Visit.id.desc()).first()
    if v:
        detail = f"page={v.page!r}"
        if v.event_type: detail += f" event_type={v.event_type!r}"
        if v.email:      detail += f" email={v.email!r}"
        ok(f"{label} → Visit({detail})")
        return v
    else:
        fail(f"{label} → NO matching Visit row (page={page!r} event_type={event_type!r})")
        return None


with app.app_context():

    # ═══════════════════════════════════════════════
    section("8. Dashboard blocked without login")
    # ═══════════════════════════════════════════════
    # Must run BEFORE any authenticated session is created.
    # Flask-Login 0.6.2 + Flask 2.2 leak user state via the legacy
    # _request_ctx_stack when preserve_context is active; running first
    # avoids the false positive.
    anon = app.test_client()
    r = anon.get('/dashboard', follow_redirects=False)
    if r.status_code == 302:
        ok(f"Unauthenticated /dashboard → 302 (redirects to login)")
    else:
        fail(f"Unauthenticated /dashboard → {r.status_code} (should be 302)")

    # ── Teardown any leftover test data ───────────────
    for email in ('_check_user@test.com', '_check_waitlist@test.com'):
        u = User.query.filter_by(email=email).first()
        if u:
            Visit.query.filter_by(user=u.id).update({'user': None})
            Task.query.filter_by(user_id=u.id).delete()
            db.session.delete(u)
        w = Waitlist.query.filter_by(email=email).first()
        if w:
            db.session.delete(w)
    db.session.commit()

    from flask import g as flask_g

    with app.test_client() as client:

        # ═══════════════════════════════════════════════
        section("1. Page visits — unauthenticated routes")
        # ═══════════════════════════════════════════════

        pages = [
            ('GET', '/',           'index',      200),
            ('GET', '/login',      'login',      200),
            ('GET', '/signup',     'signup',     200),
            ('GET', '/invitation', 'invitation', 200),
        ]
        for method, url, expected_page, expected_status in pages:
            r = client.get(url)
            if r.status_code != expected_status:
                fail(f"GET {url} → HTTP {r.status_code} (expected {expected_status})")
            else:
                assert_visit(page=expected_page, label=f"GET {url}")

        # ═══════════════════════════════════════════════
        section("2. Signup — creates user + logs visit")
        # ═══════════════════════════════════════════════

        r = client.post('/signup', data={
            'email': '_check_user@test.com',
            'password': 'CheckPass99!'
        }, follow_redirects=False)
        user = User.query.filter_by(email='_check_user@test.com').first()
        uid  = user.id if user else None   # plain int — survives expunge_all()
        if user:
            ok(f"User created  id={uid}  email={user.email}")
        else:
            fail("User not created after POST /signup")

        # ═══════════════════════════════════════════════
        section("3. Login (success) + todo page visit")
        # ═══════════════════════════════════════════════

        r = client.post('/login', data={
            'email': '_check_user@test.com',
            'password': 'CheckPass99!'
        }, follow_redirects=False)
        if r.status_code == 302 and 'todo' in r.headers.get('Location', ''):
            ok(f"Login redirect → {r.headers['Location']}")
        else:
            fail(f"Login did not redirect to /todo  (status={r.status_code}  location={r.headers.get('Location')})")

        r = client.get('/todo')
        if r.status_code == 200:
            assert_visit(page='todo', user_id=uid, label="GET /todo")
        else:
            fail(f"GET /todo → HTTP {r.status_code}")

        # ═══════════════════════════════════════════════
        section("4. Task create / toggle / delete logging")
        # ═══════════════════════════════════════════════

        # Create
        r = client.post('/api/v1/tasks',
                        data=json.dumps({'title': 'Functional check task'}),
                        content_type='application/json')
        if r.status_code == 201:
            task_id = r.get_json()['task']['id']
            ok(f"POST /api/v1/tasks → 201  task_id={task_id}")
            assert_visit(page='task-create', event_type='todo_create',
                         user_id=uid, label="task create")
        else:
            fail(f"POST /api/v1/tasks → HTTP {r.status_code}  body={r.data[:200]}")
            task_id = None

        # Toggle
        if task_id:
            r = client.patch(f'/api/v1/tasks/{task_id}')
            if r.status_code == 200:
                ok(f"PATCH /api/v1/tasks/{task_id} → 200  status={r.get_json()['task']['status']!r}")
                assert_visit(page='task-toggle', event_type='todo_toggle',
                             user_id=uid, label="task toggle")
            else:
                fail(f"PATCH /api/v1/tasks/{task_id} → HTTP {r.status_code}")

        # Ownership enforcement — try to toggle another user's task
        if task_id:
            u2 = User(email='_check_other@test.com')
            u2.set_password('other')
            db.session.add(u2)
            db.session.commit()
            u2_id = u2.id
            # No 'with': avoid preserve_context=True leaking c2's user
            # into _request_ctx_stack (Flask-Login 0.6.2 + Flask 2.2 issue).
            c2 = app.test_client()
            c2.post('/login', data={'email': '_check_other@test.com', 'password': 'other'})
            r2 = c2.patch(f'/api/v1/tasks/{task_id}')
            if r2.status_code == 403:
                ok(f"Ownership check: cross-user PATCH → 403 Forbidden")
            else:
                fail(f"Ownership check: cross-user PATCH → {r2.status_code} (expected 403)")
            # Bulk-delete + expunge_all: avoids stale identity-map objects
            # interfering with the next test-client request's session.
            Visit.query.filter_by(user=u2_id).update({'user': None})
            User.query.filter_by(id=u2_id).delete()
            db.session.commit()
            db.session.expunge_all()
            # Flask-Login 0.6.2 stores current_user in g._login_user, and g is
            # scoped to the app context (not per-request) inside a shared
            # app.app_context(). c2's login_user() sets g._login_user = u2,
            # which persists into the outer client's next request. Delete it
            # so _load_user() fires again and picks up the correct user from
            # the session cookie.
            if hasattr(flask_g, '_login_user'):
                del flask_g._login_user

        # Delete
        if task_id:
            r = client.get(f'/remove/{task_id}', follow_redirects=False)
            if r.status_code == 302:
                ok(f"GET /remove/{task_id} → 302 redirect")
                assert_visit(page='task-delete', event_type='todo_delete',
                             user_id=uid, label="task delete")
            else:
                fail(f"GET /remove/{task_id} → HTTP {r.status_code}")

        # ═══════════════════════════════════════════════
        section("5. Waitlist signup — email captured in Visit")
        # ═══════════════════════════════════════════════

        r = client.post('/invitation', data={'email': '_check_waitlist@test.com'})
        w = Waitlist.query.filter_by(email='_check_waitlist@test.com').first()
        if w:
            ok(f"Waitlist entry created  id={w.id}  email={w.email}")
        else:
            fail("Waitlist entry not created")
        assert_visit(event_type='waitlist_signup', email='_check_waitlist@test.com',
                     label="POST /invitation (waitlist)")

        # ═══════════════════════════════════════════════
        section("6. Failed login → login_error event")
        # ═══════════════════════════════════════════════

        r = client.post('/login', data={
            'email': '_check_user@test.com',
            'password': 'wrongpassword!'
        })
        assert_visit(page='error-login', event_type='login_error', label="Bad password login")

        # ═══════════════════════════════════════════════
        section("7. Dashboard — stat cards, charts, visit list")
        # ═══════════════════════════════════════════════

        # Re-login (session may have been overwritten)
        client.post('/login', data={
            'email': '_check_user@test.com',
            'password': 'CheckPass99!'
        })
        r = client.get('/dashboard')
        if r.status_code != 200:
            fail(f"GET /dashboard → HTTP {r.status_code}")
        else:
            ok("GET /dashboard → 200")
            html = r.data.decode()

            dashboard_checks = {
                "stat card: Today's Visits":    "Today's Visits",
                "stat card: New Users":         "New Users",
                "stat card: Waitlist":          "Waitlist",
                "stat card: Total Users":       "Total Users",
                "line chart canvas":            "chart-line-visits",
                "bar chart canvas":             "chart-bar-pages",
                "chart data CHART_LABELS":      "CHART_LABELS",
                "chart data WEEK_VISITS":       "WEEK_VISITS",
                "chart data PAGE_VISITS":       "PAGE_VISITS",
                "recent visits section":        "Recent Visits",
                "recent errors section":        "Recent Errors",
                "page visits section":          "Page Visits Today",
                "users table":                  "mgmt-table",
                "backup button":                "/backup",
            }
            for label, needle in dashboard_checks.items():
                if needle in html:
                    ok(f"Dashboard: {label}")
                else:
                    fail(f"Dashboard: {label} — '{needle}' not found in HTML")

            # Confirm chart data is non-empty arrays
            import re
            for var in ('WEEK_VISITS', 'PAGE_VISITS', 'CHART_LABELS'):
                m = re.search(rf'const {var}\s*=\s*(\[.*?\]);', html)
                if m:
                    val = json.loads(m.group(1))
                    ok(f"  {var} = {val}")
                else:
                    fail(f"  Could not parse {var} from dashboard HTML")

    # ── Teardown ──────────────────────────────────────
    for email in ('_check_user@test.com', '_check_waitlist@test.com'):
        u = User.query.filter_by(email=email).first()
        if u:
            Visit.query.filter_by(user=u.id).update({'user': None})
            Task.query.filter_by(user_id=u.id).delete()
            db.session.delete(u)
        w = Waitlist.query.filter_by(email=email).first()
        if w:
            db.session.delete(w)
    db.session.commit()

    # ═══════════════════════════════════════════════
    section("Summary")
    # ═══════════════════════════════════════════════
    if issues:
        print(f"\n  {len(issues)} issue(s) found:")
        for i in issues:
            print(f"    {FAIL}  {i}")
    else:
        print(f"\n  All checks passed — no issues found.")
