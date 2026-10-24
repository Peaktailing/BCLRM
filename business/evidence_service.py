"""现场取证：借出与归还的照片挂到工单上。

## 为什么这件事不能只做「上传附件」

危化品的账本上，「某日某人领走 30 g 乙醇」是一行字。它证明的是**有人点了
按钮**，不是「料真的出了库、瓶子交到了手上」。出事之后要回答的问题往往是
「那天是谁来拿的、拿的是不是这一瓶」，只有照片能答。

所以取证不是「顺便支持上传附件」，是**给每一笔借出/归还留一个物理现场
的快照**，并且和单号绑死：查这张单，照片就在这张单下面。

## 挂载键

    ref_type = borrow_order      所有照片都挂在借用工单上
    ref_id   = order_number      工单号
    category = evidence_borrow   借出（发料现场）
             = evidence_return   归还（回库、剩余量、瓶身）

**不用 return_record 的归还单号**：一笔归还动作在系统里可能产生多条明细
记录（一单多瓶），而照片是「这一次交接」的整体，挂工单号才能一张照片覆盖
整笔，也不会因为部分归还产生一堆只有一张图的孤儿单。两个阶段用 category
区分，互不覆盖——同一张单既有发料照片又有回库照片，正是要的。

## 必拍是可配的

有的实验室要求每次借出都拍，有的只在管控试剂上要求，还有的嫌麻烦只留痕
不强制。这件事不该由代码定，所以开关在 ``system_config`` 里，由超管在
「系统设置」页改。:meth:`EvidenceService.require` 是唯一的读取口——校验点
和设置页必须看同一个值，否则页面显示「必拍」而提交放行，或者反过来。

## 压缩在服务端

手机原图动辄 8 MB。客户端压缩（canvas）能省流量，但**不能信**：换个浏览器
或直接调接口就绕过了。所以 ``utils/photo_utils.normalize`` 在服务端再压一遍，
且压失败不丢证据——原样存，只是标注体积没降。

落盘是「原图 + 缩略图」两份，长边与质量可在系统设置里调。照片墙读缩略图
（约 17 KB），要看细节再读原图——这一条比继续降原图分辨率有用得多：
页面每帧发的是缩略图，手机上不卡，原图的分辨率却保住了。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from services.base.system_config_service import (
    EvidenceConfig,
    default_of,
    system_config_service,
)
from utils.attachment_store import attachment_store
from utils.audit import audit
from utils.error_handler import ServiceResult, handle_exception, logger
from utils.photo_utils import human_size, normalize_or_original, thumbnail

#: 挂载的业务类型。所有取证照片都挂在借用工单上。
REF_TYPE_ORDER = "borrow_order"

#: 阶段 → 附件分类。分类同时是「页面按阶段筛」的依据。
PHASE_BORROW = "borrow"
PHASE_RETURN = "return"

PHASE_CATEGORY = {
    PHASE_BORROW: "evidence_borrow",
    PHASE_RETURN: "evidence_return",
}

PHASE_LABELS = {
    PHASE_BORROW: "借出取证",
    PHASE_RETURN: "归还取证",
}

#: 真值口径。配置里存的是文本，超管手写成 "true"/"是" 也得认。
_TRUE_VALUES = {"1", "true", "yes", "on", "是", "开"}


class EvidenceService:
    """照片挂载、查询与必拍校验。"""

    def __init__(self, store=None, config=None, index=None) -> None:
        self.store = store or attachment_store
        self.config = config or system_config_service
        self._index = index  # 延迟：附件库未初始化时不要卡在导入期

    # ---------------------------------------------------------------- 开关
    @property
    def index(self):
        if self._index is None:
            from services.base.attachment_index_service import attachment_index_service
            self._index = attachment_index_service
        return self._index

    def require(self, phase: str) -> bool:
        """这个阶段是否必须拍照。页面校验与服务端校验都走这里。

        空值回落到出厂默认而不是当成「关」：配置项被误清空一次，取证要求就
        静默消失了，这种事故没人会发现。
        """
        key = (
            EvidenceConfig.REQUIRE_BORROW
            if phase == PHASE_BORROW
            else EvidenceConfig.REQUIRE_RETURN
        )
        raw = (self.config.get(key, "") or "").strip()
        if not raw:
            return default_of(key) == "1"
        return raw.lower() in _TRUE_VALUES

    def max_mb(self) -> int:
        value = self.config.get_int(
            EvidenceConfig.MAX_MB, int(default_of(EvidenceConfig.MAX_MB) or 8)
        )
        return max(1, value)

    def max_edge(self) -> int:
        """落盘前的长边上限（像素）。

        没有做成硬编码是有原因的：同一个 1440，对「拍瓶身标签」够用，对
        「拍台账整页」就不够。哪个更常用只有实验室自己知道，所以给个旋钮。
        """
        value = self.config.get_int(
            EvidenceConfig.PHOTO_MAX_EDGE, int(default_of(EvidenceConfig.PHOTO_MAX_EDGE))
        )
        # 下限 640：再低连标签上的批号都糊了，宁可多占点盘
        return min(max(value, 640), 4096)

    def quality(self) -> int:
        """JPEG 重编码质量。低于 40 会出现明显块状，高于 95 只涨体积。"""
        value = self.config.get_int(
            EvidenceConfig.PHOTO_QUALITY, int(default_of(EvidenceConfig.PHOTO_QUALITY))
        )
        return min(max(value, 40), 95)

    # ---------------------------------------------------------------- 写
    @handle_exception(context="上传取证照片")
    def attach(
        self,
        order_number: str,
        phase: str,
        files: Sequence[Any],
        operator: str = "",
        note: str = "",
    ) -> ServiceResult:
        """把一组照片挂到工单上。

        Args:
            order_number: 工单号（``borrow_order.order_number``）
            phase: ``"borrow"`` 或 ``"return"``
            files: Streamlit 的 UploadedFile 列表（有 ``.name`` 与 ``.getvalue()``）
            operator: 上传人
            note: 审计备注

        Returns:
            ServiceResult，``data`` 含 ``saved``（已存元数据）、``failed``、
            ``total_bytes``。
        """
        if not (order_number or "").strip():
            return ServiceResult.fail(
                message="没有工单号，无法挂载照片", error_code="NO_ORDER"
            )
        if phase not in PHASE_CATEGORY:
            return ServiceResult.fail(
                message=f"未知的取证阶段：{phase}", error_code="BAD_PHASE"
            )
        incoming = [item for item in (files or []) if item is not None]
        if not incoming:
            return ServiceResult.fail(
                message="没有选择照片", error_code="NO_FILES"
            )

        category = PHASE_CATEGORY[phase]
        max_mb = self.max_mb()
        max_edge = self.max_edge()
        quality = self.quality()
        saved: List[Dict[str, Any]] = []
        failed: List[str] = []
        total_bytes = 0

        for upload in incoming:
            name = getattr(upload, "name", "") or "photo.jpg"
            try:
                raw = upload.getvalue()
            except Exception as exc:
                failed.append(f"{name}：读取失败（{exc}）")
                continue
            content, compressed = normalize_or_original(
                raw, max_edge=max_edge, quality=quality
            )
            if len(content) > max_mb * 1024 * 1024:
                failed.append(
                    f"{name}：{human_size(len(content))} 超过单张上限 {max_mb} MB"
                )
                continue
            # 压缩成功后一律存成 .jpg：文件名得跟着内容走，否则下载下来
            # 是张打不开的 .heic
            stored_name_input = (
                f"{name.rsplit('.', 1)[0]}.jpg" if compressed and "." in name else name
            )
            try:
                stored = self.store.save_bytes(
                    content,
                    stored_name_input,
                    category=category,
                    max_mb=max_mb,
                    ref_type=REF_TYPE_ORDER,
                    ref_id=order_number,
                )
            except Exception as exc:
                failed.append(f"{name}：保存失败（{exc}）")
                continue
            if not stored:
                failed.append(f"{name}：保存失败")
                continue
            # 缩略图是「可选的加速件」：写失败不算这张照片失败，页面读不到
            # 会自己回落到原图。
            thumb = thumbnail(content)
            if thumb:
                self.store.save_sibling(thumb, stored)
            total_bytes += len(content)
            saved.append(
                {
                    "stored_name": stored,
                    "original_name": name,
                    "size_bytes": len(content),
                    "compressed": compressed,
                    "phase": phase,
                    "thumb_bytes": len(thumb) if thumb else 0,
                }
            )

        if saved:
            audit(
                operator,
                f"{PHASE_LABELS[phase]}上传",
                REF_TYPE_ORDER,
                order_number,
                f"{len(saved)} 张，共 {human_size(total_bytes)}"
                + (f"；{note}" if note else ""),
            )
        if not saved:
            return ServiceResult.fail(
                message="照片都没有保存成功：" + "；".join(failed),
                error_code="NOTHING_SAVED",
                data={"failed": failed},
            )
        message = f"已保存 {len(saved)} 张（{human_size(total_bytes)}）"
        if failed:
            message += f"，{len(failed)} 张失败"
        return ServiceResult.ok(
            data={"saved": saved, "failed": failed, "total_bytes": total_bytes},
            message=message,
        )

    # ---------------------------------------------------------------- 读
    def photos_of(self, order_number: str, phase: str = "") -> List[Dict[str, Any]]:
        """这张单的照片（新→旧）。``phase`` 为空取全部。"""
        if not order_number:
            return []
        category = PHASE_CATEGORY.get(phase, "") if phase else ""
        return self.index.list_by_ref(REF_TYPE_ORDER, order_number, category)

    def count(self, order_number: str, phase: str = "") -> int:
        return len(self.photos_of(order_number, phase))

    def read(self, stored_name: str) -> Optional[bytes]:
        """读照片内容（下载、看原图用）。"""
        return self.store.load(stored_name)

    def read_thumb(self, stored_name: str) -> Optional[bytes]:
        """读缩略图；没有缩略图（老照片、小图）就回落到原图。

        页面照片墙一律走这里。回落是必须的：这一版之前存的照片没有缩略图，
        而照片是要留好几年的——不能因为老照片就显示不出来。
        """
        thumb = self.store.load_sibling(stored_name)
        if thumb:
            return thumb
        return self.store.load(stored_name)

    # ---------------------------------------------------------------- 校验
    def check(
        self, order_number: str, phase: str, uploaded: int = 0
    ) -> ServiceResult:
        """必拍校验。

        规则只有一条：**开关打开时，这一单这个阶段至少要有一张照片**——
        可以这次新传的（``uploaded``），也可以是之前传过的（补充取证）。

        为什么允许「之前传过的抵账」：现场信号差，人可能先拍照存相册、
        回头再补传；也可能管理员先发料、事后统一补照片。同一笔交接只要
        有证据就不该被卡。
        """
        if not self.require(phase):
            return ServiceResult.ok(data={"required": False}, message="")
        if uploaded > 0:
            return ServiceResult.ok(data={"required": True}, message="")
        if self.count(order_number, phase) > 0:
            return ServiceResult.ok(data={"required": True, "existing": True}, message="")
        return ServiceResult.fail(
            message=(
                f"{PHASE_LABELS[phase]}照片是必填项："
                "请在下方拍照或选择照片后再提交（管理员可在系统设置里关闭此项）"
            ),
            error_code="PHOTO_REQUIRED",
            data={"required": True},
        )


evidence_service = EvidenceService()

__all__ = [
    "EvidenceService",
    "evidence_service",
    "PHASE_BORROW",
    "PHASE_RETURN",
    "PHASE_CATEGORY",
    "PHASE_LABELS",
    "REF_TYPE_ORDER",
]
