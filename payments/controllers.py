import stripe
from flask import request, redirect, jsonify, render_template, session, flash, make_response
from flask_wtf.csrf import validate_csrf, generate_csrf
from wtforms.validators import ValidationError
import os

from auth.models import User
from db.extensions import db
from extensions import limiter
from payments.models import Plan

ACTIVE_STATUSES = ('active', 'trialing')
BILLABLE_STATUSES = ('active', 'trialing', 'past_due')


def as_dict(value):
    return value.to_dict() if hasattr(value, 'to_dict') else dict(value)


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

    def csrf_ok():
        token = request.headers.get('X-CSRFToken') or request.form.get('csrf_token')
        try:
            validate_csrf(token)
        except ValidationError:
            return False
        return True

    def move_user_to_plan(user, plan):
        current = db.session.get(Plan, user.plan_id)
        if current and plan.price_cents <= current.price_cents and plan.id != user.plan_id:
            return False
        user.plan_id = plan.id
        db.session.commit()
        return True

    def private_page(html):
        response = make_response(html)
        response.headers['Cache-Control'] = 'no-store'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = "frame-ancestors 'none'"
        return response

    def customers_for(user):
        return client.v1.customers.list(params={'email': user.email, 'limit': 10}).data

    def has_billable_subscription(customers):
        for customer in customers:
            subs = client.v1.subscriptions.list(params={'customer': customer.id, 'status': 'all', 'limit': 20})
            if any(sub.status in BILLABLE_STATUSES for sub in subs.data):
                return True
        return False

    def owned_subscription(user, subscription_id):
        sub = client.v1.subscriptions.retrieve(subscription_id)
        if as_dict(sub.metadata).get('user_id') != str(user.id):
            return None
        return sub

    @app.route('/upgrade-plan', methods=['GET'])
    def upgrade_plan():
        user = logged_in_user()
        if not user:
            return redirect('/')

        plans = Plan.query.order_by(Plan.price_cents).all()
        current = db.session.get(Plan, user.plan_id)
        return private_page(render_template(
            'upgrade-plan.jinja',
            is_authenticated=True,
            user=user,
            plans=plans,
            current_plan=current,
            csrf_token=generate_csrf(),
            stripe_publishable_key=app.config['STRIPE_PUBLISHABLE_KEY'],
        ))

    @app.route('/upgrade-plan/<int:plan_id>/subscription', methods=['POST'])
    @limiter.limit('10/minute')
    def create_subscription(plan_id):
        user = logged_in_user()
        if not user:
            return jsonify({'error': 'Sign in again to continue'}), 401
        if not csrf_ok():
            return jsonify({'error': 'Your session expired, please refresh the page'}), 400

        plan = db.session.get(Plan, plan_id)
        current = db.session.get(Plan, user.plan_id)
        if not plan or not current or plan.price_cents <= current.price_cents:
            return jsonify({'error': "That plan isn't an upgrade from your current one"}), 400

        try:
            price_id = find_price_id(plan)
            if not price_id:
                return jsonify({'error': "This plan isn't available for checkout yet"}), 409

            customers = customers_for(user)
            if has_billable_subscription(customers):
                return jsonify({'error': 'You already have a subscription. Use Manage billing to change plans'}), 409

            customer_id = customers[0].id if customers else client.v1.customers.create(params={
                'email': user.email,
                'metadata': {'user_id': str(user.id)},
            }).id

            metadata = {'user_id': str(user.id), 'plan_id': str(plan.id)}
            sub = client.v1.subscriptions.create(params={
                'customer': customer_id,
                'items': [{'price': price_id}],
                'payment_behavior': 'default_incomplete',
                'payment_settings': {'save_default_payment_method': 'on_subscription'},
                'expand': ['latest_invoice.payments'],
                'metadata': metadata,
            })
        except stripe.StripeError as e:
            app.logger.error("Subscription creation failed: %s", e)
            return jsonify({'error': 'Could not start checkout, please try again'}), 502

        invoice_payments = sub.latest_invoice.payments.data if sub.latest_invoice and sub.latest_invoice.payments else []
        if not invoice_payments:
            return jsonify({'error': 'Could not start checkout, please try again'}), 502

        try:
            payment_intent = client.v1.payment_intents.retrieve(invoice_payments[0].payment.payment_intent)
        except stripe.StripeError as e:
            app.logger.error("Payment intent lookup failed: %s", e)
            return jsonify({'error': 'Could not start checkout, please try again'}), 502

        response = jsonify({
            'subscriptionId': sub.id,
            'clientSecret': payment_intent.client_secret,
            'status': sub.status,
        })
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.route('/upgrade-plan/subscription/cancel', methods=['POST'])
    def cancel_pending_subscription():
        user = logged_in_user()
        if not user:
            return jsonify({'error': 'Sign in again to continue'}), 401
        if not csrf_ok():
            return jsonify({'error': 'Your session expired, please refresh the page'}), 400

        subscription_id = (request.get_json(silent=True) or {}).get('subscriptionId', '')
        if not isinstance(subscription_id, str) or not subscription_id.startswith('sub_'):
            return jsonify({'error': 'Invalid request'}), 400

        try:
            sub = owned_subscription(user, subscription_id)
            if not sub or sub.status != 'incomplete':
                return jsonify({'error': 'Subscription not found'}), 404
            client.v1.subscriptions.cancel(subscription_id)
        except stripe.StripeError as e:
            app.logger.error("Pending subscription cancel failed: %s", e)
            return jsonify({'error': 'Could not update your subscription, please try again'}), 502

        return jsonify({'status': 'canceled'})

    @app.route('/upgrade-plan/success', methods=['GET'])
    def upgrade_success():
        user = logged_in_user()
        if not user:
            return redirect('/')

        subscription_id = request.args.get('subscription', '')
        if not subscription_id.startswith('sub_'):
            return redirect('/upgrade-plan')

        try:
            sub = owned_subscription(user, subscription_id)
        except stripe.StripeError as e:
            app.logger.error("Could not load subscription: %s", e)
            flash("We couldn't confirm your payment, please try again", "error")
            return redirect('/upgrade-plan')

        if not sub:
            flash("We couldn't confirm your payment, please try again", "error")
            return redirect('/upgrade-plan')

        if sub.status not in ACTIVE_STATUSES:
            flash("Your payment is still processing, your plan will update shortly", "warning")
            return redirect('/upgrade-plan')

        plan = db.session.get(Plan, int(as_dict(sub.metadata)['plan_id']))
        if plan and move_user_to_plan(user, plan):
            flash(f"You're now on the {plan.name} plan", "success")
        return redirect('/upgrade-plan')

    @app.route('/billing-portal', methods=['POST'])
    def billing_portal():
        user = logged_in_user()
        if not user:
            return redirect('/')
        if not csrf_ok():
            flash("Your session expired, please try again", "error")
            return redirect('/upgrade-plan')

        try:
            customers = customers_for(user)
            if not customers:
                flash("No billing account found for this email yet", "warning")
                return redirect('/upgrade-plan')

            portal = client.v1.billing_portal.sessions.create(params={
                'customer': customers[0].id,
                'return_url': base_url() + '/upgrade-plan',
            })
        except stripe.StripeError as e:
            app.logger.error("Billing portal failed: %s", e)
            flash("Could not open billing, please try again", "error")
            return redirect('/upgrade-plan')

        return redirect(portal.url, code=303)

    @app.route('/webhook', methods=['POST'])
    @limiter.exempt
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

        obj = as_dict(event['data']['object'])
        event_type = event['type']

        if event_type in ('customer.subscription.created', 'customer.subscription.updated'):
            metadata = obj.get('metadata', {})
            if obj.get('status') in ACTIVE_STATUSES and metadata.get('user_id') and metadata.get('plan_id'):
                user = db.session.get(User, int(metadata['user_id']))
                plan = db.session.get(Plan, int(metadata['plan_id']))
                if user and plan:
                    move_user_to_plan(user, plan)

        elif event_type == 'customer.subscription.deleted':
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
