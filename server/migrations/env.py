# Import the Base from our models
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# Add the parent directory to the path so we can import the server package
sys.path.append(str(Path(__file__).parent.parent.parent))

# Import settings and Base from our models
from sqlalchemy import MetaData

from server.database.models import Base
from server.settings import settings

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config


# Override the SQLAlchemy URL with the one from environment variables
config.set_main_option('sqlalchemy.url', settings.DATABASE_URL)

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
    url = config.get_main_option('sqlalchemy.url')
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={'paramstyle': 'named'},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix='sqlalchemy.',
        poolclass=pool.NullPool,
    )

    translated = MetaData()

    def translate_schema(table, to_schema, constraint, referred_schema):
        # pylint: disable=unused-argument
        return to_schema

    for table in Base.metadata.tables.values():
        table.tometadata(
            translated,
            schema='tenant_default' if table.schema == 'tenant' else table.schema,
            referred_schema_fn=translate_schema,
        )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=translated,
            compare_type=True,
            transaction_per_migration=True,
            include_schemas=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
