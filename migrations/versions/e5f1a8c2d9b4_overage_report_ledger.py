"""Replace unreported overage counter with a per-report ledger

Revision ID: e5f1a8c2d9b4
Revises: d2a6f0b8c3e1
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'e5f1a8c2d9b4'
down_revision = 'd2a6f0b8c3e1'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'overage_reports',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('pages', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('sent_at', sa.DateTime(), nullable=True),
        sa.Column('attempts', sa.Integer(), nullable=False),
        sa.Column('last_error', sa.String(length=255), nullable=True),
        sa.Column('expired', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('users') as batch:
        batch.drop_column('unreported_overage_pages')


def downgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('unreported_overage_pages', sa.Integer(), nullable=False, server_default='0'))
    op.drop_table('overage_reports')
