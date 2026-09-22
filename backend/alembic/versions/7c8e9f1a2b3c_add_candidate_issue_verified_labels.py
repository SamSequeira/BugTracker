"""add candidate issue metadata and verified ground truth labels

Revision ID: 7c8e9f1a2b3c
Revises: ade07be83770
Create Date: 2026-08-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c8e9f1a2b3c'
down_revision: Union[str, Sequence[str], None] = 'ade07be83770'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add candidate issue metadata and verified ground-truth label support."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    ci_cols = {c['name'] for c in inspector.get_columns('candidate_issues')}
    ci_idxs = {i['name'] for i in inspector.get_indexes('candidate_issues')}
    ci_checks = {ck['name'] for ck in inspector.get_check_constraints('candidate_issues')}

    # Add issue metadata fields
    if 'rule_id' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('rule_id', sa.String(), nullable=True))
    if 'issue_type' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('issue_type', sa.String(), nullable=True))
    if 'message' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('message', sa.Text(), nullable=True))
    if 'column' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('column', sa.Integer(), nullable=True))
    if 'code_snippet' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('code_snippet', sa.Text(), nullable=True))
    if 'evidence' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('evidence', sa.JSON(), nullable=True))
    if 'language' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('language', sa.String(), nullable=True))

    # Add verified ground-truth labels
    if 'verified_severity' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verified_severity', sa.String(), nullable=True))
    if 'verified_priority' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verified_priority', sa.String(), nullable=True))
    if 'verified_at' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    if 'verification_notes' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verification_notes', sa.Text(), nullable=True))

    # Indexes
    if 'ix_candidate_issues_rule_id' not in ci_idxs:
        op.create_index('ix_candidate_issues_rule_id', 'candidate_issues', ['rule_id'], unique=False)
    if 'ix_candidate_issues_issue_type' not in ci_idxs:
        op.create_index('ix_candidate_issues_issue_type', 'candidate_issues', ['issue_type'], unique=False)
    if 'ix_candidate_issues_language' not in ci_idxs:
        op.create_index('ix_candidate_issues_language', 'candidate_issues', ['language'], unique=False)
    if 'ix_candidate_issues_verified_labels' not in ci_idxs:
        op.create_index('ix_candidate_issues_verified_labels', 'candidate_issues', ['verified_severity', 'verified_priority'], unique=False)

    # Check constraints for database-level validation
    if 'ck_candidate_issues_verified_severity' not in ci_checks:
        op.create_check_constraint(
            'ck_candidate_issues_verified_severity',
            'candidate_issues',
            "verified_severity IS NULL OR verified_severity IN ('critical', 'high', 'medium', 'low')",
        )
    if 'ck_candidate_issues_verified_priority' not in ci_checks:
        op.create_check_constraint(
            'ck_candidate_issues_verified_priority',
            'candidate_issues',
            "verified_priority IS NULL OR verified_priority IN ('p1', 'p2', 'p3', 'p4')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('candidate_issues', schema=None) as batch_op:
        batch_op.drop_constraint('ck_candidate_issues_verified_priority', type_='check')
        batch_op.drop_constraint('ck_candidate_issues_verified_severity', type_='check')
        batch_op.drop_index('ix_candidate_issues_verified_labels')
        batch_op.drop_index('ix_candidate_issues_language')
        batch_op.drop_index('ix_candidate_issues_issue_type')
        batch_op.drop_index('ix_candidate_issues_rule_id')
        batch_op.drop_column('verification_notes')
        batch_op.drop_column('verified_at')
        batch_op.drop_column('verified_priority')
        batch_op.drop_column('verified_severity')
        batch_op.drop_column('language')
        batch_op.drop_column('evidence')
        batch_op.drop_column('code_snippet')
        batch_op.drop_column('column')
        batch_op.drop_column('message')
        batch_op.drop_column('issue_type')
        batch_op.drop_column('rule_id')
"""add candidate issue metadata and verified ground truth labels

Revision ID: 7c8e9f1a2b3c
Revises: ade07be83770
Create Date: 2026-08-27 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c8e9f1a2b3c'
down_revision: Union[str, Sequence[str], None] = 'ade07be83770'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to add candidate issue metadata and verified ground-truth label support."""
    with op.batch_alter_table('candidate_issues', schema=None) as batch_op:
        # Add issue metadata fields
        batch_op.add_column(sa.Column('rule_id', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('issue_type', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('message', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('column', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('code_snippet', sa.Text(), nullable=True))
        batch_op.add_column(sa.Column('evidence', sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column('language', sa.String(), nullable=True))

        # Add verified ground-truth labels
        batch_op.add_column(sa.Column('verified_severity', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('verified_priority', sa.String(), nullable=True))
        batch_op.add_column(sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column('verification_notes', sa.Text(), nullable=True))

        # Indexes
        batch_op.create_index('ix_candidate_issues_rule_id', ['rule_id'], unique=False)
        batch_op.create_index('ix_candidate_issues_issue_type', ['issue_type'], unique=False)
        batch_op.create_index('ix_candidate_issues_language', ['language'], unique=False)
        batch_op.create_index('ix_candidate_issues_verified_labels', ['verified_severity', 'verified_priority'], unique=False)

        # Check constraints for database-level validation
        batch_op.create_check_constraint(
            'ck_candidate_issues_verified_severity',
            "verified_severity IS NULL OR verified_severity IN ('critical', 'high', 'medium', 'low')",
        )
        batch_op.create_check_constraint(
            'ck_candidate_issues_verified_priority',
            "verified_priority IS NULL OR verified_priority IN ('p1', 'p2', 'p3', 'p4')",
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('candidate_issues', schema=None) as batch_op:
        batch_op.drop_constraint('ck_candidate_issues_verified_priority', type_='check')
        batch_op.drop_constraint('ck_candidate_issues_verified_severity', type_='check')
        batch_op.drop_index('ix_candidate_issues_verified_labels')
        batch_op.drop_index('ix_candidate_issues_language')
        batch_op.drop_index('ix_candidate_issues_issue_type')
        batch_op.drop_index('ix_candidate_issues_rule_id')
        batch_op.drop_column('verification_notes')
        batch_op.drop_column('verified_at')
        batch_op.drop_column('verified_priority')
        batch_op.drop_column('verified_severity')
        batch_op.drop_column('language')
        batch_op.drop_column('evidence')
        batch_op.drop_column('code_snippet')
        batch_op.drop_column('column')
        batch_op.drop_column('message')
        batch_op.drop_column('issue_type')
        batch_op.drop_column('rule_id')
