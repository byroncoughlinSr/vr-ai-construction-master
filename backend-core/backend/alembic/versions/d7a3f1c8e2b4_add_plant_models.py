"""Add the library of 3D plant models made from photos

Revision ID: d7a3f1c8e2b4
Revises: c4e2a7b9d1f5
Create Date: 2026-10-17 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'd7a3f1c8e2b4'
down_revision: Union[str, None] = 'c4e2a7b9d1f5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'plant_models',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=120), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source', sa.String(length=20), nullable=False),
        sa.Column('provider', sa.String(length=30), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('image_path', sa.String(length=500), nullable=True),
        sa.Column('model_path', sa.String(length=500), nullable=True),
        sa.Column('height_ft', sa.Float(), nullable=True),
        sa.Column('aspect', sa.Float(), nullable=True),
        sa.Column('triangles', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_plant_models_id'), 'plant_models', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_plant_models_id'), table_name='plant_models')
    op.drop_table('plant_models')
