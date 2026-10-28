#!/usr/bin/env python3
"""生产每日维护：停机冷备 → 校验/轮换 → 代码备份 → 异地同步 → 重启。

顺序固定（负责人 2026-10-28 指定）：

1. 停 ``bclrm-prod.service``，确认 inactive 且 8501 不再监听；
2. 冷备 daily（``--service-stopped``，工具自身会校验四库完整性）；
3. 校验新快照；按保留策略轮换（每日 7 天、1/15 日档 3 个自然月等）；
4. 生成代码 git bundle（含未提交 diff 快照与清单）；
5. 重启 prod 并等待健康端点；
6. 服务恢复后再做异地同步（不占停服窗口）。

纪律：
- **绝不清理任何业务表**；本工具没有、也不得增加清表步骤。
- 只要开始时 prod 是 active，就一定会尝试拉回；unit 的 ExecStopPost 再兜底。
- 默认 dry-run；``--execute`` 才真正停服。手动执行：
  ``systemctl --user start bclrm-maintenance.service`` 或
  ``/usr/bin/python3 /home/biochm/BCLRM/ops/daily_maintenance.py --execute``。
- 退出码：0 全部成功；2 预检失败（未停服）；3 执行失败（服务仍会拉回）。
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import shlex
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_ROOT = Path("/home/biochm/BCLRM")
DEFAULT_CODE_REPO = Path(
    "/home/biochm/WorkBuddy/2026-10-21-14-45-03/repos/BCLRM"
)
VAULT = Path("/data/bclrm/vault")
CODE_RETENTION_DAYS = 90
MIN_FREE_GIB = 5.0
STOP_TIMEOUT = 60
HEALTH_TIMEOUT = 120


class PreflightError(RuntimeError):
    """预检失败：不动服务。"""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(moment: Optional[datetime] = None) -> str:
    value = moment or _now()
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat()


def _stamp(moment: Optional[datetime] = None) -> str:
    value = moment or _now()
    return value.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _log(message: str) -> None:
    print(f"[{_iso()}] {message}", flush=True)


def _run(command: List[str], *, timeout: int = 900) -> subprocess.CompletedProcess:
    return subprocess.run(
        command, capture_output=True, text=True, timeout=timeout
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json_atomic(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


class Maintenance:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.root = Path(args.root)
        self.code_repo = Path(args.code_repo)
        self.code_dir = Path(args.code_dir) if args.code_dir else (VAULT / "code")
        self.python = self.root / "current_prod" / ".venv" / "bin" / "python"
        self.payload = self.root / "current_prod" / "payload" / "scripts"
        self.systemctl = shlex.split(args.systemctl)
        self.steps: List[Dict[str, Any]] = []
        self.snapshot: Optional[Path] = None
        self.started = _now()
        self.was_active = False
        self.restart: Optional[Dict[str, Any]] = None

    # -- 记录 ---------------------------------------------------------
    def step(self, name: str, ok: bool, detail: Any = None,
             seconds: Optional[float] = None) -> None:
        entry: Dict[str, Any] = {"name": name, "ok": ok, "at": _iso()}
        if detail is not None:
            entry["detail"] = detail
        if seconds is not None:
            entry["seconds"] = round(seconds, 2)
        self.steps.append(entry)
        mark = "OK  " if ok else "FAIL"
        _log(f"{mark} {name}" + (f" — {detail}" if detail else ""))

    # -- 预检 ---------------------------------------------------------
    def preflight(self) -> None:
        if not (self.root / "data" / "prod" / "db" / "main.db").is_file():
            raise PreflightError(f"prod 数据根不存在：{self.root / 'data' / 'prod'}")
        backups = (self.root / "backups").resolve()
        if self.root.resolve() == DEFAULT_ROOT.resolve():
            if not VAULT.is_mount():
                raise PreflightError(
                    f"加密备份卷未挂载：{VAULT}（先 systemctl start data-bclrm-vault.mount）"
                )
            if VAULT not in backups.parents:
                raise PreflightError(f"backups 未指向加密卷：{backups}")
        if not self.code_dir.is_dir():
            raise PreflightError(f"代码备份目录不存在：{self.code_dir}")
        free = shutil.disk_usage(self.code_dir).free / (1024 ** 3)
        if free < MIN_FREE_GIB:
            raise PreflightError(f"加密卷可用空间 {free:.1f} GiB 低于 {MIN_FREE_GIB} GiB")
        for path in (self.python, self.payload / "backup.py",
                     self.payload / "verify_backup.py",
                     self.payload / "prune_backups.py"):
            if not path.exists():
                raise PreflightError(f"缺少工具：{path}")
        if not (self.code_repo / ".git").exists():
            raise PreflightError(f"代码仓库不存在：{self.code_repo}")
        if shutil.which("git") is None:
            raise PreflightError("PATH 中找不到 git")

    # -- 服务控制 -----------------------------------------------------
    def _systemctl_run(self, verb: str, *extra: str) -> subprocess.CompletedProcess:
        return _run([*self.systemctl, verb, *extra], timeout=120)

    def service_active(self) -> bool:
        return self._systemctl_run("is-active", "--quiet", self.args.unit).returncode == 0

    def port_open(self) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", self.args.port), timeout=0.5):
                return True
        except OSError:
            return False

    def stop_service(self) -> None:
        started = time.monotonic()
        result = self._systemctl_run("stop", self.args.unit)
        if result.returncode != 0:
            raise RuntimeError(f"停服失败：{result.stderr.strip()[:300]}")
        deadline = time.monotonic() + STOP_TIMEOUT
        while time.monotonic() < deadline:
            if not self.service_active() and not self.port_open():
                self.step("stop-prod", True, f"{self.args.unit} inactive，端口已释放",
                          time.monotonic() - started)
                return
            time.sleep(1)
        raise RuntimeError(
            f"{STOP_TIMEOUT}s 内未确认停机（active={self.service_active()}, "
            f"port_open={self.port_open()}）；未做冷备"
        )

    def health_ok(self) -> bool:
        url = f"http://127.0.0.1:{self.args.port}/_stcore/health"
        try:
            with urllib.request.urlopen(url, timeout=3) as response:
                return response.status == 200 and response.read().strip() == b"ok"
        except (urllib.error.URLError, OSError):
            return False

    def restart_service(self) -> bool:
        started = time.monotonic()
        result = self._systemctl_run("start", self.args.unit)
        if result.returncode != 0:
            self.restart = {"ok": False, "error": result.stderr.strip()[:500]}
            self.step("restart-prod", False, self.restart["error"],
                      time.monotonic() - started)
            return False
        deadline = time.monotonic() + HEALTH_TIMEOUT
        while time.monotonic() < deadline:
            if self.health_ok():
                self.restart = {"ok": True, "health": "200 ok",
                                "seconds": round(time.monotonic() - started, 2)}
                self.step("restart-prod", True,
                          f"{self.args.unit} active，健康端点 200",
                          time.monotonic() - started)
                return True
            time.sleep(2)
        self.restart = {"ok": False, "error": f"{HEALTH_TIMEOUT}s 内健康检查未通过"}
        self.step("restart-prod", False, self.restart["error"],
                  time.monotonic() - started)
        return False

    # -- 备份步骤 -----------------------------------------------------
    def cold_backup(self) -> None:
        started = time.monotonic()
        command = [
            str(self.python), str(self.payload / "backup.py"),
            "--root", str(self.root), "--env", "prod", "--kind", "daily",
            "--mode", "cold", "--service-stopped", "--source", "timer",
            "--label", "daily-0500", "--json",
        ]
        result = _run(command)
        if result.returncode != 0:
            raise RuntimeError(
                f"冷备失败（exit {result.returncode}）：{result.stderr.strip()[:500]}"
            )
        try:
            payload = json.loads(result.stdout[result.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError):
            payload = {}
        snapshot = payload.get("snapshot")
        if not snapshot:
            raise RuntimeError(f"冷备输出缺少 snapshot：{result.stdout[-500:]}")
        self.snapshot = Path(snapshot)
        self.step("cold-backup", True, str(snapshot), time.monotonic() - started)

        if _now().day in (1, 15):
            self.clone_semimonthly()

    def clone_semimonthly(self) -> None:
        started = time.monotonic()
        command = [
            str(self.python), str(self.payload / "backup.py"),
            "--root", str(self.root), "--env", "prod", "--kind", "semimonthly",
            "--copy-latest-from", "daily", "--source", "timer", "--json",
        ]
        result = _run(command)
        if result.returncode != 0:
            raise RuntimeError(
                f"半月档复制失败（exit {result.returncode}）：{result.stderr.strip()[:500]}"
            )
        self.step("semimonthly", True, "由最新已验证 daily 复制",
                  time.monotonic() - started)

    def verify_new_snapshot(self) -> None:
        started = time.monotonic()
        result = _run([
            str(self.python), str(self.payload / "verify_backup.py"),
            "--snapshot", str(self.snapshot), "--json",
        ])
        if result.returncode != 0:
            raise RuntimeError(
                f"新快照校验失败：{result.stderr.strip()[:500] or result.stdout[-500:]}"
            )
        self.step("verify-new", True, self.snapshot.name,
                  time.monotonic() - started)

    def prune(self) -> None:
        started = time.monotonic()
        result = _run([
            str(self.python), str(self.payload / "prune_backups.py"),
            "--root", str(self.root), "--env", "prod", "--execute", "--json",
        ])
        if result.returncode != 0:
            raise RuntimeError(
                f"保留策略执行失败：{result.stderr.strip()[:500]}"
            )
        try:
            payload = json.loads(result.stdout[result.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError):
            payload = {}
        deleted = payload.get("deleted_snapshots", [])
        self.step("rotate", True,
                  f"删除 {len(deleted)} 份过期快照" +
                  (f"：{', '.join(Path(p).name for p in deleted)}" if deleted else ""),
                  time.monotonic() - started)

    def verify_retained(self) -> None:
        started = time.monotonic()
        snapshot_root = (self.root / "backups" / "prod").resolve()
        failures: List[str] = []
        checked = 0
        for manifest in sorted(snapshot_root.glob("*/*/manifest.json")):
            if self.snapshot is not None and manifest.parent == self.snapshot:
                continue
            checked += 1
            result = _run([
                str(self.python), str(self.payload / "verify_backup.py"),
                "--snapshot", str(manifest.parent), "--json",
            ], timeout=300)
            if result.returncode != 0:
                failures.append(manifest.parent.name)
        if failures:
            raise RuntimeError("保留快照校验失败：" + ", ".join(failures))
        self.step("verify-retained", True, f"{checked} 份保留快照通过",
                  time.monotonic() - started)

    # -- 代码备份 -----------------------------------------------------
    def _git(self, *args: str) -> subprocess.CompletedProcess:
        return _run(["git", "-C", str(self.code_repo), *args], timeout=300)

    def code_backup(self) -> None:
        started = time.monotonic()
        head = self._git("rev-parse", "HEAD")
        if head.returncode != 0:
            raise RuntimeError(f"读取 HEAD 失败：{head.stderr.strip()[:300]}")
        sha = head.stdout.strip()
        branch = self._git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        status = self._git("status", "--porcelain").stdout.splitlines()

        dest = self.code_dir
        bundle = dest / f"BCLRM-{_stamp()}-{sha[:10]}.bundle"
        partial = bundle.with_suffix(".bundle.partial")
        created = self._git("bundle", "create", str(partial), "--all")
        if created.returncode != 0:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"git bundle 创建失败：{created.stderr.strip()[:500]}")
        verified = _run(["git", "-C", str(self.code_repo), "bundle",
                         "verify", str(partial)], timeout=300)
        if verified.returncode != 0:
            partial.unlink(missing_ok=True)
            raise RuntimeError(f"git bundle 校验失败：{verified.stderr.strip()[:500]}")
        os.replace(partial, bundle)

        meta: Dict[str, Any] = {
            "created_at": _iso(),
            "repo": str(self.code_repo),
            "branch": branch,
            "head": sha,
            "bundle": bundle.name,
            "bundle_sha256": _sha256(bundle),
            "bundle_size": bundle.stat().st_size,
            "dirty": bool(status),
            "dirty_entries": status[:200],
        }
        diff = self._git("diff", "HEAD")
        if diff.returncode == 0 and diff.stdout.strip():
            patch = bundle.with_suffix(".patch")
            patch.write_text(diff.stdout, encoding="utf-8")
            meta["uncommitted_patch"] = patch.name
            meta["uncommitted_patch_sha256"] = _sha256(patch)
        untracked = self._git("ls-files", "--others", "--exclude-standard").stdout.splitlines()
        if untracked:
            meta["untracked_files"] = untracked[:200]
        _write_json_atomic(bundle.with_suffix(".json"), meta)
        self.prune_code()
        self.step("code-backup", True,
                  f"{bundle.name}（{bundle.stat().st_size / 1024:.0f} KiB，"
                  f"head {sha[:10]}{'，工作区有未提交改动' if status else ''}）",
                  time.monotonic() - started)

    def prune_code(self) -> None:
        cutoff = _now() - timedelta(days=CODE_RETENTION_DAYS)
        bundles = sorted(self.code_dir.glob("BCLRM-*.bundle"),
                         key=lambda p: p.stat().st_mtime, reverse=True)
        for index, bundle in enumerate(bundles):
            if index < 2:
                continue
            if datetime.fromtimestamp(bundle.stat().st_mtime, timezone.utc) >= cutoff:
                continue
            for suffix in (".bundle", ".json", ".patch"):
                bundle.with_suffix(suffix).unlink(missing_ok=True)

    # -- 异地 ---------------------------------------------------------
    def offsite_sync(self) -> None:
        started = time.monotonic()
        script = self.root / "ops" / "offsite_sync.py"
        if not script.is_file():
            raise RuntimeError(f"缺少异地同步工具：{script}")
        result = _run([
            "/usr/bin/python3", str(script), "--root", str(self.root),
            "--env", "prod", "--ssh-key", str(Path.home() / ".ssh" / "id_ed25519_13"),
            "--json",
        ], timeout=3600)
        if result.returncode != 0:
            raise RuntimeError(
                f"异地同步失败（exit {result.returncode}）："
                f"{result.stderr.strip()[:500] or result.stdout[-500:]}"
            )
        try:
            payload = json.loads(result.stdout[result.stdout.index("{"):])
        except (ValueError, json.JSONDecodeError):
            payload = {}
        self.step("offsite", True,
                  f"上传 {len(payload.get('uploaded', []))}，"
                  f"清理 {len(payload.get('pruned', []))}，"
                  f"清单 {payload.get('manifest_entries', '?')} 项",
                  time.monotonic() - started)

    # -- 主流程 -------------------------------------------------------
    def execute(self) -> int:
        self.preflight()
        self.was_active = self.service_active()
        if not self.was_active:
            _log("[WARN] prod 当前未运行：照常冷备，结束后不强制启动")
        try:
            if self.was_active:
                self.stop_service()
            self.cold_backup()
            self.verify_new_snapshot()
            self.prune()
            self.verify_retained()
            self.code_backup()
            ok = True
            error = None
        except Exception as exc:  # noqa: BLE001 - 任何一步失败都要继续拉回服务
            ok = False
            error = f"{type(exc).__name__}: {exc}"
            self.step("failed", False, error)
        finally:
            if self.was_active:
                if not self.restart_service():
                    ok = False
                    error = (error + "; " if error else "") + "重启/健康检查失败"
            else:
                self.step("restart-prod", True, "开始时即未运行，未强制启动")
        # 异地同步不占停服窗口：服务恢复后再上传，失败只影响本次状态
        if ok and not self.args.skip_offsite:
            try:
                self.offsite_sync()
            except Exception as exc:  # noqa: BLE001
                ok = False
                error = f"{type(exc).__name__}: {exc}"
                self.step("failed", False, error)
        status = {
            "ok": ok,
            "error": error,
            "dry_run": False,
            "started_at": _iso(self.started),
            "finished_at": _iso(),
            "snapshot": str(self.snapshot) if self.snapshot else None,
            "restart": self.restart,
            "steps": self.steps,
        }
        _write_json_atomic(self.root / "logs" / "maintenance_status.json", status)
        _log("[ OK ] 每日维护完成" if ok else f"[FAIL] 每日维护失败：{error}")
        return 0 if ok else 3

    def dry_run(self) -> int:
        self.preflight()
        plan = {
            "dry_run": True,
            "unit": self.args.unit,
            "port": self.args.port,
            "active": self.service_active(),
            "backups": str((self.root / "backups").resolve()),
            "code_repo": str(self.code_repo),
            "steps": [
                "stop prod（仅当 active）",
                "cold backup daily + service-stopped",
                "verify new snapshot",
                "prune per retention（3 个月半月档）",
                "verify retained snapshots",
                "code bundle + manifest",
                "offsite sync",
                "restart prod + health",
            ],
        }
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="BCLRM 每日 05:00 停机冷备维护")
    parser.add_argument("--root", default=str(DEFAULT_ROOT))
    parser.add_argument("--unit", default="bclrm-prod.service")
    parser.add_argument("--port", type=int, default=8501)
    parser.add_argument("--code-repo",
                        default=os.environ.get("BCLRM_CODE_REPO", str(DEFAULT_CODE_REPO)))
    parser.add_argument("--code-dir", help="代码备份目录（默认加密卷 code/）")
    parser.add_argument("--systemctl", default="systemctl --user",
                        help="测试可替换为假 systemctl 路径")
    parser.add_argument("--skip-offsite", action="store_true")
    parser.add_argument("--execute", action="store_true", help="真正停服执行；缺省 dry-run")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    maintenance = Maintenance(args)
    if not args.execute:
        try:
            return maintenance.dry_run()
        except PreflightError as exc:
            print(f"[FAIL] 预检失败：{exc}", file=sys.stderr)
            return 2

    lock_path = Path(args.root) / "logs" / ".maintenance.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("[FAIL] 已有维护任务在运行", file=sys.stderr)
            return 3
        try:
            return maintenance.execute()
        except PreflightError as exc:
            maintenance.step("preflight", False, str(exc))
            print(f"[FAIL] 预检失败：{exc}", file=sys.stderr)
            return 2


if __name__ == "__main__":
    sys.exit(main())
