"""recreate followups table

Revision ID: e7382bc87a2d
Revises: c4185fc1e1fb
Create Date: 2025-12-07 22:15:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e7382bc87a2d'
down_revision = 'c4185fc1e1fb'
branch_labels = None
depends_on = None


def upgrade():
    # Use raw SQL to handle DROP IF EXISTS safely across migrations
    # Cascade ensures dependent constraints are removed
    op.execute("DROP TABLE IF EXISTS followups CASCADE")
    
    op.create_table('followups',
        sa.Column('id', sa.String(length=100), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('contact_name', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=False),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('date_time', sa.DateTime(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('followups')
