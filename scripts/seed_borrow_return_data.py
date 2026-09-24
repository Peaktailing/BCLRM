"""生成一批「领用 → 归还」记录（测试用，带课程与实验）

用法：
    python scripts/seed_borrow_return_data.py [条数]      # 默认 40 条
    python scripts/seed_borrow_return_data.py --clean     # 清理

记录编号统一带 TESTBR 前缀，便于清理。
每条记录都会随机关联「课程 + 该课程下的实验」，用量与时间为随机值（固定随机种子）。
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_record_service import borrow_record_service
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.return_record_service import return_record_service

PREFIX = "TESTBR"
TEACHERS = ["王彩虹", "刘艳红", "张源", "李瑞龙", "张乐乐", "吴国火"]
START = datetime(2025, 9, 10)     # 2025-2026 学年
END = datetime(2026, 6, 20)


def clean():
    conn = db.connection
    cursor = conn.cursor()
    cursor.execute("DELETE FROM return_record WHERE return_number LIKE ?", (PREFIX + "%",))
    cursor.execute("DELETE FROM borrow_record WHERE record_number LIKE ?", (PREFIX + "%",))
    conn.commit()
    print(f"🧹 已清理 {PREFIX} 前缀的领用/归还记录")


def seed(count: int = 40):
    db.init_tables()
    random.seed(42)

    courses = experiment_course_service.get_by_semester(None)
    if not courses:
        print("❌ 没有课程，请先在「课程管理」中导入实验分组表")
        return

    bottles = [
        (b.bottle_number, b.reagent_name)
        for b in reagent_bottle_service.get_all_parsed()
        if getattr(b, "reagent_name", None) and not str(b.bottle_number).startswith(PREFIX)
    ]
    if not bottles:
        print("❌ 没有可用的试剂瓶")
        return

    reagent_map = {}
    for bottle_number, reagent_name in bottles:
        reagent_map.setdefault(reagent_name, bottle_number)
    reagents = list(reagent_map.items())[:10]

    span = (END - START).days
    created = with_item = 0
    for index in range(1, count + 1):
        record_number = f"{PREFIX}-{index:04d}"
        if borrow_record_service.get_by_field("record_number", record_number):
            continue

        course = random.choice(courses)
        course_items = experiment_item_service.get_by_course(course.course_name)
        exp_item = random.choice(course_items) if course_items else None
        reagent_name, bottle_number = random.choice(reagents)
        usage = round(random.uniform(5, 300), 1)
        when = START + timedelta(days=random.randint(0, span))
        time_str = when.strftime("%Y/%m/%d %H:%M")
        user = random.choice(TEACHERS)

        borrow_record_service.create({
            "record_number": record_number,
            "bottle_number": bottle_number,
            "user": user,
            "reagent_name": reagent_name,
            "borrow_time": time_str,
            "borrow_quantity": usage,
            "course_id": course.id,
            "item_id": exp_item.id if exp_item else None,
        })
        return_record_service.create({
            "return_number": f"{PREFIX}-RT-{index:04d}",
            "bottle_number": bottle_number,
            "return_user": user,
            "return_time": time_str,
            "remaining_quantity": 0.0,
            "usage_quantity": usage,
            "linked_borrow_record_number": record_number,
        })
        created += 1
        if exp_item:
            with_item += 1

    print(f"✅ 已生成 {created} 条领用/归还记录（{with_item} 条带实验项目）")
    print(f"   涉及课程 {len({c.course_name for c in courses})} 门、试剂 {len(reagents)} 种")
    print(f"   时间范围：{START:%Y/%m/%d} ~ {END:%Y/%m/%d}（2025-2026 学年）")


def main():
    if "--clean" in sys.argv:
        clean()
        return
    count = 40
    for arg in sys.argv[1:]:
        if arg.isdigit():
            count = int(arg)
    seed(count)


if __name__ == "__main__":
    main()
