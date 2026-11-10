"""Add deleted_accounts table for the account re-creation cooldown

Revision ID: b7c1d9e3f5a2
Revises: a4e8c2d6f1b3
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'b7c1d9e3f5a2'
down_revision = 'a4e8c2d6f1b3'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'deleted_accounts',
        sa.Column('email_hash', sa.String(length=64), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint('email_hash'),
    )


def downgrade():
    op.drop_table('deleted_accounts')
