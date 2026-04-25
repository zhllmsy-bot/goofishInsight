from __future__ import annotations

import atexit
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .logging import get_logger
from .settings import get_settings


settings = get_settings()
logger = get_logger(__name__)

engine = create_engine(
    settings.database_url,
    future=True,
    pool_pre_ping=True,
    pool_size=max(settings.db_pool_size, 1),
    max_overflow=max(settings.db_max_overflow, 0),
    pool_timeout=max(settings.db_pool_timeout_sec, 1),
    pool_recycle=max(settings.db_pool_recycle_sec, 1),
    pool_use_lifo=True,
)
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    future=True,
    expire_on_commit=False,
)


def dispose_engine() -> None:
    engine.dispose()


atexit.register(dispose_engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        logger.exception("database session rolled back after exception")
        session.rollback()
        raise
    finally:
        session.close()
