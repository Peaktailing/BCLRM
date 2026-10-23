"""配方聚合根与计量引擎测试。

覆盖的不是「函数能不能跑」，而是几条化学与业务上的硬规则：
限制试剂怎么定、产物为什么不进备料清单、缺物性为什么必须报错而不是猜。
"""
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capabilities.metering import CatalogSubstanceResolver, MeteringEngine, MeteringError
from domain.amount import equivalents, per_person, ratio
from domain.batch import BatchScale
from domain.recipe import (
    Recipe,
    RecipeComponent,
    RecipeError,
    RecipeStatus,
    Severity,
    SourceRef,
)
from domain.substance import ComponentRole, Substance, SubstanceRef


def _ref(name, cas=None, formula=None):
    return SubstanceRef.of(name, cas, formula)


def _catalog():
    resolver = CatalogSubstanceResolver()
    for substance in [
        Substance.of("水杨酸", cas="69-72-7", formula="C7H6O3"),
        Substance.of("乙酸酐", cas="108-24-7", formula="C4H6O3", density=1.08),
        Substance.of("硫酸", cas="7664-93-9", formula="H2SO4", density=1.84),
        Substance.of("乙醇", cas="64-17-5", formula="C2H6O", density=0.789, default_unit="mL"),
        Substance.of("阿司匹林", cas="50-78-2", formula="C9H8O4"),
    ]:
        resolver.add(substance)
    return resolver


def _aspirin_recipe(**kwargs):
    """乙酰水杨酸制备：一个真实的四组分 + 一个产物的例子。"""
    components = (
        RecipeComponent(
            _ref("水杨酸", "69-72-7", "C7H6O3"),
            ComponentRole.REACTANT,
            per_person("2", "g"),
            seq=0,
        ),
        RecipeComponent(
            _ref("乙酸酐", "108-24-7", "C4H6O3"),
            ComponentRole.REACTANT,
            equivalents("2.5"),
            seq=1,
        ),
        RecipeComponent(
            _ref("硫酸", "7664-93-9", "H2SO4"),
            ComponentRole.CATALYST,
            equivalents("0.05"),
            seq=2,
        ),
        RecipeComponent(
            _ref("乙醇", "64-17-5", "C2H6O"),
            ComponentRole.SOLVENT,
            ratio("3", unit_symbol="mL"),
            seq=3,
        ),
        RecipeComponent(
            _ref("阿司匹林", "50-78-2", "C9H8O4"),
            ComponentRole.PRODUCT,
            per_person("1", "g"),
            seq=4,
        ),
    )
    defaults = dict(
        key="teach:aspirin",
        title="乙酰水杨酸制备",
        components=components,
        status=RecipeStatus.VALIDATED,
        source=SourceRef.teaching("有机化学实验", "实验三"),
    )
    defaults.update(kwargs)
    return Recipe(**defaults)


class TestRecipeInvariants(unittest.TestCase):
    """聚合根自身守的规则。"""

    def test_valid_recipe_passes(self):
        report = _aspirin_recipe().validate()
        self.assertTrue(report.is_valid, [str(i) for i in report.issues])

    def test_empty_components_is_error(self):
        recipe = Recipe(key="k", title="空配方", components=())
        report = recipe.validate()
        self.assertFalse(report.is_valid)
        self.assertIn("NO_COMPONENT", [issue.code for issue in report.errors])

    def test_missing_title_is_error(self):
        recipe = _aspirin_recipe(title="   ")
        self.assertFalse(recipe.validate().is_valid)

    def test_only_relative_amounts_has_no_basis(self):
        recipe = Recipe(
            key="bad",
            title="只有当量",
            components=(
                RecipeComponent(_ref("甲", "64-19-7"), ComponentRole.REACTANT, equivalents("1")),
                RecipeComponent(_ref("乙", "64-17-5"), ComponentRole.REACTANT, equivalents("2")),
            ),
        )
        codes = [issue.code for issue in recipe.validate().errors]
        self.assertIn("NO_ABSOLUTE_BASIS", codes)

    def test_duplicate_substance_warns(self):
        recipe = Recipe(
            key="dup",
            title="重复",
            components=(
                RecipeComponent(_ref("乙酸", "64-19-7"), ComponentRole.REAGENT, per_person("1")),
                RecipeComponent(_ref("乙酸", "64-19-7"), ComponentRole.SOLVENT, per_person("2")),
            ),
        )
        report = recipe.validate()
        self.assertTrue(report.is_valid)
        self.assertIn("DUPLICATE_SUBSTANCE", [issue.code for issue in report.warnings])

    def test_unknown_basis_key_is_error(self):
        recipe = Recipe(
            key="badbasis",
            title="基准不存在",
            components=(
                RecipeComponent(_ref("甲", "64-19-7"), ComponentRole.REACTANT, per_person("1")),
                RecipeComponent(
                    _ref("乙", "64-17-5"),
                    ComponentRole.REAGENT,
                    equivalents("1", basis_key="cas:99-99-9"),
                ),
            ),
        )
        codes = [issue.code for issue in recipe.validate().errors]
        self.assertIn("BASIS_NOT_FOUND", codes)

    def test_basis_component_prefers_absolute_reactant(self):
        recipe = _aspirin_recipe()
        self.assertEqual(recipe.basis_component().substance.key, "cas:69-72-7")

    def test_product_excluded_from_material(self):
        recipe = _aspirin_recipe()
        self.assertEqual(len(recipe.material_components), 4)
        self.assertEqual(len(recipe.components), 5)

    def test_status_transition_guard(self):
        recipe = _aspirin_recipe(status=RecipeStatus.ARCHIVED)
        with self.assertRaises(RecipeError):
            recipe.with_status(RecipeStatus.VALIDATED)
        self.assertEqual(
            recipe.with_status(RecipeStatus.DRAFT).status, RecipeStatus.DRAFT
        )

    def test_next_version_resets_to_draft(self):
        upgraded = _aspirin_recipe().next_version()
        self.assertEqual(upgraded.version, 2)
        self.assertEqual(upgraded.status, RecipeStatus.DRAFT)

    def test_fingerprint_changes_with_content(self):
        a = _aspirin_recipe()
        b = a.with_components(a.components[:-1])
        self.assertNotEqual(a.fingerprint(), b.fingerprint())

    def test_fingerprint_stable_for_same_content(self):
        self.assertEqual(_aspirin_recipe().fingerprint(), _aspirin_recipe().fingerprint())

    def test_component_record_roundtrip(self):
        component = _aspirin_recipe().components[1]
        restored = RecipeComponent.from_record(component.to_record())
        self.assertEqual(restored.substance.key, component.substance.key)
        self.assertEqual(restored.role, component.role)
        self.assertEqual(restored.amount.describe(), component.amount.describe())


class TestMeteringEngine(unittest.TestCase):
    """计量引擎。"""

    def setUp(self):
        self.engine = MeteringEngine(_catalog())

    def test_aspirin_chain(self):
        result = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(12))
        lookup = {line.name: line.quantity for line in result.sheet.lines}

        self.assertEqual(lookup["水杨酸"].value, Decimal("24"))
        # 24 g / 138.121 = 0.1738 mol；乙酸酐 2.5 当量 → 44.35 g
        self.assertAlmostEqual(float(lookup["乙酸酐"].value), 0.1738 * 2.5 * 102.09, places=1)
        # 乙醇：24 g 的 3 倍体积 = 72 mL（不是按密度折算的 91 mL）
        self.assertEqual(lookup["乙醇"].value, Decimal("72"))

    def test_limiting_reagent_is_the_absolute_reactant(self):
        result = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(12))
        self.assertEqual(result.basis_key, "cas:69-72-7")

    def test_product_not_in_requirement_lines(self):
        sheet = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(12)).sheet
        names = [line.name for line in sheet.lines]
        self.assertNotIn("阿司匹林", names)
        self.assertEqual(len(names), 4)

    def test_include_products_option(self):
        result = self.engine.plan(
            _aspirin_recipe(), BatchScale.for_persons(12), include_products=True
        )
        self.assertIn("阿司匹林", [line.name for line in result.sheet.lines])

    def test_scale_multiplies_persons(self):
        small = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(1)).sheet
        big = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(10)).sheet
        self.assertEqual(
            big.line_of(_ref("水杨酸", "69-72-7")).quantity.value,
            small.line_of(_ref("水杨酸", "69-72-7")).quantity.value * 10,
        )

    def test_batches_also_multiply(self):
        one = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(5, 1)).sheet
        three = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(5, 3)).sheet
        self.assertEqual(
            three.line_of(_ref("水杨酸", "69-72-7")).quantity.value,
            one.line_of(_ref("水杨酸", "69-72-7")).quantity.value * 3,
        )

    def test_explanation_is_human_readable(self):
        result = self.engine.plan(_aspirin_recipe(), BatchScale.for_persons(12))
        text = " ".join(result.explain())
        self.assertIn("12 人", text)
        self.assertIn("当量", text)

    def test_invalid_recipe_raises_with_reason(self):
        recipe = Recipe(key="x", title="空", components=())
        with self.assertRaises(MeteringError) as ctx:
            self.engine.plan(recipe)
        self.assertIn("校验未通过", str(ctx.exception))

    def test_missing_molecular_weight_reports_line_number(self):
        recipe = Recipe(
            key="nomw",
            title="缺物性",
            components=(
                RecipeComponent(_ref("甲"), ComponentRole.REACTANT, per_person("1", "g")),
                RecipeComponent(_ref("乙"), ComponentRole.REACTANT, equivalents("1")),
            ),
        )
        with self.assertRaises(MeteringError) as ctx:
            self.engine.plan(recipe)
        self.assertEqual(ctx.exception.component_index, 1)
        self.assertIn("分子量", str(ctx.exception))

    def test_controlled_flag_marks_lines(self):
        sheet = self.engine.plan(
            _aspirin_recipe(),
            BatchScale.for_persons(12),
            controlled_keys={"cas:108-24-7"},
        ).sheet
        controlled = [line.name for line in sheet.controlled_lines]
        self.assertEqual(controlled, ["乙酸酐"])

    def test_empty_result_raises(self):
        recipe = Recipe(
            key="productonly",
            title="只有产物",
            components=(
                RecipeComponent(
                    _ref("阿司匹林", "50-78-2"), ComponentRole.PRODUCT, per_person("1")
                ),
            ),
        )
        with self.assertRaises(MeteringError):
            self.engine.plan(recipe)


class TestRequirementSheet(unittest.TestCase):
    """需求单：只读快照与对账。"""

    def setUp(self):
        self.sheet = MeteringEngine(_catalog()).plan(
            _aspirin_recipe(), BatchScale.for_persons(12)
        ).sheet

    def test_totals_by_dimension(self):
        totals = self.sheet.totals_by_dimension()
        self.assertEqual(totals.get("质量"), 3)
        self.assertEqual(totals.get("体积"), 1)

    def test_coverage_marks_gaps(self):
        from domain.units import Quantity

        coverage = self.sheet.coverage_with(
            {
                "cas:69-72-7": Quantity.of("10", "g"),   # 需 24 g → 缺
                "cas:108-24-7": Quantity.of("1", "kg"),  # 充足
            }
        )
        self.assertFalse(coverage.is_fully_covered)
        names = [line.requirement.name for line in coverage.shortages]
        self.assertIn("水杨酸", names)
        self.assertIn("乙醇", names)  # 完全没库存
        self.assertNotIn("乙酸酐", names)

    def test_coverage_ratio_value(self):
        from domain.units import Quantity

        coverage = self.sheet.coverage_with({"cas:69-72-7": Quantity.of("12", "g")})
        line = [l for l in coverage.lines if l.requirement.name == "水杨酸"][0]
        self.assertEqual(line.coverage_ratio, Decimal("0.5000"))
        self.assertEqual(line.gap.value, Decimal("12"))

    def test_dimension_mismatch_counts_as_zero(self):
        from domain.units import Quantity

        coverage = self.sheet.coverage_with({"cas:108-24-7": Quantity.of("5", "mL")})
        line = [l for l in coverage.lines if l.requirement.name == "乙酸酐"][0]
        self.assertFalse(line.is_covered)

    def test_explain_lists_each_line(self):
        self.assertEqual(len(self.sheet.explain()), len(self.sheet.lines))


if __name__ == "__main__":
    unittest.main()
