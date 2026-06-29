"""人员管理服务

提供用户认证、CRUD、用户-管理员关联等功能。
"""
from typing import Optional, List, Dict
from db.base_service import BaseService
from db.database import db
from utils.error_handler import logger


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

    def create_user(self, data: dict) -> Optional[int]:
        """创建用户"""
        try:
            return self.db.execute_insert(
                """INSERT INTO person
                   (user_id, name, password, role, department, phone,
                    student_or_work_id, display_name)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    data.get("user_id"),
                    data.get("name"),
                    data.get("password", "123456"),
                    data.get("role", "student"),
                    data.get("department", ""),
                    data.get("phone", ""),
                    data.get("student_or_work_id", ""),
                    data.get("display_name", data.get("name")),
                ),
            )
        except Exception as e:
            logger.error(f"创建用户失败: {e}", exception=e)
            return None

    def delete_user(self, user_id: str) -> bool:
        """删除用户"""
        try:
            self.db.execute_update("DELETE FROM person WHERE user_id = ?", (user_id,))
            return True
        except Exception as e:
            logger.error(f"删除用户失败: {e}")
            return False

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