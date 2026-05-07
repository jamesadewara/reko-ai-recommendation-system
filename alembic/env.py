import os
import sys
from logging.config import fileConfig

from sqlalchemy import create_engine, text
from sqlalchemy import pool

from alembic import context

# ── Add parent directory to sys.path ──────────────────────────────────────────
# This allows Alembic to import the FastAPI 'app' package.
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import settings
from app.db.session import Base
import app.models  # Required to populate Base.metadata for autogenerate

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# add your model's MetaData object here for 'autogenerate' support
target_metadata = Base.metadata

# ── Schema Configuration ───────────────────────────────────────────────────────
# This service owns the 'reko_auth' schema. The version table is also scoped
# to this schema so there is no conflict with other services on the same DB.
SERVICE_SCHEMA = "reko_auth"


def include_name(name, type_, parent_names):
    """
    Scope autogenerate strictly to this service's schema.
    Prevents detecting tables from other services (e.g. payment) as dropped.
    """
    if type_ == "schema":
        return name in (None, SERVICE_SCHEMA)
    return True


def get_url():
    """
    Standardizes the URL for Alembic.
    Ensures a synchronous driver (psycopg2) is used even if DATABASE_URL
    is configured for asyncpg in the .env.
    """
    url = settings.DATABASE_URL
    if url.startswith("postgresql+asyncpg://"):
        return url.replace("postgresql+asyncpg://", "postgresql://", 1)
    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        version_table="alembic_version",
        version_table_schema=SERVICE_SCHEMA,
        include_schemas=True,
        include_name=include_name,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = create_engine(get_url(), poolclass=pool.NullPool)

    with connectable.connect() as connection:
        # Ensure the schema exists before running any migrations
        connection.execute(text(f"CREATE SCHEMA IF NOT EXISTS {SERVICE_SCHEMA}"))
        connection.commit()

        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            version_table="alembic_version",
            version_table_schema=SERVICE_SCHEMA,
            include_schemas=True,
            include_name=include_name,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
