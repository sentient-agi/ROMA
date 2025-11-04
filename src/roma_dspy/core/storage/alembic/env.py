from logging.config import fileConfig
import os

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Import models for autogenerate support
from roma_dspy.core.storage.models import Base

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Override sqlalchemy.url from environment variable if present
# This allows running migrations in Docker where DATABASE_URL is set
database_url = os.getenv("DATABASE_URL")
if database_url:
    # Convert asyncpg URL to psycopg2 URL for migrations
    database_url = database_url.replace("postgresql+asyncpg://", "postgresql://")
    config.set_main_option("sqlalchemy.url", database_url)

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here
# for 'autogenerate' support
target_metadata = Base.metadata

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    # Allow running without database connection for autogenerate
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    # Try to connect; if it fails during autogenerate, use offline mode
    try:
        with connectable.connect() as connection:
            context.configure(
                connection=connection, target_metadata=target_metadata
            )

            with context.begin_transaction():
                context.run_migrations()
    except Exception as e:
        # During autogenerate without DB, fall back to offline mode
        import sys
        if "--autogenerate" in sys.argv or "revision" in sys.argv:
            run_migrations_offline()
        else:
            raise


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
