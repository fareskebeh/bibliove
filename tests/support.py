import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

_db_dir = tempfile.mkdtemp(prefix="bibliove-tests-")
os.environ["DB_CTX_URL"] = f"sqlite:///{_db_dir}/test.sqlite3"
os.environ["DB_URL"] = os.environ["DB_CTX_URL"]
os.environ.setdefault("STRIPE_SECRET_KEY", "sk_test_unit")
os.environ.setdefault("STRIPE_PUBLISHABLE_KEY", "pk_test_unit")
os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_unit")
os.environ.setdefault("RESEND_KEY", "re_unit")

from app import app, db  # noqa: E402
from extensions import limiter  # noqa: E402
from payments.models import Plan  # noqa: E402

app.config["TESTING"] = True
limiter.enabled = False

PLANS = [
    (1, "Free", 0, 50, 0.0, 1),
    (2, "Starter", 900, 500, 0.5, 3),
    (3, "Pro", 2900, 2500, 0.3, 10),
    (4, "Business", 7900, 10000, 0.2, 25),
]


def reset_database():
    with app.app_context():
        db.drop_all()
        db.create_all()
        for pid, name, price, quota, rate, keys in PLANS:
            db.session.add(Plan(id=pid, name=name, price_cents=price, overage="x", features=["a"],
                                quota_limit=quota, overage_cents_per_page=rate, max_keys=keys))
        db.session.commit()


def make_user(email="user@test.dev", plan_id=1, password="Correct-horse-1", master_quota=0):
    from datetime import datetime
    from werkzeug.security import generate_password_hash
    from auth.models import User
    with app.app_context():
        user = User(email=email, name="t", password_hash=generate_password_hash(password),
                    is_verified=True, plan_id=plan_id, master_quota=master_quota,
                    date_created=datetime.now(), quota_reset_at=datetime.now())
        db.session.add(user)
        db.session.commit()
        return user.id


def login(client, email):
    with client.session_transaction() as s:
        s["email"] = email


def csrf_token(client, path="/dashboard"):
    import re
    html = client.get(path).get_data(as_text=True)
    match = re.search(r'name="csrf-token" content="([^"]+)"', html) or re.search(r'name="csrf_token" value="([^"]+)"', html)
    return match.group(1)
