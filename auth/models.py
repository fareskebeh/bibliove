from db.extensions import db
from datetime import datetime, timedelta
from keymanager.models import ApiKey
from sqlalchemy.ext.hybrid import hybrid_property

class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    email = db.Column(db.String(70), unique=True)
    date_created=db.Column(db.DateTime, default=datetime.now)
    is_verified=db.Column(db.Boolean, default=False)
    password_hash = db.Column(db.String(255))
    plan_id = db.Column(db.Integer, db.ForeignKey('plans.id'), nullable=False, default=1)
    master_quota = db.Column(db.Integer, default=0)
    quota_reset_at = db.Column(db.DateTime, nullable=True)
    billing_start = db.Column(db.DateTime, default=datetime.now)
    @hybrid_property
    def key_count(self):
        return db.session.query(db.func.count(ApiKey.id)).filter(ApiKey.user_id == self.id).scalar()
    
class ResetToken(db.Model):
    __tablename__ = 'reset_tokens'
    id= db.Column(db.Integer, primary_key=True)
    hash = db.Column(db.String(255))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    date_created=db.Column(db.DateTime, default=datetime.now)
    expires_at = db.Column(db.DateTime, default=lambda: datetime.now() + timedelta(hours=1))
    used = db.Column(db.Boolean, default=False)

class DeletedAccount(db.Model):
    __tablename__ = 'deleted_accounts'

    email_hash = db.Column(db.String(64), primary_key=True)
    deleted_at = db.Column(db.DateTime, nullable=False, default=datetime.now)
