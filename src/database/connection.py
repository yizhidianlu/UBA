"""Database connection management."""
import os
import sys
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from .models import Base


def get_db_path():
    """Get database path based on environment."""
    # Check if running on Streamlit Cloud
    if os.environ.get('STREAMLIT_SHARING_MODE') or '/mount/src' in os.getcwd():
        # Use /tmp for Streamlit Cloud (writable directory)
        db_dir = '/tmp/uba_data'
    else:
        # Local development - use project data directory
        db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data")

    os.makedirs(db_dir, exist_ok=True)
    return os.path.join(db_dir, "uba.db")


# Database file path
DB_PATH = get_db_path()

_engine = None
_SessionLocal = None


def get_engine():
    """Get or create database engine."""
    global _engine, DB_PATH
    if _engine is None:
        # Refresh DB_PATH in case environment changed
        DB_PATH = get_db_path()
        _engine = create_engine(
            f"sqlite:///{DB_PATH}",
            echo=False,
            connect_args={"check_same_thread": False}  # Allow multi-thread access
        )
    return _engine


def get_session() -> Session:
    """Get a new database session."""
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine())
    return _SessionLocal()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)
