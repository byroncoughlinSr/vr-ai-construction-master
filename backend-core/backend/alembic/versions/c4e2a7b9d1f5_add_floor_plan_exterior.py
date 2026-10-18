"""Add the outside of the house to floor plans

Revision ID: c4e2a7b9d1f5
Revises: 9a4e6c1f2b83
Create Date: 2026-10-14 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4e2a7b9d1f5'
down_revision: Union[str, None] = '9a4e6c1f2b83'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('floor_plans', sa.Column('exterior', sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column('floor_plans', 'exterior')
