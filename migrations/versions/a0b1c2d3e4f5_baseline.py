"""Baseline schema: plans, users and api_keys as they were before the migration chain

Revision ID: a0b1c2d3e4f5
Revises:
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'a0b1c2d3e4f5'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=True),
        sa.Column('price_cents', sa.Integer(), nullable=True),
        sa.Column('features', sa.JSON(), nullable=True),
        sa.Column('quota_limit', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=70), nullable=True),
        sa.Column('date_created', sa.DateTime(), nullable=True),
        sa.Column('is_verified', sa.Boolean(), nullable=True),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('plan_id', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('master_quota', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('email'),
    )
    op.create_table(
        'api_keys',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('key_hash', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade():
    op.drop_table('api_keys')
    op.drop_table('users')
    op.drop_table('plans')
