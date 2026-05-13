from flask import Blueprint, render_template, redirect, url_for, request
from models import db, User, log_visit
from flask_login import login_user, logout_user, login_required, current_user

auth_blueprint = Blueprint('auth', __name__)


@auth_blueprint.route('/register', methods=['GET', 'POST'])
@auth_blueprint.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            return redirect(url_for('auth.login'))

        new_user = User(email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        log_visit('signup', new_user.id)
        return redirect(url_for('auth.login'))

    log_visit('signup')
    return render_template('signup.html')


@auth_blueprint.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and user.check_password(password):
            login_user(user)
            log_visit('login', user.id)
            return redirect(url_for('main.todo'))
        else:
            log_visit('error-login', event_type='login_error')

    else:
        log_visit('login')

    return render_template('login.html')


@auth_blueprint.route('/logout')
@login_required
def logout():
    log_visit('logout', current_user.id)
    logout_user()
    return redirect(url_for('main.index'))
