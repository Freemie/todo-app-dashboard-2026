import csv
import io
import secrets
import datetime
import zipfile
from flask import Blueprint, render_template, redirect, url_for, request, send_file, flash
from flask_login import login_required, current_user
from models import db, Task, User, Visit, Waitlist, log_visit

main_blueprint = Blueprint('main', __name__)

TRACKED_PAGES = ['index', 'todo', 'login', 'signup', 'invitation',
                 'task-create', 'task-toggle', 'task-delete', 'error-login']


@main_blueprint.route('/', methods=['GET'])
def index():
    log_visit('index', current_user.id if current_user.is_authenticated else None)
    return render_template('index.html')


@main_blueprint.route('/invitation', methods=['GET', 'POST'])
def invitation():
    log_visit('invitation', current_user.id if current_user.is_authenticated else None)

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if email:
            existing = Waitlist.query.filter_by(email=email).first()
            if not existing:
                entry = Waitlist(email=email, ip_address=request.remote_addr)
                db.session.add(entry)
                db.session.commit()
            log_visit('waitlist-signup',
                      current_user.id if current_user.is_authenticated else None,
                      event_type='waitlist_signup', email=email)

    return render_template('invitation.html')


@main_blueprint.route('/todo', methods=['GET', 'POST'])
@login_required
def todo():
    log_visit('todo', current_user.id)
    return render_template('todo.html')


@main_blueprint.route('/dashboard', methods=['GET', 'POST'])
@login_required
def dashboard():
    today = datetime.datetime.utcnow().date()
    week_start = today - datetime.timedelta(days=6)

    # --- summary stats ---
    visits_today = Visit.query.filter(
        db.func.date(Visit.timestamp) == today
    ).count()

    new_users = User.query.filter(
        db.func.date(User.date_created) >= week_start
    ).count()

    waitlist_week = Waitlist.query.filter(
        db.func.date(Waitlist.timestamp) >= week_start
    ).all()

    total_users = User.query.count()

    # --- chart data (today is the rightmost point) ---
    chart_week = []
    week_visits = []      # index page visits this week
    two_week_visits = []  # index page visits same days last week
    week_notes = []       # new users this week
    two_week_notes = []   # new users same days last week

    for i in range(6, -1, -1):
        day = today - datetime.timedelta(days=i)
        last_week_day = day - datetime.timedelta(days=7)

        chart_week.append(day.strftime("%a"))

        week_visits.append(Visit.query.filter(
            Visit.page == 'index',
            db.func.date(Visit.timestamp) == day
        ).count())

        two_week_visits.append(Visit.query.filter(
            Visit.page == 'index',
            db.func.date(Visit.timestamp) == last_week_day
        ).count())

        week_notes.append(User.query.filter(
            db.func.date(User.date_created) == day
        ).count())

        two_week_notes.append(User.query.filter(
            db.func.date(User.date_created) == last_week_day
        ).count())

    this_week_total = sum(week_visits)
    last_week_total = sum(two_week_visits)
    if last_week_total > 0:
        productivity_change = round(
            (this_week_total - last_week_total) / last_week_total * 100, 1)
    elif this_week_total > 0:
        productivity_change = 100.0
    else:
        productivity_change = 0

    # --- bar chart: visits per tracked page today ---
    page_visits = [
        Visit.query.filter(
            Visit.page == page,
            db.func.date(Visit.timestamp) == today
        ).count()
        for page in TRACKED_PAGES
    ]

    # --- tables ---
    all_visits = Visit.query.order_by(Visit.timestamp.desc()).all()
    all_users = User.query.order_by(User.date_created.desc()).all()
    all_tasks = Task.query.all()
    all_waitlist = Waitlist.query.order_by(Waitlist.timestamp.desc()).all()

    new_users_list = User.query.filter(
        db.func.date(User.date_created) >= week_start
    ).order_by(User.date_created.desc()).all()

    return render_template(
        'admin.html',
        date=datetime.datetime.now().strftime("%B %d, %Y"),
        total_users=total_users,
        new_users=new_users,
        visits_today=visits_today,
        productivity_change=productivity_change,
        visits=all_visits,
        users=all_users,
        tasks=all_tasks,
        waitlist=waitlist_week,
        all_waitlist=all_waitlist,
        new_users_list=new_users_list,
        chart_week=chart_week,
        week_notes=week_notes,
        two_week_notes=two_week_notes,
        week_visits=week_visits,
        two_week_visits=two_week_visits,
        page_visits=page_visits,
        tracked_pages=TRACKED_PAGES,
    )


# ── Task API ──────────────────────────────────────────────────────────────────

@main_blueprint.route('/api/v1/tasks', methods=['GET'])
@login_required
def api_get_tasks():
    tasks = Task.query.filter_by(user_id=current_user.id).all()
    return {"tasks": [task.to_dict() for task in tasks]}


@main_blueprint.route('/api/v1/tasks', methods=['POST'])
@login_required
def api_create_task():
    data = request.get_json()
    new_task = Task(title=data['title'], user_id=current_user.id)
    db.session.add(new_task)
    db.session.commit()
    log_visit('task-create', current_user.id, event_type='todo_create')
    return {"task": new_task.to_dict()}, 201


@main_blueprint.route('/api/v1/tasks/<int:task_id>', methods=['PATCH'])
@login_required
def api_toggle_task(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        return {"error": "Task not found"}, 404
    if task.user_id != current_user.id:
        return {"error": "Forbidden"}, 403
    task.toggle()
    db.session.commit()
    log_visit('task-toggle', current_user.id, event_type='todo_toggle')
    return {"task": task.to_dict()}, 200


@main_blueprint.route('/remove/<int:task_id>')
@login_required
def remove(task_id):
    task = db.session.get(Task, task_id)
    if task is None:
        return redirect(url_for('main.todo'))
    db.session.delete(task)
    db.session.commit()
    log_visit('task-delete', current_user.id, event_type='todo_delete')
    return redirect(url_for('main.todo'))


# ── Admin actions ─────────────────────────────────────────────────────────────

@main_blueprint.route('/delete_user/<int:user_id>')
@login_required
def delete_user(user_id):
    if user_id == 1:
        flash('Cannot delete the primary admin account.', 'error')
        return redirect(url_for('main.dashboard'))
    user = db.session.get(User, user_id)
    if user is None:
        return redirect(url_for('main.dashboard'))
    email = user.email
    # Nullify visit FK before deleting (column is nullable)
    Visit.query.filter_by(user=user_id).update({'user': None})
    Task.query.filter_by(user_id=user_id).delete()
    db.session.delete(user)
    db.session.commit()
    flash(f'User {email} deleted.', 'info')
    return redirect(url_for('main.dashboard'))


@main_blueprint.route('/waitlist_add/<int:entry_id>')
@login_required
def waitlist_add(entry_id):
    entry = db.session.get(Waitlist, entry_id)
    if entry is None:
        return redirect(url_for('main.dashboard'))
    if User.query.filter_by(email=entry.email).first():
        flash(f'{entry.email} already has an account.', 'info')
    else:
        temp_pw = secrets.token_urlsafe(8)
        new_user = User(email=entry.email)
        new_user.set_password(temp_pw)
        db.session.add(new_user)
        flash(f'Account created for {entry.email} — temp password: {temp_pw}', 'success')
    db.session.delete(entry)
    db.session.commit()
    return redirect(url_for('main.dashboard'))


@main_blueprint.route('/backup')
@login_required
def backup():
    def make_csv(headers, rows):
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(headers)
        w.writerows(rows)
        return buf.getvalue()

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('visits.csv', make_csv(
            ['id', 'page', 'user_id', 'event_type', 'email', 'timestamp'],
            [[v.id, v.page, v.user, v.event_type or '', v.email or '', v.timestamp]
             for v in Visit.query.order_by(Visit.timestamp.desc()).all()]
        ))
        zf.writestr('users.csv', make_csv(
            ['id', 'email', 'date_created'],
            [[u.id, u.email, u.date_created]
             for u in User.query.order_by(User.id).all()]
        ))
        zf.writestr('tasks.csv', make_csv(
            ['id', 'title', 'status', 'user_id'],
            [[t.id, t.title, t.status, t.user_id]
             for t in Task.query.all()]
        ))
        zf.writestr('waitlist.csv', make_csv(
            ['id', 'email', 'ip_address', 'timestamp'],
            [[wl.id, wl.email, wl.ip_address or '', wl.timestamp]
             for wl in Waitlist.query.order_by(Waitlist.timestamp).all()]
        ))

    zip_buf.seek(0)
    filename = f'iplanit-backup-{datetime.datetime.now().strftime("%Y%m%d-%H%M")}.zip'
    return send_file(zip_buf, mimetype='application/zip',
                     as_attachment=True, download_name=filename)


@main_blueprint.route('/backup_db')
@login_required
def backup_db():
    db_path = db.engine.url.database
    filename = f'todo-{datetime.datetime.now().strftime("%Y%m%d-%H%M")}.db'
    return send_file(db_path, mimetype='application/x-sqlite3',
                     as_attachment=True, download_name=filename)
