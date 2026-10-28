"""异地归档备份（第二副本）核心逻辑。

与 ``utils.backup.copy_to_second_location`` 的区别：

- 第二副本以 **单个 tar.gz 归档** 存放，而不是逐文件目录树；跨机传输只走
  一条压缩流，落盘后再按 sha256 复核。
- 远端只维护 **一个** 校验清单 ``SHA256SUMS.txt``，内容是当前仍存在的
  全部归档的相对路径与 sha256；本地快照被保留策略清掉后，远端对应归档与
  清单行一起删除。
- 本模块不依赖 ``config.settings``，可对任意 ``--root`` 运行，也便于测试
  用本地目录模拟远端。

远端布局::

    <base>/<env>/<kind>/<snapshot-name>.tar.gz
    <base>/SHA256SUMS.txt

``SHA256SUMS.txt`` 使用 ``sha256sum -c`` 可直接核对的裸格式，不加表头。
"""
from __future__ import annotations

import hashlib
import json
import os
import shlex
import shutil
import subprocess
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

SUMS_NAME = "SHA256SUMS.txt"
ARCHIVE_SUFFIX = ".tar.gz"
KINDS = ("daily", "semimonthly", "pre_change", "annual")
ARCHIVE_ROOT_PARTS = 3  # env / kind / name.tar.gz


class OffsiteError(RuntimeError):
    """异地备份失败：调用方应按执行失败处理（退出码 3）。"""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_sums(entries: Iterable[Tuple[str, str]]) -> str:
    """按路径排序生成 sha256sum 清单文本（相对路径，无表头）。"""
    lines = [f"{digest}  {rel}" for rel, digest in sorted(entries)]
    return "\n".join(lines) + ("\n" if lines else "")


def parse_rel(rel: str) -> Optional[Tuple[str, str, str]]:
    """把 ``env/kind/name.tar.gz`` 拆成三段；不符合布局返回 None。"""
    parts = Path(rel).parts
    if len(parts) != ARCHIVE_ROOT_PARTS:
        return None
    env, kind, name = parts
    if not name.endswith(ARCHIVE_SUFFIX):
        return None
    return env, kind, name[: -len(ARCHIVE_SUFFIX)]


# ---------------------------------------------------------------------------
# 远端实现
# ---------------------------------------------------------------------------
class LocalRemote:
    """本地目录模拟远端（测试用；也可作为离线挂载点）。"""

    def __init__(self, base: Path):
        self.base = Path(base)

    def mkdirs(self, rel_dir: str = "") -> None:
        (self.base / rel_dir).mkdir(parents=True, exist_ok=True)

    def list_archives(self) -> List[str]:
        if not self.base.is_dir():
            raise OffsiteError(f"远端根不存在：{self.base}")
        return sorted(
            str(p.relative_to(self.base))
            for p in self.base.rglob("*" + ARCHIVE_SUFFIX)
            if p.is_file()
        )

    def sha256(self, rels: Sequence[str]) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for rel in rels:
            path = self.base / rel
            if not path.is_file():
                raise OffsiteError(f"远端文件不存在：{rel}")
            result[rel] = file_sha256(path)
        return result

    def upload(self, local: Path, rel: str) -> None:
        target = self.base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        shutil.copyfile(local, partial)
        os.replace(partial, target)

    def delete(self, rels: Sequence[str]) -> None:
        for rel in rels:
            path = self.base / rel
            if path.is_file():
                path.unlink()

    def read_text(self, rel: str) -> str:
        return (self.base / rel).read_text(encoding="utf-8")

    def write_text(self, text: str, rel: str) -> None:
        target = self.base / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".partial")
        partial.write_text(text, encoding="utf-8")
        os.replace(partial, target)


class SshRemote:
    """通过 ssh 非交互访问远端（BatchMode，失败即报错）。

    显式指定身份文件，不依赖 ssh-agent/keyring：systemd 用户单元在无人登录
    时可能拿不到已解锁的 agent，而专门为归档准备的密钥不应依赖桌面会话。
    """

    SSH_OPTS = (
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=10",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=4",
    )
    DEFAULT_KEY = Path.home() / ".ssh" / "id_ed25519_13"

    def __init__(self, host: str, base: str,
                 identity_file: Optional[Path] = None):
        if not host or not base:
            raise OffsiteError("远端必须写成 user@host:/absolute/path")
        self.host = host
        self.base = base.rstrip("/") or "/"
        key = Path(identity_file) if identity_file else self.DEFAULT_KEY
        self.identity_file = key if key.is_file() else None

    # -- 底层 -----------------------------------------------------------
    def _ssh(self, command: str, stdin=None) -> str:
        options = list(self.SSH_OPTS)
        if self.identity_file:
            options += ["-i", str(self.identity_file), "-o", "IdentitiesOnly=yes"]
        if hasattr(stdin, "read"):
            proc = subprocess.run(
                ["ssh", *options, self.host, command],
                stdin=stdin,
                capture_output=True,
            )
        else:
            proc = subprocess.run(
                ["ssh", *options, self.host, command],
                input=stdin,
                capture_output=True,
            )
        if proc.returncode != 0:
            detail = proc.stderr.decode("utf-8", "replace").strip()[:400]
            raise OffsiteError(f"ssh 失败（{command[:80]}）：{detail}")
        return proc.stdout.decode("utf-8", "replace")

    def _remote_path(self, rel: str) -> str:
        return shlex.quote(f"{self.base}/{rel}") if rel else shlex.quote(self.base)

    # -- 接口 -----------------------------------------------------------
    def mkdirs(self, rel_dir: str = "") -> None:
        self._ssh(f"mkdir -p {self._remote_path(rel_dir)}")

    def list_archives(self) -> List[str]:
        command = (
            f"cd {shlex.quote(self.base)} && "
            f"find . -type f -name '*.tar.gz' -printf '%P\\n' | sort"
        )
        out = self._ssh(command)
        return [line for line in out.splitlines() if line.strip()]

    def sha256(self, rels: Sequence[str]) -> Dict[str, str]:
        if not rels:
            return {}
        quoted = " ".join(shlex.quote(rel) for rel in rels)
        out = self._ssh(f"cd {shlex.quote(self.base)} && sha256sum -- {quoted}")
        result: Dict[str, str] = {}
        for line in out.splitlines():
            digest, _, rel = line.partition("  ")
            if digest and rel:
                result[rel] = digest.strip()
        missing = [rel for rel in rels if rel not in result]
        if missing:
            raise OffsiteError(f"远端 sha256 结果缺少：{', '.join(missing[:3])}")
        return result

    def upload(self, local: Path, rel: str) -> None:
        partial = rel + ".partial"
        with open(local, "rb") as fh:
            self._ssh(f"cat > {self._remote_path(partial)}", stdin=fh)
        self._ssh(
            f"mv -f {self._remote_path(partial)} {self._remote_path(rel)}"
        )

    def delete(self, rels: Sequence[str]) -> None:
        for rel in rels:
            self._ssh(f"rm -f -- {self._remote_path(rel)}")

    def read_text(self, rel: str) -> str:
        return self._ssh(f"cat {self._remote_path(rel)}")

    def write_text(self, text: str, rel: str) -> None:
        partial = rel + ".partial"
        self._ssh(
            f"cat > {self._remote_path(partial)}",
            stdin=text.encode("utf-8"),
        )
        self._ssh(
            f"mv -f {self._remote_path(partial)} {self._remote_path(rel)}"
        )


# ---------------------------------------------------------------------------
# 同步编排
# ---------------------------------------------------------------------------
def discover_snapshots(root: Path, envs: Sequence[str],
                       kinds: Sequence[str] = KINDS
                       ) -> Dict[Tuple[str, str], List[Path]]:
    """按 env/kind 列出本地可用快照（目录内必须有 manifest.json）。"""
    found: Dict[Tuple[str, str], List[Path]] = {}
    base = Path(root) / "backups"
    for env in envs:
        for kind in kinds:
            kind_dir = base / env / kind
            if not kind_dir.is_dir():
                continue
            items = [
                p for p in sorted(kind_dir.iterdir())
                if p.is_dir() and not p.name.startswith(".")
                and (p / "manifest.json").is_file()
            ]
            if items:
                found[(env, kind)] = items
    return found


def _create_archive(snapshot: Path, temp_dir: Path) -> Path:
    """把快照目录打成 tar.gz，并确认归档内 manifest 与源一致。"""
    temp_dir.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(suffix=ARCHIVE_SUFFIX, dir=str(temp_dir))
    os.close(fd)
    archive = Path(name)
    try:
        with tarfile.open(archive, "w:gz", compresslevel=6) as tar:
            tar.add(snapshot, arcname=snapshot.name)
        with tarfile.open(archive, "r:gz") as tar:
            names = tar.getnames()
            if not names:
                raise OffsiteError(f"归档为空：{snapshot}")
            member = tar.extractfile(f"{snapshot.name}/manifest.json")
            if member is None:
                raise OffsiteError(f"归档缺少 manifest：{snapshot}")
            archived_manifest = member.read()
        source_manifest = (snapshot / "manifest.json").read_bytes()
        if archived_manifest != source_manifest:
            raise OffsiteError(f"归档内 manifest 与源不一致：{snapshot}")
    except Exception:
        archive.unlink(missing_ok=True)
        raise
    return archive


def sync(root: Path, envs: Sequence[str], remote, temp_dir: Path,
         prune: bool = True, dry_run: bool = False) -> Dict[str, object]:
    """把本地快照归档到远端，并让远端清单与远端实际文件一致。"""
    root = Path(root)
    temp_dir = Path(temp_dir)
    local = discover_snapshots(root, envs)
    if not local:
        raise OffsiteError(
            f"本地没有任何快照（{root}/backups 是否已挂载？），拒绝同步"
        )

    if dry_run:
        try:
            remote_archives = set(remote.list_archives())
        except OffsiteError:
            remote_archives = set()
        planned: List[str] = []
        for (env, kind), snaps in sorted(local.items()):
            for snap in snaps:
                rel = f"{env}/{kind}/{snap.name}{ARCHIVE_SUFFIX}"
                if rel not in remote_archives:
                    planned.append(rel)
        return {
            "ok": True,
            "dry_run": True,
            "planned_uploads": planned,
            "local_snapshots": sum(len(v) for v in local.values()),
        }

    remote.mkdirs("")
    remote_archives = set(remote.list_archives())
    planned = []
    uploaded: List[str] = []
    pruned: List[str] = []
    warnings: List[str] = []

    try:
        for (env, kind), snaps in sorted(local.items()):
            for snap in snaps:
                rel = f"{env}/{kind}/{snap.name}{ARCHIVE_SUFFIX}"
                if rel in remote_archives:
                    continue
                archive = _create_archive(snap, temp_dir)
                try:
                    remote.mkdirs(f"{env}/{kind}")
                    digest = file_sha256(archive)
                    remote.upload(archive, rel)
                    remote_digest = remote.sha256([rel]).get(rel)
                    if remote_digest != digest:
                        remote.delete([rel])
                        raise OffsiteError(f"远端归档校验失败：{rel}")
                    uploaded.append(rel)
                    remote_archives.add(rel)
                finally:
                    archive.unlink(missing_ok=True)

        # 保留策略镜像：本地已不存在的快照，远端归档与清单行一起删除。
        # 安全阀：某类本地一份不剩时跳过该类，避免 /data 未挂载时误删远端。
        if prune:
            stale: List[str] = []
            for rel in sorted(remote_archives):
                parsed = parse_rel(rel)
                if parsed is None:
                    continue
                env, kind, name = parsed
                if env not in envs:
                    continue
                snaps = local.get((env, kind), [])
                if not snaps:
                    warnings.append(f"{env}/{kind} 本地无快照，跳过远端清理")
                    continue
                if name not in {s.name for s in snaps}:
                    stale.append(rel)
            if stale:
                remote.delete(stale)
                for rel in stale:
                    remote_archives.discard(rel)
                pruned.extend(stale)

        # 清单只覆盖远端当前实际存在的归档；先列再哈希，避免引用已删文件。
        remote_archives = set(remote.list_archives())
        digests = remote.sha256(sorted(remote_archives))
        text = render_sums((rel, digests[rel]) for rel in remote_archives)
        remote.write_text(text, SUMS_NAME)
        if remote.read_text(SUMS_NAME) != text:
            raise OffsiteError("远端校验清单回读不一致")
    except OffsiteError:
        raise
    except (OSError, tarfile.TarError, ValueError) as exc:
        raise OffsiteError(str(exc)) from exc

    return {
        "ok": True,
        "dry_run": False,
        "uploaded": uploaded,
        "pruned": pruned,
        "warnings": warnings,
        "manifest_entries": len(remote_archives),
        "local_snapshots": sum(len(v) for v in local.values()),
    }


def write_status(root: Path, payload: Dict[str, object]) -> None:
    path = Path(root) / "logs" / "offsite_status.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    data = dict(payload)
    data.setdefault("at", utc_now_iso())
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
