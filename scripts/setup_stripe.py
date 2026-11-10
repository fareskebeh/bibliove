import argparse
import os
import sys
from pathlib import Path

import stripe
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PLANS = [
    ("Starter", 900, "0.5"),
    ("Pro", 2900, "0.3"),
    ("Business", 7900, "0.2"),
]
METER_EVENT = "bibliove_pages"


def find_price(client, lookup_key):
    found = client.v1.prices.list(params={"lookup_keys": [lookup_key], "limit": 1}).data
    return found[0] if found else None


def find_meter(client):
    for meter in client.v1.billing.meters.list(params={"limit": 100}).data:
        if meter.event_name == METER_EVENT and meter.status == "active":
            return meter
    return None


def ensure_meter(client, apply):
    meter = find_meter(client)
    if meter:
        print(f"  exists  meter {meter.id} ({METER_EVENT})")
        return meter.id
    if not apply:
        print(f"  would create meter ({METER_EVENT})")
        return None
    meter = client.v1.billing.meters.create(params={
        "display_name": "Bibliove pages",
        "event_name": METER_EVENT,
        "default_aggregation": {"formula": "sum"},
        "customer_mapping": {"event_payload_key": "stripe_customer_id", "type": "by_id"},
        "value_settings": {"event_payload_key": "value"},
    })
    print(f"  created meter {meter.id}")
    return meter.id


def ensure_base_price(client, name, cents, apply):
    lookup = f"bibliove_{name.lower()}"
    price = find_price(client, lookup)
    if price:
        print(f"  exists  {lookup} {price.id}")
        return
    if not apply:
        print(f"  would create {lookup} ${cents / 100:.2f}/month")
        return
    price = client.v1.prices.create(params={
        "currency": "usd",
        "unit_amount": cents,
        "recurring": {"interval": "month"},
        "lookup_key": lookup,
        "product_data": {"name": f"Bibliove {name}"},
    })
    print(f"  created {lookup} {price.id}")


def ensure_overage_price(client, name, cents_per_page, meter_id, apply):
    lookup = f"bibliove_{name.lower()}_overage"
    price = find_price(client, lookup)
    if price:
        print(f"  exists  {lookup} {price.id}")
        return
    if not apply:
        print(f"  would create {lookup} {cents_per_page} cents/page")
        return
    if meter_id is None:
        raise SystemExit("cannot create overage prices without a meter")
    price = client.v1.prices.create(params={
        "currency": "usd",
        "unit_amount_decimal": cents_per_page,
        "recurring": {"interval": "month", "usage_type": "metered", "meter": meter_id},
        "lookup_key": lookup,
        "product_data": {"name": f"Bibliove {name} page overage"},
    })
    print(f"  created {lookup} {price.id}")


def ensure_webhook(client, url, apply):
    endpoints = client.v1.webhook_endpoints.list(params={"limit": 100}).data
    for endpoint in endpoints:
        if endpoint.url == url:
            print(f"  exists  webhook endpoint {endpoint.id} for {url}")
            return
    if not apply:
        print(f"  would create webhook endpoint for {url}")
        return
    endpoint = client.v1.webhook_endpoints.create(params={
        "url": url,
        "enabled_events": [
            "invoice.paid",
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        ],
    })
    print(f"  created webhook endpoint {endpoint.id}")
    print(f"  signing secret (shown once, put it in STRIPE_WEBHOOK_SECRET): {endpoint.secret}")


def main():
    parser = argparse.ArgumentParser(description="Create Bibliove's Stripe products, prices, meter and webhook.")
    parser.add_argument("--mode", choices=["test", "live"], default="test")
    parser.add_argument("--apply", action="store_true", help="create missing objects; without it, only report")
    parser.add_argument("--webhook-url", help="public URL ending in /webhook to register")
    args = parser.parse_args()

    key = os.getenv("STRIPE_SECRET_KEY", "")
    expected = "sk_test_" if args.mode == "test" else "sk_live_"
    if not key.startswith(expected):
        sys.exit(f"STRIPE_SECRET_KEY does not match --mode {args.mode} (expected a {expected}… key)")

    client = stripe.StripeClient(key)
    print(f"Stripe {args.mode} mode, {'applying' if args.apply else 'dry run'}")

    print("Base prices:")
    for name, cents, _ in PLANS:
        ensure_base_price(client, name, cents, args.apply)

    print("Meter:")
    meter_id = ensure_meter(client, args.apply)

    print("Overage prices:")
    for name, _, rate in PLANS:
        ensure_overage_price(client, name, rate, meter_id, args.apply)

    if args.webhook_url:
        print("Webhook:")
        ensure_webhook(client, args.webhook_url, args.apply)


if __name__ == "__main__":
    main()
