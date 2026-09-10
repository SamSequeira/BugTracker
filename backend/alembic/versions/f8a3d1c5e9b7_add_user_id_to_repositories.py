"""add user_id to repositories

Revision ID: f8a3d1c5e9b7
Revises: e7f12a8b9c45
Create Date: 2026-08-26 11:27:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8a3d1c5e9b7'
down_revision: Union[str, Sequence[str], None] = 'e7f12a8b9c45'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('repositories', sa.Column('user_id', sa.String(), nullable=True))
    op.create_index(op.f('ix_repositories_user_id'), 'repositories', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_repositories_user_id_users',
        'repositories',
        'users',
        ['user_id'],
        ['id'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_repositories_user_id_users', 'repositories', type_='foreignkey')
    op.drop_index(op.f('ix_repositories_user_id'), table_name='repositories')
    op.drop_column('repositories', 'user_id')
