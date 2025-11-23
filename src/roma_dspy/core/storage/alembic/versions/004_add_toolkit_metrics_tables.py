"""Add toolkit_traces and tool_invocation_traces tables

Revision ID: 004_toolkit_metrics
Revises: 003_add_dag_snapshot
Create Date: 2025-10-09

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "004_toolkit_metrics"
down_revision: Union[str, None] = "003_add_dag_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add toolkit_traces and tool_invocation_traces tables for toolkit observability."""

    # Create toolkit_traces table
    op.create_table(
        "toolkit_traces",
        sa.Column("trace_id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column(
            "timestamp",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("toolkit_class", sa.String(length=128), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("trace_id"),
    )

    # Create indexes for toolkit_traces
    op.create_index(
        "idx_toolkit_traces_execution",
        "toolkit_traces",
        ["execution_id", "timestamp"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "idx_toolkit_traces_operation", "toolkit_traces", ["operation"], unique=False
    )
    op.create_index(
        "idx_toolkit_traces_toolkit_class",
        "toolkit_traces",
        ["toolkit_class"],
        unique=False,
    )
    op.create_index(
        "idx_toolkit_traces_success", "toolkit_traces", ["success"], unique=False
    )

    # Create tool_invocation_traces table
    op.create_table(
        "tool_invocation_traces",
        sa.Column("trace_id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("toolkit_class", sa.String(length=128), nullable=False),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column(
            "invoked_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("duration_ms", sa.Float(), nullable=False),
        sa.Column("input_size_bytes", sa.Integer(), nullable=False),
        sa.Column("output_size_bytes", sa.Integer(), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("trace_id"),
    )

    # Create indexes for tool_invocation_traces
    op.create_index(
        "idx_tool_invocations_execution",
        "tool_invocation_traces",
        ["execution_id", "invoked_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "idx_tool_invocations_toolkit",
        "tool_invocation_traces",
        ["toolkit_class"],
        unique=False,
    )
    op.create_index(
        "idx_tool_invocations_tool",
        "tool_invocation_traces",
        ["tool_name"],
        unique=False,
    )
    op.create_index(
        "idx_tool_invocations_toolkit_tool",
        "tool_invocation_traces",
        ["toolkit_class", "tool_name"],
        unique=False,
    )
    op.create_index(
        "idx_tool_invocations_success",
        "tool_invocation_traces",
        ["success"],
        unique=False,
    )


def downgrade() -> None:
    """Remove toolkit_traces and tool_invocation_traces tables."""

    # Drop tool_invocation_traces indexes and table
    op.drop_index("idx_tool_invocations_success", table_name="tool_invocation_traces")
    op.drop_index(
        "idx_tool_invocations_toolkit_tool", table_name="tool_invocation_traces"
    )
    op.drop_index("idx_tool_invocations_tool", table_name="tool_invocation_traces")
    op.drop_index("idx_tool_invocations_toolkit", table_name="tool_invocation_traces")
    op.drop_index("idx_tool_invocations_execution", table_name="tool_invocation_traces")
    op.drop_table("tool_invocation_traces")

    # Drop toolkit_traces indexes and table
    op.drop_index("idx_toolkit_traces_success", table_name="toolkit_traces")
    op.drop_index("idx_toolkit_traces_toolkit_class", table_name="toolkit_traces")
    op.drop_index("idx_toolkit_traces_operation", table_name="toolkit_traces")
    op.drop_index("idx_toolkit_traces_execution", table_name="toolkit_traces")
    op.drop_table("toolkit_traces")
