"""领域层基础测试：单位、分子式、CAS、物质换算、计量规则。

这些用例完全不碰数据库与页面——领域层「零依赖」不是口号，是这里能
在没有 DB 的临时库里跑通的前提。
"""
import os
import sys
import unittest
from decimal import Decimal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.amount import (
    AmountSpec,
    ConcentrationAmount,
    EquivalentsAmount,
    FixedAmount,
    PerBatchAmount,
    PerPersonAmount,
    RatioAmount,
    concentration,
    equivalents,
    per_person,
    ratio,
)
from domain.batch import BatchScale
from domain.chemistry import CasError, CasNumber, FormulaError, MolecularFormula
from domain.substance import ComponentRole, ConversionError, Substance, SubstanceRef
from domain.units import Dimension, Quantity, UnitError, parse_unit


class TestQuantity(unittest.TestCase):
    """数量值对象。"""

    def test_same_dimension_conversion(self):
        self.assertEqual(Quantity.of("1.5", "g").to("mg").value, Decimal("1500.0"))
        self.assertEqual(Quantity.of("2", "L").to("mL").value, Decimal("2000"))

    def test_decimal_precision_without_float_dust(self):
        # 0.1 + 0.2 在 float 下是 0.30000000000000004，这里是精确的 0.3
        total = Quantity.of("0.1", "g") + Quantity.of("0.2", "g")
        self.assertEqual(total.value, Decimal("0.3"))

    def test_cross_dimension_addition_rejected(self):
        with self.assertRaises(UnitError):
            Quantity.of("1", "g") + Quantity.of("1", "mL")

    def test_cross_dimension_conversion_rejected(self):
        with self.assertRaises(UnitError):
            Quantity.of("1", "g").to("mL")

    def test_subtraction_can_go_negative_then_clamp(self):
        result = Quantity.of("1", "g") - Quantity.of("3", "g")
        self.assertEqual(result.value, Decimal("-2"))
        self.assertEqual(result.clamp_non_negative().value, Decimal("0"))

    def test_division_by_quantity_gives_ratio(self):
        ratio_value = Quantity.of("500", "mg") / Quantity.of("1", "g")
        self.assertEqual(ratio_value, Decimal("0.5"))

    def test_unknown_unit_raises(self):
        with self.assertRaises(UnitError):
            parse_unit("光年")

    def test_unit_aliases(self):
        self.assertEqual(parse_unit("毫升"), parse_unit("mL"))
        self.assertEqual(parse_unit("ug"), parse_unit("μg"))

    def test_nan_rejected(self):
        with self.assertRaises(UnitError):
            Quantity.of(float("nan"), "g")

    def test_format_trims_trailing_zeros(self):
        self.assertEqual(Quantity.of("2.500", "g").format(3), "2.5 g")
        self.assertEqual(Quantity.of("12", "g").format(2), "12 g")


class TestMolecularFormula(unittest.TestCase):
    """分子式与分子量。"""

    def test_glucose(self):
        self.assertEqual(MolecularFormula.parse("C6H12O6").molar_mass, Decimal("180.156"))

    def test_hydrate_with_interpunct(self):
        self.assertEqual(MolecularFormula.parse("CuSO4·5H2O").molar_mass, Decimal("249.677"))

    def test_hydrate_with_dot(self):
        self.assertEqual(
            MolecularFormula.parse("Na2CO3.10H2O").composition["H"], Decimal("20")
        )

    def test_bracket_group(self):
        counts = MolecularFormula.parse("(NH4)2SO4").composition
        self.assertEqual(counts["N"], Decimal("2"))
        self.assertEqual(counts["H"], Decimal("8"))
        self.assertEqual(counts["O"], Decimal("4"))

    def test_fractional_count(self):
        self.assertEqual(MolecularFormula.parse("Fe0.5O").composition["Fe"], Decimal("0.5"))

    def test_unknown_element_raises(self):
        with self.assertRaises(FormulaError):
            MolecularFormula.parse("Xx2O")

    def test_empty_raises(self):
        with self.assertRaises(FormulaError):
            MolecularFormula.parse("   ")

    def test_try_parse_returns_none(self):
        self.assertIsNone(MolecularFormula.try_parse("不是式子"))
        self.assertIsNone(MolecularFormula.try_parse(""))

    def test_hill_text(self):
        self.assertEqual(MolecularFormula.parse("OH2C2").hill_text(), "C2H2O")

    def test_mass_fraction(self):
        water = MolecularFormula.parse("H2O")
        self.assertAlmostEqual(float(water.mass_fraction("H")), 0.1119, places=3)


class TestCasNumber(unittest.TestCase):
    """CAS 校验位。"""

    def test_valid_numbers(self):
        self.assertTrue(CasNumber.is_valid("7732-18-5"))
        self.assertTrue(CasNumber.is_valid("64-19-7"))

    def test_wrong_check_digit(self):
        self.assertFalse(CasNumber.is_valid("7732-18-4"))

    def test_malformed(self):
        self.assertFalse(CasNumber.is_valid("64-19"))
        self.assertFalse(CasNumber.is_valid(""))
        with self.assertRaises(CasError):
            CasNumber.parse("64-19")

    def test_try_parse_soft(self):
        self.assertIsNone(CasNumber.try_parse("abc"))


class TestSubstanceConversion(unittest.TestCase):
    """物质换算：质量 ↔ 物质的量 ↔ 体积。"""

    def setUp(self):
        self.acetic = Substance.of(
            "乙酸", cas="64-19-7", formula="C2H4O2", density=1.049
        )

    def test_molar_mass_from_formula(self):
        self.assertEqual(self.acetic.molar_mass, Decimal("60.052"))

    def test_mass_to_moles(self):
        moles = self.acetic.moles_of(Quantity.of("6.0052", "g"))
        self.assertAlmostEqual(float(moles.value), 0.1, places=6)

    def test_volume_to_mass_uses_density(self):
        mass = self.acetic.mass_of(Quantity.of("10", "mL"))
        self.assertAlmostEqual(float(mass.value), 10.49, places=6)

    def test_volume_to_moles_chain(self):
        moles = self.acetic.moles_of(Quantity.of("10", "mL"))
        self.assertAlmostEqual(float(moles.value), 10.49 / 60.052, places=6)

    def test_missing_density_raises_with_reason(self):
        solid = Substance.of("水杨酸", cas="69-72-7", formula="C7H6O3")
        with self.assertRaises(ConversionError) as ctx:
            solid.volume_of(Quantity.of("1", "g"))
        self.assertIn("密度", str(ctx.exception))

    def test_missing_molar_mass_raises(self):
        unknown = Substance.of("未知物")
        with self.assertRaises(ConversionError) as ctx:
            unknown.moles_of(Quantity.of("1", "g"))
        self.assertIn("分子量", str(ctx.exception))

    def test_purity_check(self):
        pure = Substance.of("乙醇", purity=0.995)
        self.assertTrue(pure.is_pure_enough(Decimal("0.99")))
        self.assertFalse(pure.is_pure_enough(Decimal("0.999")))


class TestSubstanceRef(unittest.TestCase):
    """物质引用键与匹配。"""

    def test_cas_has_priority(self):
        ref = SubstanceRef.of("乙酸", cas="64-19-7", formula="C2H4O2")
        self.assertEqual(ref.key, "cas:64-19-7")

    def test_formula_fallback(self):
        ref = SubstanceRef.of("未知", formula="C2H4O2")
        self.assertEqual(ref.key, "formula:C2H4O2")

    def test_name_fallback_normalizes(self):
        ref = SubstanceRef.of("  乙酸  ", formula="")
        self.assertEqual(ref.key, "name:乙酸")

    def test_matches_by_cas_across_names(self):
        a = SubstanceRef.of("乙酸", cas="64-19-7")
        b = SubstanceRef.of("醋酸", cas="64-19-7")
        self.assertTrue(a.matches(b))

    def test_same_name_different_cas_does_not_match(self):
        a = SubstanceRef.of("酒精", cas="64-17-5")
        b = SubstanceRef.of("酒精", cas="67-56-1")
        self.assertFalse(a.matches(b))

    def test_empty_reference_rejected(self):
        with self.assertRaises(ValueError):
            SubstanceRef.of("")


class TestAmountSpecs(unittest.TestCase):
    """六种计量规则的多态解析。"""

    def setUp(self):
        self.scale = BatchScale.for_persons(12, batches=2)
        self.water = Substance.of("水", formula="H2O", density=1.0, default_unit="mL")
        self.acid = Substance.of("乙酸", cas="64-19-7", formula="C2H4O2", density=1.049)

    def _ctx(self, substance, resolved=None, substances=None, basis_key=None):
        from domain.amount import ResolveContext

        return ResolveContext(
            scale=self.scale,
            substance=substance,
            resolved=resolved or {},
            substances=substances or {},
            basis_key=basis_key,
        )

    def test_per_person_multiplies_persons_and_batches(self):
        qty = per_person("2", "g").resolve(self._ctx(self.acid))
        self.assertEqual(qty.value, Decimal("48"))

    def test_per_batch_ignores_persons(self):
        qty = PerBatchAmount(Quantity.of("5", "g")).resolve(self._ctx(self.acid))
        self.assertEqual(qty.value, Decimal("10"))

    def test_fixed_also_scales_by_batches_only(self):
        qty = FixedAmount(Quantity.of("100", "mL")).resolve(self._ctx(self.water))
        self.assertEqual(qty.value, Decimal("200"))

    def test_equivalents_uses_basis_moles(self):
        basis_key = "cas:69-72-7"
        resolved = {basis_key: Quantity.of("13.812", "g")}
        substances = {
            basis_key: Substance.of("水杨酸", cas="69-72-7", formula="C7H6O3")
        }
        qty = EquivalentsAmount(Decimal("2.5")).resolve(
            self._ctx(self.acid, resolved, substances, basis_key)
        )
        # 13.812 g / 138.121 = 0.09999 mol；× 2.5 当量 × 60.052 = 15.0128 g
        expected = 13.812 / float(substances[basis_key].molar_mass) * 2.5 * 60.052
        self.assertAlmostEqual(float(qty.value), expected, places=4)

    def test_equivalents_without_basis_raises(self):
        from domain.amount import AmountError

        with self.assertRaises(AmountError):
            EquivalentsAmount(Decimal("2")).resolve(self._ctx(self.acid))

    def test_ratio_same_dimension(self):
        basis_key = "cas:69-72-7"
        resolved = {basis_key: Quantity.of("100", "mL")}
        qty = RatioAmount(Decimal("3"), basis_key, "mL").resolve(
            self._ctx(self.water, resolved, {}, None)
        )
        self.assertEqual(qty.value, Decimal("300"))

    def test_ratio_cross_dimension_uses_basis_value(self):
        """24 g 的 3 倍体积 = 72 mL，而不是 24/0.789。"""
        basis_key = "cas:69-72-7"
        resolved = {basis_key: Quantity.of("24", "g")}
        qty = RatioAmount(Decimal("3"), basis_key, "mL").resolve(
            self._ctx(self.water, resolved, {}, None)
        )
        self.assertEqual(qty.value, Decimal("72"))

    def test_concentration_uses_vessel_volume(self):
        scale = BatchScale.with_vessel("500", "mL", persons=1)
        spec = ConcentrationAmount(Decimal("0.1"), "mol/L")
        ctx = self._ctx(self.acid)
        ctx = ctx.__class__(
            scale=scale,
            substance=self.acid,
            resolved=ctx.resolved,
            substances=ctx.substances,
        )
        qty = spec.resolve(ctx)
        # 0.1 mol/L × 0.5 L = 0.05 mol × 60.052 = 3.0026 g
        self.assertAlmostEqual(float(qty.value), 0.05 * 60.052, places=4)

    def test_concentration_without_volume_raises(self):
        from domain.amount import AmountError

        with self.assertRaises(AmountError):
            ConcentrationAmount(Decimal("0.1"), "mol/L").resolve(self._ctx(self.acid))

    def test_record_roundtrip_for_each_type(self):
        specs = [
            per_person("1.5", "g"),
            PerBatchAmount(Quantity.of("2", "mL")),
            FixedAmount(Quantity.of("100", "mL")),
            equivalents("1.2"),
            ratio("3", unit_symbol="mL"),
            concentration("0.5", "mol/L"),
        ]
        for spec in specs:
            record = spec.to_record()
            restored = AmountSpec.from_record(record)
            self.assertEqual(type(restored), type(spec), record)
            self.assertEqual(restored.describe(), spec.describe())

    def test_unknown_amount_type_raises(self):
        from domain.amount import AmountError

        with self.assertRaises(AmountError):
            AmountSpec.from_record({"amount_type": "按心情"})


class TestBatchScale(unittest.TestCase):
    def test_multiplier(self):
        self.assertEqual(BatchScale.for_persons(12, 3).multiplier, Decimal("36"))

    def test_rejects_zero_persons(self):
        with self.assertRaises(ValueError):
            BatchScale.for_persons(0)

    def test_record_roundtrip(self):
        scale = BatchScale.with_vessel("250", "mL", persons=20, batches=2, label="一班")
        restored = BatchScale.from_record(scale.to_record())
        self.assertEqual(restored.persons, 20)
        self.assertEqual(restored.batches, 2)
        self.assertEqual(restored.vessel_volume.value, Decimal("250"))

    def test_vessel_must_be_volume(self):
        with self.assertRaises(UnitError):
            BatchScale(vessel_volume=Quantity.of("1", "g"))


if __name__ == "__main__":
    unittest.main()
