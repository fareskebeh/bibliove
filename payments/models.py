from db.extensions import db
from sqlalchemy import JSON

FREE_PLAN_ID = 1

class Plan(db.Model):
    __tablename__='plans'

    id= db.Column(db.Integer, primary_key=True)
    name= db.Column(db.String(50))
    price_cents = db.Column(db.Integer)
    overage=db.Column(db.String(128))
    features=db.Column(JSON)
    quota_limit=db.Column(db.Integer)
    overage_cents_per_page = db.Column(db.Float, nullable=False, default=0)

    @property
    def stripe_lookup_key(self):
        return f"bibliove_{self.name.lower()}"

    @property
    def stripe_overage_lookup_key(self):
        return f"bibliove_{self.name.lower()}_overage"


class OverageReport(db.Model):
    __tablename__ = 'overage_reports'

    id = db.Column(db.String(36), primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    pages = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False)
    sent_at = db.Column(db.DateTime, nullable=True)
    attempts = db.Column(db.Integer, nullable=False, default=0)
    last_error = db.Column(db.String(255), nullable=True)
    expired = db.Column(db.Boolean, nullable=False, default=False)
