"""Drop the old construction plan tables

The construction plan moved to pm-mcp in a6d2f8c4b1e7, which left these
tables in place, unused: construction_phases, tasks, permits, inspections,
budget_items, budget_categories, change_orders. This drops them. It refuses
if any of them other than budget_categories (a lookup list) still has rows.

Downgrade recreates the tables empty.

Revision ID: c1f7e3a9d5b2
Revises: a6d2f8c4b1e7
Create Date: 2026-10-23 18:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c1f7e3a9d5b2'
down_revision: Union[str, None] = 'a6d2f8c4b1e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Children before parents.
TABLES = ['inspections', 'budget_items', 'change_orders', 'permits', 'tasks',
          'budget_categories', 'construction_phases']
LOOKUPS = {'budget_categories'}


def upgrade() -> None:
    bind = op.get_bind()
    present = [t for t in TABLES if t in sa.inspect(bind).get_table_names()]
    occupied = [
        t for t in present
        if t not in LOOKUPS and bind.execute(sa.text(f'SELECT COUNT(*) FROM {t}')).scalar()
    ]
    if occupied:
        raise RuntimeError(
            f"Tables {occupied} still have rows; move them to pm-mcp or delete them before upgrading."
        )
    for table in present:
        op.drop_table(table)


def downgrade() -> None:
    op.create_table('construction_phases',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('phase_order', sa.Integer(), nullable=False),
    sa.Column('depends_on_phase_id', sa.Integer(), nullable=True),
    sa.Column('planned_start_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('planned_end_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_start_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_end_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('progress_percentage', sa.Float(), nullable=True),
    sa.Column('budgeted_cost', sa.Float(), nullable=True),
    sa.Column('actual_cost', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['depends_on_phase_id'], ['construction_phases.id'], name='construction_phases_depends_on_phase_id_fkey'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='construction_phases_project_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='construction_phases_pkey')
    )
    op.create_index('ix_construction_phases_id', 'construction_phases', ['id'], unique=False)

    op.create_table('budget_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category_type', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id', name='budget_categories_pkey'),
    sa.UniqueConstraint('name', name='budget_categories_name_key')
    )
    op.create_index('ix_budget_categories_id', 'budget_categories', ['id'], unique=False)

    op.create_table('tasks',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('phase_id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('depends_on_task_id', sa.Integer(), nullable=True),
    sa.Column('task_order', sa.Integer(), nullable=True),
    sa.Column('planned_start_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('planned_end_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_start_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_end_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('planned_duration_days', sa.Float(), nullable=True),
    sa.Column('actual_duration_days', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('priority', sa.String(length=20), nullable=True),
    sa.Column('required_labor_hours', sa.Float(), nullable=True),
    sa.Column('required_equipment', sa.Text(), nullable=True),
    sa.Column('budgeted_cost', sa.Float(), nullable=True),
    sa.Column('actual_cost', sa.Float(), nullable=True),
    sa.Column('requires_inspection', sa.Boolean(), nullable=True),
    sa.Column('inspection_status', sa.String(length=50), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['depends_on_task_id'], ['tasks.id'], name='tasks_depends_on_task_id_fkey'),
    sa.ForeignKeyConstraint(['phase_id'], ['construction_phases.id'], name='tasks_phase_id_fkey'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='tasks_project_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='tasks_pkey')
    )
    op.create_index('ix_tasks_id', 'tasks', ['id'], unique=False)

    op.create_table('permits',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('permit_number', sa.String(length=100), nullable=False),
    sa.Column('permit_type', sa.String(length=100), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('issuing_authority', sa.String(length=255), nullable=True),
    sa.Column('jurisdiction', sa.String(length=255), nullable=True),
    sa.Column('application_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('approval_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expiration_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('issued_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('application_fee', sa.Float(), nullable=True),
    sa.Column('permit_fee', sa.Float(), nullable=True),
    sa.Column('total_cost', sa.Float(), nullable=True),
    sa.Column('conditions', sa.Text(), nullable=True),
    sa.Column('inspection_required', sa.Boolean(), nullable=True),
    sa.Column('application_url', sa.String(length=500), nullable=True),
    sa.Column('permit_document_url', sa.String(length=500), nullable=True),
    sa.Column('contact_name', sa.String(length=255), nullable=True),
    sa.Column('contact_phone', sa.String(length=50), nullable=True),
    sa.Column('contact_email', sa.String(length=255), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='permits_project_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='permits_pkey'),
    sa.UniqueConstraint('permit_number', name='permits_permit_number_key')
    )
    op.create_index('ix_permits_id', 'permits', ['id'], unique=False)

    op.create_table('change_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('number', sa.Integer(), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('cost_impact', sa.Float(), nullable=True),
    sa.Column('schedule_impact_days', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=30), nullable=True),
    sa.Column('requested_by', sa.String(length=255), nullable=True),
    sa.Column('floor_plan_version', sa.Integer(), nullable=True),
    sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='change_orders_project_id_fkey', ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name='change_orders_pkey')
    )
    op.create_index('ix_change_orders_id', 'change_orders', ['id'], unique=False)
    op.create_index('ix_change_orders_project_id', 'change_orders', ['project_id'], unique=False)

    op.create_table('budget_items',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('category_id', sa.Integer(), nullable=False),
    sa.Column('budgeted_amount', sa.Float(), nullable=False),
    sa.Column('actual_amount', sa.Float(), nullable=True),
    sa.Column('quantity', sa.Float(), nullable=True),
    sa.Column('unit', sa.String(length=50), nullable=True),
    sa.Column('unit_cost', sa.Float(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('approved_by', sa.String(length=255), nullable=True),
    sa.Column('approved_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('vendor_name', sa.String(length=255), nullable=True),
    sa.Column('vendor_contact', sa.String(length=255), nullable=True),
    sa.Column('purchase_order_number', sa.String(length=100), nullable=True),
    sa.Column('planned_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('notes', sa.Text(), nullable=True),
    sa.Column('receipt_url', sa.String(length=500), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('phase_id', sa.Integer(), nullable=True),
    sa.ForeignKeyConstraint(['category_id'], ['budget_categories.id'], name='budget_items_category_id_fkey'),
    sa.ForeignKeyConstraint(['phase_id'], ['construction_phases.id'], name='budget_items_phase_id_fkey', ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='budget_items_project_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='budget_items_pkey')
    )
    op.create_index('ix_budget_items_id', 'budget_items', ['id'], unique=False)

    op.create_table('inspections',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('inspection_type', sa.String(length=100), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.Integer(), nullable=True),
    sa.Column('permit_id', sa.Integer(), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('inspector_name', sa.String(length=255), nullable=True),
    sa.Column('inspector_company', sa.String(length=255), nullable=True),
    sa.Column('inspector_certification', sa.String(length=100), nullable=True),
    sa.Column('scheduled_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('actual_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('requested_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('result_details', sa.Text(), nullable=True),
    sa.Column('critical_findings', sa.Text(), nullable=True),
    sa.Column('recommended_actions', sa.Text(), nullable=True),
    sa.Column('requires_followup', sa.Boolean(), nullable=True),
    sa.Column('followup_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('followup_completed', sa.Boolean(), nullable=True),
    sa.Column('report_url', sa.String(length=500), nullable=True),
    sa.Column('photos', sa.JSON(), nullable=True),
    sa.Column('inspection_fee', sa.Float(), nullable=True),
    sa.Column('reinspection_fee', sa.Float(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['permit_id'], ['permits.id'], name='inspections_permit_id_fkey'),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name='inspections_project_id_fkey'),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], name='inspections_task_id_fkey'),
    sa.PrimaryKeyConstraint('id', name='inspections_pkey')
    )
    op.create_index('ix_inspections_id', 'inspections', ['id'], unique=False)
