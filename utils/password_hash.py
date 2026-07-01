"""密码哈希工具 - PBKDF2-SHA256 + 盐

使用 PBKDF2 算法（100,000 次迭代）对密码进行安全哈希存储。
格式: pbkdf2:sha256:iterations$salt$hash
"""
import hashlib
import os
import base64


HASH_ITERATIONS = 100_000
HASH_ALGORITHM = "sha256"
SALT_LENGTH = 16


def hash_password(password: str) -> str:
    """使用 PBKDF2-SHA256 对密码进行加盐哈希

    Args:
        password: 明文密码

    Returns:
        格式化的哈希字符串: pbkdf2:sha256:100000$salt$hash
    """
    salt = os.urandom(SALT_LENGTH)
    dk = hashlib.pbkdf2_hmac(
        HASH_ALGORITHM,
        password.encode("utf-8"),
        salt,
        HASH_ITERATIONS,
    )
    salt_b64 = base64.b64encode(salt).decode("ascii")
    hash_b64 = base64.b64encode(dk).decode("ascii")
    return f"pbkdf2:{HASH_ALGORITHM}:{HASH_ITERATIONS}${salt_b64}${hash_b64}"


def verify_password(password: str, hashed: str) -> bool:
    """验证密码是否匹配

    兼容旧格式 (纯 SHA-256 hex) 和 新格式 (PBKDF2)。

    Args:
        password: 明文密码
        hashed: 存储的哈希值

    Returns:
        是否匹配
    """
    if not hashed:
        return False

    # 新格式: pbkdf2:sha256:100000$salt$hash
    if hashed.startswith("pbkdf2:"):
        try:
            _, algo, iterations_str = hashed.split(":", 2)
            iterations_str, rest = iterations_str.split("$", 1)
            salt_b64, hash_b64 = rest.split("$", 1)
            salt = base64.b64decode(salt_b64)
            stored_hash = base64.b64decode(hash_b64)
            iterations = int(iterations_str)
            dk = hashlib.pbkdf2_hmac(algo, password.encode("utf-8"), salt, iterations)
            return dk == stored_hash
        except (ValueError, IndexError):
            return False

    # 旧格式兼容: 纯 SHA-256 hex
    if len(hashed) == 64 and all(c in "0123456789abcdef" for c in hashed):
        return hashlib.sha256(password.encode("utf-8")).hexdigest() == hashed

    return False