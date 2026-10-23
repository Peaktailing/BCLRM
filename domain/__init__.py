"""领域层：实验物料交叉点的纯对象模型。

本包是**零依赖**的——不导入 ``db`` / ``services`` / ``business`` / Streamlit。
它只描述「物质、计量、配方、需求」这四件事本身及其不变量，可以在没有
数据库、没有页面、甚至没有网络的环境里被完整测试。

分层关系（依赖只能自上而下）::

    views  →  business  →  capabilities  →  domain
                            ↓
                       services / db

领域对象不负责存取，也不负责编排；存取由 ``services`` 的仓储实现，
编排由 ``business`` 的用例服务负责。
"""
from domain.amount import (
    AmountError,
    AmountSpec,
    ConcentrationAmount,
    EquivalentsAmount,
    FixedAmount,
    PerBatchAmount,
    PerPersonAmount,
    RatioAmount,
    ResolveContext,
    concentration,
    equivalents,
    fixed,
    per_batch,
    per_person,
    ratio,
)
from domain.batch import BatchScale, scale_of
from domain.custody import (
    Custodian,
    CustodyError,
    Holding,
    Holdings,
    holdings_from_rows,
    share_of,
)
from domain.chemistry import (
    ATOMIC_WEIGHTS,
    CasError,
    CasNumber,
    FormulaError,
    MolecularFormula,
    combine_formulas,
    element_counts_to_formula,
)
from domain.recipe import (
    Recipe,
    RecipeComponent,
    RecipeError,
    RecipeStatus,
    Severity,
    SourceKind,
    SourceRef,
    ValidationIssue,
    ValidationReport,
)
from domain.pipeline import (
    Acceptance,
    IssueLine,
    LotPick,
    PipelineError,
    PipelineResult,
    Shortfall,
    Stage,
    TeacherRequest,
    TransferLine,
    TransferProposal,
)
from domain.requirement import (
    CoverageLine,
    CoverageReport,
    RequirementLine,
    RequirementSheet,
    merge_sheets,
)
from domain.substance import (
    ComponentRole,
    ConversionError,
    Substance,
    SubstanceCatalog,
    SubstanceRef,
    normalize_name,
)
from domain.units import (
    Dimension,
    Quantity,
    Unit,
    UnitError,
    parse_unit,
    total,
)

__all__ = [
    # 单位与数量
    "Dimension", "Unit", "UnitError", "Quantity", "parse_unit", "total",
    # 化学值对象
    "ATOMIC_WEIGHTS", "MolecularFormula", "FormulaError",
    "CasNumber", "CasError", "combine_formulas", "element_counts_to_formula",
    # 物质
    "Substance", "SubstanceRef", "SubstanceCatalog", "ComponentRole",
    "ConversionError", "normalize_name",
    # 规模
    "BatchScale", "scale_of",
    # 计量规则
    "AmountSpec", "AmountError", "ResolveContext",
    "FixedAmount", "PerPersonAmount", "PerBatchAmount",
    "EquivalentsAmount", "RatioAmount", "ConcentrationAmount",
    "fixed", "per_person", "per_batch", "equivalents", "ratio", "concentration",
    # 配方
    "Recipe", "RecipeComponent", "RecipeError", "RecipeStatus",
    "SourceRef", "SourceKind", "Severity", "ValidationIssue", "ValidationReport",
    # 需求
    "RequirementLine", "RequirementSheet", "CoverageLine", "CoverageReport",
    "merge_sheets",
    # 保管权
    "Custodian", "CustodyError", "Holding", "Holdings",
    "holdings_from_rows", "share_of",
    # 两段管线
    "Stage", "PipelineError", "TeacherRequest", "IssueLine", "Shortfall",
    "LotPick", "Acceptance", "TransferLine", "TransferProposal", "PipelineResult",
]
