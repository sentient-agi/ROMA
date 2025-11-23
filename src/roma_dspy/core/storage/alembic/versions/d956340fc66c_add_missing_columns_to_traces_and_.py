"""add_missing_columns_to_traces_and_checkpoints

Revision ID: d956340fc66c
Revises: 005_deprecate_dag_snapshot
Create Date: 2025-10-15 00:01:47.244754

This migration adds missing columns to align the database schema with the current models.

Changes:
1. lm_traces: Add temperature, max_tokens, prediction_strategy, cost_usd
2. lm_traces: Rename 'id' to 'trace_id', remove provider and old cost columns
3. checkpoints: Complete schema overhaul to match DAGSnapshot storage model
4. task_traces: Add missing columns and rename id to trace_id
5. executions: Add final_result column
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d956340fc66c"
down_revision: Union[str, Sequence[str], None] = "005_deprecate_dag_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema to match current models."""

    # === lm_traces table updates ===
    # Add missing columns
    op.add_column("lm_traces", sa.Column("temperature", sa.Float(), nullable=True))
    op.add_column("lm_traces", sa.Column("max_tokens", sa.Integer(), nullable=True))
    op.add_column(
        "lm_traces",
        sa.Column("prediction_strategy", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "lm_traces",
        sa.Column("cost_usd", sa.Numeric(precision=10, scale=6), nullable=True),
    )

    # Remove obsolete columns
    op.drop_column("lm_traces", "provider")
    op.drop_column("lm_traces", "prompt_cost")
    op.drop_column("lm_traces", "completion_cost")
    op.drop_column("lm_traces", "total_cost")

    # Rename primary key column
    op.alter_column("lm_traces", "id", new_column_name="trace_id")

    # === checkpoints table updates ===
    # Add new columns for DAGSnapshot storage
    op.add_column(
        "checkpoints",
        sa.Column(
            "state", sa.String(length=32), nullable=False, server_default="valid"
        ),
    )
    op.add_column(
        "checkpoints",
        sa.Column(
            "dag_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "checkpoints",
        sa.Column(
            "preserved_results",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "checkpoints",
        sa.Column(
            "module_states",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "checkpoints",
        sa.Column(
            "failed_task_ids",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "checkpoints", sa.Column("file_size_bytes", sa.BigInteger(), nullable=True)
    )
    op.add_column(
        "checkpoints",
        sa.Column("compressed", sa.Boolean(), nullable=False, server_default="true"),
    )

    # Modify checkpoint_id length to match model
    op.alter_column("checkpoints", "checkpoint_id", type_=sa.String(length=128))

    # Remove old columns
    op.drop_column("checkpoints", "depth")
    op.drop_column("checkpoints", "tasks_completed")
    op.drop_column("checkpoints", "tasks_total")
    op.drop_column("checkpoints", "state_snapshot")
    op.drop_column("checkpoints", "checkpoint_metadata")

    # Update file_path column length
    op.alter_column("checkpoints", "file_path", type_=sa.Text())

    # Add index for state
    op.create_index("idx_checkpoints_state", "checkpoints", ["state"], unique=False)
    op.create_index("idx_checkpoints_trigger", "checkpoints", ["trigger"], unique=False)

    # === task_traces table updates ===
    # Rename primary key
    op.alter_column("task_traces", "id", new_column_name="trace_id")

    # Rename parent_id to parent_task_id
    op.alter_column("task_traces", "parent_id", new_column_name="parent_task_id")

    # Add missing columns
    op.add_column(
        "task_traces", sa.Column("node_type", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "task_traces",
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "task_traces",
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "task_traces",
        sa.Column(
            "updated_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Make task_type NOT NULL (it was nullable before)
    op.alter_column("task_traces", "task_type", nullable=False, server_default="THINK")

    # Update checkpoint_id foreign key to match new length
    op.drop_constraint(
        "task_traces_checkpoint_id_fkey", "task_traces", type_="foreignkey"
    )
    op.alter_column("task_traces", "checkpoint_id", type_=sa.String(length=128))
    op.create_foreign_key(
        "task_traces_checkpoint_id_fkey",
        "task_traces",
        "checkpoints",
        ["checkpoint_id"],
        ["checkpoint_id"],
        ondelete="SET NULL",
    )

    # Add index for parent_task_id
    op.create_index(
        "idx_task_traces_parent", "task_traces", ["parent_task_id"], unique=False
    )

    # === executions table updates ===
    # Add final_result column
    op.add_column(
        "executions",
        sa.Column(
            "final_result", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )

    # === circuit_breakers table updates ===
    # Rename 'name' to 'circuit_id' to match model
    op.alter_column("circuit_breakers", "name", new_column_name="circuit_id")


def downgrade() -> None:
    """Downgrade schema to previous version."""

    # === circuit_breakers table ===
    op.alter_column("circuit_breakers", "circuit_id", new_column_name="name")

    # === executions table ===
    op.drop_column("executions", "final_result")

    # === task_traces table ===
    op.drop_index("idx_task_traces_parent", table_name="task_traces")

    op.drop_constraint(
        "task_traces_checkpoint_id_fkey", "task_traces", type_="foreignkey"
    )
    op.alter_column("task_traces", "checkpoint_id", type_=sa.String(length=64))
    op.create_foreign_key(
        "task_traces_checkpoint_id_fkey",
        "task_traces",
        "checkpoints",
        ["checkpoint_id"],
        ["checkpoint_id"],
        ondelete="SET NULL",
    )

    op.alter_column("task_traces", "task_type", nullable=True)
    op.drop_column("task_traces", "updated_at")
    op.drop_column("task_traces", "max_retries")
    op.drop_column("task_traces", "retry_count")
    op.drop_column("task_traces", "node_type")

    op.alter_column("task_traces", "parent_task_id", new_column_name="parent_id")
    op.alter_column("task_traces", "trace_id", new_column_name="id")

    # === checkpoints table ===
    op.drop_index("idx_checkpoints_trigger", table_name="checkpoints")
    op.drop_index("idx_checkpoints_state", table_name="checkpoints")

    op.alter_column("checkpoints", "file_path", type_=sa.String(length=512))

    op.add_column(
        "checkpoints",
        sa.Column(
            "checkpoint_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "checkpoints",
        sa.Column(
            "state_snapshot",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
    )
    op.add_column(
        "checkpoints",
        sa.Column("tasks_total", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "checkpoints",
        sa.Column("tasks_completed", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "checkpoints",
        sa.Column("depth", sa.Integer(), nullable=False, server_default="0"),
    )

    op.alter_column("checkpoints", "checkpoint_id", type_=sa.String(length=64))

    op.drop_column("checkpoints", "compressed")
    op.drop_column("checkpoints", "file_size_bytes")
    op.drop_column("checkpoints", "failed_task_ids")
    op.drop_column("checkpoints", "module_states")
    op.drop_column("checkpoints", "preserved_results")
    op.drop_column("checkpoints", "dag_snapshot")
    op.drop_column("checkpoints", "state")

    # === lm_traces table ===
    op.alter_column("lm_traces", "trace_id", new_column_name="id")

    op.add_column(
        "lm_traces",
        sa.Column("total_cost", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "lm_traces",
        sa.Column("completion_cost", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "lm_traces",
        sa.Column("prompt_cost", sa.Numeric(precision=10, scale=6), nullable=True),
    )
    op.add_column(
        "lm_traces", sa.Column("provider", sa.String(length=64), nullable=True)
    )

    op.drop_column("lm_traces", "cost_usd")
    op.drop_column("lm_traces", "prediction_strategy")
    op.drop_column("lm_traces", "max_tokens")
    op.drop_column("lm_traces", "temperature")
