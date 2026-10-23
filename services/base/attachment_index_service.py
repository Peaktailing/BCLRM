"""附件索引服务（attach_cold.db，四库分离）

仅管理附件元数据索引；物理文件存放在 attachments/ 目录，
由 utils/attachment_store.py 负责读写。
"""
from typing import Optional

from db.base_service import BaseService
from db.database import init_attach_db
from utils.error_handler import logger


class AttachmentIndexService(BaseService):
    """附件索引表服务（独立附件索引库）"""

    def __init__(self):
        super().__init__("attachment_index", db=init_attach_db())

    def get_by_stored_name(self, stored_name: str) -> Optional[dict]:
        """按存储文件名查询索引"""
        return self.get_by_field("stored_name", stored_name)

    def delete_by_stored_name(self, stored_name: str) -> bool:
        """按存储文件名删除索引"""
        return self.delete_by_field("stored_name", stored_name)

    def list_by_ref(
        self, ref_type: str, ref_id: str, category: str = ""
    ) -> list:
        """按业务关联取附件（新→旧）。

        取证照片挂在工单上，页面要「这张单拍了几张」就得反查。``category``
        用来区分阶段（借出 / 归还），空串表示这一单的全部。
        """
        if not ref_type or not ref_id:
            return []
        sql = (
            "SELECT * FROM attachment_index "
            "WHERE ref_type = ? AND ref_id = ?"
        )
        params: list = [ref_type, ref_id]
        if category:
            sql += " AND category = ?"
            params.append(category)
        sql += " ORDER BY id DESC"
        try:
            return self.db.execute_query(sql, tuple(params))
        except Exception as exc:  # 附件库未初始化等
            logger.warning(f"按关联查询附件失败：{exc}")
            return []

    def count_by_ref(self, ref_type: str, ref_id: str, category: str = "") -> int:
        return len(self.list_by_ref(ref_type, ref_id, category))


# 全局实例
attachment_index_service = AttachmentIndexService()
