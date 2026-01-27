"""
数据库迁移脚本：为 Valuation 表添加新字段

运行方法:
    python scripts/migrate_add_pb_fields.py
"""
import sys
import os
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from sqlalchemy import text
from src.database import get_session, init_db


def migrate():
    """执行数据库迁移"""
    print("开始数据库迁移...")

    # 初始化数据库
    init_db()
    session = get_session()

    try:
        # 检查表是否存在
        result = session.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='valuations'"
        ))
        if not result.fetchone():
            print("valuations 表不存在，跳过迁移")
            return

        # 获取现有列
        result = session.execute(text("PRAGMA table_info(valuations)"))
        columns = {row[1] for row in result.fetchall()}

        # 添加新字段（如果不存在）
        migrations = [
            ("pb_method", "ALTER TABLE valuations ADD COLUMN pb_method VARCHAR(50)"),
            ("report_period", "ALTER TABLE valuations ADD COLUMN report_period VARCHAR(20)"),
        ]

        for column_name, sql in migrations:
            if column_name not in columns:
                print(f"添加字段: {column_name}")
                session.execute(text(sql))
                session.commit()
            else:
                print(f"字段已存在: {column_name}")

        # 更新现有数据，设置默认值
        print("更新现有数据...")
        session.execute(text(
            "UPDATE valuations SET pb_method = 'direct' WHERE pb_method IS NULL"
        ))
        session.commit()

        print("数据库迁移完成！")

    except Exception as e:
        print(f"迁移失败: {e}")
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    migrate()
