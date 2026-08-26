"""Alembic environment configuration — uses app settings for DB URL."""
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add backend/ to sys.path so we can import app modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import settings
from app.db.base import Base

# Import the models package so EVERY model registers on Base.metadata (its __init__
# imports all of them). The old explicit list covered only ~13 of 51 models, so a
# baseline/autogenerate would have silently missed the rest. (ELR-026)
import app.db.models  # noqa: F401

import os

config = context.config

# Prefer an explicit DATABASE_URL env var (standard for migration tools / CI /
# a throwaway test DB); fall back to the app's computed URL. (ELR-026)
_db_url = os.environ.get("DATABASE_URL") or settings.DATABASE_URL
config.set_main_option("sqlalchemy.url", _db_url)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection, target_metadata=target_metadata
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
