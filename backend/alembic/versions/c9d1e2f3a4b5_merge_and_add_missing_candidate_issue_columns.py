"""merge branches and add missing candidate_issue columns

Revision ID: c9d1e2f3a4b5
Revises: b2c3d4e5f6a7, 7c8e9f1a2b3c
Create Date: 2026-09-08 10:05:00.000000

Context
-------
Two migration branches diverged from the common ancestor f8a3d1c5e9b7:

  Branch A (applied to DB):
    f8a3d1c5e9b7 -> a1b2c3d4e5f6 -> b2c3d4e5f6a7  [HEAD, applied]

  Branch B (stamped as applied, but DDL was never run):
    f8a3d1c5e9b7 -> ade07be83770 -> 7c8e9f1a2b3c  [HEAD, stamped]

Branch B (7c8e9f1a2b3c) was stamped rather than executed because it
overlapped with Branch A on rule_id and code_snippet. Branch B's
remaining columns that were NEVER added to the actual DB are added here:

  - column           (Integer, nullable)
  - issue_type       (String(100), nullable, indexed)
  - message          (Text, nullable)
  - evidence         (JSON, nullable)
  - language         (String(50), nullable, indexed)
  - verified_severity  (String(20), nullable)
  - verified_priority  (String(20), nullable)
  - verified_at        (DateTime with timezone, nullable)
  - verification_notes (Text, nullable)

Plus the composite index and check constraints that 7c8e9f1a2b3c defined.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9d1e2f3a4b5'
down_revision: Union[str, Sequence[str], None] = ('b2c3d4e5f6a7', '7c8e9f1a2b3c')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add the candidate_issues columns that were defined in migration
    7c8e9f1a2b3c but were never actually applied to the database (because
    the DB went through branch b2c3d4e5f6a7 instead)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    ci_cols = {c['name'] for c in inspector.get_columns('candidate_issues')}
    ci_idxs = {i['name'] for i in inspector.get_indexes('candidate_issues')}
    ci_checks = {ck['name'] for ck in inspector.get_check_constraints('candidate_issues')}

    # --- Columns missing from DB -----------------------------------------
    if 'column' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('column', sa.Integer(), nullable=True))
    if 'issue_type' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('issue_type', sa.String(length=100), nullable=True))
    if 'message' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('message', sa.Text(), nullable=True))
    if 'evidence' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('evidence', sa.JSON(), nullable=True))
    if 'language' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('language', sa.String(length=50), nullable=True))
    if 'verified_severity' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verified_severity', sa.String(length=20), nullable=True))
    if 'verified_priority' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verified_priority', sa.String(length=20), nullable=True))
    if 'verified_at' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True))
    if 'verification_notes' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('verification_notes', sa.Text(), nullable=True))

    # --- Indexes -----------------------------------------------------------
    if 'ix_candidate_issues_issue_type' not in ci_idxs:
        op.create_index(
            'ix_candidate_issues_issue_type',
            'candidate_issues',
            ['issue_type'],
            unique=False,
        )
    if 'ix_candidate_issues_language' not in ci_idxs:
        op.create_index(
            'ix_candidate_issues_language',
            'candidate_issues',
            ['language'],
            unique=False,
        )
    if 'ix_candidate_issues_verified_labels' not in ci_idxs:
        op.create_index(
            'ix_candidate_issues_verified_labels',
            'candidate_issues',
            ['verified_severity', 'verified_priority'],
            unique=False,
        )

    # --- Check constraints ------------------------------------------------
    # NOTE: The model defines ('high', 'medium', 'low') — matching that here.
    if 'ck_candidate_issues_verified_severity' not in ci_checks:
        op.create_check_constraint(
            'ck_candidate_issues_verified_severity',
            'candidate_issues',
            "verified_severity IS NULL OR verified_severity IN ('high', 'medium', 'low')",
        )
    if 'ck_candidate_issues_verified_priority' not in ci_checks:
        op.create_check_constraint(
            'ck_candidate_issues_verified_priority',
            'candidate_issues',
            "verified_priority IS NULL OR verified_priority IN ('p1', 'p2', 'p3', 'p4')",
        )


def downgrade() -> None:
    """Remove columns added by this migration."""
    op.drop_constraint('ck_candidate_issues_verified_priority', 'candidate_issues', type_='check')
    op.drop_constraint('ck_candidate_issues_verified_severity', 'candidate_issues', type_='check')
    op.drop_index('ix_candidate_issues_verified_labels', table_name='candidate_issues')
    op.drop_index('ix_candidate_issues_language', table_name='candidate_issues')
    op.drop_index('ix_candidate_issues_issue_type', table_name='candidate_issues')
    op.drop_column('candidate_issues', 'verification_notes')
    op.drop_column('candidate_issues', 'verified_at')
    op.drop_column('candidate_issues', 'verified_priority')
    op.drop_column('candidate_issues', 'verified_severity')
    op.drop_column('candidate_issues', 'language')
    op.drop_column('candidate_issues', 'evidence')
    op.drop_column('candidate_issues', 'message')
    op.drop_column('candidate_issues', 'issue_type')
    op.drop_column('candidate_issues', 'column')
