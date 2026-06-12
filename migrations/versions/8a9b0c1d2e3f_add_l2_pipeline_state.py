from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "8a9b0c1d2e3f"
down_revision: Union[str, Sequence[str], None] = "5f6d7a8b9c01"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "pipeline_state",
        sa.Column(
            "l2_pending_l1_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
            comment="待 L2 消费的 L1 完成次数",
        ),
    )
    op.add_column(
        "pipeline_state",
        sa.Column("last_l2_cursor", sa.DateTime(timezone=False), nullable=True, comment="L2 已处理 L1 更新时间游标"),
    )
    op.add_column(
        "pipeline_state",
        sa.Column("l2_last_extraction_time", sa.DateTime(timezone=False), nullable=True, comment="最近一次 L2 完成时间"),
    )
    op.add_column(
        "pipeline_state",
        sa.Column(
            "l2_running",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
            comment="L2 是否正在运行",
        ),
    )
    op.add_column(
        "pipeline_state",
        sa.Column("l2_next_run_at", sa.DateTime(timezone=False), nullable=True, comment="下一次 L2 计划触发时间"),
    )
    op.create_index("idx_pipeline_state_l2_next_run_at", "pipeline_state", ["l2_next_run_at"])
    op.create_index("idx_pipeline_state_l2_running", "pipeline_state", ["l2_running"])


def downgrade() -> None:
    op.drop_index("idx_pipeline_state_l2_running", table_name="pipeline_state")
    op.drop_index("idx_pipeline_state_l2_next_run_at", table_name="pipeline_state")
    op.drop_column("pipeline_state", "l2_next_run_at")
    op.drop_column("pipeline_state", "l2_running")
    op.drop_column("pipeline_state", "l2_last_extraction_time")
    op.drop_column("pipeline_state", "last_l2_cursor")
    op.drop_column("pipeline_state", "l2_pending_l1_count")
