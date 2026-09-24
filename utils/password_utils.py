"""密码工具模块

提供安全的密码哈希和验证功能，使用 PBKDF2-HMAC-SHA256 算法。

使用 Python 内置的 hashlib 和 os 模块，无需额外依赖。
"""
import hashlib
import hmac
import os
import base64
from typing import Tuple


# PBKDF2 参数
HASH_ITERATIONS = 600_000  # OWASP 2023 推荐的最小迭代次数
HASH_ALGORITHM = "sha256"
SALT_LENGTH = 32  # 盐值长度（字节）
HASH_LENGTH = 32  # 哈希输出长度（字节）
LEGACY_ITERATIONS = 100_000  # 历史实现（utils.security）的迭代次数，仅用于兼容校验


def generate_salt() -> bytes:
    """生成密码学安全的随机盐值"""
    return os.urandom(SALT_LENGTH)


def hash_password(password: str, salt: bytes = None) -> str:
    """使用 PBKDF2-HMAC-SHA256 对密码进行哈希

    Args:
        password: 明文密码
        salt: 盐值（bytes），None 则自动生成

    Returns:
        格式为 "pbkdf2:sha256:iterations$salt_base64$hash_base64" 的哈希字符串
    """
    if salt is None:
        salt = generate_salt()

    dk = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        HASH_ITERATIONS,
        dklen=HASH_LENGTH,
    )

    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(dk).decode("ascii")

    return f"pbkdf2:{HASH_ALGORITHM}:{HASH_ITERATIONS}${salt_b64}${hash_b64}"


def _verify_legacy_sha256(password: str, stored: str) -> bool:
    """校验历史格式 "salt:hash"（PBKDF2-SHA256 + 随机盐，hex 编码）

    用于兼容早期 utils.security 写入的密码，避免升级后老用户无法登录。
    """
    if ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), LEGACY_ITERATIONS
    ).hex()
    return hmac.compare_digest(derived, expected)


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码是否匹配存储的哈希值

    支持两种存储格式：
    - 新格式：``pbkdf2:sha256:<iterations>$salt_b64$hash_b64``
    - 旧格式：``salt:hash``（历史 utils.security 写入，兼容校验）

    Args:
        password: 待验证的明文密码
        password_hash: 存储的密码哈希字符串

    Returns:
        True 表示密码匹配
    """
    if not password_hash:
        return False

    # 历史格式兼容（升级前由 utils.security 写入）
    if not password_hash.startswith("pbkdf2:"):
        return _verify_legacy_sha256(password, password_hash)

    try:
        # 解析存储的哈希格式
        algo_part, rest = password_hash.split("$", 1)
        _, algorithm, iterations_str = algo_part.split(":", 2)
        salt_b64, stored_hash_b64 = rest.split("$", 1)

        salt = base64.b64decode(salt_b64)
        iterations = int(iterations_str)

        dk = hashlib.pbkdf2_hmac(
            algorithm,
            password.encode("utf-8"),
            salt,
            iterations,
            dklen=HASH_LENGTH,
        )

        return base64.b64encode(dk).decode("ascii") == stored_hash_b64
    except (ValueError, IndexError, base64.binascii.Error):
        return False


def is_password_hash_set(password_hash: str) -> bool:
    """检查密码哈希是否已设置（非空且格式正确）

    Args:
        password_hash: 密码哈希字符串

    Returns:
        True 表示已设置密码
    """
    return bool(password_hash and password_hash.startswith("pbkdf2:"))