"""课程采购单数据服务类

对应数据表：
- purchase_plan        课程采购单表头（按「课程名 + 目标学年」唯一）
- purchase_plan_item   采购单明细（课程 - 实验 - 试剂）
"""
from typing import List, Optional

from db.base_service import BaseService
from models.core.purchase_plan import PurchasePlan, PurchasePlanItem
from utils.error_handler import logger


class PurchasePlanService(BaseService):
    """课程采购单表头服务"""

    def __init__(self):
        super().__init__("purchase_plan")
        logger.info("采购单服务初始化完成")

    def get_by_id(self, record_id: int) -> Optional[PurchasePlan]:
        record = super().get_by_id(record_id)
        return self._parse_record(record) if record else None

    def get_all_parsed(self) -> List[PurchasePlan]:
        """全部采购单（最新在前）"""
        return [self._parse_record(record) for record in self.get_all(order_by="id DESC")]

    def get_by_course(self, course_name: str, target_semester: str) -> Optional[PurchasePlan]:
        """按「课程名 + 目标学年」查询（用于覆盖更新判断）"""
        rows = self.db.execute_query(
            "SELECT * FROM purchase_plan WHERE course_name = ? AND target_semester = ? LIMIT 1",
            (course_name, target_semester)
        )
        return self._parse_record(rows[0]) if rows else None

    def _parse_record(self, record: dict) -> PurchasePlan:
        return PurchasePlan(
            id=record.get('id'),
            plan_number=record.get('plan_number'),
            course_name=record.get('course_name'),
            source_semester=record.get('source_semester'),
            target_semester=record.get('target_semester'),
            source_student_count=record.get('source_student_count'),
            target_student_count=record.get('target_student_count'),
            status=record.get('status'),
            item_count=record.get('item_count'),
            total_quantity=record.get('total_quantity'),
            remark=record.get('remark'),
            created_by=record.get('created_by'),
            updated_by=record.get('updated_by'),
        )


class PurchasePlanItemService(BaseService):
    """采购单明细服务"""

    def __init__(self):
        super().__init__("purchase_plan_item")
        logger.info("采购单明细服务初始化完成")

    def get_by_plan(self, plan_id: int) -> List[PurchasePlanItem]:
        """查询某采购单的全部明细（按实验序号、采购量排序）"""
        records = self.db.execute_query(
            "SELECT * FROM purchase_plan_item WHERE plan_id = ? ORDER BY item_id, id",
            (plan_id,)
        )
        return [self._parse_record(record) for record in records]

    def delete_by_plan(self, plan_id: int) -> bool:
        """删除某采购单的全部明细（覆盖更新时使用）"""
        try:
            self.db.execute_update("DELETE FROM purchase_plan_item WHERE plan_id = ?", (plan_id,))
            return True
        except Exception as e:
            logger.error(f"删除采购单明细失败: {str(e)}", exception=e)
            return False

    def _parse_record(self, record: dict) -> PurchasePlanItem:
        return PurchasePlanItem(
            id=record.get('id'),
            plan_id=record.get('plan_id'),
            item_id=record.get('item_id'),
            item_name=record.get('item_name'),
            reagent_name=record.get('reagent_name'),
            cas_number=record.get('cas_number'),
            source_quantity=record.get('source_quantity'),
            per_capita_usage=record.get('per_capita_usage'),
            student_count=record.get('student_count'),
            demand_quantity=record.get('demand_quantity'),
            purchase_quantity=record.get('purchase_quantity'),
            current_stock=record.get('current_stock'),
            is_manual=record.get('is_manual'),
            supplier=record.get('supplier'),
            unit_price=record.get('unit_price'),
            remark=record.get('remark'),
        )


# 全局实例
purchase_plan_service = PurchasePlanService()
purchase_plan_item_service = PurchasePlanItemService()
