"""add dashboard architecture and file tables

Revision ID: a1b2c3d4e5f6
Revises: f8a3d1c5e9b7
Create Date: 2026-08-26 23:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f8a3d1c5e9b7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create architecture_summaries table
    op.create_table(
        'architecture_summaries',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('analysis_run_id', sa.String(), nullable=False),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('architecture_overview', sa.Text(), nullable=True),
        sa.Column('health_assessment', sa.Text(), nullable=True),
        sa.Column('parser_version', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_architecture_summaries_analysis_run_id'),
        'architecture_summaries',
        ['analysis_run_id'],
        unique=True,
    )

    # 2. Create analysis_technologies table
    op.create_table(
        'analysis_technologies',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('analysis_run_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('category', sa.String(length=50), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=True),
        sa.Column('detection_source', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('analysis_run_id', 'name', name='uq_analysis_technologies_run_name'),
    )
    op.create_index(
        op.f('ix_analysis_technologies_analysis_run_id'),
        'analysis_technologies',
        ['analysis_run_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_analysis_technologies_category'),
        'analysis_technologies',
        ['category'],
        unique=False,
    )
    op.create_index(
        op.f('ix_analysis_technologies_name'),
        'analysis_technologies',
        ['name'],
        unique=False,
    )

    # 3. Create architecture_components table
    op.create_table(
        'architecture_components',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('analysis_run_id', sa.String(), nullable=False),
        sa.Column('name', sa.String(length=150), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('component_type', sa.String(length=50), nullable=True),
        sa.Column('root_path', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('analysis_run_id', 'name', name='uq_arch_components_run_name'),
    )
    op.create_index(
        op.f('ix_architecture_components_analysis_run_id'),
        'architecture_components',
        ['analysis_run_id'],
        unique=False,
    )

    # 4. Create source_files table
    op.create_table(
        'source_files',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('analysis_run_id', sa.String(), nullable=False),
        sa.Column('component_id', sa.String(), nullable=True),
        sa.Column('file_path', sa.String(), nullable=False),
        sa.Column('file_name', sa.String(), nullable=False),
        sa.Column('extension', sa.String(length=50), nullable=True),
        sa.Column('language', sa.String(length=50), nullable=False),
        sa.Column('line_count', sa.Integer(), nullable=True),
        sa.Column('role', sa.Text(), nullable=True),
        sa.Column('intent', sa.Text(), nullable=True),
        sa.Column('is_supported', sa.Boolean(), server_default=sa.text('true'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['analysis_run_id'], ['analysis_runs.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['component_id'], ['architecture_components.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('analysis_run_id', 'file_path', name='uq_source_files_run_file_path'),
    )
    op.create_index(
        op.f('ix_source_files_analysis_run_id'),
        'source_files',
        ['analysis_run_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_source_files_component_id'),
        'source_files',
        ['component_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_source_files_file_path'),
        'source_files',
        ['file_path'],
        unique=False,
    )
    op.create_index(
        op.f('ix_source_files_language'),
        'source_files',
        ['language'],
        unique=False,
    )

    # 5. Add source_file_id column and foreign key to candidate_issues
    op.add_column('candidate_issues', sa.Column('source_file_id', sa.String(), nullable=True))
    op.create_index(
        op.f('ix_candidate_issues_source_file_id'),
        'candidate_issues',
        ['source_file_id'],
        unique=False,
    )
    op.create_foreign_key(
        'fk_candidate_issues_source_file_id_source_files',
        'candidate_issues',
        'source_files',
        ['source_file_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 6. Add performance indexes on existing tables
    op.create_index(
        op.f('ix_analysis_runs_repository_id'),
        'analysis_runs',
        ['repository_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_candidate_issues_analysis_run_id'),
        'candidate_issues',
        ['analysis_run_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_candidate_issues_file_path'),
        'candidate_issues',
        ['file_path'],
        unique=False,
    )
    op.create_index(
        op.f('ix_candidate_issues_severity'),
        'candidate_issues',
        ['severity'],
        unique=False,
    )
    op.create_index(
        op.f('ix_issue_statuses_candidate_issue_id'),
        'issue_statuses',
        ['candidate_issue_id'],
        unique=True,
    )

    # 7. Create issue_recommendations table
    op.create_table(
        'issue_recommendations',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('candidate_issue_id', sa.String(), nullable=False),
        sa.Column('recommendation', sa.Text(), nullable=False),
        sa.Column('priority_order', sa.Integer(), server_default=sa.text('1'), nullable=False),
        sa.Column('fix_type', sa.String(length=50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_issue_id'], ['candidate_issues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_issue_recommendations_candidate_issue_id'),
        'issue_recommendations',
        ['candidate_issue_id'],
        unique=False,
    )


def downgrade() -> None:
    # 7. Drop issue_recommendations table
    op.drop_index(op.f('ix_issue_recommendations_candidate_issue_id'), table_name='issue_recommendations')
    op.drop_table('issue_recommendations')

    # 6. Drop performance indexes on existing tables
    op.drop_index(op.f('ix_issue_statuses_candidate_issue_id'), table_name='issue_statuses')
    op.drop_index(op.f('ix_candidate_issues_severity'), table_name='candidate_issues')
    op.drop_index(op.f('ix_candidate_issues_file_path'), table_name='candidate_issues')
    op.drop_index(op.f('ix_candidate_issues_analysis_run_id'), table_name='candidate_issues')
    op.drop_index(op.f('ix_analysis_runs_repository_id'), table_name='analysis_runs')

    # 5. Drop source_file_id FK and column from candidate_issues
    op.drop_constraint('fk_candidate_issues_source_file_id_source_files', 'candidate_issues', type_='foreignkey')
    op.drop_index(op.f('ix_candidate_issues_source_file_id'), table_name='candidate_issues')
    op.drop_column('candidate_issues', 'source_file_id')

    # 4. Drop source_files table
    op.drop_index(op.f('ix_source_files_language'), table_name='source_files')
    op.drop_index(op.f('ix_source_files_file_path'), table_name='source_files')
    op.drop_index(op.f('ix_source_files_component_id'), table_name='source_files')
    op.drop_index(op.f('ix_source_files_analysis_run_id'), table_name='source_files')
    op.drop_table('source_files')

    # 3. Drop architecture_components table
    op.drop_index(op.f('ix_architecture_components_analysis_run_id'), table_name='architecture_components')
    op.drop_table('architecture_components')

    # 2. Drop analysis_technologies table
    op.drop_index(op.f('ix_analysis_technologies_name'), table_name='analysis_technologies')
    op.drop_index(op.f('ix_analysis_technologies_category'), table_name='analysis_technologies')
    op.drop_index(op.f('ix_analysis_technologies_analysis_run_id'), table_name='analysis_technologies')
    op.drop_table('analysis_technologies')

    # 1. Drop architecture_summaries table
    op.drop_index(op.f('ix_architecture_summaries_analysis_run_id'), table_name='architecture_summaries')
    op.drop_table('architecture_summaries')
