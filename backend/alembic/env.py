"""Alembic environment.

The database URL comes from app settings (.env), never from alembic.ini.
Run against the pytest database with: `alembic -x test=true upgrade head`.
"""

from logging.config import fileConfig

from sqlalchemy import create_engine, pool

import app.models  # noqa: F401  (registers all models on Base.metadata)
from alembic import context
from app.core.config import get_settings
from app.core.db import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

_use_test_db = context.get_x_argument(as_dictionary=True).get("test", "").lower() in {"1", "true", "yes"}
DATABASE_URL = get_settings().database_url(test=_use_test_db)


def run_migrations_offline() -> None:
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(DATABASE_URL, poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
