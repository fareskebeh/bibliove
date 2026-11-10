from db.extensions import db
from datetime import datetime

class ApiKey(db.Model):
    __tablename__ = "api_keys"

    id=db.Column(db.Integer, primary_key=True, unique=True)
    key_hash = db.Column(db.String(255), nullable=False)
    name=db.Column(db.String(100))
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)


class ApiUsage(db.Model):
    __tablename__ = "api_usage"
    __table_args__ = (db.Index('ix_api_usage_key_created', 'key_id', 'created_at'),)

    id = db.Column(db.Integer, primary_key=True)
    key_id = db.Column(db.Integer, db.ForeignKey('api_keys.id', ondelete='CASCADE'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)