"""
数据库迁移脚本：添加资金账户表和增强字段

运行方法:
    python scripts/migrate_add_portfolio_and_fields.py
"""
import sys
import os
from pathlib import Path
import sqlite3

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


def migrate():
    """执行数据库迁移"""
    print("开始添加资金账户和增强字段...")

    db_path = project_root / 'data' / 'uba.db'
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # 1. 创建 portfolios 表
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='portfolios'")
        if not cursor.fetchone():
            print("创建 portfolios 表...")
            cursor.execute("""
                CREATE TABLE portfolios (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    name VARCHAR(100) DEFAULT '默认账户',
                    total_asset FLOAT DEFAULT 0,
                    cash FLOAT DEFAULT 0,
                    market_value FLOAT DEFAULT 0,
                    frozen_cash FLOAT DEFAULT 0,
                    available_cash FLOAT DEFAULT 0,
                    total_profit FLOAT DEFAULT 0,
                    total_profit_rate FLOAT DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
            """)
            cursor.execute("CREATE INDEX ix_portfolios_user_id ON portfolios(user_id)")
            print("portfolios 表创建成功")
        else:
            print("portfolios 表已存在")

        # 2. 为 portfolio_positions 表添加新字段
        cursor.execute("PRAGMA table_info(portfolio_positions)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        new_position_fields = [
            ('market_value', 'FLOAT'),
            ('profit', 'FLOAT'),
            ('profit_rate', 'FLOAT'),
        ]

        for col_name, col_type in new_position_fields:
            if col_name not in existing_cols:
                print(f"添加字段: portfolio_positions.{col_name}")
                cursor.execute(f"ALTER TABLE portfolio_positions ADD COLUMN {col_name} {col_type}")
            else:
                print(f"字段已存在: portfolio_positions.{col_name}")

        # 3. 为 actions 表添加新字段
        cursor.execute("PRAGMA table_info(actions)")
        existing_action_cols = {row[1] for row in cursor.fetchall()}

        new_action_fields = [
            ('planned_amount', 'FLOAT'),
            ('executed_amount', 'FLOAT'),
            ('commission', 'FLOAT DEFAULT 0'),
            ('stamp_duty', 'FLOAT DEFAULT 0'),
            ('transfer_fee', 'FLOAT DEFAULT 0'),
            ('total_cost', 'FLOAT DEFAULT 0'),
            ('order_id', 'VARCHAR(100)'),
            ('order_status', 'VARCHAR(50)'),
        ]

        for col_name, col_type in new_action_fields:
            col_name_only = col_name.split()[0]  # 去掉 DEFAULT 部分
            if col_name_only not in existing_action_cols:
                print(f"添加字段: actions.{col_name_only}")
                cursor.execute(f"ALTER TABLE actions ADD COLUMN {col_name} {col_type}")
            else:
                print(f"字段已存在: actions.{col_name_only}")

        conn.commit()
        print("\n资金账户和增强字段迁移成功！")

    except Exception as e:
        print(f"迁移失败: {e}")
        import traceback
        traceback.print_exc()
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
