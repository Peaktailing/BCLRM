"""release 工具链测试包。

不在这里改环境变量：``tests/__init__.py`` 已把整套测试的数据根切到临时目录。
本包所有用例另外自建临时 root，确保 build/backup/deploy 只操作传入的 --root。
"""
