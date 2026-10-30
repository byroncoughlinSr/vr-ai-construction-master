"""Add plant_models.turn

How far a photo model is turned (degrees, 0/90/180/270) so its front faces the
way furniture's does: an island's seating side, a sofa's seat. Image-to-3D
models come out facing wherever the photo was taken from.

Revision ID: b4e8d2a6c9f1
Revises: c1f7e3a9d5b2
Create Date: 2026-10-29 12:30:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'b4e8d2a6c9f1'
down_revision: Union[str, None] = 'c1f7e3a9d5b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('plant_models', sa.Column('turn', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('plant_models', 'turn')
