"""add issue triage and inspector schema

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-26 23:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    ci_cols = {c['name'] for c in inspector.get_columns('candidate_issues')}
    ci_idxs = {i['name'] for i in inspector.get_indexes('candidate_issues')}

    # 1. Update candidate_issues with triage & inspector columns
    if 'issue_key' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('issue_key', sa.String(length=50), nullable=True))
    if 'rule_id' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('rule_id', sa.String(length=50), nullable=True))
    if 'security_impact' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('security_impact', sa.Text(), nullable=True))
    if 'code_snippet' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('code_snippet', sa.Text(), nullable=True))
    if 'assigned_to_user_id' not in ci_cols:
        op.add_column('candidate_issues', sa.Column('assigned_to_user_id', sa.String(), nullable=True))

    if 'ix_candidate_issues_issue_key' not in ci_idxs:
        op.create_index(op.f('ix_candidate_issues_issue_key'), 'candidate_issues', ['issue_key'], unique=False)
    if 'ix_candidate_issues_rule_id' not in ci_idxs:
        op.create_index(op.f('ix_candidate_issues_rule_id'), 'candidate_issues', ['rule_id'], unique=False)
    if 'ix_candidate_issues_assigned_to_user_id' not in ci_idxs:
        op.create_index(op.f('ix_candidate_issues_assigned_to_user_id'), 'candidate_issues', ['assigned_to_user_id'], unique=False)
    
    ci_uniques = {u['name'] for u in inspector.get_unique_constraints('candidate_issues')}
    if 'uq_candidate_issues_run_issue_key' not in ci_uniques:
        op.create_unique_constraint('uq_candidate_issues_run_issue_key', 'candidate_issues', ['analysis_run_id', 'issue_key'])

    ci_fks = {fk['name'] for fk in inspector.get_foreign_keys('candidate_issues')}
    if 'fk_candidate_issues_assigned_to_user_id_users' not in ci_fks:
        op.create_foreign_key(
            'fk_candidate_issues_assigned_to_user_id_users',
            'candidate_issues',
            'users',
            ['assigned_to_user_id'],
            ['id'],
            ondelete='SET NULL',
        )

    # 2. Update issue_statuses with remarks/notes and resolution tracking
    op.add_column('issue_statuses', sa.Column('remarks', sa.Text(), nullable=True))
    op.add_column('issue_statuses', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('issue_statuses', sa.Column('resolved_by_user_id', sa.String(), nullable=True))

    op.create_index(op.f('ix_issue_statuses_resolved_by_user_id'), 'issue_statuses', ['resolved_by_user_id'], unique=False)
    op.create_foreign_key(
        'fk_issue_statuses_resolved_by_user_id_users',
        'issue_statuses',
        'users',
        ['resolved_by_user_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 3. Update issue_recommendations with structured code diff patch
    op.add_column('issue_recommendations', sa.Column('diff_remove', sa.Text(), nullable=True))
    op.add_column('issue_recommendations', sa.Column('diff_add', sa.Text(), nullable=True))

    # 4. Create issue_similarities table for relational similarity & counts
    op.create_table(
        'issue_similarities',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('candidate_issue_id', sa.String(), nullable=False),
        sa.Column('similar_issue_id', sa.String(), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=True),
        sa.Column('similarity_reason', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_issue_id'], ['candidate_issues.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['similar_issue_id'], ['candidate_issues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_issue_id', 'similar_issue_id', name='uq_issue_similarities_pair'),
        sa.CheckConstraint('candidate_issue_id < similar_issue_id', name='ck_issue_similarities_canonical_pair'),
    )
    op.create_index(op.f('ix_issue_similarities_candidate_issue_id'), 'issue_similarities', ['candidate_issue_id'], unique=False)
    op.create_index(op.f('ix_issue_similarities_similar_issue_id'), 'issue_similarities', ['similar_issue_id'], unique=False)


def downgrade() -> None:
    # 4. Drop issue_similarities table
    op.drop_index(op.f('ix_issue_similarities_similar_issue_id'), table_name='issue_similarities')
    op.drop_index(op.f('ix_issue_similarities_candidate_issue_id'), table_name='issue_similarities')
    op.drop_table('issue_similarities')

    # 3. Drop code diff columns from issue_recommendations
    op.drop_column('issue_recommendations', 'diff_add')
    op.drop_column('issue_recommendations', 'diff_remove')

    # 2. Drop remarks and resolution tracking from issue_statuses
    op.drop_constraint('fk_issue_statuses_resolved_by_user_id_users', 'issue_statuses', type_='foreignkey')
    op.drop_index(op.f('ix_issue_statuses_resolved_by_user_id'), table_name='issue_statuses')
    op.drop_column('issue_statuses', 'resolved_by_user_id')
    op.drop_column('issue_statuses', 'resolved_at')
    op.drop_column('issue_statuses', 'remarks')

    # 1. Drop triage & inspector columns from candidate_issues
    op.drop_constraint('fk_candidate_issues_assigned_to_user_id_users', 'candidate_issues', type_='foreignkey')
    op.drop_constraint('uq_candidate_issues_run_issue_key', 'candidate_issues', type_='unique')
    op.drop_index(op.f('ix_candidate_issues_assigned_to_user_id'), table_name='candidate_issues')
    op.drop_index(op.f('ix_candidate_issues_rule_id'), table_name='candidate_issues')
    op.drop_index(op.f('ix_candidate_issues_issue_key'), table_name='candidate_issues')
    op.drop_column('candidate_issues', 'assigned_to_user_id')
    op.drop_column('candidate_issues', 'code_snippet')
    op.drop_column('candidate_issues', 'security_impact')
    op.drop_column('candidate_issues', 'rule_id')
    op.drop_column('candidate_issues', 'issue_key')
"""add issue triage and inspector schema

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-08-26 23:35:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, Sequence[str], None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update candidate_issues with triage & inspector columns
    op.add_column('candidate_issues', sa.Column('issue_key', sa.String(length=50), nullable=True))
    op.add_column('candidate_issues', sa.Column('rule_id', sa.String(length=50), nullable=True))
    op.add_column('candidate_issues', sa.Column('security_impact', sa.Text(), nullable=True))
    op.add_column('candidate_issues', sa.Column('code_snippet', sa.Text(), nullable=True))
    op.add_column('candidate_issues', sa.Column('assigned_to_user_id', sa.String(), nullable=True))

    op.create_index(op.f('ix_candidate_issues_issue_key'), 'candidate_issues', ['issue_key'], unique=False)
    op.create_index(op.f('ix_candidate_issues_rule_id'), 'candidate_issues', ['rule_id'], unique=False)
    op.create_index(op.f('ix_candidate_issues_assigned_to_user_id'), 'candidate_issues', ['assigned_to_user_id'], unique=False)
    op.create_unique_constraint('uq_candidate_issues_run_issue_key', 'candidate_issues', ['analysis_run_id', 'issue_key'])
    op.create_foreign_key(
        'fk_candidate_issues_assigned_to_user_id_users',
        'candidate_issues',
        'users',
        ['assigned_to_user_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 2. Update issue_statuses with remarks/notes and resolution tracking
    op.add_column('issue_statuses', sa.Column('remarks', sa.Text(), nullable=True))
    op.add_column('issue_statuses', sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('issue_statuses', sa.Column('resolved_by_user_id', sa.String(), nullable=True))

    op.create_index(op.f('ix_issue_statuses_resolved_by_user_id'), 'issue_statuses', ['resolved_by_user_id'], unique=False)
    op.create_foreign_key(
        'fk_issue_statuses_resolved_by_user_id_users',
        'issue_statuses',
        'users',
        ['resolved_by_user_id'],
        ['id'],
        ondelete='SET NULL',
    )

    # 3. Update issue_recommendations with structured code diff patch
    op.add_column('issue_recommendations', sa.Column('diff_remove', sa.Text(), nullable=True))
    op.add_column('issue_recommendations', sa.Column('diff_add', sa.Text(), nullable=True))

    # 4. Create issue_similarities table for relational similarity & counts
    op.create_table(
        'issue_similarities',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('candidate_issue_id', sa.String(), nullable=False),
        sa.Column('similar_issue_id', sa.String(), nullable=False),
        sa.Column('similarity_score', sa.Float(), nullable=True),
        sa.Column('similarity_reason', sa.String(length=100), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['candidate_issue_id'], ['candidate_issues.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['similar_issue_id'], ['candidate_issues.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('candidate_issue_id', 'similar_issue_id', name='uq_issue_similarities_pair'),
        sa.CheckConstraint('candidate_issue_id < similar_issue_id', name='ck_issue_similarities_canonical_pair'),
    )
    op.create_index(op.f('ix_issue_similarities_candidate_issue_id'), 'issue_similarities', ['candidate_issue_id'], unique=False)
    op.create_index(op.f('ix_issue_similarities_similar_issue_id'), 'issue_similarities', ['similar_issue_id'], unique=False)


def downgrade() -> None:
    # 4. Drop issue_similarities table
    op.drop_index(op.f('ix_issue_similarities_similar_issue_id'), table_name='issue_similarities')
    op.drop_index(op.f('ix_issue_similarities_candidate_issue_id'), table_name='issue_similarities')
    op.drop_table('issue_similarities')

    # 3. Drop code diff columns from issue_recommendations
    op.drop_column('issue_recommendations', 'diff_add')
    op.drop_column('issue_recommendations', 'diff_remove')

    # 2. Drop remarks and resolution tracking from issue_statuses
    op.drop_constraint('fk_issue_statuses_resolved_by_user_id_users', 'issue_statuses', type_='foreignkey')
    op.drop_index(op.f('ix_issue_statuses_resolved_by_user_id'), table_name='issue_statuses')
    op.drop_column('issue_statuses', 'resolved_by_user_id')
    op.drop_column('issue_statuses', 'resolved_at')
    op.drop_column('issue_statuses', 'remarks')

    # 1. Drop triage & inspector columns from candidate_issues
    op.drop_constraint('fk_candidate_issues_assigned_to_user_id_users', 'candidate_issues', type_='foreignkey')
    op.drop_constraint('uq_candidate_issues_run_issue_key', 'candidate_issues', type_='unique')
    op.drop_index(op.f('ix_candidate_issues_assigned_to_user_id'), table_name='candidate_issues')
    op.drop_index(op.f('ix_candidate_issues_rule_id'), table_name='candidate_issues')
    op.drop_index(op.f('ix_candidate_issues_issue_key'), table_name='candidate_issues')
    op.drop_column('candidate_issues', 'assigned_to_user_id')
    op.drop_column('candidate_issues', 'code_snippet')
    op.drop_column('candidate_issues', 'security_impact')
    op.drop_column('candidate_issues', 'rule_id')
    op.drop_column('candidate_issues', 'issue_key')
