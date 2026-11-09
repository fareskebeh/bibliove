from flask import jsonify, render_template, request, redirect, make_response, url_for, flash
from .models import User, ResetToken
from db.extensions import db
import re
import random
from flask import session
from werkzeug.security import generate_password_hash, check_password_hash
from payments.models import Plan
from keymanager.models import ApiKey
from hashlib import sha256
import secrets
import os
from dotenv import load_dotenv
import resend
from extensions import limiter

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
    #change before I quit
    @limiter.limit('10000/hour')
    def register():
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
    @limiter.limit('10/hour')
    def verify_email():
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
                    chosen_plan = session.get('chosen_plan_id')
                    if not chosen_plan or chosen_plan =='Free':
                        flash("Email verified! Please log in.", "success")
                        session.pop('pending_verification_email', None)
                        return redirect("/login")
                    else:
                        return redirect('/dummy-checkout')
                else:
                    flash("User not found", "error")
                    return redirect("/register")
            else:
                flash("Invalid verification code", "error")
                return redirect('/verify')
        
        return render_template("verify.jinja", is_authenticated=True if email else False)

    @app.route('/login', methods=['GET', 'POST'])
    @limiter.limit('10/hour')
    def login():
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
        return render_template("dashboard.jinja", is_authenticated=is_authenticated, email=session.get("email"), user_keys=user_keys, user=user)

    @app.route('/pricing')
    @limiter.limit('100/minute')
    def pricing():
        is_authenticated = True if session.get("email") else False
        user = User.query.filter(User.email==session.get("email")).first()
        plans = Plan.query.all()
        return render_template("pricing.jinja", plans=plans, is_authenticated=is_authenticated, user=user)
    
    @app.route('/password-reset', methods=['GET', 'POST'])
    @limiter.limit('5/hour')
    def forgot_pw():
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
    @limiter.limit('3/hour')
    def reset_password():
        is_authenticated = True if session.get("email") else False
        
        token = request.args.get('token')
        if token:
            query_hash= str(sha256(token.encode()).hexdigest())
            match = ResetToken.query.filter_by(hash=query_hash).first()
            if not match or match.used:
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
    
    @app.route('/upgrade-plan', methods=['GET'])
    @limiter.limit('100/minute')
    def upgrade_plan_get():
        email = session.get('email')
        if not email:
            return redirect('/')
        
        user = User.query.filter_by(email=email).first()
        if not user:
            return redirect('/')
        
        return render_template('upgrade-plan.jinja', 
            is_authenticated=True, 
        )