"""密码工具模块

提供密码哈希生成和验证功能，使用 Python 标准库 PBKDF2 算法。
"""
import hashlib
import os
import base64
from typing import Tuple

PBKDF2_ITERATIONS = 100000
SALT_LENGTH = 16
HASH_ALGORITHM = "sha256"


def hash_password(password: str) -> str:
    """生成密码哈希

    使用 PBKDF2-HMAC-SHA256 算法，100000 次迭代，16字节随机盐。
    格式: pbkdf2_sha256$<iterations>$<salt_b64>$<hash_b64>

    Args:
        password: 明文密码

    Returns:
        密码哈希字符串
    """
    salt = os.urandom(SALT_LENGTH)
    dk = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        PBKDF2_ITERATIONS
    )
    salt_b64 = base64.b64encode(salt).decode("ascii").strip()
    hash_b64 = base64.b64encode(dk).decode("ascii").strip()
    return f"pbkdf2_{HASH_ALGORITHM}${PBKDF2_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, password_hash: str) -> bool:
    """验证密码

    Args:
        password: 明文密码
        password_hash: 存储的密码哈希

    Returns:
        True 表示验证通过，False 表示验证失败
    """
    if not password_hash or not isinstance(password_hash, str):
        return False

    try:
        parts = password_hash.split("$")
        if len(parts) != 4:
            return False

        algorithm = parts[0]
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2].encode("ascii"))
        stored_hash = base64.b64decode(parts[3].encode("ascii"))

        if algorithm != f"pbkdf2_{HASH_ALGORITHM}":
            return False

        dk = hashlib.pbkdf2_hmac(
            HASH_ALGORITHM,
            password.encode("utf-8"),
            salt,
            iterations
        )

        return dk == stored_hash
    except (ValueError, IndexError, base64.binascii.Error):
        return False
