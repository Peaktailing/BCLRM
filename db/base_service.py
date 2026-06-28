"""SQLite 数据库基础服务类

该模块提供数据库 CRUD 操作的基础封装。
"""
from typing import List, Dict, Optional, Any
from db.database import Database
from utils.error_handler import logger


class BaseService:
    """数据库基础服务类

    提供通用的 CRUD 操作，各业务服务类继承此类获得基础数据库操作能力。
    """

    def __init__(self, table_name: str, db: Database = None):
        """初始化服务

        Args:
            table_name: 数据表名称
            db: 数据库实例，默认使用全局实例
        """
        self.table_name = table_name
        self.db = db or Database()

    def get_all(self, order_by: str = None, limit: int = None) -> List[Dict]:
        """获取所有记录

        Args:
            order_by: 排序字段，格式如 'created_at DESC'
            limit: 限制返回数量

        Returns:
            记录列表
        """
        query = f"SELECT * FROM {self.table_name}"

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {limit}"

        try:
            return self.db.execute_query(query)
        except Exception as e:
            logger.error(f"获取所有记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return []

    def get_by_id(self, record_id: int) -> Optional[Dict]:
        """根据 ID 获取记录

        Args:
            record_id: 记录 ID

        Returns:
            记录字典或 None
        """
        query = f"SELECT * FROM {self.table_name} WHERE id = ?"
        try:
            results = self.db.execute_query(query, (record_id,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"根据ID获取记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return None

    def get_by_field(self, field_name: str, value: Any) -> Optional[Dict]:
        """根据字段值获取单条记录

        Args:
            field_name: 字段名
            value: 字段值

        Returns:
            记录字典或 None
        """
        query = f"SELECT * FROM {self.table_name} WHERE {field_name} = ? LIMIT 1"
        try:
            results = self.db.execute_query(query, (value,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"根据字段获取记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return None

    def get_all_by_field(self, field_name: str, value: Any, order_by: str = None) -> List[Dict]:
        """根据字段值获取所有匹配记录

        Args:
            field_name: 字段名
            value: 字段值
            order_by: 排序字段

        Returns:
            记录列表
        """
        query = f"SELECT * FROM {self.table_name} WHERE {field_name} = ?"

        if order_by:
            query += f" ORDER BY {order_by}"

        try:
            return self.db.execute_query(query, (value,))
        except Exception as e:
            logger.error(f"根据字段获取所有记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return []

    def create(self, fields: Dict) -> Optional[int]:
        """创建记录

        Args:
            fields: 字段字典

        Returns:
            新记录的 ID，失败返回 None
        """
        if not fields:
            logger.warning(f"创建记录失败 [{self.table_name}]: 字段为空")
            return None

        # 构建插入语句
        columns = ', '.join(fields.keys())
        placeholders = ', '.join(['?' for _ in fields])
        query = f"INSERT INTO {self.table_name} ({columns}) VALUES ({placeholders})"

        try:
            record_id = self.db.execute_insert(query, tuple(fields.values()))
            logger.info(f"创建记录成功 [{self.table_name}] ID: {record_id}")
            return record_id
        except Exception as e:
            logger.error(f"创建记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return None

    def update(self, record_id: int, fields: Dict) -> bool:
        """更新记录

        Args:
            record_id: 记录 ID
            fields: 要更新的字段字典

        Returns:
            是否成功
        """
        if not fields:
            logger.warning(f"更新记录失败 [{self.table_name}]: 字段为空")
            return False

        # 构建更新语句
        set_clause = ', '.join([f"{key} = ?" for key in fields.keys()])
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"

        params = tuple(fields.values()) + (record_id,)

        try:
            affected_rows = self.db.execute_update(query, params)
            success = affected_rows > 0
            if success:
                logger.info(f"更新记录成功 [{self.table_name}] ID: {record_id}")
            else:
                logger.warning(f"更新记录未找到 [{self.table_name}] ID: {record_id}")
            return success
        except Exception as e:
            logger.error(f"更新记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return False

    def update_by_field(self, field_name: str, value: Any, fields: Dict) -> bool:
        """根据字段值更新记录

        Args:
            field_name: 匹配字段名
            value: 匹配字段值
            fields: 要更新的字段字典

        Returns:
            是否成功
        """
        if not fields:
            logger.warning(f"更新记录失败 [{self.table_name}]: 字段为空")
            return False

        set_clause = ', '.join([f"{key} = ?" for key in fields.keys()])
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {field_name} = ?"

        params = tuple(fields.values()) + (value,)

        try:
            affected_rows = self.db.execute_update(query, params)
            return affected_rows > 0
        except Exception as e:
            logger.error(f"根据字段更新记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return False

    def delete(self, record_id: int) -> bool:
        """删除记录

        Args:
            record_id: 记录 ID

        Returns:
            是否成功
        """
        query = f"DELETE FROM {self.table_name} WHERE id = ?"

        try:
            affected_rows = self.db.execute_update(query, (record_id,))
            success = affected_rows > 0
            if success:
                logger.info(f"删除记录成功 [{self.table_name}] ID: {record_id}")
            else:
                logger.warning(f"删除记录未找到 [{self.table_name}] ID: {record_id}")
            return success
        except Exception as e:
            logger.error(f"删除记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return False

    def delete_by_field(self, field_name: str, value: Any) -> bool:
        """根据字段值删除记录

        Args:
            field_name: 匹配字段名
            value: 匹配字段值

        Returns:
            是否成功
        """
        query = f"DELETE FROM {self.table_name} WHERE {field_name} = ?"

        try:
            affected_rows = self.db.execute_update(query, (value,))
            return affected_rows > 0
        except Exception as e:
            logger.error(f"根据字段删除记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return False

    def count(self) -> int:
        """统计记录总数

        Returns:
            记录总数
        """
        query = f"SELECT COUNT(*) as count FROM {self.table_name}"
        try:
            result = self.db.execute_query(query)
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"统计记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return 0

    def count_by_field(self, field_name: str, value: Any) -> int:
        """根据字段值统计记录数

        Args:
            field_name: 字段名
            value: 字段值

        Returns:
            记录数
        """
        query = f"SELECT COUNT(*) as count FROM {self.table_name} WHERE {field_name} = ?"
        try:
            result = self.db.execute_query(query, (value,))
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"统计记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return 0

    def search(self, keyword: str, fields: List[str], order_by: str = None) -> List[Dict]:
        """多字段模糊搜索

        Args:
            keyword: 搜索关键词
            fields: 要搜索的字段列表
            order_by: 排序字段

        Returns:
            匹配的记录列表
        """
        if not keyword or not fields:
            return []

        # 构建 LIKE 搜索条件
        conditions = ' OR '.join([f"{field} LIKE ?" for field in fields])
        query = f"SELECT * FROM {self.table_name} WHERE {conditions}"

        # 所有字段都使用相同的关键词
        params = tuple([f"%{keyword}%" for _ in fields])

        if order_by:
            query += f" ORDER BY {order_by}"

        try:
            return self.db.execute_query(query, params)
        except Exception as e:
            logger.error(f"搜索记录失败 [{self.table_name}]: {str(e)}", exception=e)
            return []

    def search_multi_condition(
        self,
        conditions: List[Dict[str, Any]],
        order_by: str = None,
        limit: int = None
    ) -> List[Dict]:
        """多条件组合查询（数据库层过滤，支持精确匹配和模糊匹配）

        将过滤逻辑下沉到 SQLite 数据库层执行，避免全量加载后在 Python 内存中过滤，
        大幅减少数据传输量和内存占用，提升查询效率。

        Args:
            conditions: 条件列表，每个条件为 dict，格式：
                {
                    "field": "字段名",
                    "value": 匹配值,
                    "match_type": "exact" | "fuzzy" | "keyword"
                }
                - exact: 精确匹配 (field = ?)
                - fuzzy: 模糊匹配 (field LIKE ?)
                - keyword: 关键词跨字段搜索 (field1 LIKE ? OR field2 LIKE ? ...)，
                  此时 value 为关键词字符串，额外需要 "keyword_fields" 列表
            order_by: 排序字段，格式如 'created_at DESC'
            limit: 限制返回数量

        Returns:
            匹配的记录列表
        """
        if not conditions:
            return self.get_all(order_by=order_by, limit=limit)

        where_clauses = []
        params = []

        for cond in conditions:
            match_type = cond.get("match_type", "exact")
            field = cond.get("field", "")
            value = cond.get("value")

            if value is None or value == "":
                continue

            if match_type == "exact":
                where_clauses.append(f"{field} = ?")
                params.append(value)
            elif match_type == "fuzzy":
                where_clauses.append(f"{field} LIKE ?")
                params.append(f"%{value}%")
            elif match_type == "keyword":
                keyword = str(value)
                keyword_fields = cond.get("keyword_fields", [field])
                if keyword_fields:
                    keyword_clauses = " OR ".join([f"{kf} LIKE ?" for kf in keyword_fields])
                    where_clauses.append(f"({keyword_clauses})")
                    params.extend([f"%{keyword}%" for _ in keyword_fields])

        if not where_clauses:
            return self.get_all(order_by=order_by, limit=limit)

        query = f"SELECT * FROM {self.table_name} WHERE {' AND '.join(where_clauses)}"

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {limit}"

        try:
            return self.db.execute_query(query, tuple(params))
        except Exception as e:
            logger.error(
                f"多条件查询失败 [{self.table_name}]: {str(e)}",
                exception=e
            )
            return []

    def exists(self, field_name: str, value: Any) -> bool:
        """检查记录是否存在

        Args:
            field_name: 字段名
            value: 字段值

        Returns:
            是否存在
        """
        return self.get_by_field(field_name, value) is not None

    def get_distinct_values(self, field_name: str) -> List[Any]:
        """获取字段的所有不同值

        Args:
            field_name: 字段名

        Returns:
            不同值列表
        """
        query = f"SELECT DISTINCT {field_name} FROM {self.table_name} WHERE {field_name} IS NOT NULL"
        try:
            result = self.db.execute_query(query)
            return [row[field_name] for row in result]
        except Exception as e:
            logger.error(f"获取不同值失败 [{self.table_name}]: {str(e)}", exception=e)
            return []