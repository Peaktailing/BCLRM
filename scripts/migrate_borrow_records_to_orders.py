"""把历史领用记录迁移为领用工单（统一用量口径）

用法：
    python scripts/migrate_borrow_records_to_orders.py

为每条 borrow_record 建立一张工单 + 一条明细：
- 领用量   = borrow_quantity
- 已归还量 = 领用量 − 归还记录中的用量合计（单次归还场景等价）
- 领用时间 = borrow_time
- 工单类型：有 course_id → 课程领用；否则 → 零星领用

工单号统一加 ``BO-MIG-`` 前缀，重复执行会跳过已迁移的记录。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from models.core.borrow_order import (
    ORDER_STATUS_BORROWING,
    ORDER_STATUS_PARTIAL,
    ORDER_STATUS_RETURNED,
    ORDER_TYPE_COURSE,
    ORDER_TYPE_SPORADIC,
)
from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from services.core.borrow_order_service import (
    borrow_order_item_service,
    borrow_order_service,
)
from services.core.borrow_record_service import borrow_record_service
from services.core.return_record_service import return_record_service

PREFIX = "BO-MIG-"


def main():
    db.init_tables()

    borrow_records = borrow_record_service.get_all_parsed()
    return_records = return_record_service.get_all_parsed()
    print(f"待检查领用记录：{len(borrow_records)} 条")

    migrated = skipped = 0
    for record in borrow_records:
        order_number = PREFIX + (record.record_number or "")
        if borrow_order_service.get_by_order_number(order_number):
            skipped += 1
            continue

        borrow_qty = float(record.borrow_quantity or 0)
        usage = sum(
            float(r.usage_quantity or 0)
            for r in return_records
            if getattr(r, "linked_borrow_record_number", None) == record.record_number
        )
        returned = round(max(0.0, borrow_qty - usage), 4)
        if returned + 1e-6 >= borrow_qty and borrow_qty > 0:
            status = ORDER_STATUS_RETURNED
            item_status = "已归还"
        elif returned > 0:
            status = ORDER_STATUS_PARTIAL
            item_status = "待归还"
        else:
            status = ORDER_STATUS_BORROWING
            item_status = "待归还"

        course = experiment_course_service.get_by_id(record.course_id) if record.course_id else None
        item = experiment_item_service.get_by_id(record.item_id) if record.item_id else None

        order_id = borrow_order_service.create({
            "order_number": order_number,
            "order_type": ORDER_TYPE_COURSE if record.course_id else ORDER_TYPE_SPORADIC,
            "applicant": record.user,
            "borrow_time": record.borrow_time,
            "course_id": record.course_id,
            "item_id": record.item_id,
            "course_name": getattr(course, "course_name", None),
            "item_name": getattr(item, "item_name", None),
            "status": status,
            "remark": "由历史领用记录迁移",
            "created_by": "migration",
        })
        if not order_id:
            print(f"  ❌ 迁移失败：{record.record_number}")
            continue

        borrow_order_item_service.create({
            "order_id": order_id,
            "bottle_number": record.bottle_number,
            "reagent_name": record.reagent_name,
            "borrow_qty": borrow_qty,
            "returned_qty": returned,
            "status": item_status,
        })
        migrated += 1

    print(f"✅ 迁移完成：新建工单 {migrated} 张，跳过 {skipped} 张")
    print(f"   现有工单总数：{len(borrow_order_service.get_all_parsed())}")


if __name__ == "__main__":
    main()
