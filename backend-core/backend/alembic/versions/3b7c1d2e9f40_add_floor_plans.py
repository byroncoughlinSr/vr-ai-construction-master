"""Add versioned floor plans

Revision ID: 3b7c1d2e9f40
Revises: 85fad89572ff
Create Date: 2026-10-11 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3b7c1d2e9f40'
down_revision: Union[str, None] = '85fad89572ff'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('floor_plans',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('layout', sa.JSON(), nullable=True),
        sa.Column('rooms', sa.JSON(), nullable=False),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('change_note', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('image_url', sa.String(length=500), nullable=True),
        sa.Column('image_generation_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'version', name='uq_floor_plan_version'),
    )
    op.create_index(op.f('ix_floor_plans_id'), 'floor_plans', ['id'], unique=False)
    op.create_index(op.f('ix_floor_plans_project_id'), 'floor_plans', ['project_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_floor_plans_project_id'), table_name='floor_plans')
    op.drop_index(op.f('ix_floor_plans_id'), table_name='floor_plans')
    op.drop_table('floor_plans')
