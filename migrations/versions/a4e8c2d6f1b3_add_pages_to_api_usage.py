"""Record processed pages on each api_usage row

Revision ID: a4e8c2d6f1b3
Revises: 7d2f9c4e1b6a
Create Date: 2026-11-10

"""
from alembic import op
import sqlalchemy as sa


revision = 'a4e8c2d6f1b3'
down_revision = '7d2f9c4e1b6a'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('api_usage', sa.Column('pages', sa.Integer(), nullable=True))


def downgrade():
    op.drop_column('api_usage', 'pages')
