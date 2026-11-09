from db.extensions import db
from sqlalchemy import JSON

class Plan(db.Model):
    __tablename__='plans'

    id= db.Column(db.Integer, primary_key=True)
    name= db.Column(db.String(50))
    price_cents = db.Column(db.Integer)
    overage=db.Column(db.String(128))
    features=db.Column(JSON)
    quota_limit=db.Column(db.Integer)

    @property
    def stripe_lookup_key(self):
        return f"bibliove_{self.name.lower()}"
