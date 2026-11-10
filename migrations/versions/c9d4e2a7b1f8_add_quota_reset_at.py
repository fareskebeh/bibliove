"""Add quota_reset_at to users for creation-date quota resets

Revision ID: c9d4e2a7b1f8
Revises: b7c1d9e3f5a2
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'c9d4e2a7b1f8'
down_revision = 'b7c1d9e3f5a2'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('users', sa.Column('quota_reset_at', sa.DateTime(), nullable=True))
    op.execute('UPDATE users SET quota_reset_at = date_created WHERE quota_reset_at IS NULL')


def downgrade():
    op.drop_column('users', 'quota_reset_at')
