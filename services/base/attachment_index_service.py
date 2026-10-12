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


# 全局实例
attachment_index_service = AttachmentIndexService()
