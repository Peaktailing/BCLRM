"""化学品-试剂类型关联表服务

对应数据表：chemical_reagent_type
"""
from db.base_service import BaseService
from utils.error_handler import logger
from typing import List


class ChemicalReagentTypeService(BaseService):
    """化学品-试剂类型关联表服务"""

    def __init__(self, db=None):
        super().__init__("chemical_reagent_type", db=db)
        logger.info("化学品-试剂类型关联表服务初始化完成")

    def get_types_by_chemical_id(self, chemical_id: int) -> List[str]:
        """获取化学品关联的所有试剂类型名称

        Args:
            chemical_id: 化学品 ID

        Returns:
            试剂类型名称列表
        """
        query = """
            SELECT rt.name FROM reagent_type rt
            INNER JOIN chemical_reagent_type crt ON rt.id = crt.type_id
            WHERE crt.chemical_id = ?
            ORDER BY rt.name
        """
        try:
            results = self.db.execute_query(query, (chemical_id,))
            return [row['name'] for row in results]
        except Exception as e:
            logger.error(f"获取化学品试剂类型失败: {str(e)}")
            return []

    def set_types_for_chemical(self, chemical_id: int, type_ids: List[int]) -> bool:
        """设置化学品的试剂类型（先删除旧关联，再插入新关联）

        Args:
            chemical_id: 化学品 ID
            type_ids: 试剂类型 ID 列表

        Returns:
            是否成功
        """
        try:
            self.db.execute_update(
                "DELETE FROM chemical_reagent_type WHERE chemical_id = ?",
                (chemical_id,)
            )
            for type_id in type_ids:
                self.db.execute_insert(
                    "INSERT OR IGNORE INTO chemical_reagent_type (chemical_id, type_id) VALUES (?, ?)",
                    (chemical_id, type_id)
                )
            return True
        except Exception as e:
            logger.error(f"设置化学品试剂类型失败: {str(e)}")
            return False


# 全局实例
chemical_reagent_type_service = ChemicalReagentTypeService()