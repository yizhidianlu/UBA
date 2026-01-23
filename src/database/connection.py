"""Database connection management."""
import os
import sys
import sqlite3
from sqlalchemy import create_engine, text
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


def run_migrations(db_path: str):
    """Run database migrations to add missing columns and tables."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Migration 1: Add new columns to stock_candidates table
    cursor.execute("PRAGMA table_info(stock_candidates)")
    existing_columns = {row[1] for row in cursor.fetchall()}

    stock_candidate_migrations = [
        ('recommended_add_pb', 'REAL'),
        ('recommended_sell_pb', 'REAL'),
        ('ai_score', 'INTEGER'),
        ('ai_suggestion', 'TEXT'),
    ]

    for col_name, col_type in stock_candidate_migrations:
        if col_name not in existing_columns:
            try:
                cursor.execute(f'ALTER TABLE stock_candidates ADD COLUMN {col_name} {col_type}')
                print(f'Migration: Added column {col_name} to stock_candidates')
            except Exception as e:
                print(f'Migration warning: {e}')

    # Migration 2: Create ai_analysis_reports table if not exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_analysis_reports'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS ai_analysis_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                summary TEXT,
                valuation_analysis TEXT,
                fundamental_analysis TEXT,
                risk_analysis TEXT,
                investment_suggestion TEXT,
                pb_recommendation TEXT,
                full_report TEXT,
                ai_score INTEGER,
                price_at_report REAL,
                pb_at_report REAL,
                pe_at_report REAL,
                market_cap_at_report REAL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS ix_ai_analysis_reports_code ON ai_analysis_reports(code)')
        print('Migration: Created ai_analysis_reports table')

    # Migration 3: Create users table if not exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    if not cursor.fetchone():
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email VARCHAR(255) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login_at DATETIME
            )
        ''')
        cursor.execute('CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)')
        print('Migration: Created users table')

    conn.commit()
    conn.close()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Run migrations to add any missing columns/tables
    run_migrations(DB_PATH)
