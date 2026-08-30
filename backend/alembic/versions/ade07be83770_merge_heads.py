"""merge_heads

Revision ID: ade07be83770
Revises: b6e1c29a4f8d, f8a3d1c5e9b7
Create Date: 2026-08-27 11:58:54.739097

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ade07be83770'
down_revision: Union[str, Sequence[str], None] = ('b6e1c29a4f8d', 'f8a3d1c5e9b7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
