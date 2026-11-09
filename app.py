from flask import Flask, jsonify, render_template
from dotenv import load_dotenv
import os
from core.controllers import core_routes_init
from auth.controllers import auth_routes_init
from keymanager.controllers import key_routes_init
from flask_migrate import Migrate
from db.extensions import db
from auth.models import User
from keymanager.models import ApiKey
from payments.models import Plan
from extensions import limiter
from payments.controllers import payment_routes_init

load_dotenv()

app = Flask(__name__, template_folder="auth/templates")
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DB_CTX_URL")
app.config["REMEMBER_COOKIE_SAMESITE"] = os.getenv("REMEMBER_COOKIE_SAMESITE")
app.config["SESSION_COOKIE_SAMESITE"] = os.getenv("SESSION_COOKIE_SAMESITE")
app.config["SECRET_KEY"] = os.getenv("SECRET_KEY")
app.config['STRIPE_SECRET_KEY'] = os.getenv('STRIPE_SECRET_KEY')
app.config['STRIPE_PUBLISHABLE_KEY'] = os.getenv('STRIPE_PUBLISHABLE_KEY')


db.init_app(app)

migrate = Migrate(app, db)

limiter.init_app(app)

core_routes_init(app)
auth_routes_init(app)
key_routes_init(app)
payment_routes_init(app)

@app.errorhandler(429)
def ratelimit_handler():
    return jsonify({
        "error": "Too many requests",
        "message": "Rate limit exceeded. Please slow down.",
    }), 429

@app.errorhandler(429)
def ratelimit_handler(e):
    return render_template("429.jinja"), 429

DEBUG=True if os.getenv("DEBUG") == 'True' else False
if __name__ == "__main__":
    app.run('0.0.0.0',debug=DEBUG, port=8000)