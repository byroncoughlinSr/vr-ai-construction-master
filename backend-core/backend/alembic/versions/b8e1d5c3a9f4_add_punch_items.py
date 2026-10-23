"""Add the punch list

Revision ID: b8e1d5c3a9f4
Revises: f3c9a1b7d2e6
Create Date: 2026-10-22 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b8e1d5c3a9f4'
down_revision: Union[str, None] = 'f3c9a1b7d2e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'punch_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('number', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('room', sa.String(length=100), nullable=True),
        sa.Column('trade', sa.String(length=50), nullable=True),
        sa.Column('priority', sa.String(length=20), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=True),
        sa.Column('assignee', sa.String(length=255), nullable=True),
        sa.Column('due_date', sa.Date(), nullable=True),
        sa.Column('phase_id', sa.Integer(), nullable=True),
        sa.Column('closed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['phase_id'], ['construction_phases.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_punch_items_id'), 'punch_items', ['id'], unique=False)
    op.create_index(op.f('ix_punch_items_project_id'), 'punch_items', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_punch_items_project_id'), table_name='punch_items')
    op.drop_index(op.f('ix_punch_items_id'), table_name='punch_items')
    op.drop_table('punch_items')
