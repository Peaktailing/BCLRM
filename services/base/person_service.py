"""人员管理服务

提供用户认证、CRUD、用户-管理员关联等功能。
"""
from typing import Optional, List, Dict
from db.base_service import BaseService
from db.database import db
from utils.error_handler import logger
from business.password_validator import validate_password_strength, validate_phone


class PersonService(BaseService):
    """人员管理服务"""

    def __init__(self):
        super().__init__("person", db)

    # ── 认证 ──────────────────────────────────────────────

    def authenticate(self, work_id: str, password: str) -> Optional[Dict]:
        """工号+密码认证

        Args:
            work_id: 工号/学号
            password: 密码

        Returns:
            用户字典或 None
        """
        try:
            results = self.db.execute_query(
                "SELECT * FROM person WHERE student_or_work_id = ? AND password = ?",
                (work_id.strip(), password),
            )
            return results[0] if results else None
        except Exception as e:
            logger.error(f"认证失败: {e}", exception=e)
            return None

    def get_by_user_id(self, user_id: str) -> Optional[Dict]:
        """根据 user_id 获取用户"""
        return self.get_by_field("user_id", user_id)

    def get_by_work_id(self, work_id: str) -> Optional[Dict]:
        """根据工号获取用户"""
        return self.get_by_field("student_or_work_id", work_id)

    # ── 用户-管理员关联 ──────────────────────────────────

    def get_admin_ids(self, user_id: str) -> List[str]:
        """获取某用户从属的管理员 user_id 列表"""
        rows = self.db.execute_query(
            "SELECT admin_id FROM user_admin WHERE user_id = ?", (user_id,)
        )
        return [r["admin_id"] for r in rows]

    def get_admins_for_user(self, user_id: str) -> List[Dict]:
        """获取某用户从属的管理员详细信息"""
        admin_ids = self.get_admin_ids(user_id)
        if not admin_ids:
            return []
        placeholders = ",".join(["?" for _ in admin_ids])
        return self.db.execute_query(
            f"SELECT * FROM person WHERE user_id IN ({placeholders})", admin_ids
        )

    def get_users_for_admin(self, admin_id: str) -> List[Dict]:
        """获取某管理员管辖的用户"""
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
        """添加用户-管理员关联"""
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
        """移除用户-管理员关联"""
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
        """创建用户（带校验）

        Args:
            data: 用户数据字典，需包含 user_id, name, password, role, student_or_work_id

        Returns:
            (success: bool, message: str, user_id: Optional[int])
        """
        # 校验手机号
        phone = data.get("phone", "")
        if phone:
            valid, msg = validate_phone(phone)
            if not valid:
                return False, f"手机号校验失败: {msg}", None

        # 校验密码强度
        password = data.get("password", "")
        if not password:
            return False, "密码不能为空", None
        valid, msg = validate_password_strength(password)
        if not valid:
            return False, f"密码校验失败: {msg}", None

        # 校验工号唯一性
        work_id = data.get("student_or_work_id", "")
        if work_id and self.get_by_work_id(work_id):
            return False, f"工号 {work_id} 已存在", None

        # 校验 user_id 唯一性
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
                    password,
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
        """更新用户信息（带校验）

        Args:
            user_id: 用户唯一标识
            data: 要更新的字段字典，可包含 name, role, department, phone,
                  student_or_work_id, display_name, password

        Returns:
            (success: bool, message: str)
        """
        user = self.get_by_user_id(user_id)
        if not user:
            return False, f"用户 {user_id} 不存在"

        # 校验手机号
        phone = data.get("phone")
        if phone is not None and phone:
            valid, msg = validate_phone(phone)
            if not valid:
                return False, f"手机号校验失败: {msg}"

        # 校验密码强度
        password = data.get("password")
        if password is not None and password:
            valid, msg = validate_password_strength(password)
            if not valid:
                return False, f"密码校验失败: {msg}"

        # 校验工号唯一性
        new_work_id = data.get("student_or_work_id")
        if new_work_id and new_work_id != user.get("student_or_work_id"):
            existing = self.get_by_work_id(new_work_id)
            if existing and existing.get("user_id") != user_id:
                return False, f"工号 {new_work_id} 已被其他用户使用"

        # 只更新提供的字段
        allowed_fields = ["name", "role", "department", "phone",
                          "student_or_work_id", "display_name", "password"]
        update_fields = {}
        for k, v in data.items():
            if k in allowed_fields and v is not None:
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
        """删除用户

        Returns:
            (success: bool, message: str)
        """
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
        """获取所有用户"""
        return self.get_all(order_by="user_id")

    def get_users_by_role(self, role: str) -> List[Dict]:
        """按角色获取用户"""
        return self.db.execute_query(
            "SELECT * FROM person WHERE role = ? ORDER BY user_id", (role,)
        )


# 全局单例
person_service = PersonService()