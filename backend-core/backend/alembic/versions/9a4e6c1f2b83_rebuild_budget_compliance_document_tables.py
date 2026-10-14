"""Rebuild the budget, permit, inspection and document tables to match the models

The initial migration created these six tables with an older column layout than
app/models (budget.py, compliance.py, documents.py), so on a database built by
migrations every ORM query touching them failed — including deleting a project,
which loads its budget items, permits, inspections and documents to cascade.

Databases created by the old create_all() hook already match the models and are
left alone. A drifted database can't have stored rows through the ORM, so the
tables are dropped and recreated; if any of them holds rows anyway, the upgrade
stops instead of discarding them.

Revision ID: 9a4e6c1f2b83
Revises: 3b7c1d2e9f40
Create Date: 2026-10-11 13:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9a4e6c1f2b83'
down_revision: Union[str, None] = '3b7c1d2e9f40'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Children before parents.
TABLES = ['document_comments', 'documents', 'inspections', 'permits', 'budget_items', 'budget_categories']


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c['name'] for c in inspector.get_columns('budget_items')}
    if 'name' in columns:
        return  # already the model layout (created by create_all)

    occupied = [
        t for t in TABLES
        if bind.execute(sa.text(f'SELECT COUNT(*) FROM {t}')).scalar()
    ]
    if occupied:
        raise RuntimeError(
            f"Tables {occupied} have rows in the old layout; migrate them by hand before upgrading."
        )
    for table in TABLES:
        op.drop_table(table)

    op.create_table('budget_categories',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('name', sa.String(length=100), nullable=False),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('category_type', sa.String(length=50), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('name')
    )
    op.create_index(op.f('ix_budget_categories_id'), 'budget_categories', ['id'], unique=False)
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
    sa.ForeignKeyConstraint(['category_id'], ['budget_categories.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_budget_items_id'), 'budget_items', ['id'], unique=False)
    op.create_table('documents',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('filename', sa.String(length=255), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('document_type', sa.String(length=50), nullable=False),
    sa.Column('category', sa.String(length=100), nullable=True),
    sa.Column('file_path', sa.String(length=500), nullable=False),
    sa.Column('file_url', sa.String(length=500), nullable=False),
    sa.Column('file_size', sa.Integer(), nullable=True),
    sa.Column('mime_type', sa.String(length=100), nullable=True),
    sa.Column('file_hash', sa.String(length=128), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=True),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('tags', sa.JSON(), nullable=True),
    sa.Column('location_in_project', sa.String(length=255), nullable=True),
    sa.Column('coordinates', sa.JSON(), nullable=True),
    sa.Column('version', sa.String(length=20), nullable=True),
    sa.Column('previous_version_id', sa.Integer(), nullable=True),
    sa.Column('uploaded_by', sa.String(length=255), nullable=True),
    sa.Column('approved_by', sa.String(length=255), nullable=True),
    sa.Column('approval_date', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_approved', sa.Boolean(), nullable=True),
    sa.Column('status', sa.String(length=50), nullable=True),
    sa.Column('exif_data', sa.JSON(), nullable=True),
    sa.Column('custom_metadata', sa.JSON(), nullable=True),
    sa.Column('taken_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('uploaded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['previous_version_id'], ['documents.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_documents_id'), 'documents', ['id'], unique=False)
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
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('permit_number')
    )
    op.create_index(op.f('ix_permits_id'), 'permits', ['id'], unique=False)
    op.create_table('document_comments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('document_id', sa.Integer(), nullable=False),
    sa.Column('author', sa.String(length=255), nullable=False),
    sa.Column('comment_text', sa.Text(), nullable=False),
    sa.Column('x_coordinate', sa.Float(), nullable=True),
    sa.Column('y_coordinate', sa.Float(), nullable=True),
    sa.Column('page_number', sa.Integer(), nullable=True),
    sa.Column('is_resolved', sa.Boolean(), nullable=True),
    sa.Column('resolved_by', sa.String(length=255), nullable=True),
    sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
    sa.ForeignKeyConstraint(['document_id'], ['documents.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_document_comments_id'), 'document_comments', ['id'], unique=False)
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
    sa.ForeignKeyConstraint(['permit_id'], ['permits.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_inspections_id'), 'inspections', ['id'], unique=False)


def downgrade() -> None:
    # The old layout never worked with the models; there is nothing useful to go back to.
    pass
