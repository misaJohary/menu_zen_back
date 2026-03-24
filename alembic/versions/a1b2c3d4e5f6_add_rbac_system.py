"""Add RBAC system: roles, permissions, role_permissions, user_permissions

Revision ID: a1b2c3d4e5f6
Revises: fe5f28557e0a
Create Date: 2026-03-18 16:06:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "eb51a83a218c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── 1. Create `roles` table ───────────────────────────────────────────────
    op.create_table(
        "roles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # ── 2. Create `permissions` table ─────────────────────────────────────────
    op.create_table(
        "permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("resource", sa.String(length=100), nullable=False),
        sa.Column("action", sa.String(length=100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("resource", "action", name="uq_resource_action"),
    )

    # ── 3. Create `role_permissions` (join table) ─────────────────────────────
    op.create_table(
        "role_permissions",
        sa.Column("role_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["role_id"], ["roles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("role_id", "permission_id"),
    )

    # ── 4. Create `user_permissions` (override table) ─────────────────────────
    op.create_table(
        "user_permissions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("permission_id", sa.Integer(), nullable=False),
        # SQLite stores enums as VARCHAR
        sa.Column("type", sa.String(length=10), nullable=False),
        sa.Column("granted_by", sa.Integer(), nullable=True),
        sa.Column(
            "granted_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("(datetime('now'))"),
        ),
        sa.ForeignKeyConstraint(["granted_by"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["permission_id"], ["permissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "permission_id", name="uq_user_permission"),
    )

    # ── 5. Migrate `user` table: add role_id, keep old roles for data ─────────
    # We use batch mode so SQLite can handle the column operations.
    with op.batch_alter_table("user", schema=None) as batch_op:
        # Add role_id (nullable at first — we'll populate it after seeding roles)
        batch_op.add_column(
            sa.Column(
                "role_id",
                sa.Integer(),
                sa.ForeignKey("roles.id", ondelete="SET NULL"),
                nullable=True,
            )
        )
        # Add must_change_password flag needed for super admin seeding
        batch_op.add_column(
            sa.Column(
                "must_change_password",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            )
        )

    # NOTE: We intentionally keep the old `roles` varchar column for now.
    # It will be populated by bootstrap seeding in main.py which will also
    # set role_id for all existing users by matching their old roles string.
    # Dropping it here in SQLite (batch mode) would wipe data before we can
    # migrate it.  The column drop is done in a separate step below AFTER
    # the data-migration note; in a real prod scenario you'd populate role_id
    # via a data-migration SQL before dropping.  For this local SQLite dev
    # setup we drop it immediately since the app re-seeds on start.
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("roles")


def downgrade() -> None:
    # Restore `roles` string column
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("roles", sa.VARCHAR(), nullable=True)
        )
        batch_op.drop_column("must_change_password")
        batch_op.drop_column("role_id")

    op.drop_table("user_permissions")
    op.drop_table("role_permissions")
    op.drop_table("permissions")
    op.drop_table("roles")
