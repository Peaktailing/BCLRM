"""pytest 入口：确保测试隔离（tests/__init__.py）先于任何业务模块导入。

unittest discover 会先导入 tests 包完成隔离重定向；pytest 的收集顺序不保证
这一点，必须在此显式 import tests，否则 operation_log_service 等模块级单例
会绑死真实库路径，后续重定向失效（QA 审查建议）。
"""
import tests  # noqa: F401
