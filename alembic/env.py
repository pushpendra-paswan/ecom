from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app.core.config import settings
from app.db import Base

# Alembic Config object (gives access to alembic.ini)
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# The models' metadata, used by "alembic revision --autogenerate".
# From M1 on, import every model module here so its tables are registered on Base.
target_metadata = Base.metadata

# The database URL comes from the Settings class, not from alembic.ini
database_url = settings.DATABASE_URL


def run_migrations_offline() -> None:
    # Offline mode: only generate SQL, do not connect to the database
    context.configure(
        url=database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    # Online mode: connect to the database and run the migrations
    engine = create_engine(database_url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
