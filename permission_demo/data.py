"""数据访问层 - 封装对 SQLite 数据库的 CRUD 操作"""

from typing import Optional
from models import get_connection, User, ReagentBottle, BorrowRecord
from datetime import datetime


# ── 用户操作 ──────────────────────────────────────────────


def get_user(username: str) -> Optional[User]:
    """根据用户名获取用户"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE name = ?", (username,)).fetchone()
    conn.close()
    if row:
        return User(**dict(row))
    return None


def get_all_users() -> list[User]:
    """获取所有用户"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [User(**dict(r)) for r in rows]


def get_users_by_role(role: str) -> list[User]:
    """按角色获取用户列表"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM users WHERE role = ? ORDER BY id", (role,)
    ).fetchall()
    conn.close()
    return [User(**dict(r)) for r in rows]


def add_user(name: str, role: str, display_name: str = "", department: str = "") -> bool:
    """添加用户"""
    conn = get_connection()
    try:
        conn.execute(
            "INSERT INTO users (name, role, display_name, department) VALUES (?, ?, ?, ?)",
            (name, role, display_name or name, department),
        )
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


def delete_user(user_id: int) -> bool:
    """删除用户"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
        conn.commit()
        return True
    except Exception:
        return False
    finally:
        conn.close()


# ── 试剂瓶操作 ────────────────────────────────────────────


def get_all_bottles() -> list[ReagentBottle]:
    """获取所有试剂瓶"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM reagent_bottles ORDER BY bottle_number").fetchall()
    conn.close()
    return [ReagentBottle(**dict(r)) for r in rows]


def get_bottles_by_creator(creator: str) -> list[ReagentBottle]:
    """获取某创建者的试剂瓶"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM reagent_bottles WHERE creator = ? ORDER BY bottle_number",
        (creator,),
    ).fetchall()
    conn.close()
    return [ReagentBottle(**dict(r)) for r in rows]


def get_bottle_by_number(bottle_number: int) -> Optional[ReagentBottle]:
    """按瓶号获取试剂瓶"""
    conn = get_connection()
    row = conn.execute(
        "SELECT * FROM reagent_bottles WHERE bottle_number = ?", (bottle_number,)
    ).fetchone()
    conn.close()
    if row:
        return ReagentBottle(**dict(row))
    return None


def add_bottle(
    bottle_number: int,
    reagent_name: str,
    cas_number: str,
    specification: str,
    quantity: float,
    unit: str,
    storage_location: str,
    creator: str,
    is_controlled: bool = False,
) -> bool:
    """添加试剂瓶"""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO reagent_bottles
               (bottle_number, reagent_name, cas_number, specification, quantity, unit,
                storage_location, creator, is_controlled)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (bottle_number, reagent_name, cas_number, specification, quantity,
             unit, storage_location, creator, 1 if is_controlled else 0),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"添加试剂瓶失败: {e}")
        return False
    finally:
        conn.close()


def update_bottle(
    bottle_number: int,
    reagent_name: str = None,
    cas_number: str = None,
    specification: str = None,
    quantity: float = None,
    storage_location: str = None,
) -> bool:
    """更新试剂瓶信息（仅更新提供的字段）"""
    conn = get_connection()
    try:
        fields = []
        params = []
        for key, val in [
            ("reagent_name", reagent_name),
            ("cas_number", cas_number),
            ("specification", specification),
            ("quantity", quantity),
            ("storage_location", storage_location),
        ]:
            if val is not None:
                fields.append(f"{key} = ?")
                params.append(val)
        if not fields:
            return True
        params.append(bottle_number)
        conn.execute(
            f"UPDATE reagent_bottles SET {', '.join(fields)} WHERE bottle_number = ?",
            params,
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"更新试剂瓶失败: {e}")
        return False
    finally:
        conn.close()


def delete_bottle(bottle_number: int) -> bool:
    """删除试剂瓶"""
    conn = get_connection()
    try:
        conn.execute("DELETE FROM reagent_bottles WHERE bottle_number = ?", (bottle_number,))
        conn.commit()
        return True
    except Exception as e:
        print(f"删除试剂瓶失败: {e}")
        return False
    finally:
        conn.close()


# ── 借还记录操作 ──────────────────────────────────────────


def get_all_borrow_records() -> list[BorrowRecord]:
    """获取所有借还记录"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM borrow_records ORDER BY id DESC"
    ).fetchall()
    conn.close()
    return [BorrowRecord(**dict(r)) for r in rows]


def get_borrow_records_by_borrower(borrower: str) -> list[BorrowRecord]:
    """获取某借用人的记录"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM borrow_records WHERE borrower = ? ORDER BY id DESC",
        (borrower,),
    ).fetchall()
    conn.close()
    return [BorrowRecord(**dict(r)) for r in rows]


def get_pending_borrows() -> list[BorrowRecord]:
    """获取待审批的借出记录"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM borrow_records WHERE status = '待审批' ORDER BY borrow_time"
    ).fetchall()
    conn.close()
    return [BorrowRecord(**dict(r)) for r in rows]


def create_borrow_record(
    record_number: str,
    bottle_number: int,
    reagent_name: str,
    borrower: str,
    quantity: float,
) -> bool:
    """创建借出申请记录"""
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO borrow_records
               (record_number, bottle_number, reagent_name, borrower, quantity, status)
               VALUES (?, ?, ?, ?, ?, '待审批')""",
            (record_number, bottle_number, reagent_name, borrower, quantity),
        )
        conn.commit()
        return True
    except Exception as e:
        print(f"创建借出记录失败: {e}")
        return False
    finally:
        conn.close()


def approve_borrow(record_id: int, approver: str, approved: bool) -> bool:
    """审批借出申请"""
    conn = get_connection()
    try:
        status = "已批准" if approved else "已拒绝"
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn.execute(
            "UPDATE borrow_records SET status = ?, approver = ?, approve_time = ? WHERE id = ?",
            (status, approver, now, record_id),
        )
        conn.commit()

        if approved:
            # 通过时更新试剂瓶数量（扣减）
            record = conn.execute(
                "SELECT bottle_number, quantity FROM borrow_records WHERE id = ?",
                (record_id,),
            ).fetchone()
            if record:
                conn.execute(
                    "UPDATE reagent_bottles SET quantity = quantity - ? WHERE bottle_number = ?",
                    (record["quantity"], record["bottle_number"]),
                )
                conn.commit()
        return True
    except Exception as e:
        print(f"审批失败: {e}")
        return False
    finally:
        conn.close()


def get_next_bottle_number() -> int:
    """获取下一个可用的试剂瓶号"""
    conn = get_connection()
    row = conn.execute("SELECT MAX(bottle_number) as max_bn FROM reagent_bottles").fetchone()
    conn.close()
    return (row["max_bn"] or 1000) + 1


def get_next_record_number() -> str:
    """生成下一个借出记录编号"""
    now = datetime.now()
    date_prefix = now.strftime("%Y%m%d")
    conn = get_connection()
    row = conn.execute(
        "SELECT COUNT(*) as cnt FROM borrow_records WHERE record_number LIKE ?",
        (f"BR{date_prefix}%",),
    ).fetchone()
    conn.close()
    seq = (row["cnt"] or 0) + 1
    return f"BR{date_prefix}{seq:04d}"