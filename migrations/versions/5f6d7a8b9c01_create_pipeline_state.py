from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "5f6d7a8b9c01"
down_revision: Union[str, Sequence[str], None] = "022c32e6a89a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "pipeline_state",
        sa.Column("user_id", sa.Text(), nullable=False, comment="用户ID"),
        sa.Column("source_session_key", sa.Text(), nullable=False, comment="来源会话ID"),
        sa.Column("conversation_count", sa.Integer(), nullable=False, server_default="0", comment="待处理会话轮次数"),
        sa.Column("warmup_threshold", sa.Integer(), nullable=False, server_default="1", comment="预热触发阈值"),
        sa.Column("last_l1_cursor", sa.BigInteger(), nullable=False, server_default="0", comment="L1 已处理 L0 时间游标"),
        sa.Column("last_scene_name", sa.Text(), nullable=False, server_default="", comment="上一次 L1 情境名称"),
        sa.Column("l1_running", sa.Boolean(), nullable=False, server_default=sa.false(), comment="L1 是否正在运行"),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False, comment="创建时间"),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False, comment="更新时间"),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false(), comment="是否删除"),
        sa.Column("deleted_at", sa.DateTime(timezone=False), nullable=True, comment="删除时间"),
        sa.PrimaryKeyConstraint("user_id", "source_session_key"),
    )
    op.create_index("idx_pipeline_state_updated_at", "pipeline_state", ["updated_at"])
    op.create_index("idx_pipeline_state_l1_running", "pipeline_state", ["l1_running"])


def downgrade() -> None:
    op.drop_index("idx_pipeline_state_l1_running", table_name="pipeline_state")
    op.drop_index("idx_pipeline_state_updated_at", table_name="pipeline_state")
    op.drop_table("pipeline_state")
