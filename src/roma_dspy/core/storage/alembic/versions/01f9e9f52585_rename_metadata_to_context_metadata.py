"""rename_metadata_to_context_metadata

Revision ID: 01f9e9f52585
Revises: d956340fc66c
Create Date: 2025-10-15 04:10:13.397474

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "01f9e9f52585"
down_revision: Union[str, Sequence[str], None] = "d956340fc66c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Rename metadata column to context_metadata in toolkit and tool invocation traces."""
    # Rename metadata to context_metadata in toolkit_traces
    op.alter_column("toolkit_traces", "metadata", new_column_name="context_metadata")

    # Rename metadata to context_metadata in tool_invocation_traces
    op.alter_column(
        "tool_invocation_traces", "metadata", new_column_name="context_metadata"
    )


def downgrade() -> None:
    """Revert context_metadata back to metadata."""
    # Revert context_metadata to metadata in tool_invocation_traces
    op.alter_column(
        "tool_invocation_traces", "context_metadata", new_column_name="metadata"
    )

    # Revert context_metadata to metadata in toolkit_traces
    op.alter_column("toolkit_traces", "context_metadata", new_column_name="metadata")
