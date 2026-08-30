"""add users table

Revision ID: b6e1c29a4f8d
Revises: da36fbd2123c
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b6e1c29a4f8d"
down_revision: Union[str, Sequence[str], None] = "da36fbd2123c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("users"):
        op.create_table(
            "users",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(length=100), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=False),
            sa.Column("password_hash", sa.String(length=255), nullable=False),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
                nullable=False,
            ),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if inspector.has_table("users"):
        op.drop_index("ix_users_email", table_name="users")
        op.drop_table("users")
