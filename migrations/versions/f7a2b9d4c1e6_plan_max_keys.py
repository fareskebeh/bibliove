"""Add per-plan API key limits

Revision ID: f7a2b9d4c1e6
Revises: e5f1a8c2d9b4
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'f7a2b9d4c1e6'
down_revision = 'e5f1a8c2d9b4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('plans', sa.Column('max_keys', sa.Integer(), nullable=False, server_default='1'))
    op.execute("UPDATE plans SET max_keys = 1 WHERE name = 'Free'")
    op.execute("UPDATE plans SET max_keys = 3 WHERE name = 'Starter'")
    op.execute("UPDATE plans SET max_keys = 10 WHERE name = 'Pro'")
    op.execute("UPDATE plans SET max_keys = 25 WHERE name = 'Business'")


def downgrade():
    op.drop_column('plans', 'max_keys')
