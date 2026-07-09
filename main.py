from flask import Flask, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_apscheduler import APScheduler
import os
import requests

from flask_wtf import FlaskForm
from flask_wtf.csrf import CSRFProtect
from wtforms import StringField, PasswordField
from wtforms.validators import InputRequired

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
    password = db.Column(db.String(64), unique=False, nullable=False)

class user_stats(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    balance = db.Column(db.Integer, nullable=False, unique=False)
    balance_history = db.relationship("user_balance", backref="user_stats", lazy=True, cascade="all, delete-orphan")

class user_balance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    balance = db.Column(db.Integer, unique=False, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_stats.id"), nullable=False)

class user_search(FlaskForm):
    user = StringField("user", validators=[InputRequired()])

class sign_up(FlaskForm):
    name = StringField("name", validators=[InputRequired()])
    password = PasswordField("password", validators=[InputRequired()])

@app.route('/')
def index():
    search_form = user_search()
    return render_template("index.html", search=search_form)

@app.route('/search')
def search():
    search_form = user_search()
    search = request.args.get("user", None)

    if not search:
        return redirect(url_for('index'))

    user = user_stats.query.filter(user_stats.name == search).first()

    if not user:
        return render_template("message.html", message="User not found...", search=search_form)

    return render_template("search.html", user=user, search=search_form)

@app.route('/user/<u>')
def get_user(u):
    search_form = user_search()
    user = user_stats.query.filter(user_stats.name == u).first()

    return render_template("user.html")

@app.route('/sign_up', methods=['GET', 'POST'])
def sign_up():
    form = sign_up()

    if request.method == 'GET':
        return render_template("sign-up.html", sign_up=form)


    if not form.validate_on_submit():
        return render_template("sign-up.html", sign_up=form, message="You probably made something wrong! Try again! :3")

    url = '/auth/login'
    data = {
        'username': form.name.data,
        'password': form.password.data
    }

    response = requests.post(BASE_URL + url, json = data).json()

    if not response.get("success"):
        return render_template("sign-up.html", sign_up=form, message=response.get("message"))

    new_credentials = user_credentials(
        name=form.name.data,
        password=form.password.data
    )
    db.session.add(new_credentials)
    db.session.commit()

    return redirect(f"/user/{form.name.data}")

@scheduler.task("interval", minutes=5)
def collect_data():
    # get data from leaderboard and put it in da list
    # get data from credentials and put it in da list

    # for in loop
    # add balance to history and update balance in user_stats
    pass


if __name__ == "__main__":
    with app.app_context(): 
        db.create_all()
    app.run(debug=True)



