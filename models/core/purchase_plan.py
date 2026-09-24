"""课程采购单数据模型

按「课程名 + 目标学年」生成，同一课程重复生成会覆盖旧单。

- purchase_plan        课程采购单表头
- purchase_plan_item   明细（课程 - 实验 - 试剂）
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class PurchasePlan:
    """课程采购单表头"""
    id: Optional[int] = None
    plan_number: Optional[str] = None            # 单号（CP + 时间戳）
    course_name: Optional[str] = None            # 课程名（采购单粒度）
    source_semester: Optional[str] = None        # 用量来源学年（如 2025-2026）
    target_semester: Optional[str] = None        # 采购目标学年（如 2026-2027）
    source_student_count: Optional[int] = None   # 历史人数（该课程各班级合计）
    target_student_count: Optional[int] = None   # 预计人数（默认 30）
    status: Optional[str] = None                 # 待采购 / 已下单 / 已到货 / 已取消
    item_count: Optional[int] = None             # 明细条目数
    total_quantity: Optional[float] = None       # 需求总量
    remark: Optional[str] = None
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


@dataclass
class PurchasePlanItem:
    """采购单明细（课程 - 实验 - 试剂）"""
    id: Optional[int] = None
    plan_id: Optional[int] = None
    item_id: Optional[int] = None              # 实验项目ID
    item_name: Optional[str] = None            # 实验名称
    reagent_name: Optional[str] = None
    cas_number: Optional[str] = None
    source_quantity: Optional[float] = None    # 来源学年总用量（历史）
    per_capita_usage: Optional[float] = None   # 人均用量 = 历史用量 ÷ 历史人数
    student_count: Optional[int] = None        # 预计人数
    demand_quantity: Optional[float] = None    # 需求量 = 人均 × 人数（可人工修改）
    purchase_quantity: Optional[float] = None  # 采购量（可人工修改）
    current_stock: Optional[float] = None      # 当前库存（仅参考）
    is_manual: Optional[int] = None            # 是否被人工修改过
    supplier: Optional[str] = None
    unit_price: Optional[float] = None
    remark: Optional[str] = None
