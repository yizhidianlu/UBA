"""
数据库迁移脚本：为AI报告表添加可审计字段

运行方法:
    python scripts/migrate_add_ai_audit_fields.py
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
    print("开始添加AI报告可审计字段...")

    db_path = project_root / 'data' / 'uba.db'
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        return

    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()

    try:
        # 检查表是否存在
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='ai_analysis_reports'")
        if not cursor.fetchone():
            print("ai_analysis_reports 表不存在，跳过迁移")
            return

        # 获取现有列
        cursor.execute("PRAGMA table_info(ai_analysis_reports)")
        existing_cols = {row[1] for row in cursor.fetchall()}

        # 新增字段
        new_fields = [
            ('input_data_json', 'TEXT'),
            ('data_sources_json', 'TEXT'),
            ('model_name', 'VARCHAR(100)'),
            ('model_version', 'VARCHAR(50)'),
            ('prompt_tokens', 'INTEGER'),
            ('completion_tokens', 'INTEGER'),
            ('total_tokens', 'INTEGER'),
            ('estimated_cost', 'FLOAT'),
            ('generation_time_ms', 'INTEGER'),
            ('data_completeness_score', 'FLOAT'),
            ('missing_fields', 'TEXT'),
        ]

        for col_name, col_type in new_fields:
            if col_name not in existing_cols:
                print(f"添加字段: {col_name}")
                cursor.execute(f"ALTER TABLE ai_analysis_reports ADD COLUMN {col_name} {col_type}")
            else:
                print(f"字段已存在: {col_name}")

        conn.commit()
        print("\nAI报告可审计字段迁移成功！")

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
