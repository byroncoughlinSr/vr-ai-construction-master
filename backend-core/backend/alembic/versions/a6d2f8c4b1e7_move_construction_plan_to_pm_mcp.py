"""Move the construction plan to pm-mcp

Phases, tasks, permits, inspections, budget lines, expenses and change orders
now live in pm-mcp (see services/pm_client.py). This links each project to its
pm-mcp project, links punch items to the pm-mcp records they are copied to, and
turns the references to phases and tasks into plain pm-mcp ids (punch items'
phase, crew and equipment assignments' task) by dropping their foreign keys.

The old tables (construction_phases, tasks, permits, inspections, budget_items,
budget_categories, change_orders) are left in place, unused by the app.

Revision ID: a6d2f8c4b1e7
Revises: b8e1d5c3a9f4
Create Date: 2026-10-23 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a6d2f8c4b1e7'
down_revision: Union[str, None] = 'b8e1d5c3a9f4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Foreign keys that now hold pm-mcp ids: (table, column, Postgres constraint name, target).
_REFERENCES = (
    ('punch_items', 'phase_id', 'punch_items_phase_id_fkey', 'construction_phases'),
    ('labor_assignments', 'task_id', 'labor_assignments_task_id_fkey', 'tasks'),
    ('equipment_assignments', 'task_id', 'equipment_assignments_task_id_fkey', 'tasks'),
)


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for table, _column, constraint, _target in _REFERENCES:
        if constraint in {fk['name'] for fk in inspector.get_foreign_keys(table)}:
            op.drop_constraint(constraint, table, type_='foreignkey')

    op.add_column('projects', sa.Column('pm_project_id', sa.Integer(), nullable=True))
    op.create_index('ix_projects_pm_project_id', 'projects', ['pm_project_id'])
    op.add_column('punch_items', sa.Column('pm_record_id', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('punch_items', 'pm_record_id')
    op.drop_index('ix_projects_pm_project_id', table_name='projects')
    op.drop_column('projects', 'pm_project_id')
    # pm-mcp ids that don't exist in the old tables can't keep a foreign key:
    # a punch item loses its phase; an assignment to a pm-mcp task goes.
    for table, column, constraint, target in _REFERENCES:
        orphan = f'{column} IS NOT NULL AND {column} NOT IN (SELECT id FROM {target})'
        nullable = table == 'punch_items'
        if nullable:
            op.execute(f'UPDATE {table} SET {column} = NULL WHERE {orphan}')
        else:
            op.execute(f'DELETE FROM {table} WHERE {orphan}')
        op.create_foreign_key(constraint, table, target, [column], ['id'],
                              ondelete='SET NULL' if nullable else None)
