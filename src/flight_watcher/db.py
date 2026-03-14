import logging
import os
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import URL as SQLAlchemyURL
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

logger = logging.getLogger(__name__)


def get_database_url() -> str:
    """Build DATABASE_URL from env vars. DATABASE_URL env var overrides individual vars."""
    if url := os.environ.get("DATABASE_URL"):
        return url
    host = os.environ.get("POSTGRES_HOST", "localhost")
    port = os.environ.get("POSTGRES_PORT", "5432")
    db = os.environ.get("POSTGRES_DB", "flight_watcher")
    user = os.environ.get("POSTGRES_USER", "flight_watcher")
    password = os.environ.get("POSTGRES_PASSWORD", "changeme")
    url = SQLAlchemyURL.create(
        drivername="postgresql+psycopg",
        username=user,
        password=password,
        host=host,
        port=int(port),
        database=db,
    )
    return url.render_as_string(hide_password=False)


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


_engine = None


def get_engine():
    """Return the SQLAlchemy engine, creating it on first call."""
    global _engine
    if _engine is None:
        _engine = create_engine(get_database_url(), pool_pre_ping=True)
    return _engine


# SessionLocal is a module-level name so tests can patch it.
# It is initialised lazily on first call to get_session() in production.
SessionLocal = None


@contextmanager
def get_session() -> Generator[Session, None, None]:
    """Context manager for database sessions."""
    global SessionLocal
    if SessionLocal is None:
        SessionLocal = sessionmaker(bind=get_engine(), autocommit=False, autoflush=False)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def dispose_engine() -> None:
    """Dispose the SQLAlchemy engine and reset module globals."""
    global _engine, SessionLocal
    if _engine is not None:
        _engine.dispose()
        _engine = None
        SessionLocal = None
        logger.info("Database engine disposed")
