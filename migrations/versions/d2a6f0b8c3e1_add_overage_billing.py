"""Add per-page overage rates, Stripe customer ids and unreported overage counts

Revision ID: d2a6f0b8c3e1
Revises: c9d4e2a7b1f8
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'd2a6f0b8c3e1'
down_revision = 'c9d4e2a7b1f8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('plans', sa.Column('overage_cents_per_page', sa.Float(), nullable=False, server_default='0'))
    op.add_column('users', sa.Column('stripe_customer_id', sa.String(length=64), nullable=True))
    op.add_column('users', sa.Column('unreported_overage_pages', sa.Integer(), nullable=False, server_default='0'))
    op.execute("UPDATE plans SET overage_cents_per_page = 0.5 WHERE name = 'Starter'")
    op.execute("UPDATE plans SET overage_cents_per_page = 0.3 WHERE name = 'Pro'")
    op.execute("UPDATE plans SET overage_cents_per_page = 0.2 WHERE name = 'Business'")


def downgrade():
    op.drop_column('users', 'unreported_overage_pages')
    op.drop_column('users', 'stripe_customer_id')
    op.drop_column('plans', 'overage_cents_per_page')
