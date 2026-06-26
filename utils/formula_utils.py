"""化学式格式化工具

提供化学式上下标转换功能，将普通文本格式的化学式转换为可显示上下标的格式。
"""

import re

def format_formula(formula: str) -> str:
    """
    将化学式中的数字转换为下标格式，但·后面的数字保持正常显示。
    
    Args:
        formula: 原始化学式字符串，如 "H2O", "C6H12O6", "Na₂[Fe(CN)₅NO]", "P·5H2O", "C12H14N2·2HCl"
    
    Returns:
        格式化后的化学式字符串，数字转换为下标格式（·后面的数字除外）
    
    Examples:
        >>> format_formula("H2O")
        'H₂O'
        >>> format_formula("C6H12O6")
        'C₆H₁₂O₆'
        >>> format_formula("Na2[Fe(CN)5NO]")
        'Na₂[Fe(CN)₅NO]'
        >>> format_formula("P·5H2O")
        'P·5H₂O'
        >>> format_formula("C12H14N2·2HCl")
        'C₁₂H₁₄N₂·2HCl'
    """
    if not formula:
        return ""
    
    # 定义数字到下标的映射
    subscript_map = {
        '0': '₀', '1': '₁', '2': '₂', '3': '₃', '4': '₄',
        '5': '₅', '6': '₆', '7': '₇', '8': '₈', '9': '₉'
    }
    
    # 使用正则表达式匹配数字并转换为下标
    result = []
    i = 0
    while i < len(formula):
        if formula[i] == '·':
            # 遇到·符号，保持原样，并标记后面的数字不转换
            result.append('·')
            i += 1
            # 跳过·后面的所有数字，保持正常显示
            while i < len(formula) and formula[i].isdigit():
                result.append(formula[i])
                i += 1
        elif formula[i].isdigit():
            # 如果是数字，转换为下标
            result.append(subscript_map.get(formula[i], formula[i]))
            i += 1
        else:
            result.append(formula[i])
            i += 1
    
    return ''.join(result)

def format_formula_html(formula: str) -> str:
    """
    将化学式转换为HTML格式，使用<sub>标签显示下标。
    
    Args:
        formula: 原始化学式字符串
    
    Returns:
        HTML格式的化学式字符串
    
    Examples:
        >>> format_formula_html("H2O")
        'H<sub>2</sub>O'
        >>> format_formula_html("C6H12O6")
        'C<sub>6</sub>H<sub>12</sub>O<sub>6</sub>'
    """
    if not formula:
        return ""
    
    # 使用正则表达式将数字包装在<sub>标签中
    # 匹配数字序列，用<sub>标签包裹
    result = re.sub(r'(\d+)', r'<sub>\1</sub>', formula)
    
    return result

def parse_formula(formula: str) -> dict:
    """
    解析化学式，提取元素及其数量。
    
    Args:
        formula: 化学式字符串
    
    Returns:
        元素到数量的字典
    
    Examples:
        >>> parse_formula("H2O")
        {'H': 2, 'O': 1}
        >>> parse_formula("C6H12O6")
        {'C': 6, 'H': 12, 'O': 6}
    """
    if not formula:
        return {}
    
    # 使用正则表达式匹配元素和数量
    pattern = r'([A-Z][a-z]?)(\d*)'
    matches = re.findall(pattern, formula)
    
    result = {}
    for element, count in matches:
        if element:
            result[element] = int(count) if count else 1
    
    return result
