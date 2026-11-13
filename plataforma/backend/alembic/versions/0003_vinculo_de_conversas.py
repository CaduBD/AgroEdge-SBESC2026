"""vínculo de conversas do chatbot (Telegram) com usuários

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-11 22:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
import sqlmodel

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CANAL = sa.Enum("telegram", name="canal")


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_tokens_servico")
    with op.batch_alter_table("tokens_servico", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "escopo",
                sqlmodel.sql.sqltypes.AutoString(),
                nullable=False,
                server_default="usuario",
            )
        )
    # Até aqui o único token de serviço era o do chatbot (criado pelo seed com esse nome).
    op.execute("UPDATE tokens_servico SET escopo = 'chatbot' WHERE nome = 'chatbot'")

    op.create_table(
        "bots_canal",
        sa.Column("canal", CANAL, nullable=False),
        sa.Column("usuario_bot", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("canal"),
    )
    op.create_table(
        "vinculos_canal",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("canal", CANAL, nullable=False),
        sa.Column("conversa_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("nome", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("alertas", sa.Boolean(), nullable=False),
        sa.Column("cultivo_id", sa.Integer(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("ultimo_uso", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("canal", "conversa_id", name="uq_vinculo_canal_conversa"),
    )
    op.create_index(
        op.f("ix_vinculos_canal_usuario_id"), "vinculos_canal", ["usuario_id"], unique=False
    )
    op.create_table(
        "codigos_vinculo",
        sa.Column("codigo", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("canal", CANAL, nullable=False),
        sa.Column("criado_em", sa.DateTime(), nullable=False),
        sa.Column("expira_em", sa.DateTime(), nullable=False),
        sa.Column("usado_em", sa.DateTime(), nullable=True),
        sa.Column("vinculo_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["usuario_id"], ["usuarios.id"]),
        sa.PrimaryKeyConstraint("codigo"),
    )
    op.create_index(
        op.f("ix_codigos_vinculo_usuario_id"), "codigos_vinculo", ["usuario_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_codigos_vinculo_usuario_id"), table_name="codigos_vinculo")
    op.drop_table("codigos_vinculo")
    op.drop_index(op.f("ix_vinculos_canal_usuario_id"), table_name="vinculos_canal")
    op.drop_table("vinculos_canal")
    op.drop_table("bots_canal")
    with op.batch_alter_table("tokens_servico", schema=None) as batch_op:
        batch_op.drop_column("escopo")
