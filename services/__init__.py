"""数据访问服务模块。

为避免导入包时触发「services ↔ business」循环依赖，本文件不再 eager import
任何服务类/实例。调用方请直接导入具体模块，例如::

    from services.core.reagent_bottle_service import reagent_bottle_service
"""
