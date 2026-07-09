from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler

import os
import requests
from datetime import datetime

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
    user = StringField("user")

class sign_up(FlaskForm):
    name = StringField("name", validators=[InputRequired()])
    password = PasswordField("password", validators=[InputRequired()])
    auth_code = StringField("auth code", validators=[Optional()])

@app.route('/')
def index():
    search_form = user_search()
    return render_template("index.html", search=search_form)

@app.route('/search')
def search():
    search_form = user_search()
    search = request.args.get("user", None)

    users = user_stats.query.filter(user_stats.name.contains(search))

    if not users:
        return render_template("message.html", message="User not found...", search=search_form)

    return render_template("search.html", users=users, search=search_form)

@app.route('/user/<u>')
def get_user(u):
    search_form = user_search()
    user = user_stats.query.filter(user_stats.name == u).first()

    if not user:
        return render_template("message.html", message="User not found...", search=search_form)

    return render_template("user.html", user=user)

@app.route('/sign_up', methods=['GET', 'POST'])
def get_credentials():
    form = sign_up()

    if request.method == 'GET':
        return render_template("sign-up.html", sign_up=form)

    if not form.validate_on_submit():
        return render_template("sign-up.html", sign_up=form, message="You probably made something wrong! Try again! :3")

    url = '/auth/login'
    data = {
        'username': form.name.data,
        'password': form.password.data,
        'totp_code': form.auth_code.data
    }

    response = requests.post(BASE_URL + url, json = data).json()

    if not response.get("success"):
        return render_template("sign-up.html", sign_up=form, message=response.get("message"))

    session_id = response.get("data").get("session_id")

    headers = {"Authorization": f"Bearer {session_id}"}
    url = "/user/info"
    response = requests.get(BASE_URL + url, headers=headers).json().get("data")

    new_credentials = user_credentials(
        name=response.get("username"),
        session_id=session_id
    )

    new_stat = user_stats(
        name=response.get("username"),
        balance=response.get("balance"),
        created_at=response.get("created")
    )

    db.session.add(new_credentials)
    db.session.add(new_stat)
    db.session.commit()

    return redirect(f"/user/{response.get("username")}")

@scheduler.task("interval", minutes=5)
def collect_data():
    with app.app_context():
        users = []
        response = requests.get(BASE_URL + "/info/leaderboard").json().get("data")
        
        for user in response.get("leaderboard"):
            users.append(user)

        credentials = user_credentials.query.all()
        for user in credentials:
            headers = {"Authorization": f"Bearer {user.session_id}"}
            url = "/user/info"

            response = requests.get(BASE_URL + url, headers=headers).json().get("data")

            user_entry = {
                "username": response.get("username"),
                "balance": response.get("balance")
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
