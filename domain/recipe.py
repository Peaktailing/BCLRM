"""配方（Recipe）：实验方案的物料侧聚合根。

这里刻意**不叫 Experiment**。BCLRM 的底座是「试剂在学校里怎么流动」，
biomanager 的底座是「实验从开始到结束」。两者正交，交叉点只有一个：
**方案声明要用什么、用多少**。所以本模块只认「配方」这个物料视角的
概念，实验（课程实验 / 科研项目 / 临时试做）只作为一条可选的来源
引用挂在旁边——先不管它属于教学还是科研，配方都能独立成立。

聚合根守的是这几条不变量：

1. 每个组分必须能被解析（绝对量、或依赖一个确实存在的基准组分）
2. 依赖型组分（当量、配比）必须有绝对量基准，否则整张配方不可执行
3. 组分角色与计量方式不能自相矛盾（产物不参与当量基准）
4. 同一物质重复出现要提示（多半是录入重复，也可能是有意分批加料）
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Iterable, Iterator, Optional, Protocol, Sequence

from domain.amount import AmountError, AmountSpec, ResolveContext
from domain.batch import BatchScale
from domain.substance import ComponentRole, Substance, SubstanceRef
from domain.units import Quantity, Unit


class RecipeError(ValueError):
    """配方层面的错误（不是单条计量的问题，而是整张配方不成立）。"""


class RecipeStatus(str, Enum):
    """配方生命周期。草稿可改，已验证可投产，归档只读。"""

    DRAFT = "draft"
    VALIDATED = "validated"
    ARCHIVED = "archived"

    @property
    def label(self) -> str:
        return {
            RecipeStatus.DRAFT: "草稿",
            RecipeStatus.VALIDATED: "已验证",
            RecipeStatus.ARCHIVED: "已归档",
        }[self]

    def can_transition_to(self, target: "RecipeStatus") -> bool:
        """状态迁移合法性（纯函数，业务层与视图层共用一套判断）。"""
        allowed = {
            RecipeStatus.DRAFT: {RecipeStatus.VALIDATED, RecipeStatus.ARCHIVED},
            RecipeStatus.VALIDATED: {RecipeStatus.DRAFT, RecipeStatus.ARCHIVED},
            RecipeStatus.ARCHIVED: {RecipeStatus.DRAFT},
        }
        return target in allowed[self]


class SourceKind(str, Enum):
    """配方来源的类别。**只用于溯源，不参与任何业务分支。**"""

    TEACHING = "teaching"
    RESEARCH = "research"
    MANUAL = "manual"

    @property
    def label(self) -> str:
        return {
            SourceKind.TEACHING: "教学",
            SourceKind.RESEARCH: "科研",
            SourceKind.MANUAL: "手工录入",
        }[self]


@dataclass(frozen=True)
class SourceRef:
    """配方的来源引用（可空）。

    教学课程实验、科研项目、或一张纸上抄来的方案，都只是「这条配方
    从哪来」。它的存在让报表能说明出处，但不能让计算逻辑分叉。
    """

    kind: SourceKind
    code: str = ""
    title: str = ""

    @classmethod
    def teaching(cls, course_name: str, item_name: str) -> "SourceRef":
        return cls(SourceKind.TEACHING, f"{course_name}/{item_name}", item_name)

    @classmethod
    def research(cls, project_code: str, title: str = "") -> "SourceRef":
        return cls(SourceKind.RESEARCH, project_code, title)

    def describe(self) -> str:
        stem = f"{self.kind.label}：{self.title or self.code}"
        return f"{stem}（{self.code}）" if self.code and self.title else stem


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"

    @property
    def label(self) -> str:
        return {"error": "错误", "warning": "提示"}[self.value]


@dataclass(frozen=True)
class ValidationIssue:
    """一条校验结论。"""

    severity: Severity
    code: str
    message: str
    component_index: Optional[int] = None

    @property
    def is_error(self) -> bool:
        return self.severity is Severity.ERROR

    def __str__(self) -> str:
        where = f"[组分 {self.component_index + 1}] " if self.component_index is not None else ""
        return f"{where}{self.message}"


@dataclass(frozen=True)
class ValidationReport:
    """配方校验报告。"""

    issues: tuple[ValidationIssue, ...] = ()

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if i.is_error)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(i for i in self.issues if not i.is_error)

    @property
    def is_valid(self) -> bool:
        return not self.errors

    def merge(self, other: "ValidationReport") -> "ValidationReport":
        return ValidationReport(self.issues + other.issues)

    def summary(self) -> str:
        if not self.issues:
            return "校验通过"
        if self.is_valid:
            return f"校验通过，{len(self.warnings)} 条提示"
        return f"{len(self.errors)} 个错误、{len(self.warnings)} 条提示"


@dataclass(frozen=True)
class RecipeComponent:
    """配方中的一行组分。

    Attributes:
        substance: 物质引用（跨模块公共键）
        role: 角色，决定是否参与计量、是否备料
        amount: 计量规则（多态）
        seq: 显示顺序
        coefficient: 化学计量系数，限制试剂判定用
        purity_required: 纯度下限（0~1）
        note: 备注
    """

    substance: SubstanceRef
    role: ComponentRole
    amount: AmountSpec
    seq: int = 0
    coefficient: Decimal = Decimal("1")
    purity_required: Optional[Decimal] = None
    note: str = ""

    def __post_init__(self) -> None:
        if self.coefficient is None or self.coefficient <= 0:
            raise RecipeError(f"{self.substance} 的化学计量系数必须为正")
        if self.purity_required is not None and not (0 < self.purity_required <= 1):
            raise RecipeError(f"{self.substance} 的纯度要求应在 0~1 之间")

    # ---------------------------------------------------------------- 判定
    @property
    def depends_on_basis(self) -> bool:
        return self.amount.requires_basis()

    @property
    def needs_material(self) -> bool:
        return self.role.needs_material

    def label(self) -> str:
        name = self.substance.name or str(self.substance)
        return f"{name}（{self.role.label}）"

    # ---------------------------------------------------------------- 序列化
    def to_record(self, recipe_id: Optional[int] = None) -> dict:
        record = {
            "seq": self.seq,
            "role": self.role.value,
            "substance_key": self.substance.key,
            "display_name": self.substance.name,
            "cas_number": self.substance.cas.value if self.substance.cas else None,
            "formula": self.substance.formula.text if self.substance.formula else None,
            "coefficient": float(self.coefficient),
            "purity_required": (
                float(self.purity_required) if self.purity_required is not None else None
            ),
            "note": self.note,
        }
        record.update(self.amount.to_record())
        if recipe_id is not None:
            record["recipe_id"] = recipe_id
        return record

    @classmethod
    def from_record(cls, record: dict) -> "RecipeComponent":
        return cls(
            substance=SubstanceRef.of(
                record.get("display_name") or "",
                record.get("cas_number"),
                record.get("formula"),
            ),
            role=ComponentRole(record.get("role") or ComponentRole.REAGENT.value),
            amount=AmountSpec.from_record(record),
            seq=int(record.get("seq") or 0),
            coefficient=Decimal(str(record.get("coefficient") or 1)),
            purity_required=(
                Decimal(str(record["purity_required"]))
                if record.get("purity_required") not in (None, "")
                else None
            ),
            note=record.get("note") or "",
        )


@dataclass(frozen=True)
class Recipe:
    """配方聚合根。

    不可变：改一条组分返回新的 Recipe（``with_components``），版本号由
    调用方决定是否递增。这样「同一张配方正在被计算的同时有人改它」这
    类并发问题在对象层面就不存在。
    """

    key: str
    title: str
    components: tuple[RecipeComponent, ...] = ()
    version: int = 1
    status: RecipeStatus = RecipeStatus.DRAFT
    source: Optional[SourceRef] = None
    owner: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not (self.key or "").strip():
            raise RecipeError("配方必须有关键字（key）")
        if self.version < 1:
            raise RecipeError("配方版本号至少为 1")

    # ---------------------------------------------------------------- 视图
    def __iter__(self) -> Iterator[RecipeComponent]:
        return iter(self.components)

    def __len__(self) -> int:
        return len(self.components)

    @property
    def material_components(self) -> tuple[RecipeComponent, ...]:
        """会产生物料需求的组分（产物默认排除）。"""
        return tuple(c for c in self.components if c.needs_material)

    @property
    def reactants(self) -> tuple[RecipeComponent, ...]:
        """参与化学计量的组分。"""
        return tuple(c for c in self.components if c.role.participates_in_stoichiometry)

    def component_of(self, ref: SubstanceRef) -> Optional[RecipeComponent]:
        for component in self.components:
            if component.substance.key == ref.key:
                return component
        for component in self.components:
            if component.substance.matches(ref):
                return component
        return None

    def has_substance(self, ref: SubstanceRef) -> bool:
        return self.component_of(ref) is not None

    def roles_present(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for component in self.components:
            counts[component.role.label] = counts.get(component.role.label, 0) + 1
        return counts

    def basis_component(self) -> Optional[RecipeComponent]:
        """可作当量/配比基准的组分：参与计量且自身是绝对量。

        取第一个这样的组分（通常是限制试剂或称量基准物）。若配方里
        全是相对量，返回 ``None``——这在 :meth:`validate` 里是硬错误。
        """
        for component in self.components:
            if component.role.participates_in_stoichiometry and not component.depends_on_basis:
                return component
        for component in self.components:
            if component.needs_material and not component.depends_on_basis:
                return component
        return None

    def absolute_components(self) -> tuple[RecipeComponent, ...]:
        """不依赖其他组分的计量行（第一轮解析对象）。"""
        return tuple(c for c in self.components if not c.depends_on_basis)

    def dependent_components(self) -> tuple[RecipeComponent, ...]:
        """依赖基准的计量行（第二轮解析对象）。"""
        return tuple(c for c in self.components if c.depends_on_basis)

    # ---------------------------------------------------------------- 校验
    def validate(self) -> ValidationReport:
        """配方自洽性校验（不查库存、不查数据库）。"""
        issues: list[ValidationIssue] = []

        if not self.title.strip():
            issues.append(ValidationIssue(Severity.ERROR, "TITLE_EMPTY", "配方标题不能为空"))

        if not self.components:
            issues.append(
                ValidationIssue(Severity.ERROR, "NO_COMPONENT", "配方至少需要一个组分")
            )
            return ValidationReport(tuple(issues))

        if not self.reactants:
            issues.append(
                ValidationIssue(
                    Severity.WARNING,
                    "NO_REACTANT",
                    "配方中没有反应物角色，将按配液/配料清单处理（不参与化学计量）",
                )
            )

        if not self.material_components:
            issues.append(
                ValidationIssue(
                    Severity.ERROR, "NO_MATERIAL", "配方中所有组分都是产物，没有需要备料的物质"
                )
            )

        basis = self.basis_component()
        if basis is None and self.dependent_components():
            issues.append(
                ValidationIssue(
                    Severity.ERROR,
                    "NO_ABSOLUTE_BASIS",
                    "配方中只有当量/配比型计量，缺少可作基准的绝对量组分，无法计算",
                )
            )

        known_keys = {c.substance.key for c in self.components}
        seen: dict[str, int] = {}
        for index, component in enumerate(self.components):
            # 依赖的基准必须在本配方里
            basis_key = getattr(component.amount, "basis_key", None)
            if component.depends_on_basis and basis_key and basis_key not in known_keys:
                issues.append(
                    ValidationIssue(
                        Severity.ERROR,
                        "BASIS_NOT_FOUND",
                        f"{component.label()} 指定的基准组分不在配方中：{basis_key}",
                        index,
                    )
                )
            # 重复物质
            key = component.substance.key
            if key in seen:
                issues.append(
                    ValidationIssue(
                        Severity.WARNING,
                        "DUPLICATE_SUBSTANCE",
                        f"{component.label()} 与第 {seen[key] + 1} 行是同一物质，请确认是否需要分次加入",
                        index,
                    )
                )
            else:
                seen[key] = index
            # 产物不该参与当量
            if component.role is ComponentRole.PRODUCT and component.depends_on_basis:
                issues.append(
                    ValidationIssue(
                        Severity.WARNING,
                        "PRODUCT_RELATIVE_AMOUNT",
                        f"{component.label()} 是产物却按相对量计量，请确认是否为理论产量估算",
                        index,
                    )
                )

        return ValidationReport(tuple(issues))

    # ---------------------------------------------------------------- 变换
    def with_components(self, components: Iterable[RecipeComponent]) -> "Recipe":
        return Recipe(
            key=self.key,
            title=self.title,
            components=tuple(components),
            version=self.version,
            status=self.status,
            source=self.source,
            owner=self.owner,
            note=self.note,
        )

    def next_version(self, components: Optional[Iterable[RecipeComponent]] = None) -> "Recipe":
        """升版：内容变化时产生新版本（草稿改版同样升版，保证可追溯）。"""
        return Recipe(
            key=self.key,
            title=self.title,
            components=tuple(components) if components is not None else self.components,
            version=self.version + 1,
            status=RecipeStatus.DRAFT,
            source=self.source,
            owner=self.owner,
            note=self.note,
        )

    def with_status(self, status: RecipeStatus) -> "Recipe":
        if not self.status.can_transition_to(status):
            raise RecipeError(f"配方状态不能从「{self.status.label}」变为「{status.label}」")
        return Recipe(
            key=self.key,
            title=self.title,
            components=self.components,
            version=self.version,
            status=status,
            source=self.source,
            owner=self.owner,
            note=self.note,
        )

    # ---------------------------------------------------------------- 指纹
    def fingerprint(self) -> str:
        """内容指纹：用于判断「配方真的变了吗」，避免无意义的版本膨胀。"""
        digest = hashlib.sha256()
        digest.update(self.key.encode("utf-8"))
        digest.update(self.title.encode("utf-8"))
        for component in sorted(self.components, key=lambda c: (c.seq, c.substance.key)):
            record = component.to_record()
            for name in sorted(record):
                digest.update(f"{name}={record[name]}|".encode("utf-8"))
        return digest.hexdigest()[:16]

    def describe(self) -> str:
        source = f"，来源：{self.source.describe()}" if self.source else ""
        return f"{self.title}（v{self.version}，{len(self.material_components)} 项备料{source}）"


@dataclass(frozen=True)
class ResolvedComponent:
    """一条组分解析后的结果（计算引擎的中间产物）。"""

    component: RecipeComponent
    quantity: Quantity
    explanation: str
    substance: Optional[Substance] = None

    @property
    def ref(self) -> SubstanceRef:
        return self.component.substance


class SubstanceCatalogLike(Protocol):
    """结构协议：任何提供 ``get(ref)`` 的对象都可当作物质目录。

    用 Protocol 而不是导入 :class:`domain.substance.SubstanceCatalog`，
    是为了让计算引擎可以接任何来源的目录（数据库快照、测试桩、缓存），
    领域层不必知道它们的存在。
    """

    def get(self, ref: SubstanceRef) -> Optional[Substance]:  # pragma: no cover
        ...


__all__ = [
    "RecipeError",
    "RecipeStatus",
    "SourceKind",
    "SourceRef",
    "Severity",
    "ValidationIssue",
    "ValidationReport",
    "RecipeComponent",
    "Recipe",
    "ResolvedComponent",
    "resolve_context",
    "SubstanceCatalogLike",
]
