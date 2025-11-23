"""Add dag_snapshot to executions table

Revision ID: 003_add_dag_snapshot
Revises: 002_add_event_traces
Create Date: 2025-10-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "003_add_dag_snapshot"
down_revision: Union[str, None] = "002_event_traces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add dag_snapshot JSONB column to executions table."""
    op.add_column(
        "executions",
        sa.Column(
            "dag_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True
        ),
    )


def downgrade() -> None:
    """Remove dag_snapshot column from executions table."""
    op.drop_column("executions", "dag_snapshot")
