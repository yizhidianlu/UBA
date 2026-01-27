"""
数据库迁移脚本：添加行业配置表

运行方法:
    python scripts/migrate_add_industry_configs.py
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
    print("开始添加行业配置表...")

    db_path = project_root / 'data' / 'uba.db'
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # 检查表是否已存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='industry_configs'")
        if cursor.fetchone():
            print("industry_configs 表已存在")
            return

        # 创建表
        print("创建 industry_configs 表...")
        cursor.execute("""
            CREATE TABLE industry_configs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                industry_name VARCHAR(100) NOT NULL UNIQUE,
                display_name VARCHAR(100),
                description TEXT,
                default_buy_pb FLOAT,
                default_add_pb FLOAT,
                default_sell_pb FLOAT,
                typical_pb_range_min FLOAT,
                typical_pb_range_max FLOAT,
                typical_roe FLOAT,
                cyclical BOOLEAN DEFAULT 0,
                recommended_max_position FLOAT,
                risk_level VARCHAR(20),
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # 创建索引
        cursor.execute("CREATE INDEX ix_industry_configs_name ON industry_configs(industry_name)")

        conn.commit()
        print("industry_configs 表创建成功！")

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
