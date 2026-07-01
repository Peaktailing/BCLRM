"""工单服务 - 借出/还入工单审批

设计思路：
- 教师提交借出/还入工单，管理员审批
- 工单是审批容器，审批通过后才执行实际的借出/归还操作
- 试剂瓶级别跟踪实际借出/归还状态（解决"a借b还"问题）
"""
from typing import Optional, List, Dict
from db.database import db
from utils.error_handler import logger, ServiceResult
from utils.id_generator import id_generator
from datetime import datetime


class WorkOrderService:
    """工单服务"""

    # ── 借出工单 ──────────────────────────────────────────

    def create_borrow_order(self, applicant_id: str, applicant_name: str,
                            items: List[Dict], remark: str = "") -> ServiceResult:
        """创建借出工单

        Args:
            applicant_id: 申请人 user_id
            applicant_name: 申请人姓名
            items: [{bottle_number, borrow_qty}, ...]
            remark: 备注
        """
        if not items:
            return ServiceResult.fail("工单至少需要一项试剂")

        order_number = "BO" + datetime.now().strftime("%Y%m%d%H%M%S") + id_generator.generate_short_id()
        try:
            cursor = db.connection.cursor()
            cursor.execute(
                """INSERT INTO borrow_order (order_number, applicant_id, applicant_name, status, remark)
                   VALUES (?, ?, ?, '待审批', ?)""",
                (order_number, applicant_id, applicant_name, remark),
            )
            order_id = cursor.lastrowid

            for item in items:
                cursor.execute(
                    """INSERT INTO borrow_order_item (order_id, bottle_number, borrow_qty, status)
                       VALUES (?, ?, ?, '待审批')""",
                    (order_id, item["bottle_number"], item["borrow_qty"]),
                )

            db.connection.commit()
            logger.info(f"借出工单创建成功: {order_number}, {len(items)}项")
            return ServiceResult.ok(data={"order_id": order_id, "order_number": order_number},
                                    message=f"借出工单 {order_number} 已提交，等待审批")
        except Exception as e:
            db.connection.rollback()
            logger.error(f"创建借出工单失败: {e}", exception=e)
            return ServiceResult.fail(f"创建工单失败: {str(e)}")

    def approve_borrow_order(self, order_id: int, approver_id: str) -> ServiceResult:
        """审批通过借出工单，执行实际借出"""
        order = self._get_borrow_order(order_id)
        if not order:
            return ServiceResult.fail("工单不存在")
        if order["status"] != "待审批":
            return ServiceResult.fail(f"工单状态为「{order['status']}」，无法审批")

        try:
            cursor = db.connection.cursor()
            now = datetime.now().strftime("%Y/%m/%d %H:%M")

            # 更新工单状态
            cursor.execute(
                "UPDATE borrow_order SET status='已批准', approver_id=?, approved_at=? WHERE id=?",
                (approver_id, now, order_id),
            )
            cursor.execute(
                "UPDATE borrow_order_item SET status='已批准' WHERE order_id=?",
                (order_id,),
            )

            # 获取工单项
            items = db.execute_query(
                "SELECT * FROM borrow_order_item WHERE order_id=?", (order_id,)
            )

            # 执行实际借出操作（更新试剂瓶状态）
            from services.core.reagent_bottle_service import reagent_bottle_service
            from services.core.borrow_record_service import borrow_record_service

            for item in items:
                bn = item["bottle_number"]
                qty = item["borrow_qty"]

                bottle = reagent_bottle_service.get_by_bottle_number(bn)
                if not bottle:
                    continue

                remaining = getattr(bottle, 'remaining_quantity', 0) or 0
                new_qty = remaining - qty

                record_num = "BR" + datetime.now().strftime("%Y%m%d%H%M%S") + id_generator.generate_short_id()
                borrow_record_service.create({
                    "record_number": record_num,
                    "bottle_number": bn,
                    "user": order["applicant_name"],
                    "borrow_time": now,
                    "reagent_name": getattr(bottle, 'reagent_name', ''),
                    "cas_number": getattr(bottle, 'cas_number', ''),
                })

                # 更新试剂瓶
                from utils.field_mapper import ReagentBottleField
                reagent_bottle_service.update(bottle.id, {
                    ReagentBottleField.REMAINING_QUANTITY: new_qty,
                    ReagentBottleField.BORROWABLE_FLAG: "已借出" if new_qty <= 0 else "可借",
                    ReagentBottleField.BORROWABLE_CHECK: new_qty > 0,
                    ReagentBottleField.LAST_BORROW_TIME: now,
                })

            db.connection.commit()
            logger.info(f"借出工单审批通过: {order['order_number']}")
            return ServiceResult.ok(message=f"工单 {order['order_number']} 已批准，试剂已借出")
        except Exception as e:
            db.connection.rollback()
            logger.error(f"审批借出工单失败: {e}", exception=e)
            return ServiceResult.fail(f"审批失败: {str(e)}")

    def reject_borrow_order(self, order_id: int, approver_id: str) -> ServiceResult:
        """拒绝借出工单"""
        order = self._get_borrow_order(order_id)
        if not order:
            return ServiceResult.fail("工单不存在")
        try:
            db.execute_update(
                "UPDATE borrow_order SET status='已拒绝', approver_id=? WHERE id=?",
                (approver_id, order_id),
            )
            db.execute_update(
                "UPDATE borrow_order_item SET status='已拒绝' WHERE order_id=?", (order_id,)
            )
            logger.info(f"借出工单已拒绝: {order['order_number']}")
            return ServiceResult.ok(message=f"工单 {order['order_number']} 已拒绝")
        except Exception as e:
            logger.error(f"拒绝工单失败: {e}", exception=e)
            return ServiceResult.fail(f"操作失败: {str(e)}")

    def get_pending_borrow_orders(self) -> List[Dict]:
        """获取待审批的借出工单"""
        orders = db.execute_query(
            "SELECT * FROM borrow_order WHERE status='待审批' ORDER BY created_at DESC"
        )
        for o in orders:
            o["items"] = db.execute_query(
                "SELECT * FROM borrow_order_item WHERE order_id=?", (o["id"],)
            )
        return orders

    def get_borrow_orders_by_applicant(self, applicant_id: str) -> List[Dict]:
        """获取某申请人的借出工单"""
        orders = db.execute_query(
            "SELECT * FROM borrow_order WHERE applicant_id=? ORDER BY created_at DESC",
            (applicant_id,)
        )
        for o in orders:
            o["items"] = db.execute_query(
                "SELECT * FROM borrow_order_item WHERE order_id=?", (o["id"],)
            )
        return orders

    def _get_borrow_order(self, order_id: int) -> Optional[Dict]:
        rows = db.execute_query("SELECT * FROM borrow_order WHERE id=?", (order_id,))
        return rows[0] if rows else None

    # ── 还入工单 ──────────────────────────────────────────

    def create_return_order(self, applicant_id: str, applicant_name: str,
                            items: List[Dict], remark: str = "") -> ServiceResult:
        """创建还入工单"""
        if not items:
            return ServiceResult.fail("工单至少需要一项试剂")

        order_number = "RO" + datetime.now().strftime("%Y%m%d%H%M%S") + id_generator.generate_short_id()
        try:
            cursor = db.connection.cursor()
            cursor.execute(
                """INSERT INTO return_order (order_number, applicant_id, applicant_name, status, remark)
                   VALUES (?, ?, ?, '待审批', ?)""",
                (order_number, applicant_id, applicant_name, remark),
            )
            order_id = cursor.lastrowid

            for item in items:
                cursor.execute(
                    """INSERT INTO return_order_item (order_id, bottle_number, return_qty, status)
                       VALUES (?, ?, ?, '待审批')""",
                    (order_id, item["bottle_number"], item["return_qty"]),
                )

            db.connection.commit()
            logger.info(f"还入工单创建成功: {order_number}")
            return ServiceResult.ok(data={"order_id": order_id, "order_number": order_number},
                                    message=f"还入工单 {order_number} 已提交，等待审批")
        except Exception as e:
            db.connection.rollback()
            logger.error(f"创建还入工单失败: {e}", exception=e)
            return ServiceResult.fail(f"创建工单失败: {str(e)}")

    def approve_return_order(self, order_id: int, approver_id: str) -> ServiceResult:
        """审批通过还入工单"""
        order = self._get_return_order(order_id)
        if not order:
            return ServiceResult.fail("工单不存在")
        if order["status"] != "待审批":
            return ServiceResult.fail(f"工单状态为「{order['status']}」，无法审批")

        try:
            cursor = db.connection.cursor()
            now = datetime.now().strftime("%Y/%m/%d %H:%M")

            cursor.execute(
                "UPDATE return_order SET status='已批准', approver_id=?, approved_at=? WHERE id=?",
                (approver_id, now, order_id),
            )
            cursor.execute(
                "UPDATE return_order_item SET status='已批准' WHERE order_id=?", (order_id,)
            )

            items = db.execute_query(
                "SELECT * FROM return_order_item WHERE order_id=?", (order_id,)
            )

            from services.core.reagent_bottle_service import reagent_bottle_service
            from services.core.return_record_service import return_record_service
            from utils.field_mapper import ReagentBottleField

            for item in items:
                bn = item["bottle_number"]
                rqty = item["return_qty"]

                bottle = reagent_bottle_service.get_by_bottle_number(bn)
                if not bottle:
                    continue

                return_num = "RT" + datetime.now().strftime("%Y%m%d%H%M%S") + id_generator.generate_short_id()
                return_record_service.create({
                    "return_number": return_num,
                    "bottle_number": bn,
                    "return_user": order["applicant_name"],
                    "return_time": now,
                    "remaining_quantity": rqty,
                    "last_update_time": now,
                    "modifier": order["applicant_name"],
                })

                reagent_bottle_service.update(bottle.id, {
                    ReagentBottleField.REMAINING_QUANTITY: rqty,
                    ReagentBottleField.BORROWABLE_FLAG: "可借" if rqty > 0 else "耗尽",
                    ReagentBottleField.BORROWABLE_CHECK: rqty > 0,
                    ReagentBottleField.LAST_RETURN_TIME: now,
                })

            db.connection.commit()
            logger.info(f"还入工单审批通过: {order['order_number']}")
            return ServiceResult.ok(message=f"工单 {order['order_number']} 已批准，试剂已归还")
        except Exception as e:
            db.connection.rollback()
            logger.error(f"审批还入工单失败: {e}", exception=e)
            return ServiceResult.fail(f"审批失败: {str(e)}")

    def reject_return_order(self, order_id: int, approver_id: str) -> ServiceResult:
        """拒绝还入工单"""
        order = self._get_return_order(order_id)
        if not order:
            return ServiceResult.fail("工单不存在")
        try:
            db.execute_update(
                "UPDATE return_order SET status='已拒绝', approver_id=? WHERE id=?",
                (approver_id, order_id),
            )
            db.execute_update(
                "UPDATE return_order_item SET status='已拒绝' WHERE order_id=?", (order_id,)
            )
            return ServiceResult.ok(message=f"工单 {order['order_number']} 已拒绝")
        except Exception as e:
            logger.error(f"拒绝工单失败: {e}", exception=e)
            return ServiceResult.fail(f"操作失败: {str(e)}")

    def get_pending_return_orders(self) -> List[Dict]:
        """获取待审批的还入工单"""
        orders = db.execute_query(
            "SELECT * FROM return_order WHERE status='待审批' ORDER BY created_at DESC"
        )
        for o in orders:
            o["items"] = db.execute_query(
                "SELECT * FROM return_order_item WHERE order_id=?", (o["id"],)
            )
        return orders

    def _get_return_order(self, order_id: int) -> Optional[Dict]:
        rows = db.execute_query("SELECT * FROM return_order WHERE id=?", (order_id,))
        return rows[0] if rows else None


# 全局单例
work_order_service = WorkOrderService()