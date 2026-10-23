"""配方业务服务集成测试（隔离临时库）。

验证的是「用例」而不是「函数」：
- 内容没变不升版、内容变了升版、校验不过不落库
- 试算不写库、生成需求单写库且带单据号
- 需求单一经生成即冻结（库存变化不回写历史）
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests import TEST_DB

from business.recipe_service import RecipeBusinessService
from business.requirement_service import RequirementBusinessService
from capabilities.circulation import InMemoryCirculationGateway
from capabilities.metering import CatalogSubstanceResolver, MeteringEngine
from capabilities.supply import StockLot, StockSnapshot
from domain.substance import Substance, SubstanceRef
from domain.units import Quantity
from services.recipe_repository import SqliteRecipeRepository, SqliteRequirementRepository

_TABLES = ("requirement_line", "requirement_sheet", "recipe_component", "recipe")


class FakeStockProvider:
    """固定库存快照，避免用例依赖真实瓶子表。"""

    def __init__(self, snapshot):
        self._snapshot = snapshot

    def snapshot(self, label: str = ""):
        return self._snapshot


def _resolver():
    resolver = CatalogSubstanceResolver()
    resolver.add(Substance.of("水杨酸", cas="69-72-7", formula="C7H6O3"))
    resolver.add(Substance.of("乙酸酐", cas="108-24-7", formula="C4H6O3", density=1.08))
    resolver.add(Substance.of("阿司匹林", cas="50-78-2", formula="C9H8O4"))
    return resolver


def _payload(per_person="2", title="乙酰水杨酸制备"):
    return {
        "key": "teach:aspirin",
        "title": title,
        "source": {"kind": "teaching", "code": "有机化学实验/实验三", "title": "实验三"},
        "components": [
            {
                "substance": {"name": "水杨酸", "cas": "69-72-7", "formula": "C7H6O3"},
                "role": "reactant",
                "amount": {"amount_type": "per_person", "amount_value": per_person, "amount_unit": "g"},
                "seq": 0,
            },
            {
                "substance": {"name": "乙酸酐", "cas": "108-24-7", "formula": "C4H6O3"},
                "role": "reactant",
                "amount": {"amount_type": "equivalents", "amount_value": 2.5},
                "seq": 1,
            },
            {
                "substance": {"name": "阿司匹林", "cas": "50-78-2", "formula": "C9H8O4"},
                "role": "product",
                "amount": {"amount_type": "per_person", "amount_value": 1, "amount_unit": "g"},
                "seq": 2,
            },
        ],
    }


def _snapshot(lots):
    return StockSnapshot.of(lots)


class TestRecipeBusiness(unittest.TestCase):
    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        self.resolver = _resolver()
        self.repo = SqliteRecipeRepository()
        self.service = RecipeBusinessService(repository=self.repo, resolver=self.resolver)

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ---------------------------------------------------------------- 保存
    def test_save_creates_recipe(self):
        result = self.service.save_recipe(_payload(), operator="张老师")
        self.assertTrue(result.success, result.message)
        self.assertEqual(result.data["recipe"].version, 1)
        self.assertEqual(len(result.data["detail"]["components"]), 3)

    def test_saved_recipe_reads_back_identically(self):
        self.service.save_recipe(_payload())
        loaded = self.service.get_recipe("teach:aspirin")
        self.assertTrue(loaded.success)
        recipe = loaded.data["recipe"]
        self.assertEqual(recipe.title, "乙酰水杨酸制备")
        self.assertEqual(len(recipe.components), 3)
        self.assertEqual(recipe.components[1].amount.describe(), "2.5 当量")
        self.assertEqual(recipe.source.kind.value, "teaching")

    def test_unchanged_content_does_not_bump_version(self):
        self.service.save_recipe(_payload())
        second = self.service.save_recipe(_payload())
        self.assertTrue(second.success)
        self.assertEqual(second.data["recipe"].version, 1)
        self.assertIn("没有变化", second.message)

    def test_changed_content_bumps_version_and_resets_status(self):
        self.service.save_recipe(_payload())
        self.service.change_status("teach:aspirin", "validated", "张老师")
        changed = self.service.save_recipe(_payload(per_person="3"))
        self.assertTrue(changed.success, changed.message)
        self.assertEqual(changed.data["recipe"].version, 2)
        self.assertEqual(changed.data["recipe"].status.value, "draft")

    def test_invalid_payload_not_saved(self):
        bad = _payload()
        bad["components"] = []
        result = self.service.save_recipe(bad)
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "RECIPE_INVALID")
        self.assertFalse(self.repo.exists("teach:aspirin"))

    def test_unknown_role_rejected(self):
        bad = _payload()
        bad["components"][0]["role"] = "催化剂啊"
        result = self.service.save_recipe(bad)
        self.assertFalse(result.success)

    def test_missing_key_rejected(self):
        bad = _payload()
        bad.pop("key")
        self.assertFalse(self.service.save_recipe(bad).success)

    def test_validate_endpoint(self):
        self.service.save_recipe(_payload())
        result = self.service.validate_recipe("teach:aspirin")
        self.assertTrue(result.success)
        self.assertTrue(result.data["is_valid"])

    def test_list_recipes(self):
        self.service.save_recipe(_payload())
        listed = self.service.list_recipes()
        self.assertEqual(listed.data["total"], 1)
        self.assertEqual(listed.data["items"][0]["material_count"], 2)

    def test_archive_then_guard(self):
        self.service.save_recipe(_payload())
        archived = self.service.change_status("teach:aspirin", "archived")
        self.assertTrue(archived.success)
        loaded = self.service.get_recipe("teach:aspirin")
        self.assertEqual(loaded.data["recipe"].status.value, "archived")


class TestRequirementBusiness(unittest.TestCase):
    def setUp(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()
        self.resolver = _resolver()
        self.recipes = RecipeBusinessService(
            repository=SqliteRecipeRepository(), resolver=self.resolver
        )
        self.recipes.save_recipe(_payload())
        self.snapshot = _snapshot(
            [
                StockLot("B001", SubstanceRef.of("水杨酸", "69-72-7"), Quantity.of("50", "g")),
                StockLot("B002", SubstanceRef.of("乙酸酐", "108-24-7"), Quantity.of("500", "mL")),
            ]
        )
        self.gateway = InMemoryCirculationGateway()
        self.service = RequirementBusinessService(
            recipes=self.recipes,
            resolver=self.resolver,
            metering=MeteringEngine(self.resolver),
            gateway=self.gateway,
            sheets=SqliteRequirementRepository(),
            stock_provider=FakeStockProvider(self.snapshot),
        )

    def tearDown(self):
        for table in _TABLES:
            try:
                TEST_DB.connection.execute(f"DELETE FROM {table}")
            except Exception:
                pass
        TEST_DB.connection.commit()

    # ---------------------------------------------------------------- 试算
    def test_preview_does_not_write(self):
        result = self.service.preview("teach:aspirin", {"persons": 12})
        self.assertTrue(result.success, result.message)
        self.assertFalse(self.service.recent_sheets().data["items"])

    def test_preview_lines_and_coverage(self):
        result = self.service.preview("teach:aspirin", {"persons": 12})
        data = result.data
        self.assertEqual(len(data["lines"]), 2)
        self.assertTrue(data["is_fulfillable"])
        self.assertTrue(all(line["is_covered"] for line in data["lines"]))

    def test_preview_reports_shortage(self):
        self.snapshot = _snapshot([])
        self.service._stock_provider = FakeStockProvider(self.snapshot)
        result = self.service.preview("teach:aspirin", {"persons": 12})
        self.assertFalse(result.data["is_fulfillable"])
        self.assertEqual(len(result.data["shortages"]), 2)
        self.assertTrue(result.data["proposal"])

    def test_preview_unknown_recipe(self):
        result = self.service.preview("不存在")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "RECIPE_NOT_FOUND")

    # ---------------------------------------------------------------- 落库
    def test_create_sheet_persists_with_number(self):
        result = self.service.create_sheet("teach:aspirin", {"persons": 12}, requester="张老师")
        self.assertTrue(result.success, result.message)
        number = result.data["sheet_number"]
        self.assertRegex(number, r"^RQ\d{8}-\d{4}$")

        loaded = self.service.get_sheet(number)
        self.assertTrue(loaded.success)
        self.assertEqual(len(loaded.data["lines"]), 2)

    def test_sheet_freezes_stock_snapshot(self):
        """库存后来变了，历史单的缺口快照不变。"""
        created = self.service.create_sheet("teach:aspirin", {"persons": 12}, requester="张老师")
        number = created.data["sheet_number"]

        self.service._stock_provider = FakeStockProvider(_snapshot([]))
        again = self.service.get_sheet(number)
        self.assertIn("水杨酸", [line["name"] for line in again.data["lines"]])

    def test_create_sheet_with_submit_creates_ticket(self):
        result = self.service.create_sheet(
            "teach:aspirin", {"persons": 12}, requester="张老师", submit=True
        )
        self.assertTrue(result.success, result.message)
        ticket = result.data["ticket"]
        self.assertIsNotNone(ticket)
        self.assertEqual(ticket["status"], "submitted")

    def test_ticket_lifecycle_through_service(self):
        created = self.service.create_sheet(
            "teach:aspirin", {"persons": 12}, requester="张老师", submit=True
        )
        ticket_no = created.data["ticket"]["ticket_no"]

        approved = self.service.approve_ticket(ticket_no, "李管理员")
        self.assertTrue(approved.success, approved.message)

        issued = self.service.issue_ticket(ticket_no, "王库管")
        self.assertTrue(issued.success, issued.message)
        self.assertEqual(issued.data["ticket"]["status"], "issued")

    def test_self_approval_rejected_through_service(self):
        created = self.service.create_sheet(
            "teach:aspirin", {"persons": 12}, requester="张老师", submit=True
        )
        ticket_no = created.data["ticket"]["ticket_no"]
        result = self.service.approve_ticket(ticket_no, "张老师")
        self.assertFalse(result.success)
        self.assertEqual(result.error_code, "CIRCULATION_DENIED")

    def test_open_tickets(self):
        self.service.create_sheet(
            "teach:aspirin", {"persons": 12}, requester="张老师", submit=True
        )
        listed = self.service.open_tickets()
        self.assertEqual(listed.data["total"], 1)

    def test_batches_multiply_requirement(self):
        one = self.service.preview("teach:aspirin", {"persons": 5, "batches": 1})
        three = self.service.preview("teach:aspirin", {"persons": 5, "batches": 3})
        self.assertEqual(
            three.data["lines"][0]["quantity_value"],
            one.data["lines"][0]["quantity_value"] * 3,
        )


if __name__ == "__main__":
    unittest.main()
