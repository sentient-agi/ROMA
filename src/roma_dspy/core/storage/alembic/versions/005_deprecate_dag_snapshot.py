"""Deprecate dag_snapshot in executions table

Revision ID: 005_deprecate_dag_snapshot
Revises: 004_add_toolkit_metrics_tables
Create Date: 2025-10-14 20:00:00.000000

This migration marks the dag_snapshot column as deprecated in favor of
checkpoint-based DAG storage. The column is retained for backward compatibility
but will be removed in a future version (v0.3.0).

Migration Phase: Phase 2 - Deprecation
- Column remains in database (safety net)
- Application no longer writes to this column
- Application reads from checkpoints instead
- Comment added to indicate deprecation

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "005_deprecate_dag_snapshot"
down_revision: Union[str, None] = "004_toolkit_metrics"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add deprecation comment to dag_snapshot column.

    This is a non-destructive change that marks the column as deprecated
    for future removal while maintaining backward compatibility.
    """
    # Add comment to column indicating deprecation
    op.execute("""
        COMMENT ON COLUMN executions.dag_snapshot IS
        'DEPRECATED: Use checkpoints table instead. This column is no longer written by the application as of v0.2.0 and will be removed in v0.3.0. DAG snapshots are now stored in the checkpoints table with better structure and compression.'
    """)


def downgrade() -> None:
    """
    Remove deprecation comment from dag_snapshot column.

    Restores the column to its original state without the deprecation notice.
    """
    # Remove comment from column
    op.execute("""
        COMMENT ON COLUMN executions.dag_snapshot IS NULL
    """)
