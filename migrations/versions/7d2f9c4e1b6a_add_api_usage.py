"""Add api_usage table for per-key request history

Revision ID: 7d2f9c4e1b6a
Revises: fc0ae12c8fce
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = '7d2f9c4e1b6a'
down_revision = 'fc0ae12c8fce'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'api_usage',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['key_id'], ['api_keys.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_api_usage_key_created', 'api_usage', ['key_id', 'created_at'])


def downgrade():
    op.drop_index('ix_api_usage_key_created', table_name='api_usage')
    op.drop_table('api_usage')
