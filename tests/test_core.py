"""单元测试 - 试剂管理系统核心业务逻辑

测试覆盖：
- Pydantic 模型验证
- 密码工具函数
- 数据库单例模式
- ID 生成器格式
- BaseService CRUD 操作
- 权限服务（集成测试）
- 密码认证（集成测试）
- 入库服务（集成测试）
"""
import sys
import os
import unittest
import tempfile
import shutil

# 添加项目根目录到 Python 路径
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)


# ============================================================================
# Pydantic 模型验证测试
# ============================================================================

class TestPydanticModels(unittest.TestCase):
    """测试 Pydantic 模型的数据验证功能"""

    def test_person_model_creation(self):
        from models.base.person import Person
        data = {"name": "张三", "role": "admin", "department": "化学系", "id": 1}
        p = Person(**data)
        self.assertEqual(p.name, "张三")
        self.assertEqual(p.role, "admin")
        self.assertEqual(p.id, 1)

    def test_person_model_defaults(self):
        from models.base.person import Person
        p = Person()
        self.assertIsNone(p.name)
        self.assertIsNone(p.role)
        self.assertIsNone(p.password_hash)

    def test_person_model_extra_fields_ignored(self):
        from models.base.person import Person
        data = {"name": "李四", "extra_field": "should_be_ignored"}
        p = Person(**data)
        self.assertEqual(p.name, "李四")
        self.assertFalse(hasattr(p, "extra_field"))

    def test_reagent_bottle_type_coercion(self):
        from models.core.reagent_bottle import ReagentBottle
        data = {"remaining_quantity": 100, "specification": 500,
                "is_controlled": 1, "borrowable_check": 1}
        bottle = ReagentBottle(**data)
        self.assertEqual(bottle.remaining_quantity, 100.0)
        self.assertEqual(bottle.is_controlled, 1)
        self.assertTrue(bottle.borrowable_check)

    def test_reagent_bottle_serialization(self):
        from models.core.reagent_bottle import ReagentBottle
        bottle = ReagentBottle(bottle_number="202607070001",
                               reagent_name="氯化钠", remaining_quantity=50.5)
        d = bottle.model_dump()
        self.assertEqual(d["bottle_number"], "202607070001")
        self.assertEqual(d["reagent_name"], "氯化钠")
        self.assertEqual(d["remaining_quantity"], 50.5)

    def test_all_models_importable_and_pydantic(self):
        from models.base.person import Person
        from models.base.chemical import ChemicalInfo
        from models.base.controlled_list import ControlledList
        from models.base.manufacturer import Manufacturer
        from models.base.reagent_type import ReagentType
        from models.base.storage_location import StorageLocation
        from models.base.storage_requirement import StorageRequirement
        from models.base.supplier import Supplier
        from models.core.reagent_bottle import ReagentBottle
        from models.core.borrow_record import BorrowRecord
        from models.core.return_record import ReturnRecord

        models = [Person, ChemicalInfo, ControlledList, Manufacturer,
                  ReagentType, StorageLocation, StorageRequirement, Supplier,
                  ReagentBottle, BorrowRecord, ReturnRecord]
        for model in models:
            self.assertTrue(hasattr(model, 'model_dump'),
                            f"{model.__name__} 不是 Pydantic 模型")

    def test_borrow_record_model(self):
        from models.core.borrow_record import BorrowRecord
        data = {"record_number": "202607070001", "bottle_number": "202607070001",
                "user": "张三", "reagent_name": "氯化钠", "is_controlled": 1,
                "approved": True}
        record = BorrowRecord(**data)
        self.assertEqual(record.record_number, "202607070001")
        self.assertEqual(record.user, "张三")
        self.assertTrue(record.approved)


# ============================================================================
# 密码工具函数测试
# ============================================================================

class TestPasswordUtils(unittest.TestCase):
    """测试密码哈希和验证功能"""

    def test_hash_and_verify(self):
        from utils.password_utils import hash_password, verify_password
        hashed = hash_password("secure_password_123")
        self.assertTrue(verify_password("secure_password_123", hashed))

    def test_wrong_password_fails(self):
        from utils.password_utils import hash_password, verify_password
        hashed = hash_password("correct_password")
        self.assertFalse(verify_password("wrong_password", hashed))

    def test_hash_format(self):
        from utils.password_utils import hash_password
        hashed = hash_password("test")
        self.assertTrue(hashed.startswith("pbkdf2:sha256:"))
        parts = hashed.split("$")
        self.assertEqual(len(parts), 3)

    def test_unique_salts(self):
        from utils.password_utils import hash_password
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        self.assertNotEqual(h1, h2)

    def test_is_password_hash_set(self):
        from utils.password_utils import is_password_hash_set, hash_password
        self.assertTrue(is_password_hash_set(hash_password("test")))
        self.assertFalse(is_password_hash_set(""))
        self.assertFalse(is_password_hash_set("not_a_hash"))

    def test_empty_password_hash(self):
        from utils.password_utils import verify_password
        self.assertFalse(verify_password("anything", ""))
        self.assertFalse(verify_password("", ""))

    def test_pbkdf2_iterations(self):
        from utils.password_utils import hash_password, HASH_ITERATIONS
        hashed = hash_password("test")
        parts = hashed.split(":", 2)
        iterations = int(parts[2].split("$")[0])
        self.assertGreaterEqual(iterations, HASH_ITERATIONS)


# ============================================================================
# 数据库单例测试
# ============================================================================

class TestDatabaseSingleton(unittest.TestCase):
    """测试数据库单例模式修复"""

    def test_different_paths_create_different_instances(self):
        from db.database import Database
        db1 = Database(os.path.join(project_root, "db/main.db"))
        db2 = Database(os.path.join(project_root, "db/archive_cold.db"))
        self.assertIsNot(db1, db2)

    def test_same_path_returns_same_instance(self):
        from db.database import Database
        path = os.path.join(project_root, "db/main.db")
        db1 = Database(path)
        db2 = Database(path)
        self.assertIs(db1, db2)

    def test_relative_path_normalization(self):
        from db.database import Database
        db1 = Database("db/main.db")
        db2 = Database(os.path.join(project_root, "db/main.db"))
        self.assertIs(db1, db2)


# ============================================================================
# ID 生成器测试
# ============================================================================

class TestIDGenerator(unittest.TestCase):
    """测试 ID 生成器格式"""

    def test_generate_bottle_number_format(self):
        from utils.id_generator import id_generator
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        bottle_no = id_generator.generate_bottle_number()
        self.assertEqual(len(bottle_no), 12)
        self.assertTrue(bottle_no.startswith(today))

    def test_generate_barcode_format(self):
        from utils.id_generator import id_generator
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        barcode = id_generator.generate_barcode()
        self.assertEqual(len(barcode), 12)
        self.assertTrue(barcode.startswith(today))

    def test_generate_borrow_record_number(self):
        from utils.id_generator import id_generator
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        record_no = id_generator.generate_borrow_record_number()
        self.assertEqual(len(record_no), 12)
        self.assertTrue(record_no.startswith(today))

    def test_generate_return_record_number(self):
        from utils.id_generator import id_generator
        from datetime import datetime
        today = datetime.now().strftime("%Y%m%d")
        return_no = id_generator.generate_return_record_number()
        self.assertEqual(len(return_no), 12)
        self.assertTrue(return_no.startswith(today))


# ============================================================================
# BaseService CRUD 测试
# ============================================================================

class TestBaseServiceCRUD(unittest.TestCase):
    """测试 BaseService 的 CRUD 操作"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        from db.database import Database
        self.db = Database(self.db_path)
        self.db.init_tables()
        from db.base_service import BaseService
        self.service = BaseService("person", db=self.db)

    def tearDown(self):
        self.db.close()
        shutil.rmtree(self.tmpdir)

    def test_create_and_get_by_id(self):
        record_id = self.service.create({"name": "测试用户", "role": "admin"})
        self.assertIsNotNone(record_id)
        record = self.service.get_by_id(record_id)
        self.assertEqual(record["name"], "测试用户")

    def test_update_record(self):
        record_id = self.service.create({"name": "原名称", "role": "user"})
        self.assertTrue(self.service.update(record_id, {"name": "新名称"}))
        self.assertEqual(self.service.get_by_id(record_id)["name"], "新名称")

    def test_delete_record(self):
        record_id = self.service.create({"name": "待删除"})
        self.assertTrue(self.service.delete(record_id))
        self.assertIsNone(self.service.get_by_id(record_id))

    def test_count(self):
        self.service.create({"name": "用户1"})
        self.service.create({"name": "用户2"})
        self.assertEqual(self.service.count(), 2)

    def test_search(self):
        self.service.create({"name": "氯化钠"})
        self.service.create({"name": "氢氧化钠"})
        self.service.create({"name": "硫酸铜"})
        results = self.service.search("氯化", ["name"])
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "氯化钠")

    def test_get_max_value_by_prefix(self):
        self.service.create({"name": "202607070001"})
        self.service.create({"name": "202607070005"})
        self.assertEqual(
            self.service.get_max_value_by_prefix("name", "20260707"),
            "202607070005")

    def test_get_max_value_by_prefix_empty(self):
        self.assertIsNone(
            self.service.get_max_value_by_prefix("name", "99999999"))

    def test_field_name_validation(self):
        with self.assertRaises(ValueError):
            self.service.get_by_field("name; DROP TABLE person;--", "test")

    def test_table_name_validation(self):
        from db.base_service import BaseService
        with self.assertRaises(ValueError):
            BaseService("person; DROP TABLE person;--", db=self.db)


# ============================================================================
# 服务集成测试基类
# ============================================================================

class _ServiceIntegrationTest(unittest.TestCase):
    """服务集成测试基类——使用临时数据库 + 重置服务单例"""

    def _setup_service(self, module_name, service_class_name, svc_attr_name):
        """通用方法：替换模块级服务单例为测试数据库版本"""
        m = __import__(module_name, fromlist=[service_class_name])
        svc_cls = getattr(m, service_class_name)
        self._orig = getattr(m, svc_attr_name)
        # 重置类级单例
        svc_cls._instance = None
        new_svc = svc_cls(db=self.db)
        setattr(m, svc_attr_name, new_svc)
        self._module = m
        self._svc_cls = svc_cls
        self._svc_attr = svc_attr_name
        return new_svc

    def _setup_business_service(self, module_name, service_class_name, svc_attr_name, **kwargs):
        """创建业务服务实例，注入测试服务依赖"""
        m = __import__(module_name, fromlist=[service_class_name])
        svc_cls = getattr(m, service_class_name)
        self._orig = getattr(m, svc_attr_name)
        new_svc = svc_cls(**kwargs)
        setattr(m, svc_attr_name, new_svc)
        self._module = m
        self._svc_cls = svc_cls
        self._svc_attr = svc_attr_name
        return new_svc

    def _restore_service(self):
        svc_cls = self._svc_cls
        svc_cls._instance = None
        setattr(self._module, self._svc_attr, self._orig)

    def _setup_db(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        from db.database import Database
        self.db = Database(self.db_path)
        self.db.init_tables()

    def tearDown(self):
        self.db.close()
        self._restore_service()
        shutil.rmtree(self.tmpdir)


# ============================================================================
# 权限服务集成测试
# ============================================================================

class TestPermissionService(_ServiceIntegrationTest):
    """测试权限服务（集成测试）"""

    def setUp(self):
        self._setup_db()
        self.test_ps = self._setup_service(
            'services.base.person_service', 'PersonService', 'person_service')
        self.test_perm = self._setup_business_service(
            'business.permission_service', 'PermissionService', 'permission_service',
            person_service=self.test_ps)

        self.test_ps.create({"name": "超级管理员", "role": "super_admin"})
        self.test_ps.create({"name": "管理员", "role": "admin"})
        self.test_ps.create({"name": "教师", "role": "teacher"})
        self.test_ps.create({"name": "普通用户", "role": "user"})

    def test_super_admin_permission(self):
        self.assertTrue(self.test_perm.check_permission("超级管理员", "super_admin")[0])

    def test_admin_permission(self):
        self.assertTrue(self.test_perm.check_permission("管理员", "admin")[0])

    def test_teacher_permission(self):
        self.assertTrue(self.test_perm.check_permission("教师", "teacher")[0])

    def test_user_permission(self):
        self.assertTrue(self.test_perm.check_permission("普通用户", "user")[0])

    def test_insufficient_permission(self):
        self.assertFalse(self.test_perm.check_permission("普通用户", "admin")[0])

    def test_user_not_found(self):
        self.assertFalse(self.test_perm.check_permission("不存在", "user")[0])

    def test_is_admin(self):
        self.assertTrue(self.test_perm.is_admin("超级管理员"))
        self.assertTrue(self.test_perm.is_admin("管理员"))
        self.assertFalse(self.test_perm.is_admin("普通用户"))

    def test_get_user_role(self):
        self.assertEqual(self.test_perm.get_user_role("超级管理员"), "super_admin")
        self.assertEqual(self.test_perm.get_user_role("教师"), "teacher")
        self.assertEqual(self.test_perm.get_user_role("不存在"), "user")


# ============================================================================
# 密码认证集成测试
# ============================================================================

class TestPasswordAuthentication(_ServiceIntegrationTest):
    """测试密码认证服务（集成测试）"""

    def setUp(self):
        self._setup_db()
        self.test_ps = self._setup_service(
            'services.base.person_service', 'PersonService', 'person_service')
        self.test_ps.create({"name": "测试用户", "role": "user"})

    def test_set_and_authenticate(self):
        self.assertTrue(self.test_ps.set_password("测试用户", "my_password_123").is_success())
        result = self.test_ps.authenticate("测试用户", "my_password_123")
        self.assertTrue(result.is_success())
        self.assertEqual(result.data.name, "测试用户")

    def test_wrong_password_fails(self):
        self.test_ps.set_password("测试用户", "correct_password")
        result = self.test_ps.authenticate("测试用户", "wrong_password")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "WRONG_PASSWORD")

    def test_no_password_set(self):
        result = self.test_ps.authenticate("测试用户", "any_password")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "PASSWORD_NOT_SET")

    def test_weak_password_rejected(self):
        result = self.test_ps.set_password("测试用户", "123")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "WEAK_PASSWORD")

    def test_user_not_found_auth(self):
        result = self.test_ps.authenticate("不存在", "any_password")
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "USER_NOT_FOUND")

    def test_has_password_check(self):
        self.assertFalse(self.test_ps.has_password("测试用户"))
        self.test_ps.set_password("测试用户", "valid_password_123")
        self.assertTrue(self.test_ps.has_password("测试用户"))


# ============================================================================
# 入库服务集成测试
# ============================================================================

class TestInventoryService(_ServiceIntegrationTest):
    """测试入库服务（集成测试）"""

    def setUp(self):
        self._setup_db()
        self.test_cs = self._setup_service(
            'services.base.chemical_service', 'ChemicalService', 'chemical_service')
        self.test_ss = self._setup_service(
            'services.base.supplier_service', 'SupplierService', 'supplier_service')
        self.test_sls = self._setup_service(
            'services.base.storage_location_service', 'StorageLocationService', 'storage_location_service')
        self.test_rbs = self._setup_service(
            'services.core.reagent_bottle_service', 'ReagentBottleService', 'reagent_bottle_service')
        self.test_invs = self._setup_business_service(
            'business.inventory_service', 'InventoryService', 'inventory_service',
            chemical_service=self.test_cs, supplier_service=self.test_ss,
            storage_location_service=self.test_sls, reagent_bottle_service=self.test_rbs)

        self.test_cs.create({"name": "氯化钠", "cas_number": "7647-14-5"})
        self.test_ss.create({"name": "测试供应商"})
        self.test_sls.create({"name": "测试位置"})

    def test_validate_inputs_valid(self):
        result = self.test_invs.validate_inventory_inputs(
            "氯化钠", "7647-14-5", 100.0, 500.0)
        self.assertTrue(result.is_success())

    def test_validate_inputs_empty_name(self):
        result = self.test_invs.validate_inventory_inputs("", "", 100, 500)
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "EMPTY_REAGENT_NAME")

    def test_validate_inputs_quantity_exceeds(self):
        result = self.test_invs.validate_inventory_inputs(
            "氯化钠", "7647-14-5", 600, 500)
        self.assertTrue(result.is_failure())
        self.assertEqual(result.error_code, "QUANTITY_EXCEEDS_SPECIFICATION")

    def test_create_inventory_record(self):
        result = self.test_invs.create_inventory_record(
            reagent_name="氯化钠", cas_number="7647-14-5",
            remaining_quantity=100, specification=500,
            purity="分析纯", supplier="测试供应商", storage_location="测试位置")
        self.assertTrue(result.is_success(), f"入库失败: {result.message}")
        self.assertIn("bottle_number", result.data)
        self.assertIn("barcode", result.data)


# ============================================================================
# 运行入口
# ============================================================================

if __name__ == "__main__":
    unittest.main(verbosity=2)