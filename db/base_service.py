"""SQLite 数据库基础服务类

该模块提供数据库 CRUD 操作的基础封装。

## 写入版本（rev）

带 ``rev`` 列的表，每次写入都会把 ``rev`` 自增 1；调用方可以把「读出时
的 rev」交给 ``update(..., expect=rev)``，只有库里仍是那一版才写成功。

为什么需要它：业务方法普遍是「读 → 判断 → 写」，两步之间另一路写入完全
可以插进来（同一瓶被两个人同时流转、审批与撤回同时发生）。条件更新
（``update_where``）能防住「状态被改」，但防不住「值被改而状态没变」
——例如管理人被换成了别人，状态仍是可借。rev 是唯一一个每次写入都动的
字段，所以它同时是「有没有人动过」的判据。

约定：
- 版本只由这里推进。调用方 ``fields`` 里塞的 ``rev`` 会被丢掉，
  否则「改一次 rev 不动」或「手动倒回」会让整套判断失效。
- ``expect=None`` 表示「我没读，也没有要比的版本」（批量作业、导入），
  只做写入，不做校验。
"""
import re
from typing import List, Dict, Optional, Any
from db.database import Database
from utils.error_handler import StaleRevisionError, logger
from utils.permission_guard import enforce_write

# SQL 标识符安全校验正则：仅允许 字母/数字/下划线，必须以字母或下划线开头
_FIELD_NAME_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*$')
# ORDER BY 安全校验：字段名 + 可选 ASC/DESC
_ORDER_BY_PATTERN = re.compile(r'^[a-zA-Z_][a-zA-Z0-9_]*(\s+(ASC|DESC))?$', re.IGNORECASE)


class BaseService:
    """数据库基础服务类

    提供通用的 CRUD 操作，各业务服务类继承此类获得基础数据库操作能力。
    """

    #: 版本列名。子类要换名字（例如 Lims 的 sync_version）时覆盖这个常量。
    REVISION_COLUMN = "rev"

    def __init__(self, table_name: str, db: Database = None):
        """初始化服务

        Args:
            table_name: 数据表名称
            db: 数据库实例，默认使用全局实例
        """
        if not _FIELD_NAME_PATTERN.match(table_name):
            raise ValueError(f"非法表名: {table_name}")
        self.table_name = table_name
        self.db = db or Database()
        # 表有没有版本列：延迟探测一次。表结构在一个进程里不会变，
        # 但每次写都问一次 PRAGMA 是白花的。
        self._has_revision: Optional[bool] = None

    # ------------------------------------------------------------------
    # 版本列
    # ------------------------------------------------------------------
    @property
    def revision_column(self) -> str:
        return self.REVISION_COLUMN

    def has_revision(self) -> bool:
        """这张表有没有版本列（结果缓存，首次写入时探测）。"""
        if self._has_revision is None:
            try:
                info = self.db.execute_query(f"PRAGMA table_info({self.table_name})")
                self._has_revision = any(
                    (row.get("name") or "") == self.revision_column for row in info
                )
            except Exception as exc:              # 表还不存在等：当作没有
                logger.warning(f"探测版本列失败 [{self.table_name}]: {exc}")
                self._has_revision = False
        return self._has_revision

    def _bump_clause(self) -> str:
        return f", {self.revision_column} = {self.revision_column} + 1"

    def _drop_revision(self, fields: Dict) -> Dict:
        """丢掉调用方写的版本列：版本只由本类推进。"""
        if self.revision_column not in fields:
            return fields
        return {key: value for key, value in fields.items() if key != self.revision_column}

    def _check_not_stale(self, expect: Optional[int], lookup: Dict) -> None:
        """条件不成立时判断：是「行没了」还是「版本变了」。

        ``lookup`` 是能唯一定位那一行的条件（``{"id": …}`` 或
        ``{"field": value}``）。行不存在就静静返回 False（沿用既有语义），
        存在则抛 StaleRevisionError——这两件事对调用方的意义完全不同。
        """
        if expect is None:
            return
        where = " AND ".join(f"{key} = ?" for key in lookup)
        rows = self.db.execute_query(
            f"SELECT {self.revision_column} AS rev FROM {self.table_name} WHERE {where}",
            tuple(lookup.values()),
        )
        if not rows:
            return
        current = rows[0].get("rev")
        raise StaleRevisionError(
            f"这行在你读出来之后已被改动过（你看的是第 {int(expect)} 版，现在是第 {current} 版），请刷新后再操作",
            details={"table": self.table_name, "expected": int(expect), "current": current},
        )

    @staticmethod
    def _validate_field_name(field_name: str) -> None:
        """校验字段名安全，防止 SQL 注入"""
        if not _FIELD_NAME_PATTERN.match(field_name):
            raise ValueError(f"非法字段名: {field_name}")

    @staticmethod
    def _validate_order_by(order_by: str) -> None:
        """校验 ORDER BY 子句安全，防止 SQL 注入"""
        if not _ORDER_BY_PATTERN.match(order_by):
            raise ValueError(f"非法排序表达式: {order_by}")

    def get_all(self, order_by: str = None, limit: int = None) -> List[Dict]:
        """获取所有记录

        Args:
            order_by: 排序字段，格式如 'created_at DESC'
            limit: 限制返回数量

        Returns:
            记录列表
        """
        if order_by:
            self._validate_order_by(order_by)

        query = f"SELECT * FROM {self.table_name}"

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {int(limit)}"

        try:
            return self.db.execute_query(query)
        except Exception as e:
            logger.error(f"获取所有记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

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
            raise

    def get_by_field(self, field_name: str, value: Any) -> Optional[Dict]:
        """根据字段值获取单条记录

        Args:
            field_name: 字段名
            value: 字段值

        Returns:
            记录字典或 None
        """
        self._validate_field_name(field_name)
        query = f"SELECT * FROM {self.table_name} WHERE {field_name} = ? LIMIT 1"
        try:
            results = self.db.execute_query(query, (value,))
            return results[0] if results else None
        except Exception as e:
            logger.error(f"根据字段获取记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

    def get_all_by_field(self, field_name: str, value: Any, order_by: str = None) -> List[Dict]:
        """根据字段值获取所有匹配记录

        Args:
            field_name: 字段名
            value: 字段值
            order_by: 排序字段

        Returns:
            记录列表
        """
        self._validate_field_name(field_name)
        if order_by:
            self._validate_order_by(order_by)

        query = f"SELECT * FROM {self.table_name} WHERE {field_name} = ?"

        if order_by:
            query += f" ORDER BY {order_by}"

        try:
            return self.db.execute_query(query, (value,))
        except Exception as e:
            logger.error(f"根据字段获取所有记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

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

        # 集中式服务端写权限守卫（规则见 utils/permission_guard.py）
        enforce_write(self.table_name, fields, action="新增")

        # 校验所有字段名安全
        for key in fields.keys():
            self._validate_field_name(key)

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
            raise

    def update(self, record_id: int, fields: Dict, expect: Optional[int] = None) -> bool:
        """更新记录

        Args:
            record_id: 记录 ID
            fields: 要更新的字段字典
            expect: 期望的版本号。Given（非 None）时只有库里仍是这一版才写，
                    否则抛 :class:`utils.error_handler.StaleRevisionError`。
                    None 表示不比版本（批量作业、导入）。

        Returns:
            是否成功（0 行受影响 = 记录不存在或版本不符）
        """
        if not fields:
            logger.warning(f"更新记录失败 [{self.table_name}]: 字段为空")
            return False

        # 集中式服务端写权限守卫（规则见 utils/permission_guard.py）
        enforce_write(self.table_name, fields, action="更新")

        # 校验所有字段名安全
        for key in fields.keys():
            self._validate_field_name(key)

        fields = self._drop_revision(fields)
        versioned = self.has_revision()

        # 构建更新语句
        set_clause = ', '.join([f"{key} = ?" for key in fields.keys()])
        if versioned:
            set_clause += self._bump_clause()
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE id = ?"
        params = tuple(fields.values()) + (record_id,)

        if versioned and expect is not None:
            query += f" AND {self.revision_column} = ?"
            params += (int(expect),)

        try:
            affected_rows = self.db.execute_update(query, params)
            success = affected_rows > 0
            if success:
                logger.info(f"更新记录成功 [{self.table_name}] ID: {record_id}")
            elif versioned and expect is not None:
                self._check_not_stale(expect, {"id": record_id})
                logger.warning(
                    f"更新记录未找到 [{self.table_name}] ID: {record_id}"
                )
            else:
                logger.warning(f"更新记录未找到 [{self.table_name}] ID: {record_id}")
            return success
        except StaleRevisionError:
            raise
        except Exception as e:
            logger.error(f"更新记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

    def update_by_field(self, field_name: str, value: Any, fields: Dict,
                        expect: Optional[int] = None) -> bool:
        """根据字段值更新记录

        Args:
            field_name: 匹配字段名
            value: 匹配字段值
            fields: 要更新的字段字典
            expect: 期望的版本号（同 :meth:`update`）；配合唯一字段使用时
                    才有一一对应的意义，否则只有那一版的行会被改。

        Returns:
            是否成功
        """
        if not fields:
            logger.warning(f"更新记录失败 [{self.table_name}]: 字段为空")
            return False

        # 集中式服务端写权限守卫（规则见 utils/permission_guard.py）
        # row_identity：目标行身份（update_by_field 传入匹配字段值），
        # 用于守卫的「自助豁免」行级校验（只能改自己的密码，见 QA 审查 M8）
        enforce_write(
            self.table_name, fields, action="更新",
            row_identity={field_name: value},
        )

        self._validate_field_name(field_name)

        fields = self._drop_revision(fields)
        versioned = self.has_revision()

        set_clause = ', '.join([f"{key} = ?" for key in fields.keys()])
        if versioned:
            set_clause += self._bump_clause()
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {field_name} = ?"
        params = tuple(fields.values()) + (value,)

        if versioned and expect is not None:
            query += f" AND {self.revision_column} = ?"
            params += (int(expect),)

        try:
            affected_rows = self.db.execute_update(query, params)
            if not affected_rows and versioned and expect is not None:
                self._check_not_stale(expect, {field_name: value})
            return affected_rows > 0
        except StaleRevisionError:
            raise
        except Exception as e:
            logger.error(f"根据字段更新记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

    def update_where(self, conditions: Dict, fields: Dict) -> bool:
        """带条件更新：仅当所有条件均满足时才写入（原子抢占）

        用于「先校验状态、再按状态写回」的并发防护（如工单审批/撤回/驳回）：
        旧模式 check-then-act 中，审批人与申请人几乎同时操作时双方都能通过
        状态校验，导致已撤回工单仍被执行领用、审批状态被互相覆盖
        （QA 审查发现）。条件更新把「校验 + 写入」合并为单条原子 SQL。

        Args:
            conditions: WHERE 条件字典（字段名 → 期望值，AND 连接，值参数化）
            fields: 要更新的字段字典

        Returns:
            是否更新成功（0 行受影响 = 条件不满足，未发生写入）

        注意：这里的条件本身就是版本。调用方把「比较时看到的值」写进
        ``conditions``（例如 ``remaining_quantity``、``borrowable_flag``），
        就是一次 compare-and-set，不必再用 ``rev``。仍然自增 ``rev``，
        是为了让别处的 ``expect`` 也能感知到这次写入。
        """
        if not fields:
            logger.warning(f"更新记录失败 [{self.table_name}]: 字段为空")
            return False
        if not conditions:
            # 空条件会导致全表更新，直接拒绝（防止调用方遗漏条件）
            logger.warning(f"条件更新失败 [{self.table_name}]: 条件为空，拒绝执行")
            return False

        # 集中式服务端写权限守卫（规则见 utils/permission_guard.py）
        enforce_write(self.table_name, fields, action="更新")

        # 校验字段名安全（SET 子句与 WHERE 子句均需校验）
        for key in list(fields.keys()) + list(conditions.keys()):
            self._validate_field_name(key)

        fields = self._drop_revision(fields)
        set_clause = ', '.join([f"{key} = ?" for key in fields.keys()])
        if self.has_revision():
            set_clause += self._bump_clause()
        # None 条件转成 IS NULL，否则 `field = NULL` 永远不成立；
        # 用于「仅当 bottle_number 仍为空时回填」这类原子抢占。
        where_parts = []
        where_params = []
        for key, value in conditions.items():
            if value is None:
                where_parts.append(f"{key} IS NULL")
            else:
                where_parts.append(f"{key} = ?")
                where_params.append(value)
        where_clause = ' AND '.join(where_parts)
        query = f"UPDATE {self.table_name} SET {set_clause} WHERE {where_clause}"

        params = tuple(fields.values()) + tuple(where_params)

        try:
            affected_rows = self.db.execute_update(query, params)
            if affected_rows:
                logger.info(
                    f"条件更新成功 [{self.table_name}] "
                    f"条件: {list(conditions.keys())}"
                )
            else:
                logger.warning(
                    f"条件更新未命中 [{self.table_name}] 条件: {conditions}"
                )
            return affected_rows > 0
        except Exception as e:
            logger.error(f"条件更新记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

    def delete(self, record_id: int) -> bool:
        """删除记录

        Args:
            record_id: 记录 ID

        Returns:
            是否成功
        """
        # 集中式服务端写权限守卫（规则见 utils/permission_guard.py）
        enforce_write(self.table_name, action="删除")

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
            raise

    def delete_by_field(self, field_name: str, value: Any) -> bool:
        """根据字段值删除记录

        Args:
            field_name: 匹配字段名
            value: 匹配字段值

        Returns:
            是否成功
        """
        # 集中式服务端写权限守卫（规则见 utils/permission_guard.py）
        enforce_write(self.table_name, action="删除")

        self._validate_field_name(field_name)
        query = f"DELETE FROM {self.table_name} WHERE {field_name} = ?"

        try:
            affected_rows = self.db.execute_update(query, (value,))
            return affected_rows > 0
        except Exception as e:
            logger.error(f"根据字段删除记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

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
            raise

    def count_by_field(self, field_name: str, value: Any) -> int:
        """根据字段值统计记录数

        Args:
            field_name: 字段名
            value: 字段值

        Returns:
            记录数
        """
        self._validate_field_name(field_name)
        query = f"SELECT COUNT(*) as count FROM {self.table_name} WHERE {field_name} = ?"
        try:
            result = self.db.execute_query(query, (value,))
            return result[0]['count'] if result else 0
        except Exception as e:
            logger.error(f"统计记录失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

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

        # 校验所有搜索字段名安全
        for field in fields:
            self._validate_field_name(field)

        if order_by:
            self._validate_order_by(order_by)

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
            raise

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
        if order_by:
            self._validate_order_by(order_by)

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

            self._validate_field_name(field)

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
                    for kf in keyword_fields:
                        self._validate_field_name(kf)
                    keyword_clauses = " OR ".join([f"{kf} LIKE ?" for kf in keyword_fields])
                    where_clauses.append(f"({keyword_clauses})")
                    params.extend([f"%{keyword}%" for _ in keyword_fields])

        if not where_clauses:
            return self.get_all(order_by=order_by, limit=limit)

        query = f"SELECT * FROM {self.table_name} WHERE {' AND '.join(where_clauses)}"

        if order_by:
            query += f" ORDER BY {order_by}"

        if limit:
            query += f" LIMIT {int(limit)}"

        try:
            return self.db.execute_query(query, tuple(params))
        except Exception as e:
            logger.error(
                f"多条件查询失败 [{self.table_name}]: {str(e)}",
                exception=e
            )
            raise

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
        self._validate_field_name(field_name)
        query = f"SELECT DISTINCT {field_name} FROM {self.table_name} WHERE {field_name} IS NOT NULL"
        try:
            result = self.db.execute_query(query)
            return [row[field_name] for row in result]
        except Exception as e:
            logger.error(f"获取不同值失败 [{self.table_name}]: {str(e)}", exception=e)
            raise

    def get_max_value_by_prefix(self, field_name: str, prefix: str) -> Optional[str]:
        """获取指定字段以 prefix 开头的最大值（用于编号自增）

        使用 MAX() 聚合查询替代全表扫描，性能远优于加载全部记录后 Python 过滤。

        Args:
            field_name: 字段名
            prefix: 前缀字符串

        Returns:
            最大值字符串，无匹配记录时返回 None
        """
        self._validate_field_name(field_name)
        query = f"SELECT MAX({field_name}) as max_val FROM {self.table_name} WHERE {field_name} LIKE ?"
        try:
            result = self.db.execute_query(query, (f"{prefix}%",))
            if result and result[0].get('max_val'):
                return result[0]['max_val']
            return None
        except Exception as e:
            logger.error(f"获取最大值失败 [{self.table_name}.{field_name}]: {str(e)}", exception=e)
            raise