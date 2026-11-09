import stripe
from flask import request, redirect, jsonify, render_template, session, flash
import json
import os

def payment_routes_init(app):
    stripe_secret = app.config['STRIPE_SECRET_KEY']
    client = stripe.StripeClient(stripe_secret)
    YOUR_DOMAIN = 'http://127.0.0.1:8000'

    @app.route('/create-checkout-session', methods=['POST'])
    def create_checkout_session():
        try:
            prices = client.v1.prices.list(params={
                'lookup_keys': [request.form['lookup_key']],
                'expand': ['data.product'],
            })

            checkout_session = client.v1.checkout.sessions.create(params={
                'line_items': [
                    {
                        'price': prices.data[0].id,
                        'quantity': 1,
                    },
                ],
                'mode': 'subscription',
                'success_url': YOUR_DOMAIN +
                '/success.html?session_id={CHECKOUT_SESSION_ID}',
            })
            return redirect(checkout_session.url, code=303)
        except Exception as e:
            print(e)
            return "Server error", 500

    @app.route('/create-portal-session', methods=['POST'])
    def customer_portal():
        # For demonstration purposes, we're using the Checkout session to retrieve the customer_account ID.
        # Typically this is stored alongside the authenticated user in your database.
        checkout_session_id = request.form.get('session_id')
        checkout_session = client.v1.checkout.sessions.retrieve(checkout_session_id)

        # This is the URL to which the customer will be redirected after they're
        # done managing their billing with the portal.
        return_url = YOUR_DOMAIN

        portalSession = client.v1.billing_portal.sessions.create(params={
            'customer_account': checkout_session.customer_account,
            'return_url': return_url,
        })
        return redirect(portalSession.url, code=303)

    @app.route('/webhook', methods=['POST'])
    def webhook_received():
        # To run this example, set an environment variable STRIPE_WEBHOOK_SECRET to
        # your endpoint's unique secret.
        #
        # If you are testing with the CLI, find the secret by running 'stripe listen'.
        # If you are using an endpoint defined with the API or dashboard, look in
        # your webhook settings at https://dashboard.stripe.com/webhooks.
        #
        # Don't include webhook secrets in code.
        webhook_secret = os.environ.get('STRIPE_WEBHOOK_SECRET')

        request_data = json.loads(request.data)

        if webhook_secret:
            # Retrieve the event by verifying the signature using the raw body and secret if webhook signing is configured.
            signature = request.headers.get('stripe-signature')
            try:
                event = client.construct_event(
                    payload=request.data, sig_header=signature, secret=webhook_secret)
                data = event['data']
            except Exception as e:
                return e
            # Get the type of webhook event sent - used to check the status of PaymentIntents.
            event_type = event['type']
        else:
            data = request_data['data']
            event_type = request_data['type']
        data_object = data['object']

        print('event ' + event_type)

        if event_type == 'checkout.session.completed':
            print('🔔 Payment succeeded!')
        elif event_type == 'customer.subscription.trial_will_end':
            print('Subscription trial will end')
        elif event_type == 'customer.subscription.created':
            print('Subscription created %s', event.id)
        elif event_type == 'customer.subscription.updated':
            print('Subscription created %s', event.id)
        elif event_type == 'customer.subscription.deleted':
            # handle subscription canceled automatically based
            # upon your subscription settings. Or if the user cancels it.
            print('Subscription canceled: %s', event.id)
        elif event_type == 'entitlements.active_entitlement_summary.updated':
            # handle active entitlement summary updated
            print('Active entitlement summary updated: %s', event.id)

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