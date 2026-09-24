"""导入实验课程分组表（命令行）

用法：
    python scripts/import_experiment_courses.py [csv路径]

解析学院实验分组表（CSV / Excel），导入「课程」与「实验项目」（幂等）。
与页面「课程管理 → 导入课程」共用同一套业务逻辑。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from business.course_import_service import course_import_service

DEFAULT_CSV = 'tmp/26-27-1实验分组表-生工院专业课实验分组表.csv'


def main():
    csv_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_CSV
    if not os.path.exists(csv_path):
        print(f"❌ 找不到文件: {csv_path}")
        return

    db.init_tables()

    parsed = course_import_service.parse(csv_path, csv_path)
    if parsed.is_failure():
        print(f"❌ 解析失败：{parsed.message}")
        return
    print(f"解析完成：{parsed.message}")

    info = parsed.data
    result = course_import_service.import_courses(
        courses=info["courses"],
        semester=info["semester"],
        term=info["term"],
        college=info["college"],
        items=info["items"],
    )
    if result.is_success():
        print(f"✅ {result.message}")
    else:
        print(f"❌ {result.message}")


if __name__ == "__main__":
    main()
