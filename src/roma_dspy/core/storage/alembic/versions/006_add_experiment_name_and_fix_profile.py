"""Add experiment_name column and fix profile population

Revision ID: 006_add_experiment_name_and_fix_profile
Revises: 005_deprecate_dag_snapshot
Create Date: 2025-11-04 00:00:00.000000

This migration:
1. Adds experiment_name column to track which experiment an execution belongs to
2. Fixes the profile column which exists but was never populated
3. Creates indexes for efficient filtering by experiment and profile

The experiment_name comes from the profile config's observability.mlflow.experiment_name field
and is used to group executions in the TUI and filter in the API.

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '006_experiment_profile'
down_revision: Union[str, None] = '01f9e9f52585'  # Points to latest head (rename_metadata_to_context_metadata)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Add experiment_name and profile columns to executions table.

    Steps:
    1. Add profile column with temporary default for existing rows
    2. Add experiment_name column with temporary default for existing rows
    3. Remove server defaults (make them required for new rows)
    4. Create indexes for efficient filtering
    """
    # Check if profile column exists, add if missing
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [col['name'] for col in inspector.get_columns('executions')]

    # Add profile column if it doesn't exist
    if 'profile' not in columns:
        op.add_column(
            'executions',
            sa.Column('profile', sa.String(length=128), nullable=False, server_default='unknown')
        )
    else:
        # If it exists, backfill NULL values
        op.execute("""
            UPDATE executions
            SET profile = 'unknown'
            WHERE profile IS NULL
        """)

    # Add experiment_name column with temporary default
    op.add_column(
        'executions',
        sa.Column('experiment_name', sa.String(length=255), nullable=False, server_default='unknown')
    )

    # Remove server defaults - future inserts must provide values
    op.alter_column('executions', 'profile', server_default=None)
    op.alter_column('executions', 'experiment_name', server_default=None)

    # Create indexes for efficient filtering
    op.create_index(
        'ix_executions_experiment_name',
        'executions',
        ['experiment_name']
    )

    # Check if profile index already exists, create if not
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('executions')]
    if 'ix_executions_profile' not in existing_indexes:
        op.create_index(
            'ix_executions_profile',
            'executions',
            ['profile']
        )


def downgrade() -> None:
    """
    Remove experiment_name and profile columns and indexes.
    """
    # Drop experiment_name index and column
    op.drop_index('ix_executions_experiment_name', table_name='executions')
    op.drop_column('executions', 'experiment_name')

    # Drop profile index (if exists) and column
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    existing_indexes = [idx['name'] for idx in inspector.get_indexes('executions')]
    if 'ix_executions_profile' in existing_indexes:
        op.drop_index('ix_executions_profile', table_name='executions')

    op.drop_column('executions', 'profile')
