"""
数据库迁移脚本：为 Valuation 表添加唯一约束

运行方法:
    python scripts/migrate_add_unique_constraint.py
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
    print("开始添加唯一约束...")

    db_path = project_root / 'data' / 'uba.db'
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # 1. 检查是否已有唯一约束
        cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='valuations'")
        result = cursor.fetchone()
        if result and 'UNIQUE' in result[0]:
            print("唯一约束已存在，跳过迁移")
            return

        # 2. 清理重复数据（保留最新的）
        print("清理重复数据...")
        cursor.execute("""
            DELETE FROM valuations
            WHERE id NOT IN (
                SELECT MAX(id)
                FROM valuations
                GROUP BY asset_id, date
            )
        """)
        deleted = cursor.rowcount
        print(f"已删除 {deleted} 条重复数据")

        # 3. 创建新表结构（带唯一约束）
        print("创建新表结构...")
        cursor.execute("""
            CREATE TABLE valuations_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                date DATE NOT NULL,
                pb FLOAT NOT NULL,
                price FLOAT,
                book_value_per_share FLOAT,
                data_source VARCHAR(50) DEFAULT 'akshare',
                pb_method VARCHAR(50),
                report_period VARCHAR(20),
                fetched_at DATETIME,
                FOREIGN KEY(asset_id) REFERENCES assets(id),
                UNIQUE(asset_id, date)
            )
        """)

        # 4. 复制数据
        print("复制数据到新表...")
        cursor.execute("""
            INSERT INTO valuations_new
            SELECT * FROM valuations
        """)

        # 5. 删除旧表
        print("删除旧表...")
        cursor.execute("DROP TABLE valuations")

        # 6. 重命名新表
        print("重命名新表...")
        cursor.execute("ALTER TABLE valuations_new RENAME TO valuations")

        # 7. 创建索引
        print("创建索引...")
        cursor.execute("""
            CREATE INDEX ix_valuation_asset_date
            ON valuations (asset_id, date)
        """)

        conn.commit()
        print("唯一约束添加成功！")

    except Exception as e:
        print(f"迁移失败: {e}")
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    migrate()
