"""人员管理服务

提供用户认证、CRUD、用户-管理员关联等功能。
"""
from typing import Optional, List, Dict
from db.base_service import BaseService
from db.database import db
from utils.error_handler import logger
from business.password_validator import validate_password_strength, validate_phone
from utils.password_hash import hash_password, verify_password


class PersonService(BaseService):
    """人员管理服务"""

    def __init__(self):
        super().__init__("person", db)

    # ── 认证 ──────────────────────────────────────────────

    def authenticate(self, work_id: str, password: str) -> Optional[Dict]:
        """工号+密码认证（密码哈希验证）"""
        try:
            results = self.db.execute_query(
                "SELECT * FROM person WHERE student_or_work_id = ?",
                (work_id.strip(),),
            )
            if not results:
                return None
            user = results[0]
            stored_pwd = user.get("password", "")
            if verify_password(password, stored_pwd):
                return user
            return None
        except Exception as e:
            logger.error(f"认证失败: {e}", exception=e)
            return None

    def get_by_user_id(self, user_id: str) -> Optional[Dict]:
        return self.get_by_field("user_id", user_id)

    def get_by_work_id(self, work_id: str) -> Optional[Dict]:
        return self.get_by_field("student_or_work_id", work_id)

    # ── 用户-管理员关联 ──────────────────────────────────

    def get_admin_ids(self, user_id: str) -> List[str]:
        rows = self.db.execute_query(
            "SELECT admin_id FROM user_admin WHERE user_id = ?", (user_id,)
        )
        return [r["admin_id"] for r in rows]

    def get_admins_for_user(self, user_id: str) -> List[Dict]:
        admin_ids = self.get_admin_ids(user_id)
        if not admin_ids:
            return []
        placeholders = ",".join(["?" for _ in admin_ids])
        return self.db.execute_query(
            f"SELECT * FROM person WHERE user_id IN ({placeholders})", admin_ids
        )

    def get_users_for_admin(self, admin_id: str) -> List[Dict]:
        rows = self.db.execute_query(
            "SELECT user_id FROM user_admin WHERE admin_id = ?", (admin_id,)
        )
        user_ids = [r["user_id"] for r in rows]
        if not user_ids:
            return []
        placeholders = ",".join(["?" for _ in user_ids])
        return self.db.execute_query(
            f"SELECT * FROM person WHERE user_id IN ({placeholders})", user_ids
        )

    def add_admin_relation(self, user_id: str, admin_id: str) -> bool:
        try:
            self.db.execute_insert(
                "INSERT OR IGNORE INTO user_admin (user_id, admin_id) VALUES (?, ?)",
                (user_id, admin_id),
            )
            return True
        except Exception as e:
            logger.error(f"添加关联失败: {e}")
            return False

    def remove_admin_relation(self, user_id: str, admin_id: str) -> bool:
        try:
            self.db.execute_update(
                "DELETE FROM user_admin WHERE user_id = ? AND admin_id = ?",
                (user_id, admin_id),
            )
            return True
        except Exception as e:
            logger.error(f"移除关联失败: {e}")
            return False

    # ── 用户 CRUD ─────────────────────────────────────────

    def create_user(self, data: dict) -> tuple:
        """创建用户（带校验，密码哈希存储）"""
        phone = data.get("phone", "")
        if phone:
            valid, msg = validate_phone(phone)
            if not valid:
                return False, f"手机号校验失败: {msg}", None

        password = data.get("password", "")
        if not password:
            return False, "密码不能为空", None
        valid, msg = validate_password_strength(password)
        if not valid:
            return False, f"密码校验失败: {msg}", None

        work_id = data.get("student_or_work_id", "")
        if work_id and self.get_by_work_id(work_id):
            return False, f"工号 {work_id} 已存在", None

        user_id = data.get("user_id", "")
        if user_id and self.get_by_user_id(user_id):
            return False, f"用户ID {user_id} 已存在", None

        try:
            new_id = self.db.execute_insert(
                """INSERT INTO person
                   (user_id, name, password, role, department, phone,
                    student_or_work_id, display_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    user_id,
                    data.get("name"),
                    hash_password(password),
                    data.get("role", "student"),
                    data.get("department", ""),
                    phone,
                    work_id,
                    data.get("display_name", data.get("name")),
                ),
            )
            return True, "用户创建成功", new_id
        except Exception as e:
            logger.error(f"创建用户失败: {e}", exception=e)
            return False, f"创建用户失败: {str(e)}", None

    def update_user(self, user_id: str, data: dict) -> tuple:
        """更新用户信息（带校验，密码哈希存储）"""
        user = self.get_by_user_id(user_id)
        if not user:
            return False, f"用户 {user_id} 不存在"

        phone = data.get("phone")
        if phone is not None and phone:
            valid, msg = validate_phone(phone)
            if not valid:
                return False, f"手机号校验失败: {msg}"

        password = data.get("password")
        if password is not None and password:
            valid, msg = validate_password_strength(password)
            if not valid:
                return False, f"密码校验失败: {msg}"

        new_work_id = data.get("student_or_work_id")
        if new_work_id and new_work_id != user.get("student_or_work_id"):
            existing = self.get_by_work_id(new_work_id)
            if existing and existing.get("user_id") != user_id:
                return False, f"工号 {new_work_id} 已被其他用户使用"

        allowed_fields = ["name", "role", "department", "phone",
                          "student_or_work_id", "display_name", "password"]
        update_fields = {}
        for k, v in data.items():
            if k in allowed_fields and v is not None:
                if k == "password":
                    update_fields[k] = hash_password(v)
                else:
                    update_fields[k] = v

        if not update_fields:
            return False, "没有需要更新的字段"

        try:
            success = self.update_by_field("user_id", user_id, update_fields)
            if success:
                return True, "用户信息更新成功"
            return False, "更新用户信息失败"
        except Exception as e:
            logger.error(f"更新用户失败: {e}", exception=e)
            return False, f"更新用户失败: {str(e)}"

    def delete_user(self, user_id: str) -> tuple:
        user = self.get_by_user_id(user_id)
        if not user:
            return False, f"用户 {user_id} 不存在"
        try:
            self.db.execute_update("DELETE FROM person WHERE user_id = ?", (user_id,))
            return True, f"用户 {user.get('display_name', user.get('name'))} 已删除"
        except Exception as e:
            logger.error(f"删除用户失败: {e}", exception=e)
            return False, f"删除用户失败: {str(e)}"

    def get_all_users(self) -> List[Dict]:
        return self.get_all(order_by="user_id")

    def get_users_by_role(self, role: str) -> List[Dict]:
        return self.db.execute_query(
            "SELECT * FROM person WHERE role = ? ORDER BY user_id", (role,)
        )


# 全局单例
person_service = PersonService()