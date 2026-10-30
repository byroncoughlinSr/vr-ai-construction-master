"""Add kitchen_styles

Saved kitchen looks (cabinet colour and doors, countertop, backsplash, crown,
the appliances' photo models) that any house's kitchen can be drawn in.

Revision ID: a7c3e9f1b5d2
Revises: b4e8d2a6c9f1
Create Date: 2026-10-29 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a7c3e9f1b5d2'
down_revision: Union[str, None] = 'b4e8d2a6c9f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'kitchen_styles',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('style', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_kitchen_styles_id'), 'kitchen_styles', ['id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_kitchen_styles_id'), table_name='kitchen_styles')
    op.drop_table('kitchen_styles')
