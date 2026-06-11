from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "022c32e6a89a"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE memory_items (
            memory_id text PRIMARY KEY,
            user_id text NOT NULL,
            layer smallint NOT NULL,
            memory_type text NOT NULL DEFAULT 'memory',
            content text NOT NULL DEFAULT '',
            embedding vector(1024),
            priority integer NOT NULL DEFAULT 50,
            scene_name text NOT NULL DEFAULT '',
            source_conversation_id text NOT NULL DEFAULT '',
            source_session_key text NOT NULL DEFAULT '',
            metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
            status text NOT NULL DEFAULT 'active',
            created_at timestamp NOT NULL,
            updated_at timestamp NOT NULL,
            is_deleted boolean NOT NULL DEFAULT false,
            deleted_at timestamp,
            CONSTRAINT memory_items_layer_check CHECK (layer BETWEEN 0 AND 3),
            CONSTRAINT memory_items_status_check CHECK (status IN ('active', 'archived')),
            CONSTRAINT memory_items_deleted_state_check CHECK (is_deleted = (deleted_at IS NOT NULL))
        )
        """
    )

    op.create_index(
        "idx_memory_items_user_layer_status",
        "memory_items",
        ["user_id", "layer", "status"],
    )
    op.create_index(
        "idx_memory_items_user_source",
        "memory_items",
        ["user_id", "source_conversation_id"],
    )
    op.create_index(
        "idx_memory_items_type_status",
        "memory_items",
        ["memory_type", "status"],
    )
    op.create_index(
        "idx_memory_items_updated_at",
        "memory_items",
        ["updated_at"],
    )
    op.execute(
        """
        CREATE INDEX idx_memory_items_embedding_hnsw
        ON memory_items USING hnsw (embedding vector_cosine_ops)
        WHERE embedding IS NOT NULL
        """
    )

    op.execute(
        """
        CREATE TABLE switch (
            user_id text NOT NULL,
            memory_switch boolean NOT NULL DEFAULT true,
            dream_switch boolean NOT NULL DEFAULT false,
            CONSTRAINT switch_user_id_pk PRIMARY KEY (user_id)
        )
        """
    )


def downgrade() -> None:
    op.drop_table("switch")
    op.drop_index("idx_memory_items_embedding_hnsw", table_name="memory_items")
    op.drop_index("idx_memory_items_updated_at", table_name="memory_items")
    op.drop_index("idx_memory_items_type_status", table_name="memory_items")
    op.drop_index("idx_memory_items_user_source", table_name="memory_items")
    op.drop_index("idx_memory_items_user_layer_status", table_name="memory_items")
    op.drop_table("memory_items")