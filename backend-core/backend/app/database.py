from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from .config import settings

# Create SQLAlchemy engine
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # Verify connections before using them
    echo=settings.sql_echo,
)

# Create SessionLocal class for database sessions
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for all database models
Base = declarative_base()


def get_db() -> Session:
    """Dependency function to get database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_migrations():
    """Bring the schema up to date with Alembic — the only thing that creates tables.

    A database created by the old ``create_all()`` startup hook has the tables
    but no ``alembic_version``; it is stamped at the initial revision first so
    the upgrade doesn't try to recreate them.
    """
    from pathlib import Path
    from alembic import command
    from alembic.config import Config
    from sqlalchemy import inspect

    root = Path(__file__).resolve().parents[1]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.attributes["configure_logger"] = False  # keep the app's logging config

    tables = set(inspect(engine).get_table_names())
    if "alembic_version" not in tables and "projects" in tables:
        from alembic.script import ScriptDirectory
        base = ScriptDirectory.from_config(cfg).get_base()
        command.stamp(cfg, base)
    command.upgrade(cfg, "head")


def drop_tables():
    """Drop all database tables."""
    Base.metadata.drop_all(bind=engine)
