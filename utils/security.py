"""密码哈希工具

使用标准库实现（无第三方依赖）：sha256 + 随机盐的 PBKDF2 派生。
存储格式为 "salt:hash"，验证时按 salt 重新派生并做常量时间比较。
"""
import hashlib
import hmac
import secrets

_PBKDF2_ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """对密码进行加盐哈希，返回 "salt:hash" 格式的存储字符串。"""
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()
    return f"{salt}:{derived}"


def verify_password(password: str, stored: str) -> bool:
    """验证明文密码与存储哈希是否匹配，使用常量时间比较防止时序侧信道。"""
    if not stored or ":" not in stored:
        return False
    salt, expected = stored.split(":", 1)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), _PBKDF2_ITERATIONS
    ).hex()
    return hmac.compare_digest(derived, expected)
