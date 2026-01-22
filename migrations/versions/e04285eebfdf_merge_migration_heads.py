"""Merge migration heads

Revision ID: e04285eebfdf
Revises: safe_inc_update, e7382bc87a2d
Create Date: 2026-01-22 17:09:07.049055

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e04285eebfdf'
down_revision = ('safe_inc_update', 'e7382bc87a2d')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
