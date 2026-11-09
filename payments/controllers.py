import stripe
from flask import request, redirect, jsonify, render_template, session, flash
import os

from auth.models import User
from db.extensions import db
from payments.models import Plan


def payment_routes_init(app):
    client = stripe.StripeClient(app.config['STRIPE_SECRET_KEY'])

    def logged_in_user():
        email = session.get('email')
        if not email:
            return None
        return User.query.filter_by(email=email).first()

    def base_url():
        return request.host_url.rstrip('/')

    def find_price_id(plan):
        prices = client.v1.prices.list(params={
            'lookup_keys': [plan.stripe_lookup_key],
            'limit': 1,
        })
        return prices.data[0].id if prices.data else None

    def move_user_to_plan(user, plan):
        current = db.session.get(Plan, user.plan_id)
        if current and plan.price_cents <= current.price_cents and plan.id != user.plan_id:
            return False
        user.plan_id = plan.id
        db.session.commit()
        return True

    @app.route('/upgrade-plan', methods=['GET'])
    def upgrade_plan():
        user = logged_in_user()
        if not user:
            return redirect('/')

        plans = Plan.query.order_by(Plan.price_cents).all()
        current = db.session.get(Plan, user.plan_id)
        return render_template(
            'upgrade-plan.jinja',
            is_authenticated=True,
            user=user,
            plans=plans,
            current_plan=current,
        )

    @app.route('/upgrade-plan/<int:plan_id>', methods=['POST'])
    def start_upgrade(plan_id):
        user = logged_in_user()
        if not user:
            return redirect('/')

        plan = db.session.get(Plan, plan_id)
        current = db.session.get(Plan, user.plan_id)
        if not plan or not current or plan.price_cents <= current.price_cents:
            flash("That plan isn't an upgrade from your current one", "error")
            return redirect('/upgrade-plan')

        try:
            price_id = find_price_id(plan)
            if not price_id:
                flash("This plan isn't available for checkout yet", "error")
                return redirect('/upgrade-plan')

            metadata = {'user_id': str(user.id), 'plan_id': str(plan.id)}
            checkout = client.v1.checkout.sessions.create(params={
                'mode': 'subscription',
                'line_items': [{'price': price_id, 'quantity': 1}],
                'customer_email': user.email,
                'client_reference_id': str(user.id),
                'metadata': metadata,
                'subscription_data': {'metadata': metadata},
                'success_url': base_url() + '/upgrade-plan/success?session_id={CHECKOUT_SESSION_ID}',
                'cancel_url': base_url() + '/upgrade-plan',
            })
        except stripe.StripeError as e:
            app.logger.error("Checkout creation failed: %s", e)
            flash("Could not start checkout, please try again", "error")
            return redirect('/upgrade-plan')

        return redirect(checkout.url, code=303)

    @app.route('/upgrade-plan/success', methods=['GET'])
    def upgrade_success():
        user = logged_in_user()
        if not user:
            return redirect('/')

        session_id = request.args.get('session_id')
        if not session_id:
            return redirect('/upgrade-plan')

        try:
            checkout = client.v1.checkout.sessions.retrieve(session_id)
        except stripe.StripeError as e:
            app.logger.error("Could not load checkout session: %s", e)
            flash("We couldn't confirm your payment, please try again", "error")
            return redirect('/upgrade-plan')

        if checkout.metadata.get('user_id') != str(user.id) or checkout.status != 'complete':
            flash("Your payment hasn't been confirmed yet", "warning")
            return redirect('/upgrade-plan')

        plan = db.session.get(Plan, int(checkout.metadata['plan_id']))
        if plan and move_user_to_plan(user, plan):
            flash(f"You're now on the {plan.name} plan", "success")
        return redirect('/upgrade-plan')

    @app.route('/billing-portal', methods=['POST'])
    def billing_portal():
        user = logged_in_user()
        if not user:
            return redirect('/')

        try:
            customers = client.v1.customers.list(params={'email': user.email, 'limit': 1})
            if not customers.data:
                flash("No billing account found for this email yet", "warning")
                return redirect('/upgrade-plan')

            portal = client.v1.billing_portal.sessions.create(params={
                'customer': customers.data[0].id,
                'return_url': base_url() + '/upgrade-plan',
            })
        except stripe.StripeError as e:
            app.logger.error("Billing portal failed: %s", e)
            flash("Could not open billing, please try again", "error")
            return redirect('/upgrade-plan')

        return redirect(portal.url, code=303)

    @app.route('/webhook', methods=['POST'])
    def stripe_webhook():
        secret = os.getenv('STRIPE_WEBHOOK_SECRET')
        if not secret:
            app.logger.error("STRIPE_WEBHOOK_SECRET is not set")
            return jsonify({'error': 'webhook not configured'}), 500

        try:
            event = stripe.Webhook.construct_event(
                request.data, request.headers.get('Stripe-Signature', ''), secret
            )
        except (ValueError, stripe.SignatureVerificationError):
            return jsonify({'error': 'invalid signature'}), 400

        obj = event['data']['object']

        if event['type'] == 'checkout.session.completed' and obj.get('mode') == 'subscription':
            user = db.session.get(User, int(obj['metadata']['user_id']))
            plan = db.session.get(Plan, int(obj['metadata']['plan_id']))
            if user and plan:
                move_user_to_plan(user, plan)

        elif event['type'] == 'customer.subscription.deleted':
            user_id = obj.get('metadata', {}).get('user_id')
            user = db.session.get(User, int(user_id)) if user_id else None
            if user:
                user.plan_id = Plan.query.order_by(Plan.price_cents).first().id
                db.session.commit()

        return jsonify({'status': 'success'})

    @app.route('/dummy-checkout', methods=['GET', 'POST'])
    def dummy_checkout():
        is_authenticated= session.get('email')
        chosen_plan = session.get('chosen_plan_id')
        result = request.form.get('result')
        if request.method == 'GET':
            return render_template('dummy.jinja', is_authenticated=is_authenticated)
        elif request.method == 'POST':
            email = session.get('pending_verification_email')
            if result == 'success':
                flash('Subscription bought', "success")
                return redirect('/login')
            else:
                flash('Session rolled back', "warning")
                return redirect('/login')
