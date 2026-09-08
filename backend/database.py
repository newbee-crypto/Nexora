import os
from contextlib import contextmanager

from dotenv import load_dotenv
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

import logging
logger = logging.getLogger("crm.database")

DATABASE_URL = os.getenv("DATABASE_URL")

is_sqlite = False
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///crm.db"
    is_sqlite = True
elif DATABASE_URL.startswith("sqlite"):
    is_sqlite = True

engine = None

if not is_sqlite:
    try:
        temp_engine = create_engine(
            DATABASE_URL,
            pool_size=30,
            max_overflow=50,
            pool_timeout=60,
            pool_pre_ping=True,
            echo=False,
        )
        with temp_engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        engine = temp_engine
        logger.info("Successfully connected to PostgreSQL database.")
    except Exception as e:
        logger.warning(
            f"Failed to connect to PostgreSQL database ({e}). "
            "Falling back to local SQLite database 'crm.db'..."
        )
        DATABASE_URL = "sqlite:///crm.db"
        is_sqlite = True

# Resolve SQLite path relative to this file
if is_sqlite:
    path_part = DATABASE_URL.split("sqlite:///", 1)[1]
    if not os.path.isabs(path_part):
        db_dir = os.path.dirname(os.path.abspath(__file__))
        sqlite_path = os.path.abspath(os.path.join(db_dir, path_part))
        DATABASE_URL = f"sqlite:///{sqlite_path}"

    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
        echo=False,
    )
    logger.info(f"Initialized SQLite database at {DATABASE_URL}")

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency — yields a DB session for the request lifecycle."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def get_db_context():
    """Context manager version of get_db() for use in scripts without FastAPI DI."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
