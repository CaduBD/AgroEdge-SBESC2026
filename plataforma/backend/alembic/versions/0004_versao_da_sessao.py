"""versão da sessão do usuário (trocar a senha derruba as outras sessões)

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-13 16:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS _alembic_tmp_usuarios")
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("sessao_versao", sa.Integer(), nullable=False, server_default="0")
        )


def downgrade() -> None:
    with op.batch_alter_table("usuarios", schema=None) as batch_op:
        batch_op.drop_column("sessao_versao")
