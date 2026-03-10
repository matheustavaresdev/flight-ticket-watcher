import logging
import os
from contextlib import contextmanager

from sqlalchemy import create_engine
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
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{db}"


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


engine = create_engine(get_database_url(), pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


@contextmanager
def get_session() -> Session:
    """Context manager for database sessions."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
