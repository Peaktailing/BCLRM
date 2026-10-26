"""调拨单数据服务（表：transfer_order / transfer_order_item）

只做 SQL 与事务，不判「该不该同意」——那是 ``domain/transfer.py`` 与
``business/transfer_service.py`` 的事。这里唯一的判断是 CAS：

    同意 = UPDATE ... WHERE id = ? AND status = '待点头'

``rowcount = 0`` 表示这张单已经被别人处理过（或状态变了），不是错误，
是「你来晚了」——页面据此提示重看，而不是把状态覆盖一遍。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Sequence

from db.base_service import BaseService
from db.database import db
from domain.transfer import (
    ITEM_ACCEPTED,
    ITEM_DECLINED,
    ITEM_FAILED,
    ITEM_PENDING,
    TRANSFER_ACCEPTED,
    TRANSFER_CANCELLED,
    TRANSFER_OPEN_STATUSES,
    TRANSFER_REQUESTED,
)
from models.core.transfer_order import TransferOrder, TransferOrderItem
from utils.error_handler import logger


class _AlreadyAnswered(Exception):
    """CAS 没抢到：这张单已经被处理过。用来跳出事务，不写任何东西。"""


class _NothingApplied(Exception):
    """一瓶都没转成：整单回滚，宁可报失败也不留一张空生效的单。"""


class TransferOrderService(BaseService):
    """调拨单服务"""

    def __init__(self, database=None):
        super().__init__("transfer_order", database)
        logger.info("调拨单服务初始化完成")

    # ---------------------------------------------------------------- 查询
    def get_by_number(self, transfer_number: str) -> Optional[TransferOrder]:
        record = self.get_by_field("transfer_number", transfer_number)
        return self._parse(record) if record else None

    def get(self, transfer_id: int) -> Optional[TransferOrder]:
        record = self.get_by_id(int(transfer_id))
        if not record:
            return None
        order = self._parse(record)
        order.items = self.items_of(transfer_id)
        return order

    def items_of(self, transfer_id: int) -> List[TransferOrderItem]:
        rows = self.db.execute_query(
            "SELECT * FROM transfer_order_item WHERE transfer_id = ? ORDER BY line_no, id",
            (int(transfer_id),),
        )
        return [self._parse_item(row) for row in rows]

    def list_open(self) -> List[TransferOrder]:
        """全院在办（待发送 + 待点头），最新在前。"""
        placeholders = ", ".join("?" for _ in TRANSFER_OPEN_STATUSES)
        rows = self.db.execute_query(
            f"SELECT * FROM transfer_order WHERE status IN ({placeholders}) "
            "ORDER BY id DESC",
            tuple(TRANSFER_OPEN_STATUSES),
        )
        return [self._parse(row) for row in rows]

    def list_pending_for(self, manager: str) -> List[TransferOrder]:
        """等我点头的（出料人是我）。"""
        rows = self.db.execute_query(
            "SELECT * FROM transfer_order WHERE from_manager = ? AND status = ? "
            "ORDER BY id",
            ((manager or "").strip(), TRANSFER_REQUESTED),
        )
        return [self._parse(row) for row in rows]

    def list_mine(self, manager: str, include_closed: bool = False) -> List[TransferOrder]:
        """我发起过的（不管出料人是谁）。"""
        if include_closed:
            rows = self.db.execute_query(
                "SELECT * FROM transfer_order WHERE requested_by = ? ORDER BY id DESC",
                ((manager or "").strip(),),
            )
        else:
            placeholders = ", ".join("?" for _ in TRANSFER_OPEN_STATUSES)
            rows = self.db.execute_query(
                f"SELECT * FROM transfer_order WHERE requested_by = ? "
                f"AND status IN ({placeholders}) ORDER BY id DESC",
                ((manager or "").strip(),) + tuple(TRANSFER_OPEN_STATUSES),
            )
        return [self._parse(row) for row in rows]

    # ---------------------------------------------------------------- 建单
    def create_order(
        self,
        from_manager: str,
        to_manager: str,
        lines: Sequence[Dict[str, Any]],
        requested_by: str,
        reason: str,
        origin_kind: str = "",
        origin_ref: str = "",
        note: str = "",
        status: str = TRANSFER_REQUESTED,
        forced: bool = False,
    ) -> Optional[TransferOrder]:
        """建单 + 明细，一个事务。

        ``lines`` 每项：``lot_id / substance_key / cas_number / display_name /
        quantity / unit / note``。空明细直接拒绝——没有明细的单点不了头。
        """
        lines = [line for line in lines if line]
        if not lines:
            return None
        number = self.next_number()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with db.transaction():
            transfer_id = self.create(
                {
                    "transfer_number": number,
                    "from_manager": (from_manager or "").strip(),
                    "to_manager": (to_manager or "").strip(),
                    "reason": reason,
                    "origin_kind": origin_kind,
                    "origin_ref": origin_ref,
                    "status": status,
                    "requested_by": (requested_by or "").strip(),
                    "requested_at": now,
                    "forced": 1 if forced else 0,
                    "note": note,
                }
            )
            if not transfer_id:
                raise RuntimeError("调拨单建单失败")
            for index, line in enumerate(lines):
                db.execute_insert(
                    "INSERT INTO transfer_order_item (transfer_id, line_no, lot_id, "
                    "substance_key, cas_number, display_name, quantity, unit, "
                    "line_status, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        transfer_id,
                        index,
                        line.get("lot_id") or "",
                        line.get("substance_key") or "",
                        line.get("cas_number") or "",
                        line.get("display_name") or "",
                        float(line.get("quantity") or 0),
                        line.get("unit") or "",
                        ITEM_PENDING,
                        line.get("note") or "",
                    ),
                )
        logger.info(
            f"调拨单已建 {number}：{from_manager} → {to_manager}，{len(lines)} 瓶"
        )
        return self.get(transfer_id)

    # ---------------------------------------------------------------- 回答
    def commit_answer(
        self,
        transfer_id: int,
        accepted_indexes: Iterable[int],
        declined_indexes: Iterable[int],
        respondent: str,
        remark: str = "",
        status: str = TRANSFER_ACCEPTED,
        forced: bool = False,
        apply_line=None,
    ) -> Dict[str, Any]:
        """记录点头结果 + 逐瓶落实保管权，**同一个事务**。

        ``apply_line`` 是「把这一瓶的保管权转过去」的回调（业务层传进来，
        内部调 ``manager_service.transfer``），返回 ``(成功, 原因)``。某一瓶
        失败**不回滚整单**——那一瓶被借走了，是合法的部分成功，只把它标成
        「执行失败」，其余照常生效；把整单回滚会让刚点完的头白点。

        但**一瓶都没转成时要整单回滚**：留下「已同意」却没有任何一瓶易主的
        单，比拒绝更糟——账面上生效了，实际没人拿到料，事后谁也说不清。

        为什么事务在这里而不是业务层：``business`` 不许直接碰 ``db``（分层
        规则），而「改单据状态」与「改瓶的管理人」必须一起成立或一起不成立。

        Returns:
            ``{"ok": bool, "applied": [...], "failed": [...], "late": bool,
            "all_failed": bool}``；``late`` 表示 CAS 没抢到（单已被处理）。
        """
        result: Dict[str, Any] = {
            "ok": False, "applied": [], "failed": [], "late": False, "all_failed": False,
        }
        payload = self._answer_fields(status, respondent, remark, forced)
        try:
            with db.transaction():
                self._answer_writes(
                    int(transfer_id),
                    [int(i) for i in accepted_indexes],
                    [int(i) for i in declined_indexes],
                    payload,
                    apply_line,
                    result,
                )
        except _AlreadyAnswered:
            return result
        except _NothingApplied:
            result["all_failed"] = True
            return result
        return result

    def _answer_fields(
        self, status: str, respondent: str, remark: str, forced: bool
    ) -> Dict[str, Any]:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        fields: Dict[str, Any] = {
            "status": status,
            "respondent": (respondent or "").strip(),
            "answered_at": now,
            "answer_remark": remark or "",
        }
        if status == TRANSFER_ACCEPTED:
            fields["executed_at"] = now
        if forced:
            fields["forced"] = 1
        return fields

    def _answer_writes(
        self,
        transfer_id: int,
        accepted: List[int],
        declined: List[int],
        fields: Dict[str, Any],
        apply_line,
        result: Dict[str, Any],
    ) -> None:
        assignments = ", ".join(f"{key} = ?" for key in fields)
        changed = db.execute_update(
            f"UPDATE transfer_order SET {assignments} WHERE id = ? AND status = ?",
            tuple(fields.values()) + (transfer_id, TRANSFER_REQUESTED),
        )
        if not changed:
            # CAS 没抢到：单已被别人处理（同一张单只有出料人能点，通常是
            # 双击，或超管代签撞上）。一行都不写，让调用方提示刷新。
            result["late"] = True
            raise _AlreadyAnswered()

        items = {item.line_no: item for item in self.items_of(transfer_id)}
        for index in declined:
            db.execute_update(
                "UPDATE transfer_order_item SET line_status = ? "
                "WHERE transfer_id = ? AND line_no = ?",
                (ITEM_DECLINED, transfer_id, index),
            )
        for index in accepted:
            item = items.get(index)
            if item is None:
                continue
            ok, reason = (True, "")
            if apply_line is not None:
                ok, reason = apply_line(item)
            if ok:
                db.execute_update(
                    "UPDATE transfer_order_item SET line_status = ? "
                    "WHERE transfer_id = ? AND line_no = ?",
                    (ITEM_ACCEPTED, transfer_id, index),
                )
                result["applied"].append(item.lot_id)
            else:
                db.execute_update(
                    "UPDATE transfer_order_item SET line_status = ?, note = ? "
                    "WHERE transfer_id = ? AND line_no = ?",
                    (ITEM_FAILED, reason or "", transfer_id, index),
                )
                result["failed"].append({"lot_id": item.lot_id, "reason": reason})
        if apply_line is not None and not result["applied"] and result["failed"]:
            raise _NothingApplied()
        result["ok"] = True

    def mark_item_failed(self, transfer_id: int, line_no: int, reason: str = "") -> bool:
        """点了头但这一瓶没转成（被借走 / 瓶不存在）。"""
        return db.execute_update(
            "UPDATE transfer_order_item SET line_status = ?, note = ? "
            "WHERE transfer_id = ? AND line_no = ?",
            (ITEM_FAILED, reason or "", int(transfer_id), int(line_no)),
        ) > 0

    def cancel(self, transfer_id: int, operator: str, remark: str = "") -> bool:
        """撤回（只有还没被点头的能被撤回）。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return db.execute_update(
            "UPDATE transfer_order SET status = ?, respondent = ?, "
            "answered_at = ?, answer_remark = ? WHERE id = ? AND status = ?",
            (
                TRANSFER_CANCELLED,
                (operator or "").strip(),
                now,
                remark or "",
                int(transfer_id),
                TRANSFER_REQUESTED,
            ),
        ) > 0

    def mark_picked_up(self, transfer_id: int, when: str = "") -> bool:
        """实物取走（可选，不阻断流程：账上生效与实物到位是两件事）。"""
        return db.execute_update(
            "UPDATE transfer_order SET picked_up_at = ? WHERE id = ?",
            (when or datetime.now().strftime("%Y-%m-%d %H:%M:%S"), int(transfer_id)),
        ) > 0

    # ---------------------------------------------------------------- 编号
    @staticmethod
    def next_number() -> str:
        """``TR`` + 时间戳（微秒级）。与借出单 ``BO`` 同一种做法：不查表计数，
        并发下也不会撞号——撞号的代价是重试，查表计数的代价是加锁。"""
        return "TR" + datetime.now().strftime("%Y%m%d%H%M%S%f")

    # ---------------------------------------------------------------- 解析
    @staticmethod
    def _parse(record: Dict[str, Any]) -> TransferOrder:
        return TransferOrder(
            id=record.get("id"),
            transfer_number=record.get("transfer_number"),
            from_manager=record.get("from_manager"),
            to_manager=record.get("to_manager"),
            reason=record.get("reason"),
            origin_kind=record.get("origin_kind"),
            origin_ref=record.get("origin_ref"),
            status=record.get("status"),
            requested_by=record.get("requested_by"),
            requested_at=record.get("requested_at"),
            respondent=record.get("respondent"),
            answered_at=record.get("answered_at"),
            answer_remark=record.get("answer_remark"),
            executed_at=record.get("executed_at"),
            forced=record.get("forced") or 0,
            picked_up_at=record.get("picked_up_at"),
            note=record.get("note"),
            created_at=record.get("created_at"),
        )

    @staticmethod
    def _parse_item(record: Dict[str, Any]) -> TransferOrderItem:
        return TransferOrderItem(
            id=record.get("id"),
            transfer_id=record.get("transfer_id"),
            line_no=record.get("line_no"),
            lot_id=record.get("lot_id"),
            substance_key=record.get("substance_key"),
            cas_number=record.get("cas_number"),
            display_name=record.get("display_name"),
            quantity=record.get("quantity"),
            unit=record.get("unit"),
            line_status=record.get("line_status"),
            note=record.get("note"),
        )


transfer_order_service = TransferOrderService()

__all__ = ["TransferOrderService", "transfer_order_service"]
