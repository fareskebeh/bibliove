import hashlib
import hmac
from datetime import datetime, timedelta

from flask import current_app

from auth.models import DeletedAccount
from db.extensions import db

REENTRY_COOLDOWN = timedelta(days=30)


def normalize_email(email):
    return email.strip().lower()


def email_fingerprint(email):
    return hmac.new(
        current_app.config['SECRET_KEY'].encode(),
        normalize_email(email).encode(),
        hashlib.sha256,
    ).hexdigest()


def reentry_available_on(email):
    record = db.session.get(DeletedAccount, email_fingerprint(email))
    if record is None:
        return None
    available = record.deleted_at + REENTRY_COOLDOWN
    if available > datetime.now():
        return available
    db.session.delete(record)
    db.session.commit()
    return None


def record_deletion(email):
    record = db.session.get(DeletedAccount, email_fingerprint(email))
    if record is None:
        record = DeletedAccount(email_hash=email_fingerprint(email))
        db.session.add(record)
    record.deleted_at = datetime.now()
