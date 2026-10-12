"""附件物理存储管理（MSDS 等文件的真实存取）

分层约定：
- 物理文件：attachments/<category>/ 目录，文件名加随机前缀防猜测/防重名
- 索引元数据：attach_cold.db 的 attachment_index 表（services/base/attachment_index_service）
- 页面层只调用本模块，不直接操作文件系统与附件库

安全措施：
- os.path.basename 剥离路径组件，防止路径遍历
- resolve 后校验必须位于附件根目录内
- 扩展名白名单 + 大小上限校验
"""
import os
import uuid
from pathlib import Path
from typing import Optional

from config.settings import ATTACHMENTS_DIR
from utils.error_handler import logger

# 注意：attachment_index_service 在函数内延迟导入。
# 模块级导入会触发 services/__init__ → business/__init__ 循环链
# （services.core.reagent_bottle_service 反向依赖 business.bottle_state）。


class AttachmentStore:
    """附件存取封装类"""

    def __init__(self, base_dir: str = ATTACHMENTS_DIR):
        self.base_dir = Path(base_dir)

    # ------------------------------------------------------------------
    # 路径安全
    # ------------------------------------------------------------------
    def _resolve(self, stored_name: str) -> Path:
        """将存储文件名解析为绝对路径，并校验未逃逸出附件根目录

        Args:
            stored_name: 存储文件名（含随机前缀）

        Returns:
            绝对路径

        Raises:
            ValueError: 文件名非法或试图逃逸附件根目录
        """
        if not stored_name:
            raise ValueError("文件名为空")
        # 剥离路径组件，仅保留文件名
        safe_name = os.path.basename(stored_name)
        if not safe_name or safe_name != stored_name:
            raise ValueError(f"非法文件名: {stored_name}")
        root = self.base_dir.resolve()
        target = (self.base_dir / safe_name).resolve()
        # 防目录穿越：目标必须位于附件根目录内
        if root not in target.parents:
            raise ValueError("非法文件路径")
        return target

    # ------------------------------------------------------------------
    # 核心操作
    # ------------------------------------------------------------------
    def save(
        self,
        uploaded_file,
        category: str = "msds",
        allowed_exts: Optional[list] = None,
        max_mb: int = 10,
        ref_type: Optional[str] = None,
        ref_id: Optional[str] = None,
    ) -> Optional[str]:
        """保存上传文件并登记索引

        Args:
            uploaded_file: Streamlit UploadedFile 对象，None 时返回 None
            category: 附件分类子目录（如 msds）
            allowed_exts: 允许的扩展名白名单，None 表示不限制
            max_mb: 大小上限（MB）
            ref_type: 关联业务类型（如 chemical）
            ref_id: 关联业务标识（如 化学品名称/ID）

        Returns:
            存储文件名（数据库存此值），无文件返回 None

        Raises:
            ValueError: 扩展名不合法或超过大小限制
        """
        if uploaded_file is None:
            return None

        original_name = os.path.basename(uploaded_file.name or "").strip()
        if not original_name:
            raise ValueError("上传文件名为空")

        ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
        if allowed_exts and ext not in allowed_exts:
            raise ValueError(f"不支持的文件类型: .{ext}")

        content = uploaded_file.getvalue()
        if len(content) > max_mb * 1024 * 1024:
            raise ValueError(f"文件超过 {max_mb}MB 大小限制")

        stored_name = f"{uuid.uuid4().hex[:12]}_{original_name}"
        target = self._resolve(stored_name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

        try:
            from services.base.attachment_index_service import attachment_index_service
            attachment_index_service.create({
                "stored_name": stored_name,
                "original_name": original_name,
                "category": category,
                "ref_type": ref_type,
                "ref_id": ref_id,
                "size_bytes": len(content),
            })
        except Exception as e:
            # 索引登记失败不回滚物理文件（文件可按命名规则找回）
            logger.error(f"附件索引登记失败: {stored_name}", exception=e)

        logger.info(f"附件已保存: {stored_name} ({len(content)} bytes)")
        return stored_name

    def load(self, stored_name: str) -> Optional[bytes]:
        """读取附件内容

        Args:
            stored_name: save() 返回的存储文件名

        Returns:
            文件字节内容；文件不存在返回 None
        """
        try:
            target = self._resolve(stored_name)
        except ValueError:
            logger.warning(f"拒绝读取非法附件路径: {stored_name}")
            return None
        if not target.is_file():
            return None
        return target.read_bytes()

    def delete(self, stored_name: str) -> bool:
        """删除附件物理文件与索引

        Args:
            stored_name: 存储文件名

        Returns:
            是否成功（文件不存在视为失败，索引已同步清理）
        """
        deleted = False
        try:
            target = self._resolve(stored_name)
            if target.is_file():
                target.unlink()
                deleted = True
        except ValueError:
            logger.warning(f"拒绝删除非法附件路径: {stored_name}")
            return False

        try:
            from services.base.attachment_index_service import attachment_index_service
            attachment_index_service.delete_by_stored_name(stored_name)
        except Exception as e:
            logger.error(f"附件索引删除失败: {stored_name}", exception=e)
        return deleted

    def original_name(self, stored_name: str) -> Optional[str]:
        """查询附件原始文件名（用于下载展示）"""
        try:
            from services.base.attachment_index_service import attachment_index_service
            info = attachment_index_service.get_by_stored_name(stored_name)
            return info.get("original_name") if info else None
        except Exception as e:
            logger.error(f"附件索引查询失败: {stored_name}", exception=e)
            return None


# 全局实例
attachment_store = AttachmentStore()
