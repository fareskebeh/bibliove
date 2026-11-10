import uuid

import stripe

CLOSED_SUBSCRIPTION_STATES = ('canceled', 'incomplete_expired')


def _metadata(obj):
    return obj.metadata.to_dict() if hasattr(obj.metadata, 'to_dict') else dict(obj.metadata)


def close_billing_for_user(secret_key, user):
    client = stripe.StripeClient(secret_key)
    customers = client.v1.customers.list(params={'email': user.email, 'limit': 100}).data
    owned = [customer for customer in customers if _metadata(customer).get('user_id') == str(user.id)]

    for customer in owned:
        subscriptions = client.v1.subscriptions.list(params={'customer': customer.id, 'status': 'all', 'limit': 100}).data
        for subscription in subscriptions:
            if subscription.status not in CLOSED_SUBSCRIPTION_STATES:
                client.v1.subscriptions.cancel(subscription.id)

    for customer in owned:
        client.v1.customers.delete(customer.id)

    return len(owned)


def billable_pages(included, before, after):
    return max(0, after - included) - max(0, before - included)


def report_overage(secret_key, customer_id, pages):
    client = stripe.StripeClient(secret_key)
    client.v1.billing.meter_events.create(params={
        'event_name': 'bibliove_pages',
        'payload': {'stripe_customer_id': customer_id, 'value': str(pages)},
        'identifier': f'bibliove-{uuid.uuid4().hex}',
    })
