from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler

import os
import requests
from datetime import datetime
from typing import Any

from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, PasswordField
from wtforms.validators import InputRequired, Optional

app = Flask(__name__)

app.config["SECRET_KEY"] = "a secret key"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///sqlite.db" #database
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False  # Avoids a warning

db = SQLAlchemy(app)

scheduler = APScheduler()
scheduler.init_app(app)
scheduler.start()

BASE_URL = 'https://mypayindia.com/api/v2'


def build_search_form():
    return user_search()


def get_random_users(limit=4):
    users = user_stats.query.order_by(db.func.random()).limit(limit).all()
    return users


def build_user_history(user):
    history = sorted(user.balance_history, key=lambda entry: entry.timestamp)
    if not history:
        history = []

    points = []
    previous_entry = None

    for entry in history:
        delta_per_minute = 0
        if previous_entry:
            minutes = max((entry.timestamp - previous_entry.timestamp).total_seconds() / 60, 1)
            delta_per_minute = (entry.balance - previous_entry.balance) / minutes

        points.append({
            "timestamp": entry.timestamp.strftime("%Y-%m-%d %H:%M"),
            "balance": entry.balance,
            "balance_inr": round(entry.balance / 100, 2),
            "delta_per_minute": round(delta_per_minute / 100, 2),
        })
        previous_entry = entry

    if not points:
        points = [{
            "timestamp": user.created_at or "Unknown",
            "balance": user.balance,
            "balance_inr": round(user.balance / 100, 2),
            "delta_per_minute": 0,
        }]

    return points


def build_user_development_chart(users, points=8):
    datasets = []

    for index, user in enumerate(users):
        history = sorted(user.balance_history, key=lambda entry: entry.id)[-points:]
        values = history or [user]

        datasets.append({
            "label": user.name,
            "data": [
                {"x": point_index + 1, "y": entry.balance}
                for point_index, entry in enumerate(values)
            ],
            "borderColor": ["#8fd0ff", "#9f8fff", "#ffd08f", "#8ff0c7"][index % 4],
            "backgroundColor": "rgba(143, 208, 255, 0.10)",
            "tension": 0.35,
            "fill": False,
            "pointRadius": 2,
            "pointHoverRadius": 4,
        })

    return datasets


def render_tracker_error(message, status_code=404):
    return render_template(
        "message.html",
        message=message,
        random_users=get_random_users(),
    ), status_code

class user_credentials(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    session_id = db.Column(db.String(32), unique=True, nullable=False)

class user_stats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    balance = db.Column(db.Integer, nullable=False, unique=False)
    balance_history = db.relationship("user_balance", backref="user_stats", lazy=True, cascade="all, delete-orphan")
    created_at = db.Column(db.String(32), nullable=True, unique=False)

class user_balance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Integer, unique=False, nullable=False)
    timestamp = db.Column(db.DateTime, default=datetime.now, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_stats.id"), nullable=False)


class user_search(FlaskForm):
    user = StringField("User")

class sign_up(FlaskForm):
    name = StringField("Username", validators=[InputRequired()])
    password = PasswordField("Password", validators=[InputRequired()])
    auth_code = StringField("Auth code", validators=[Optional()])

@app.route('/')
def index():
    live_users = get_random_users(4)
    return render_template(
        "index.html",
        random_users=live_users,
        development_chart=build_user_development_chart(live_users),
    )

@app.route('/search')
def search():
    search_form = build_search_form()
    search = request.args.get("user", None)

    if not search:
        return render_template(
            "search.html",
            users=[],
            search=search_form,
            random_users=get_random_users(),
            search_message=None,
        )

    users = user_stats.query.filter(user_stats.name.contains(search)).all()

    if not users:
        return render_template(
            "search.html",
            users=[],
            search=search_form,
            random_users=get_random_users(),
            search_message=f'No matches for "{search}".',
        )

    return render_template("search.html", users=users, search=search_form, random_users=get_random_users())

@app.route('/user/<u>')
def get_user(u):
    user = user_stats.query.filter(user_stats.name == u).first()

    if not user:
        return render_tracker_error("User not found.", 404)

    return render_template(
        "user.html",
        user=user,
        random_users=get_random_users(),
        history_points=build_user_history(user),
    )

@app.route('/sign_up', methods=['GET', 'POST'])
def get_credentials():
    form = sign_up()

    if request.method == 'GET':
        return render_template("sign-up.html", sign_up=form, random_users=get_random_users())

    if not form.validate_on_submit():
        return render_template("sign-up.html", sign_up=form, message="Please fill in all required fields.", random_users=get_random_users()), 400

    try:
        auth_response = requests.post(
            BASE_URL + '/auth/login',
            json={
                'username': form.name.data,
                'password': form.password.data,
                'totp_code': form.auth_code.data,
            },
            timeout=12,
        ).json()
    except requests.RequestException:
        return render_template(
            "sign-up.html",
            sign_up=form,
            message="MyPayIndia is currently unreachable.",
            random_users=get_random_users(),
        ), 502

    if not auth_response.get("success"):
        return render_template(
            "sign-up.html",
            sign_up=form,
            message=auth_response.get("message", "Login failed."),
            random_users=get_random_users(),
        ), 400

    session_id = auth_response.get("data", {}).get("session_id")
    if not session_id:
        return render_template(
            "sign-up.html",
            sign_up=form,
            message="The session could not be read.",
            random_users=get_random_users(),
        ), 502

    try:
        user_response = requests.get(
            BASE_URL + '/user/info',
            headers={"Authorization": f"Bearer {session_id}"},
            timeout=12,
        ).json().get("data")
    except requests.RequestException:
        return render_template(
            "sign-up.html",
            sign_up=form,
            message="The user data could not be loaded.",
            random_users=get_random_users(),
        ), 502

    if not user_response:
        return render_template(
            "sign-up.html",
            sign_up=form,
            message="The user data is missing from the response.",
            random_users=get_random_users(),
        ), 502

    existing_stat = user_stats.query.filter(user_stats.name == user_response.get("username")).first()
    if existing_stat:
        existing_stat.balance = user_response.get("balance")
        existing_stat.created_at = user_response.get("created")
    else:
        db.session.add(user_stats(
            name=user_response.get("username"),
            balance=user_response.get("balance"),
            created_at=user_response.get("created")
        ))

    existing_credentials = user_credentials.query.filter(user_credentials.name == user_response.get("username")).first()
    if existing_credentials:
        existing_credentials.session_id = session_id
    else:
        db.session.add(user_credentials(
            name=user_response.get("username"),
            session_id=session_id
        ))

    db.session.commit()

    return redirect(f"/user/{user_response.get('username')}")


@app.errorhandler(404)
def page_not_found(_error):
    return render_tracker_error("This page could not be found.", 404)


@app.errorhandler(500)
def internal_error(_error):
    return render_tracker_error("An unexpected error occurred.", 500)

@scheduler.task("interval", minutes=5)
def collect_data():
    with app.app_context():
        users = []
        try:
            response = requests.get(BASE_URL + "/info/leaderboard", timeout=12).json().get("data")
        except requests.RequestException:
            return

        if not response or not response.get("success", True):
            if response and response.get("error") == 9003:
                return
        else:
            for user in response.get("leaderboard", []):
                users.append(user)

        credentials = user_credentials.query.all()
        for user in credentials:
            headers = {"Authorization": f"Bearer {user.session_id}"}
            url = "/user/info"

            try:
                response = requests.get(BASE_URL + url, headers=headers, timeout=12).json()
            except requests.RequestException:
                continue

            data = response.get("data")

            if not response.get("success", True):
                if response.get("error") == 1001:
                    db.session.delete(user)
                    db.session.commit()
                    continue

                if response.get("error") == 9003:
                    return

            if not data:
                continue

            user_entry = {
                "username": data.get("username"),
                "balance": data.get("balance")
            }

            users.append(user_entry)

        for u in users:
            user = user_stats.query.filter(user_stats.name == u["username"]).first()

            if not user:
                user = user_stats(
                    name=u["username"],
                    balance=u["balance"]
                )

                db.session.add(user)
                db.session.commit()

            new_balance = user_balance(
                balance=u["balance"],
                user_id=user.id
            )

            db.session.add(new_balance) # add balance to history
            user.balance = u["balance"] # change balance in user stats
            db.session.commit()


if __name__ == "__main__":
    with app.app_context(): 
        db.create_all()
    app.run(debug=True)
