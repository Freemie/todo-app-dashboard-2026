from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin
import datetime

db = SQLAlchemy()


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(128), nullable=False)
    date_created = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    tasks = db.relationship('Task', backref='owner')
    visits = db.relationship('Visit')

    @property
    def name(self):
        return self.email.split('@')[0]

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    status = db.Column(db.String(20), default='not-completed')
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

    def toggle(self):
        self.status = 'completed' if self.status == 'not-completed' else 'not-completed'

    def __repr__(self):
        return f"<Task id={self.id} title='{self.title}' status={self.status}>"

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "user_id": self.user_id
        }


class Visit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    page = db.Column(db.String(200), nullable=False)
    user = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    event_type = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(200), nullable=True)

    @property
    def date(self):
        if self.timestamp:
            return self.timestamp.strftime("%Y-%m-%d %H:%M")
        return ""

    def __repr__(self):
        return f"<Visit id={self.id} page='{self.page}' timestamp={self.timestamp}>"


class Waitlist(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(80), unique=True, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.datetime.utcnow)
    ip_address = db.Column(db.String(50), nullable=True)

    @property
    def date(self):
        if self.timestamp:
            return self.timestamp.strftime("%Y-%m-%d %H:%M")
        return ""

    def __repr__(self):
        return f"<Waitlist id={self.id} email='{self.email}' timestamp={self.timestamp}>"


def log_visit(page, user_id=None, event_type=None, email=None):
    visit = Visit(page=page, user=user_id, event_type=event_type, email=email)
    db.session.add(visit)
    db.session.commit()
