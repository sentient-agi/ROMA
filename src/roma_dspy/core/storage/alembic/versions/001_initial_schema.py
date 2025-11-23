"""Initial schema with executions, checkpoints, traces

Revision ID: 001_initial
Revises:
Create Date: 2025-10-06

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create executions table
    op.create_table(
        "executions",
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("initial_goal", sa.Text(), nullable=False),
        sa.Column("max_depth", sa.Integer(), nullable=False),
        sa.Column("total_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_tasks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column(
            "execution_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.PrimaryKeyConstraint("execution_id"),
    )
    op.create_index(
        "idx_executions_created_at",
        "executions",
        ["created_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index("idx_executions_status", "executions", ["status"], unique=False)

    # Create checkpoints table
    op.create_table(
        "checkpoints",
        sa.Column("checkpoint_id", sa.String(length=64), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("tasks_completed", sa.Integer(), nullable=False),
        sa.Column("tasks_total", sa.Integer(), nullable=False),
        sa.Column(
            "state_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column(
            "checkpoint_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("checkpoint_id"),
    )
    op.create_index(
        "idx_checkpoints_execution",
        "checkpoints",
        ["execution_id", "created_at"],
        unique=False,
        postgresql_using="btree",
    )

    # Create task_traces table
    op.create_table(
        "task_traces",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("checkpoint_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("task_type", sa.String(length=32), nullable=True),
        sa.Column("depth", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.String(length=128), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "dependencies",
            postgresql.ARRAY(sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("subgraph_id", sa.String(length=128), nullable=True),
        sa.Column(
            "task_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["checkpoint_id"], ["checkpoints.checkpoint_id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_task_traces_execution",
        "task_traces",
        ["execution_id", "created_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "idx_task_traces_task_id",
        "task_traces",
        ["execution_id", "task_id"],
        unique=False,
    )
    op.create_index("idx_task_traces_status", "task_traces", ["status"], unique=False)

    # Create lm_traces table
    op.create_table(
        "lm_traces",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("module_name", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "completion_tokens", sa.Integer(), nullable=False, server_default="0"
        ),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("prompt_cost", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("completion_cost", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("total_cost", sa.Numeric(precision=10, scale=6), nullable=True),
        sa.Column("prompt", sa.Text(), nullable=True),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column(
            "lm_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_lm_traces_execution",
        "lm_traces",
        ["execution_id", "created_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index("idx_lm_traces_task", "lm_traces", ["task_id"], unique=False)
    op.create_index("idx_lm_traces_model", "lm_traces", ["model"], unique=False)
    op.create_index("idx_lm_traces_module", "lm_traces", ["module_name"], unique=False)

    # Create circuit_breakers table
    op.create_table(
        "circuit_breakers",
        sa.Column("id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("execution_id", sa.String(length=64), nullable=True),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(
            "last_failure_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column(
            "last_success_at", postgresql.TIMESTAMP(timezone=True), nullable=True
        ),
        sa.Column("config", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "breaker_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_index(
        "idx_circuit_breakers_execution",
        "circuit_breakers",
        ["execution_id"],
        unique=False,
    )
    op.create_index(
        "idx_circuit_breakers_state", "circuit_breakers", ["state"], unique=False
    )


def downgrade() -> None:
    op.drop_index("idx_circuit_breakers_state", table_name="circuit_breakers")
    op.drop_index("idx_circuit_breakers_execution", table_name="circuit_breakers")
    op.drop_table("circuit_breakers")

    op.drop_index("idx_lm_traces_module", table_name="lm_traces")
    op.drop_index("idx_lm_traces_model", table_name="lm_traces")
    op.drop_index("idx_lm_traces_task", table_name="lm_traces")
    op.drop_index("idx_lm_traces_execution", table_name="lm_traces")
    op.drop_table("lm_traces")

    op.drop_index("idx_task_traces_status", table_name="task_traces")
    op.drop_index("idx_task_traces_task_id", table_name="task_traces")
    op.drop_index("idx_task_traces_execution", table_name="task_traces")
    op.drop_table("task_traces")

    op.drop_index("idx_checkpoints_execution", table_name="checkpoints")
    op.drop_table("checkpoints")

    op.drop_index("idx_executions_status", table_name="executions")
    op.drop_index("idx_executions_created_at", table_name="executions")
    op.drop_table("executions")
