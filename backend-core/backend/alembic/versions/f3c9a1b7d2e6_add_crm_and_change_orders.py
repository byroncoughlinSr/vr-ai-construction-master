"""Add the client CRM, change orders, and a phase on budget items

Revision ID: f3c9a1b7d2e6
Revises: e5b8c2d4f6a1
Create Date: 2026-10-19 12:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3c9a1b7d2e6'
down_revision: Union[str, None] = 'e5b8c2d4f6a1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'clients',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('company', sa.String(length=255), nullable=True),
        sa.Column('stage', sa.String(length=50), nullable=False),
        sa.Column('tier', sa.String(length=50), nullable=True),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('deal_value', sa.Float(), nullable=True),
        sa.Column('win_probability', sa.Float(), nullable=True),
        sa.Column('lost_reason', sa.Text(), nullable=True),
        sa.Column('site_address', sa.Text(), nullable=True),
        sa.Column('preferred_style', sa.String(length=255), nullable=True),
        sa.Column('target_budget', sa.Float(), nullable=True),
        sa.Column('target_square_feet', sa.Float(), nullable=True),
        sa.Column('target_completion_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('requirements', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('next_follow_up_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_action', sa.String(length=500), nullable=True),
        sa.Column('last_contact_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('sentiment', sa.String(length=30), nullable=True),
        sa.Column('ai_summary', sa.Text(), nullable=True),
        sa.Column('ai_insights', sa.JSON(), nullable=True),
        sa.Column('ai_updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_clients_id'), 'clients', ['id'], unique=False)
    op.create_index(op.f('ix_clients_stage'), 'clients', ['stage'], unique=False)
    op.create_index(op.f('ix_clients_project_id'), 'clients', ['project_id'], unique=False)

    op.create_table(
        'client_activities',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('client_id', sa.Integer(), nullable=False),
        sa.Column('kind', sa.String(length=30), nullable=False),
        sa.Column('summary', sa.String(length=500), nullable=False),
        sa.Column('details', sa.Text(), nullable=True),
        sa.Column('sentiment', sa.String(length=30), nullable=True),
        sa.Column('action_items', sa.JSON(), nullable=True),
        sa.Column('author', sa.String(length=255), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['client_id'], ['clients.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_client_activities_id'), 'client_activities', ['id'], unique=False)
    op.create_index(op.f('ix_client_activities_client_id'), 'client_activities', ['client_id'], unique=False)

    op.create_table(
        'change_orders',
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
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_change_orders_id'), 'change_orders', ['id'], unique=False)
    op.create_index(op.f('ix_change_orders_project_id'), 'change_orders', ['project_id'], unique=False)

    op.add_column('budget_items', sa.Column('phase_id', sa.Integer(), nullable=True))
    op.create_foreign_key(
        'budget_items_phase_id_fkey', 'budget_items', 'construction_phases',
        ['phase_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('budget_items_phase_id_fkey', 'budget_items', type_='foreignkey')
    op.drop_column('budget_items', 'phase_id')
    op.drop_index(op.f('ix_change_orders_project_id'), table_name='change_orders')
    op.drop_index(op.f('ix_change_orders_id'), table_name='change_orders')
    op.drop_table('change_orders')
    op.drop_index(op.f('ix_client_activities_client_id'), table_name='client_activities')
    op.drop_index(op.f('ix_client_activities_id'), table_name='client_activities')
    op.drop_table('client_activities')
    op.drop_index(op.f('ix_clients_project_id'), table_name='clients')
    op.drop_index(op.f('ix_clients_stage'), table_name='clients')
    op.drop_index(op.f('ix_clients_id'), table_name='clients')
    op.drop_table('clients')
