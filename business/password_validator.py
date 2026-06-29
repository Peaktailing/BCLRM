"""密码强度验证模块

规则：
- 至少 8 位字符
- 中等强度以上：至少包含 4 类字符（大写字母、小写字母、数字、特殊字符）中的 3 类
- 不允许常见弱口令（如 12345678、password、admin123 等）
"""

import re
import string

# ── 弱口令黑名单 ──────────────────────────────────────────

WEAK_PASSWORDS = {
    "12345678", "123456789", "1234567890", "password", "password123",
    "admin123", "admin123456", "qwertyuiop", "asdfghjkl", "zxcvbnm",
    "11111111", "22222222", "12341234", "abcd1234", "abc12345",
    "iloveyou", "monkey123", "dragon123", "master123", "letmein12",
    "welcome1", "trustno1", "sunshine", "princess", "football",
    "baseball", "shadow12", "michael1", "password1", "1234567a",
    "00000000", "88888888", "aaaa1111", "qwerty12", "1qaz2wsx",
    "abc123456", "a12345678", "abcdefg1", "passw0rd", "P@ssw0rd",
}


def validate_password_strength(password: str) -> tuple:
    """验证密码强度

    Args:
        password: 密码字符串

    Returns:
        (is_valid: bool, message: str)
    """
    if not password:
        return False, "密码不能为空"

    if len(password) < 8:
        return False, "密码长度至少需要 8 位"

    if len(password) > 128:
        return False, "密码长度不能超过 128 位"

    # 检查字符类别数
    has_upper = bool(re.search(r'[A-Z]', password))
    has_lower = bool(re.search(r'[a-z]', password))
    has_digit = bool(re.search(r'\d', password))
    has_special = bool(re.search(r'[^a-zA-Z\d]', password))

    category_count = sum([has_upper, has_lower, has_digit, has_special])

    if category_count < 3:
        missing = []
        if not has_upper:
            missing.append("大写字母")
        if not has_lower:
            missing.append("小写字母")
        if not has_digit:
            missing.append("数字")
        if not has_special:
            missing.append("特殊字符")
        return False, f"密码强度不足，需包含至少 3 类字符（当前缺少：{'、'.join(missing)}）"

    # 检查弱口令
    if password.lower() in WEAK_PASSWORDS:
        return False, "密码过于简单，属于常见弱口令，请更换"

    # 检查连续相同字符（如 aaaa、1111）
    if re.search(r'(.)\1{3,}', password):
        return False, "密码包含连续重复字符，请更换"

    # 检查键盘连续字符（如 qwert、asdfg，5个及以上才算）
    keyboard_sequences = [
        "qwertyuiop", "asdfghjkl", "zxcvbnm",
        "poiuytrewq", "lkjhgfdsa", "mnbvcxz",
        "1234567890", "0987654321",
        "qwertzuiop", "yxcvbnm",
    ]
    password_lower = password.lower()
    for seq in keyboard_sequences:
        for i in range(len(seq) - 4):
            if seq[i:i+5] in password_lower:
                return False, "密码包含键盘连续字符，请更换"

    return True, "密码强度合格"


def validate_phone(phone: str) -> tuple:
    """验证手机号格式

    Args:
        phone: 手机号字符串

    Returns:
        (is_valid: bool, message: str)
    """
    if not phone:
        return True, ""  # 手机号非必填

    phone = phone.strip()

    if not re.match(r'^1\d{10}$', phone):
        if len(phone) != 11:
            return False, "手机号必须为 11 位数字"
        if not phone.startswith("1"):
            return False, "手机号必须以 1 开头"
        if not phone.isdigit():
            return False, "手机号只能包含数字"
        return False, "手机号格式不正确，需为 1 开头的 11 位数字"

    return True, "手机号格式正确"