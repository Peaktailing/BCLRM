"""业务逻辑模块。

为避免导入包时触发「services ↔ business」循环依赖，本文件不再 eager import
任何业务服务。各页面/服务请直接导入具体模块，例如::

    from business.inventory_service import inventory_service
"""
