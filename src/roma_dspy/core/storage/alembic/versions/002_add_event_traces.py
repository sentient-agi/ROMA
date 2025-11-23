"""Add event_traces table for event persistence

Revision ID: 002_event_traces
Revises: 001_initial
Create Date: 2025-10-07

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_event_traces"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add event_traces table for comprehensive event system observability."""
    op.create_table(
        "event_traces",
        sa.Column("event_id", sa.BigInteger(), nullable=False, autoincrement=True),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("task_id", sa.String(length=128), nullable=True),
        sa.Column("dag_id", sa.String(length=128), nullable=True),
        sa.Column(
            "created_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("processed_at", postgresql.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("handler_name", sa.String(length=64), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("event_data", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("dropped", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["execution_id"], ["executions.execution_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )

    # Create indexes for query performance
    op.create_index(
        "idx_event_traces_execution",
        "event_traces",
        ["execution_id", "created_at"],
        unique=False,
        postgresql_using="btree",
    )
    op.create_index(
        "idx_event_traces_type", "event_traces", ["event_type"], unique=False
    )
    op.create_index("idx_event_traces_task", "event_traces", ["task_id"], unique=False)


def downgrade() -> None:
    """Remove event_traces table."""
    op.drop_index("idx_event_traces_task", table_name="event_traces")
    op.drop_index("idx_event_traces_type", table_name="event_traces")
    op.drop_index("idx_event_traces_execution", table_name="event_traces")
    op.drop_table("event_traces")
