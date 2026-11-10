from flask import jsonify, render_template, request, redirect, make_response, url_for, flash
from .models import User, ResetToken
from db.extensions import db
import re
import random
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash
from payments.models import Plan, FREE_PLAN_ID
from datetime import datetime, timedelta
from keymanager.models import ApiKey, ApiUsage
from keymanager.usage import scope_edges, usage_series
from hashlib import sha256
import secrets
import os
from dotenv import load_dotenv
import resend
from extensions import limiter, csrf_valid

load_dotenv()

RESEND_KEY= os.getenv("RESEND_KEY")
resend.api_key = RESEND_KEY

def generate_code():
    return random.randint(0000000, 9999999)

def auth_routes_init(app):
    
    @app.route("/home", methods=["GET"])
    @limiter.limit('100/minute')
    def home():
        is_authenticated = True if session.get("email") else False
        return render_template("home.jinja", is_authenticated=is_authenticated)
    
    @app.route("/", methods=["GET"])
    def index():
        return redirect("/home")
    
    @app.route('/register', methods=['GET', 'POST'])
    @limiter.limit('10/hour')
    def register():

        if request.method == 'POST' and not csrf_valid():
            flash("Your session expired, please try again", "error")
            return redirect(request.full_path)
        #  get the plan they chose ln #42
        chosen_plan = request.args.get('plan')
        is_authenticated = True if session.get("email") else False
        if is_authenticated:
            return redirect("/home")
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            
            if email:
                email_valid = re.match("^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email)
                if email_valid:
                    user = User.query.filter_by(email=email).first()
                    if user:
                        if user.is_verified:
                            flash("User already exists, please log in", "error")
                            return redirect("/login")
                        else:
                            code = generate_code()
                            #print(f"CODE HAS BEEN SENT {email} \nDEBUG: {code}")
                            r= resend.Emails.send( {
                                "from" : "onboarding@resend.dev",
                                "to" : email,
                                "subject" : "Your Bibliove verification code",
                                "html" : f"<p>Copy this code and paste it in the verification input field</p> <h2>{code}</h2>"
                            })
                            session['pending_verification_email'] = email
                            session['pending_verification_code'] = code
                            return redirect("/verify")
                    else:
                        user = User(email=email, password_hash=generate_password_hash(password))
                        db.session.add(user)
                        db.session.commit()
                        code = generate_code()
                        #print(f"CODE HAS BEEN SENT {email} \nDEBUG: {code}")
                        r= resend.Emails.send( {
                                "from" : "onboarding@resend.dev",
                                "to" : email,
                                "subject" : "Your Bibliove verification code",
                                "html" : f"<p>Copy this code and paste it in the verification input field</p> <h2>{code}</h2>"
                            })
                        session['pending_verification_email'] = email
                        session['pending_verification_code'] = code
                        session['chosen_plan_id'] = chosen_plan

                        return redirect("/verify")
                else:
                    flash("Invalid email format", "error")
            else:
                flash("Email is required", "error")
        
        return render_template('register.jinja', is_authenticated=is_authenticated)

    @app.route("/verify", methods=["GET", "POST"])
    @limiter.limit('20/hour')
    def verify_email():

        if request.method == 'POST' and not csrf_valid():
            flash("Your session expired, please try again", "error")
            return redirect(request.full_path)
        email = session.get("pending_verification_email")
        if not email:
            flash("No verification in progress", "error")
            return redirect("/register")
        
        if request.method == "POST":
            code_user = str(request.form.get("code"))
            code_db = str(session.get("pending_verification_code"))

            if code_user == code_db:
                # THis is in case the user inputs the correct code
                user = User.query.filter_by(email=email).first()
                if user:
                    user.is_verified = True
                    db.session.commit()
                    session.pop('pending_verification_code', None)
                    chosen_plan = (session.get('chosen_plan_id') or '').strip().lower()
                    flash("Email verified! Please log in" + ("" if not chosen_plan or chosen_plan == 'free' else " to choose your plan") + ".", "success")
                    session.pop('pending_verification_email', None)
                    return redirect("/login")
                else:
                    flash("User not found", "error")
                    return redirect("/register")
            else:
                flash("Invalid verification code", "error")
                return redirect('/verify')
        
        return render_template("verify.jinja", is_authenticated=True if email else False)

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('10/minute')
    def login():

        if request.method == 'POST' and not csrf_valid():
            flash("Your session expired, please try again", "error")
            return redirect(request.full_path)
        is_authenticated = True if session.get("email") else False
        if is_authenticated:
            return redirect("/home")
        
        if request.method == 'POST':
            email = request.form['email']
            password = request.form['password']
            user = User.query.filter_by(email=email).first()
            
            if not user:
                flash("Invalid email/password", "error")
                return render_template('login.jinja', is_authenticated=is_authenticated)
            
            if not user.is_verified:
                code = generate_code()
                r= resend.Emails.send( {
                                "from" : "onboarding@resend.dev",
                                "to" : email,
                                "subject" : "Your Bibliove verification code",
                                "html" : f"<p>Copy this code and paste it in the verification input field</p> <h2>{code}</h2>"
                            })
                session['pending_verification_email'] = email
                session['pending_verification_code'] = code
                flash("Please verify your email first", "warning")
                return redirect("/verify")
            
            if check_password_hash(user.password_hash, password):
                session['email'] = email
                session['logged_in'] = True
                return redirect(url_for('home'))
            else:
                flash("Invalid email/password", "error")
        
        return render_template('login.jinja', is_authenticated=is_authenticated)
    
    @app.route('/logout')
    def logout():
        session.clear()
        return redirect(url_for('home'))
    
    @app.route('/dashboard')
    @limiter.limit('100/minute')
    def dashboard():
        is_authenticated = True if session.get("email") else False
        if not is_authenticated:
            flash("Please log in first", "warning")
            return redirect("/login")
        user = User.query.filter(User.email==session.get("email")).first()
        if not user:
            session.clear()
            return redirect("/")
        user_keys = ApiKey.query.filter(ApiKey.user_id==user.id)
        keys = user_keys.all()
        entries_by_key = {k.id: [] for k in keys}
        year_start = scope_edges(datetime.now())['year'][0]
        for key_id, created_at, pages in db.session.query(ApiUsage.key_id, ApiUsage.created_at, ApiUsage.pages).filter(ApiUsage.user_id==user.id, ApiUsage.created_at>=year_start).all():
            if key_id in entries_by_key:
                entries_by_key[key_id].append((created_at, pages))
        series = usage_series(entries_by_key)
        usage_keys = [{"id": k.id, "name": k.name, "series": series[k.id]} for k in keys]
        recent_rows = db.session.query(ApiUsage.created_at, ApiKey.name).join(ApiKey, ApiKey.id == ApiUsage.key_id).filter(ApiUsage.user_id==user.id).order_by(ApiUsage.created_at.desc()).limit(10).all()
        recent_requests = [{"key_name": name, "created_at": created_at} for created_at, name in recent_rows]
        plan = db.session.get(Plan, user.plan_id)
        is_free = user.plan_id == FREE_PLAN_ID
        can_create = not is_free or user.key_count < 1
        return render_template("dashboard.jinja", is_authenticated=is_authenticated, email=session.get("email"), user_keys=keys, user=user, plan=plan, is_free=is_free, can_create=can_create, usage_keys=usage_keys, recent_requests=recent_requests)

    @app.route('/pricing')
    @limiter.limit('100/minute')
    def pricing():
        is_authenticated = True if session.get("email") else False
        user = User.query.filter(User.email==session.get("email")).first()
        plans = Plan.query.order_by(Plan.price_cents).all()
        current_plan = db.session.get(Plan, user.plan_id) if user else None
        return render_template("pricing.jinja", plans=plans, is_authenticated=is_authenticated, user=user, current_plan=current_plan)
    
    @app.route('/password-reset', methods=['GET', 'POST'])
    @limiter.limit('5/hour')
    def forgot_pw():

        if request.method == 'POST' and not csrf_valid():
            flash("Your session expired, please try again", "error")
            return redirect(request.full_path)
        is_authenticated = True if session.get("email") else False
        if request.method == 'POST':
            email = request.form['email']
            user = User.query.filter_by(email=email).first()
            if not user:
                flash("This user does not exist, please create an account", "error")
                return redirect('/forgot-password')
            if not user.is_verified:
                flash("Verify this account before attempting to reset password", "error")
                return redirect('/forgot-password')
            flash("Email sent, Check your inbox", "success")
            url_token = secrets.token_urlsafe(32)
            token = ResetToken(user_id=user.id, hash=sha256(url_token.encode()).hexdigest())
            r= resend.Emails.send( {
                                "from" : "onboarding@resend.dev",
                                "to" : email,
                                "subject" : "Your Bibliove password reset link",
                                "html" : f"<h1>Visit this link to reset your password</h1> <p>http://127.0.0.1:8000/reset-password?token={url_token}</p>"
                            })
            db.session.add(token)
            db.session.commit()

        return render_template('forgot-password.jinja', is_authenticated=is_authenticated)
    
    @app.route('/reset-password', methods=['GET', 'POST'])
    @limiter.limit('10/hour')
    def reset_password():

        if request.method == 'POST' and not csrf_valid():
            flash("Your session expired, please try again", "error")
            return redirect(request.full_path)
        is_authenticated = True if session.get("email") else False
        
        token = request.args.get('token')
        if token:
            query_hash= str(sha256(token.encode()).hexdigest())
            match = ResetToken.query.filter_by(hash=query_hash).first()
            if not match or match.used or match.expires_at is None or match.expires_at < datetime.now():
                #TODO: placeholder for error msg/page
                return redirect('/')
            else:
                if request.method=='GET':
                    user = User.query.filter_by(id=match.user_id).first()
                    if not user:
                        flash('User not found')
                        return redirect('/login')
                    return render_template('reset-password.jinja', is_authenticated=is_authenticated)
                elif request.method=='POST':
                    new_pw= request.form['password1']
                    new_pw_hash= generate_password_hash(new_pw)
                    user = User.query.filter_by(id=match.user_id).first()
                    if not user:
                        flash('User not found')
                        return redirect('/login')
                    old_pw= user.password_hash
                    print(f"{old_pw} \n {new_pw_hash}")
                    if check_password_hash(user.password_hash, new_pw):
                        flash('Password cannot be the same as old password')
                        return redirect(f'/reset-password?token={token}')
                    else:
                        match.used= True
                        user.password_hash= new_pw_hash
                        db.session.commit()
                        flash('Password successfully reset', 'success')
                        return redirect('/login')

    @app.route('/settings', methods=['GET'])
    @limiter.limit('100/minute')
    def settings_get():
        email = session.get('email')
        if not email:
            return redirect('/')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return redirect('/')
        
        return render_template('settings.jinja',
            is_authenticated=True,
        )