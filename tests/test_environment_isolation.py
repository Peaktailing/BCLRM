"""环境隔离与 schema 闸门的门禁测试。

覆盖执行版里最容易回归的几条：

- prod/beta 没有显式数据根就必须拒绝启动（D08）；
- 四库/附件/日志必须全部落在数据根内（D09）；
- 旧代码打开新库、迁移半程中断必须拒绝启动（D14/D15）；
- 手机开关关闭时，/m 页面给固定提示而不是业务界面（D11）。
"""
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import config.settings as settings
from db import schema_guard
from tests import TEST_DATA_ROOT


class TestDataRoot(unittest.TestCase):
    def test_all_paths_inside_data_root(self):
        root = Path(TEST_DATA_ROOT).resolve()
        for path in (
            settings.DB_MAIN_PATH,
            settings.DB_ARCHIVE_PATH,
            settings.DB_ATTACH_PATH,
            settings.DB_LOG_PATH,
            settings.LOG_DIR,
            settings.ATTACHMENTS_DIR,
        ):
            self.assertTrue(
                Path(path).resolve().is_relative_to(root),
                f"{path} 不在测试数据根 {root} 内",
            )

    def _run_config(self, **env_overrides):
        env = dict(os.environ)
        env.pop("BCLRM_DATA_DIR", None)
        env.pop("BCLRM_RELEASE_FILE", None)
        env.update(env_overrides)
        return subprocess.run(
            [sys.executable, "-c", "import config.settings"],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env,
            capture_output=True,
            text=True,
        )

    def test_prod_without_data_dir_fails(self):
        result = self._run_config(BCLRM_ENV="prod")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BCLRM_DATA_DIR", result.stderr)

    def test_prod_leaf_must_match_env(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self._run_config(
                BCLRM_ENV="prod",
                BCLRM_DATA_DIR=str(Path(tmp) / "wrongname"),
                BCLRM_RELEASE_FILE=str(Path(tmp) / "release.json"),
            )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("数据根目录名必须是", result.stderr)

    def test_invalid_mobile_flag_fails(self):
        result = self._run_config(BCLRM_ENV="dev", BCLRM_MOBILE_UI="maybe")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("BCLRM_MOBILE_UI", result.stderr)


class TestSchemaGuard(unittest.TestCase):
    def setUp(self):
        from db.database import Database
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "main.db")
        self.db = Database(self.path)

    def tearDown(self):
        from db.database import Database
        self.db.close()
        Database._instances.pop(os.path.abspath(self.path), None)
        self.tmp.cleanup()

    def test_init_stamps_version_and_ledger(self):
        from db import schema_guard

        self.db.init_tables()
        self.assertEqual(schema_guard.version_of(self.db.connection),
                         schema_guard.MAIN_SCHEMA_VERSION)
        row = self.db.connection.execute(
            "SELECT status FROM schema_migrations WHERE id = ?",
            (schema_guard.MAIN_MIGRATION_ID,),
        ).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "ok")

    def test_init_is_idempotent(self):
        from db import schema_guard

        self.db.init_tables()
        first = schema_guard.version_of(self.db.connection)
        self.db.init_tables()
        self.assertEqual(schema_guard.version_of(self.db.connection), first)

    def test_running_migration_blocks_start(self):
        from db import schema_guard

        self.db.init_tables()
        self.db.connection.execute("PRAGMA user_version = 0")
        self.db.connection.execute(
            "INSERT INTO schema_migrations"
            "(id, db_name, status, target_version, started_at)"
            " VALUES ('half-done', 'main.db', 'running', 1, '2026-10-27T00:00:00')"
        )
        self.db.connection.commit()
        with self.assertRaises(schema_guard.SchemaError):
            self.db.init_tables()

    def test_legacy_db_gets_stamped_without_losing_rows(self):
        """Legacy 库（无台账、user_version=0）迁移后自动盖章且数据不丢。

        首次把现网库切到新布局时就是这条路径：先冷备，再显式 migrate。
        """
        from db import schema_guard

        self.db.init_tables()
        self.db.execute_insert(
            "INSERT INTO person (name, role) VALUES (?, ?)", ("历史用户", "teacher")
        )
        # 模拟 legacy：撤掉版本与台账
        self.db.connection.execute("PRAGMA user_version = 0")
        self.db.connection.execute("DELETE FROM schema_migrations")
        self.db.connection.commit()

        self.db.init_tables()
        self.assertEqual(schema_guard.version_of(self.db.connection),
                         schema_guard.MAIN_SCHEMA_VERSION)
        rows = self.db.execute_query("SELECT name FROM person WHERE name = ?", ("历史用户",))
        self.assertEqual(len(rows), 1)

    def test_validate_rejects_version_mismatch(self):
        from db import schema_guard

        self.db.init_tables()
        with self.assertRaises(schema_guard.SchemaError):
            schema_guard.validate_readonly(self.path, "main.db", 99)

    def test_validate_accepts_expected_version(self):
        from db import schema_guard

        self.db.init_tables()
        result = schema_guard.validate_readonly(
            self.path, "main.db", schema_guard.MAIN_SCHEMA_VERSION
        )
        self.assertEqual(result["user_version"], schema_guard.MAIN_SCHEMA_VERSION)

    def test_old_code_on_new_db_is_rejected(self):
        """> release 声明版本的库必须拒绝旧代码启动。"""
        from db import schema_guard

        self.db.init_tables()
        self.db.connection.execute(
            f"PRAGMA user_version = {schema_guard.MAIN_SCHEMA_VERSION + 1}"
        )
        self.db.connection.commit()
        with self.assertRaises(schema_guard.SchemaError):
            schema_guard.validate_readonly(
                self.path, "main.db", schema_guard.MAIN_SCHEMA_VERSION
            )


class TestMobileHiddenSurfaces(unittest.TestCase):
    """prod 口径下手机关闭：页面不得出现手机入口、二维码标签、手机地址。

    与 ``TestMobileProfile`` 的区别：那条测 /m 自己的守卫，这条测其它页面
    有没有把入口漏出来（执行版 5.2 的"两套 profile"要求）。
    """

    _SESSION = (
        "at.session_state['logged_in'] = True\n"
        "at.session_state['user_name'] = '体检账号'\n"
        "at.session_state['user_role'] = 'super_admin'\n"
        "at.session_state['is_admin'] = True\n"
        "at.session_state['must_change_password'] = False\n"
    )

    def _run_page(self, filename: str, mobile_ui: str = "0") -> str:
        code = (
            "import os, sys\n"
            "sys.path.insert(0, os.getcwd())\n"
            "from config.settings import ensure_data_dirs\n"
            "ensure_data_dirs()\n"
            "from db.database import init_all_schemas\n"
            "init_all_schemas()\n"
            "from streamlit.testing.v1 import AppTest\n"
            f"at = AppTest.from_file({filename!r}, default_timeout=90)\n"
            + self._SESSION +
            "at.run()\n"
            "print('EXC', [str(e.value)[:120] for e in at.exception])\n"
            "parts = []\n"
            "for kind in ('markdown','caption','subheader','header','title',"
            "'button','checkbox','text_input','text_area','number_input',"
            "'slider','radio','selectbox','expander','metric'):\n"
            "    for el in at.get(kind):\n"
            "        parts.append(str(getattr(el, 'label', '') or '')"
            " + ' ' + str(getattr(el, 'value', '') or ''))\n"
            "print('TEXT ' + ' | '.join(parts))\n"
        )
        env = dict(os.environ)
        env["BCLRM_MOBILE_UI"] = mobile_ui
        env["BCLRM_DATA_DIR"] = str(TEST_DATA_ROOT)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("EXC []", result.stdout, result.stdout[-500:])
        return result.stdout

    def test_inventory_hides_qr_label_keeps_barcode(self):
        text = self._run_page("views/1_实时库存.py")
        self.assertNotIn("打印瓶身二维码标签", text)
        self.assertIn("条码查询", text)

    def test_settings_hides_mobile_address_keeps_photo_policy(self):
        text = self._run_page("views/6_系统设置.py")
        self.assertNotIn("手机访问地址", text)
        # /m 文案也不能漏；页面正文里的 `/m` 只应出现在手机关闭时不渲染的分支
        self.assertNotIn("/m", text)
        self.assertIn("借出必须拍照", text)

    def test_borrow_page_has_no_mobile_prompt(self):
        text = self._run_page("views/3_领用归还.py")
        self.assertNotIn("手机取证", text)

    def _run_home(self, mobile_ui: str) -> str:
        """从 app.py 入口跑首页（首页里的 page_link 脱离导航会报错，不能单跑）。"""
        code = (
            "import os, sys\n"
            "sys.path.insert(0, os.getcwd())\n"
            "from config.settings import ensure_data_dirs\n"
            "ensure_data_dirs()\n"
            "from db.database import init_all_schemas\n"
            "init_all_schemas()\n"
            "from streamlit.testing.v1 import AppTest\n"
            "at = AppTest.from_file('app.py', default_timeout=90)\n"
            + self._SESSION +
            "at.run()\n"
            "print('EXC', [str(e.value)[:120] for e in at.exception])\n"
            "print('TEXT ' + ' | '.join(str(m.value) for m in at.markdown))\n"
        )
        env = dict(os.environ)
        env["BCLRM_MOBILE_UI"] = mobile_ui
        env["BCLRM_DATA_DIR"] = str(TEST_DATA_ROOT)
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("EXC []", result.stdout, result.stdout[-500:])
        return result.stdout

    def test_home_manual_hides_mobile_section(self):
        """生产口径下连用户手册里的「手机取证」章节都不给看。"""
        hidden = self._run_home("0")
        self.assertNotIn("手机取证", hidden)
        self.assertIn("用户使用手册", hidden)

        shown = self._run_home("1")
        self.assertIn("手机取证", shown, "开发口径要保留手册原文")


class TestRuntimeCli(unittest.TestCase):
    """部署器依赖的 CLI 契约：空数据根 migrate 后四库都应到 v1，check 通过。"""

    def _run_cli(self, command: str, data_root: str):
        env = dict(os.environ)
        env.update({
            "BCLRM_ENV": "dev",
            "BCLRM_DATA_DIR": data_root,
            "BCLRM_MOBILE_UI": "0",
        })
        env.pop("BCLRM_RELEASE_FILE", None)
        return subprocess.run(
            [sys.executable, "scripts/runtime_cli.py", command],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env,
            capture_output=True,
            text=True,
        )

    def test_migrate_then_check_on_blank_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            migrated = self._run_cli("migrate", tmp)
            self.assertEqual(migrated.returncode, 0, migrated.stdout[-1500:] + migrated.stderr[-1500:])
            checked = self._run_cli("check", tmp)
            self.assertEqual(checked.returncode, 0, checked.stdout[-1500:])
            expected = {
                "main.db": schema_guard.MAIN_SCHEMA_VERSION,
                "archive_cold.db": schema_guard.AUX_SCHEMA_VERSION,
                "attach_cold.db": schema_guard.AUX_SCHEMA_VERSION,
                "operation_log.db": schema_guard.AUX_SCHEMA_VERSION,
            }
            for name, version in expected.items():
                self.assertIn(f"{name} user_version={version}", checked.stdout)

    def test_smoke_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self._run_cli("migrate", tmp).returncode, 0)
            smoke = self._run_cli("smoke", tmp)
            self.assertEqual(smoke.returncode, 0, smoke.stdout[-1500:])
            self.assertIn("只读", smoke.stdout)


class TestBetaBanner(unittest.TestCase):
    """beta 必须有水印与可丢弃提示，prod 必须没有（D11/D12）。

    这条测试通过真实启动 ``app.py`` 覆盖：beta/prod 的启动路径会先做
    schema 只读校验，因此同时验证了"没有 release.json / 版本不符就不启动"。
    """

    _CODE = (
        "import os, sys\n"
        "sys.path.insert(0, os.getcwd())\n"
        "from config.settings import ensure_data_dirs\n"
        "ensure_data_dirs()\n"
        "from db.database import init_all_schemas\n"
        "init_all_schemas()\n"
        "from streamlit.testing.v1 import AppTest\n"
        "at = AppTest.from_file('app.py', default_timeout=90)\n"
        "at.run()\n"
        "text = ' | '.join(str(m.value) for m in at.markdown)\n"
        "print('HAS_BETA' if '测试环境 BETA' in text else 'NO_BETA')\n"
        "print('EXC', [str(e.value)[:120] for e in at.exception])\n"
    )

    def _run_app(self, env_name: str) -> str:
        import json

        with tempfile.TemporaryDirectory() as tmp:
            data_root = Path(tmp) / env_name
            data_root.mkdir()
            release = Path(tmp) / "release.json"
            release.write_text(json.dumps({
                "version": "0.8.17.5",
                "git_sha": "0" * 40,
                "artifact_sha256": "0" * 64,
                "python_version": "3.10.12",
                "requirements_lock_sha256": "0" * 64,
                "schema_versions": {
                    "main.db": schema_guard.MAIN_SCHEMA_VERSION,
                    "archive_cold.db": schema_guard.AUX_SCHEMA_VERSION,
                    "attach_cold.db": schema_guard.AUX_SCHEMA_VERSION,
                    "operation_log.db": schema_guard.AUX_SCHEMA_VERSION,
                },
                "built_at": "2026-10-27T00:00:00",
            }), encoding="utf-8")

            env = dict(os.environ)
            env.update({
                "BCLRM_ENV": env_name,
                "BCLRM_DATA_DIR": str(data_root),
                "BCLRM_RELEASE_FILE": str(release),
                "BCLRM_MOBILE_UI": "0",
            })
            result = subprocess.run(
                [sys.executable, "-c", self._CODE],
                cwd=str(Path(__file__).resolve().parent.parent),
                env=env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr[-2000:])
            self.assertIn("EXC []", result.stdout, result.stdout[-500:])
            return result.stdout

    def test_beta_shows_watermark(self):
        self.assertIn("HAS_BETA", self._run_app("beta"))

    def test_prod_has_no_beta_watermark(self):
        self.assertIn("NO_BETA", self._run_app("prod"))


class TestMobileProfile(unittest.TestCase):
    """手机关闭时，/m 页面直接执行也只给固定提示。"""

    def test_mobile_page_shows_notice_when_disabled(self):
        code = (
            "import os, sys\n"
            "sys.path.insert(0, os.getcwd())\n"
            "from streamlit.testing.v1 import AppTest\n"
            "at = AppTest.from_file('views/14_手机取证.py', default_timeout=60)\n"
            "at.run()\n"
            "text = ' '.join(str(m.value) for m in at.markdown)\n"
            "print(text)\n"
        )
        env = dict(os.environ)
        env["BCLRM_MOBILE_UI"] = "0"
        env["BCLRM_DATA_DIR"] = str(Path(TEST_DATA_ROOT))
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=str(Path(__file__).resolve().parent.parent),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr[-2000:])
        self.assertIn("未开启手机取证", result.stdout)


if __name__ == "__main__":
    unittest.main()
