"""Database connection management."""
import os
import sys
import sqlite3
from contextlib import contextmanager
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


@contextmanager
def session_scope():
    """
    提供一个事务作用域的上下文管理器。

    使用方法:
        with session_scope() as session:
            session.add(obj)
            # 自动 commit，异常时自动 rollback

    优势:
    - 自动管理事务提交和回滚
    - 确保连接正确关闭
    - 简化错误处理
    """
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def run_migrations(db_path: str):
    """Run database migrations to add missing columns and tables."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    def add_column_if_missing(table: str, column: str, col_type: str) -> None:
        cursor.execute(f"PRAGMA table_info({table})")
        existing = {row[1] for row in cursor.fetchall()}
        if column not in existing:
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                print(f"Migration: Added column {column} to {table}")
            except Exception as exc:
                print(f"Migration warning: {exc}")

    # Migration 1: Add new columns to stock_candidates table
    stock_candidate_migrations = [
        ('recommended_add_pb', 'REAL'),
        ('recommended_sell_pb', 'REAL'),
        ('ai_score', 'INTEGER'),
        ('ai_suggestion', 'TEXT')
    ]

    for col_name, col_type in stock_candidate_migrations:
        add_column_if_missing('stock_candidates', col_name, col_type)

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

    # Migration 4: Add user_id columns for multi-user isolation
    user_scoped_tables = [
        'assets',
        'portfolio_positions',
        'signals',
        'actions',
        'visit_logs',
        'stock_candidates',
        'scan_progress',
        'ai_analysis_reports'
    ]

    for table in user_scoped_tables:
        add_column_if_missing(table, 'user_id', 'INTEGER')

    # Migration 5: Remove unique constraint on assets.code (allow per-user duplicates)
    cursor.execute("PRAGMA index_list(assets)")
    indexes = cursor.fetchall()
    has_unique_code = False
    for idx in indexes:
        index_name = idx[1]
        is_unique = idx[2]
        if is_unique:
            cursor.execute(f"PRAGMA index_info({index_name})")
            columns = [row[2] for row in cursor.fetchall()]
            if columns == ['code']:
                has_unique_code = True
                break

    if has_unique_code:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("ALTER TABLE assets RENAME TO assets_old")
        cursor.execute('''
            CREATE TABLE assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                code VARCHAR(20) NOT NULL,
                name VARCHAR(100) NOT NULL,
                market VARCHAR(20) NOT NULL,
                industry VARCHAR(100),
                tags VARCHAR(500),
                competence_score INTEGER DEFAULT 3,
                ai_score INTEGER,
                ai_suggestion TEXT,
                notes TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT INTO assets (
                id, user_id, code, name, market, industry, tags, competence_score,
                ai_score, ai_suggestion, notes, created_at, updated_at
            )
            SELECT id, user_id, code, name, market, industry, tags, competence_score,
                   ai_score, ai_suggestion, notes, created_at, updated_at
            FROM assets_old
        ''')
        cursor.execute("DROP TABLE assets_old")
        cursor.execute("PRAGMA foreign_keys=ON")
        print('Migration: Removed unique constraint on assets.code')

    # Migration 6: Remove unique constraint on visit_logs.visit_date
    cursor.execute("PRAGMA index_list(visit_logs)")
    visit_indexes = cursor.fetchall()
    has_unique_visit_date = False
    for idx in visit_indexes:
        index_name = idx[1]
        is_unique = idx[2]
        if is_unique:
            cursor.execute(f"PRAGMA index_info({index_name})")
            columns = [row[2] for row in cursor.fetchall()]
            if columns == ['visit_date']:
                has_unique_visit_date = True
                break

    if has_unique_visit_date:
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("ALTER TABLE visit_logs RENAME TO visit_logs_old")
        cursor.execute('''
            CREATE TABLE visit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                visit_date DATE NOT NULL,
                count INTEGER DEFAULT 1,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        cursor.execute('''
            INSERT INTO visit_logs (id, user_id, visit_date, count, updated_at)
            SELECT id, user_id, visit_date, count, updated_at FROM visit_logs_old
        ''')
        cursor.execute("DROP TABLE visit_logs_old")
        cursor.execute("PRAGMA foreign_keys=ON")
        print('Migration: Removed unique constraint on visit_logs.visit_date')

    conn.commit()
    conn.close()


def init_db():
    """Initialize database tables."""
    engine = get_engine()
    Base.metadata.create_all(engine)

    # Run migrations to add any missing columns/tables
    run_migrations(DB_PATH)
