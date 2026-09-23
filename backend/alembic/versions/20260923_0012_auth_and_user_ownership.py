"""add authentication identities and learning-data ownership

Revision ID: 20260923_0012
Revises: 20260921_0011
Create Date: 2026-09-23
"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20260923_0012"
down_revision: str | None = "20260921_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    user_role = postgresql.ENUM("USER", "ADMIN", name="user_role", create_type=False)
    oauth_provider = postgresql.ENUM("GOOGLE", name="oauth_provider", create_type=False)
    user_role.create(op.get_bind(), checkfirst=True)
    oauth_provider.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=True),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_users")),
    )
    op.create_index(op.f("ix_users_email"), "users", ["email"], unique=True)
    op.create_table(
        "oauth_accounts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", oauth_provider, nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_oauth_accounts_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_oauth_accounts")),
        sa.UniqueConstraint(
            "provider", "provider_subject", name=op.f("uq_oauth_accounts_provider_provider_subject")
        ),
        sa.UniqueConstraint("user_id", "provider", name=op.f("uq_oauth_accounts_user_id_provider")),
    )
    op.create_index(op.f("ix_oauth_accounts_user_id"), "oauth_accounts", ["user_id"], unique=False)
    op.create_table(
        "refresh_sessions",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_refresh_sessions_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_refresh_sessions")),
    )
    op.create_index(
        op.f("ix_refresh_sessions_user_id"), "refresh_sessions", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_sessions_token_hash"), "refresh_sessions", ["token_hash"], unique=True
    )
    op.create_index(
        op.f("ix_refresh_sessions_expires_at"), "refresh_sessions", ["expires_at"], unique=False
    )
    op.create_index(
        op.f("ix_refresh_sessions_revoked_at"), "refresh_sessions", ["revoked_at"], unique=False
    )

    op.add_column("attempts", sa.Column("user_id", sa.Uuid(), nullable=True))
    op.add_column("test_sessions", sa.Column("user_id", sa.Uuid(), nullable=True))
    legacy_user_id = uuid.uuid4()
    op.get_bind().execute(
        sa.text(
            "INSERT INTO users (id, email, display_name, password_hash, role, is_active) "
            "VALUES (:id, :email, :display_name, NULL, 'USER', false)"
        ),
        {
            "id": legacy_user_id,
            "email": "legacy-admin@local.invalid",
            "display_name": "Legacy data owner",
        },
    )
    op.get_bind().execute(sa.text("UPDATE attempts SET user_id = :id"), {"id": legacy_user_id})
    op.get_bind().execute(sa.text("UPDATE test_sessions SET user_id = :id"), {"id": legacy_user_id})
    op.alter_column("attempts", "user_id", nullable=False)
    op.alter_column("test_sessions", "user_id", nullable=False)
    op.create_foreign_key(
        op.f("fk_attempts_user_id_users"),
        "attempts",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        op.f("fk_test_sessions_user_id_users"),
        "test_sessions",
        "users",
        ["user_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(op.f("ix_attempts_user_id"), "attempts", ["user_id"], unique=False)
    op.create_index(op.f("ix_test_sessions_user_id"), "test_sessions", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_test_sessions_user_id"), table_name="test_sessions")
    op.drop_index(op.f("ix_attempts_user_id"), table_name="attempts")
    op.drop_constraint(op.f("fk_test_sessions_user_id_users"), "test_sessions", type_="foreignkey")
    op.drop_constraint(op.f("fk_attempts_user_id_users"), "attempts", type_="foreignkey")
    op.drop_column("test_sessions", "user_id")
    op.drop_column("attempts", "user_id")
    op.drop_table("refresh_sessions")
    op.drop_table("oauth_accounts")
    op.drop_index(op.f("ix_users_email"), table_name="users")
    op.drop_table("users")
    postgresql.ENUM(name="oauth_provider").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="user_role").drop(op.get_bind(), checkfirst=True)
