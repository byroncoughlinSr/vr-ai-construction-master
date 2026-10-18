"""Add furniture to floor plans and a kind to the photo model library

Revision ID: e5b8c2d4f6a1
Revises: d7a3f1c8e2b4
Create Date: 2026-10-17 21:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'e5b8c2d4f6a1'
down_revision: Union[str, None] = 'd7a3f1c8e2b4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('floor_plans', sa.Column('furniture', sa.JSON(), nullable=True))
    op.add_column(
        'plant_models',
        sa.Column('kind', sa.String(length=20), nullable=False, server_default='plant'),
    )


def downgrade() -> None:
    op.drop_column('plant_models', 'kind')
    op.drop_column('floor_plans', 'furniture')
