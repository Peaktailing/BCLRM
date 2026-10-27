#!/usr/bin/env python3
"""升级演练（执行版 4.4/6 节 Stage 0B）。

选择一份**已验证**快照 → 恢复到临时目录 → 用目标 release 在 8700 起的空闲
端口启动（绝不占用 8501/8601）→ 依次执行 runtime_cli check / migrate /
check / smoke → 写报告。演练不触碰生产目录，也不写生产数据根。

``--no-server`` 仅用于单元测试/无 Streamlit 环境的离线排查：跳过端口启动，
其余迁移与冒烟步骤照常执行。

退出码：0 通过；2 快照/release 预检失败；3 演练执行失败。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from deploy import release_layout as layout  # noqa: E402
from utils import backup as backup_mod  # noqa: E402


def _truncate(text: str, limit: int = 4000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[截断]"


def _step(name: str, result: subprocess.CompletedProcess) -> Dict[str, Any]:
    return {
        "step": name,
        "returncode": result.returncode,
        "stdout": _truncate(result.stdout),
        "stderr": _truncate(result.stderr),
    }


def _start_server(release: Path, data_root: Path, python: str,
                  port: int, log_path: Path) -> subprocess.Popen:
    """在独立进程组启动 Streamlit，便于一次 terminate 收掉子进程。"""
    payload = layout.payload_dir(release)
    command = [
        layout.interpreter_for(release, python), "-m", "streamlit", "run", "app.py",
        "--server.port", str(port), "--server.address", "127.0.0.1",
        "--server.headless", "true", "--browser.gatherUsageStats", "false",
    ]
    log = open(log_path, "wb")
    return subprocess.Popen(
        command, cwd=str(payload),
        env=layout.runtime_env("beta", data_root, release),
        stdout=log, stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def _stop_server(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=20)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass


def rehearse(
    *, root: Path, snapshot: Path, release: Path, python: str,
    port_start: int, health_timeout: float, no_server: bool,
    report_path: Optional[Path], keep: bool,
) -> Dict[str, Any]:
    release = Path(release)
    doc = layout.read_release(release)
    if not layout.payload_dir(release).is_dir():
        raise layout.LayoutError(f"release 缺少 payload：{layout.payload_dir(release)}")
    report = backup_mod.verify_snapshot(Path(snapshot))
    if not report["ok"]:
        raise backup_mod.BackupVerificationError(
            "快照校验失败：" + "; ".join(report["errors"][:5])
        )

    workspace = Path(tempfile.mkdtemp(prefix="bclrm-rehearse-"))
    target = workspace / "beta"  # 叶目录必须等于 BCLRM_ENV
    result: Dict[str, Any] = {
        "ok": False,
        "started_at": layout.utc_now_iso(),
        "snapshot": str(snapshot),
        "release": str(release),
        "version": doc["version"],
        "git_sha": doc["git_sha"],
        "schema_versions": doc["schema_versions"],
        "workspace": str(workspace),
        "port": None,
        "health": False,
        "steps": [],
        "errors": [],
        "warnings": [],
        "no_server": no_server,
    }
    process = None
    server_log = workspace / "server.log"
    try:
        backup_mod.restore_snapshot(Path(snapshot), target, replace=False)
        if not no_server:
            port = layout.find_free_port(port_start)
            if port in (8501, 8601):
                raise layout.ExecutionFailure("端口分配命中了生产/验收端口")
            result["port"] = port
            process = _start_server(release, target, python, port, server_log)
            health_url = f"http://127.0.0.1:{port}/_stcore/health"
            result["health"] = layout.wait_http_ok(health_url, timeout=health_timeout)
            if not result["health"]:
                tail = ""
                if server_log.is_file():
                    tail = _truncate(server_log.read_text(encoding="utf-8",
                                                          errors="replace")[-2000:])
                raise layout.ExecutionFailure(
                    f"目标 release 在备用端口 {port} 未通过健康检查：{tail}"
                )

        # check（迁移前）允许因 schema 落后失败，只记录，不计入失败
        pre = layout.run_runtime_cli(release, "check", "beta", target,
                                     python=python)
        result["steps"].append(_step("check(before migrate)", pre))
        if pre.returncode != 0:
            result["warnings"].append("迁移前 check 未通过（旧 schema 属预期，迁移后再判定）")

        migrate = layout.run_runtime_cli(release, "migrate", "beta", target,
                                         python=python)
        result["steps"].append(_step("migrate", migrate))
        if migrate.returncode != 0:
            result["errors"].append("migrate 失败")

        check = layout.run_runtime_cli(release, "check", "beta", target,
                                       python=python)
        result["steps"].append(_step("check(after migrate)", check))
        if check.returncode != 0:
            result["errors"].append("迁移后 check 失败")

        smoke = layout.run_runtime_cli(release, "smoke", "beta", target,
                                       python=python)
        result["steps"].append(_step("smoke", smoke))
        if smoke.returncode != 0:
            result["errors"].append("smoke 失败")
    except (layout.LayoutError, layout.ExecutionFailure,
            backup_mod.BackupVerificationError, backup_mod.BackupError,
            OSError) as exc:
        result["errors"].append(str(exc))
    finally:
        if process is not None:
            _stop_server(process)
        result["finished_at"] = layout.utc_now_iso()
        result["ok"] = not result["errors"]

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        destination = report_path or (
            Path(root) / "logs" / "rehearsals" / f"{stamp}-{result['version']}.json"
        )
        layout.write_json_atomic(Path(destination), result)

        status_file = Path(root) / "logs" / "cron_status.json"
        try:
            status = layout.read_json(status_file, required=False)
        except layout.LayoutError:
            status = {}
        status["rehearsal"] = {
            "ok": result["ok"],
            "at": result["finished_at"],
            "version": result["version"],
            "snapshot": result["snapshot"],
            "report": str(destination),
            "errors": result["errors"][:5],
        }
        layout.write_json_atomic(status_file, status)

        if not keep:
            shutil.rmtree(workspace, ignore_errors=True)
    result["report"] = str(destination)
    return result


def resolve_snapshot(args: argparse.Namespace) -> Path:
    if args.snapshot:
        return Path(args.snapshot)
    latest = backup_mod.latest_snapshot(
        Path(args.root), args.env, kind=args.kind, require_verified=True
    )
    if latest is None:
        raise layout.LayoutError("没有可用已验证快照，先执行 backup.py")
    return latest


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="在备用端口演练快照升级")
    parser.add_argument("--root", default=str(layout.DEFAULT_ROOT))
    parser.add_argument("--snapshot", help="已验证快照目录")
    parser.add_argument("--env", default="prod", choices=("prod", "beta"),
                        help="未给 --snapshot 时取该环境最近验证快照")
    parser.add_argument("--kind", choices=backup_mod.BACKUP_KINDS)
    parser.add_argument("--release", type=Path, help="目标 release 目录")
    parser.add_argument("--version", help="目标版本（与 --release 二选一）")
    parser.add_argument("--python", help="解释器覆盖（默认 release/.venv/bin/python）")
    parser.add_argument("--port-start", type=int, default=8700)
    parser.add_argument("--health-timeout", type=float, default=90.0)
    parser.add_argument("--no-server", action="store_true",
                        help="跳过端口启动（仅测试/离线排查）")
    parser.add_argument("--report", type=Path, help="报告输出路径")
    parser.add_argument("--keep", action="store_true", help="保留恢复现场")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    if bool(args.release) == bool(args.version):
        parser.error("--release 与 --version 必须二选一")
    root = Path(args.root)
    release = args.release or layout.release_dir(root, args.version)
    try:
        snapshot = resolve_snapshot(args)
        if args.port_start in (8501, 8601):
            raise layout.LayoutError("--port-start 不得是生产/验收端口")
        result = rehearse(
            root=root, snapshot=snapshot, release=release,
            python=args.python or sys.executable,
            port_start=args.port_start, health_timeout=args.health_timeout,
            no_server=args.no_server, report_path=args.report, keep=args.keep,
        )
    except layout.LayoutError as exc:
        print(f"[FAIL] 预检失败：{exc}")
        return 2
    except backup_mod.BackupVerificationError as exc:
        print(f"[FAIL] 快照校验失败：{exc}")
        return 2
    except (OSError, backup_mod.BackupError) as exc:
        print(f"[FAIL] 演练执行失败：{exc}")
        return 3

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        print(f"[INFO] snapshot={result['snapshot']}")
        print(f"[INFO] release={result['version']} port={result['port']} "
              f"health={result['health']}")
        for step in result["steps"]:
            print(f"[INFO] {step['step']} -> {step['returncode']}")
        for warning in result["warnings"]:
            print(f"[WARN] {warning}")
        for error in result["errors"]:
            print(f"[FAIL] {error}")
        print(f"[INFO] 报告：{result.get('report')}")
        print("[ OK ] 演练通过" if result["ok"] else "[FAIL] 演练未通过")
    return 0 if result["ok"] else 3


if __name__ == "__main__":
    sys.exit(main())
