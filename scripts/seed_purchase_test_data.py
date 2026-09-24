"""生成 / 清理采购单功能的测试数据

用法：
    python scripts/seed_purchase_test_data.py           # 生成测试数据
    python scripts/seed_purchase_test_data.py --clean   # 清理测试数据

生成内容：
- 3 个测试试剂瓶（库存有限，确保会产生采购建议）
- 4 条「领用 → 归还」记录（归属 2025-2026 学年），
  其中【测试】试剂甲 被**两门课程共用**，用于验证「库存只扣一次」

所有测试数据的编号/瓶号统一带 TESTPUR 前缀，便于清理。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from services.base.experiment_course_service import experiment_course_service
from services.core.borrow_record_service import borrow_record_service
from services.core.reagent_bottle_service import reagent_bottle_service
from services.core.return_record_service import return_record_service

PREFIX = "TESTPUR"
SEMESTER_TIME = "2025/10/15 10:00"   # 落在 2025-2026 学年

BOTTLES = [
    ("TESTPUR001", "【测试】试剂甲", 50.0),
    ("TESTPUR002", "【测试】试剂乙", 30.0),
    ("TESTPUR003", "【测试】试剂丙", 200.0),
]

# (序号, 试剂, 课程下标, 用量)
USAGES = [
    ("01", "【测试】试剂甲", 0, 500.0),   # 课程1
    ("02", "【测试】试剂甲", 1, 300.0),   # 课程2 —— 与课程1 共用试剂甲
    ("03", "【测试】试剂乙", 0, 200.0),   # 课程1
    ("04", "【测试】试剂丙", 2, 100.0),   # 课程3
]


def clean():
    conn = db.connection
    cursor = conn.cursor()
    cursor.execute("DELETE FROM return_record WHERE return_number LIKE ?", (PREFIX + "%",))
    cursor.execute("DELETE FROM borrow_record WHERE record_number LIKE ?", (PREFIX + "%",))
    cursor.execute("DELETE FROM reagent_bottle WHERE bottle_number LIKE ?", (PREFIX + "%",))
    conn.commit()
    print(f"🧹 已清理 {PREFIX} 前缀的测试数据")


def seed():
    db.init_tables()

    courses = experiment_course_service.get_by_semester(None)[:3]
    if len(courses) < 3:
        print("❌ 课程不足 3 门，请先在「课程管理」中导入实验分组表")
        return

    for bottle_number, reagent_name, remaining in BOTTLES:
        if reagent_bottle_service.get_by_bottle_number(bottle_number):
            continue
        reagent_bottle_service.create({
            "bottle_number": bottle_number,
            "reagent_name": reagent_name,
            "cas_number": "999-99-9",
            "remaining_quantity": remaining,
            "borrowable_flag": "可借",
            "expired_flag": "正常",
        })
    print("✅ 测试试剂瓶：" + "、".join(f"{b[1]}(库存 {b[2]:g})" for b in BOTTLES))

    for index, reagent_name, course_index, usage in USAGES:
        record_number = f"{PREFIX}-BR-{index}"
        if borrow_record_service.get_by_field("record_number", record_number):
            continue
        course = courses[course_index]
        bottle_number = next(b[0] for b in BOTTLES if b[1] == reagent_name)

        borrow_record_service.create({
            "record_number": record_number,
            "bottle_number": bottle_number,
            "user": "王彩虹",
            "reagent_name": reagent_name,
            "borrow_time": SEMESTER_TIME,
            "borrow_quantity": usage,
            "course_id": course.id,
        })
        return_record_service.create({
            "return_number": f"{PREFIX}-RT-{index}",
            "bottle_number": bottle_number,
            "return_user": "王彩虹",
            "return_time": SEMESTER_TIME,
            "remaining_quantity": 0.0,
            "usage_quantity": usage,
            "linked_borrow_record_number": record_number,
        })
        print(f"  ➕ {reagent_name} × {course.course_name}（{course.class_name}）用量 {usage:g}")

    print("\n✅ 测试数据生成完成")
    print("   请到「采购管理 → 采购建议」选择学年 2025-2026 生成建议")


def main():
    if "--clean" in sys.argv:
        clean()
    else:
        seed()


if __name__ == "__main__":
    main()
