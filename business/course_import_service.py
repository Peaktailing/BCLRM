"""实验课程 / 实验项目导入服务

把学院实验分组表（CSV / Excel）解析为「课程」与「实验项目」并幂等导入。
支持多张表按需导入：学年 / 学期 / 学院优先从表格标题解析，也允许调用方覆盖。

表格模板（前 3 行固定为：标题行 / 表头行 / 子表头行）：
    标题行：如「生物与食品工程学院2026-2027-1实验项目分组表」
    表头行：序号 | 教师 | 课程名称 | 开课专业 | 开课班级 | 班级人数 | 实验项目 | 第一组 ... | 地点
    子表头：周次 | 星期 | 日期 | 节次 | 人数 ...
数据自第 4 行起。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

from services.base.experiment_course_service import experiment_course_service
from services.base.experiment_item_service import experiment_item_service
from utils.error_handler import logger, ServiceResult, handle_exception


def normalize_class_name(name: Optional[str]) -> Optional[str]:
    """统一班级名：两位年份补全为四位（如 24级1班 -> 2024级1班）"""
    if not name:
        return name
    return re.sub(r'^(\d{2})级', lambda m: f"20{m.group(1)}级", str(name).strip())


def parse_title(title: str):
    """从标题解析（学院, 学年, 学期）"""
    text = str(title or '').strip()
    match = re.search(r'(\d{4})-(\d{4})-(\d)', text)
    if not match:
        return None, None, None
    college = text[:match.start()].strip() or None
    return college, f"{match.group(1)}-{match.group(2)}", match.group(3)


def _clean(value) -> Optional[str]:
    """清洗单元格文本，空值返回 None"""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text or None


class CourseImportService:
    """实验课程 / 实验项目导入服务"""

    #: 数据起始行下标（0=标题 1=表头 2=子表头）
    DATA_START_ROW = 3
    #: 模板列下标
    COL_TEACHER = 1
    COL_COURSE = 2
    COL_MAJOR = 3
    COL_CLASS = 4
    COL_COUNT = 5
    COL_ITEM = 6
    COL_LOCATION = 27

    # ------------------------------------------------------------------
    # 解析
    # ------------------------------------------------------------------
    def _read_csv(self, source):
        """按常见中文编码依次尝试读取 CSV"""
        for encoding in ('utf-8-sig', 'utf-8', 'gbk', 'gb18030'):
            try:
                if hasattr(source, "seek"):
                    source.seek(0)
                return pd.read_csv(source, encoding=encoding, header=None, dtype=str)
            except Exception:
                continue
        raise ValueError("无法识别的 CSV 编码（已尝试 utf-8/gbk/gb18030）")

    def _extract(self, raw) -> Tuple[List[Dict], List[Dict]]:
        """从原始表格提取（课程列表, 实验项目列表）"""
        data = raw.iloc[self.DATA_START_ROW:].reset_index(drop=True)
        location_col = self.COL_LOCATION if raw.shape[1] > self.COL_LOCATION else raw.shape[1] - 1

        df = pd.DataFrame({
            'teacher': data[self.COL_TEACHER],
            'course_name': data[self.COL_COURSE],
            'major': data[self.COL_MAJOR],
            'class_name': data[self.COL_CLASS],
            'student_count': data[self.COL_COUNT],
            'item_name': data[self.COL_ITEM],
            'location': data[location_col],
        })
        df = df[df['course_name'].notna() & (df['course_name'].astype(str).str.strip() != '')]

        # ---- 实验项目（按课程名去重保序）----
        items: List[Dict] = []
        for course_name, group in df.groupby('course_name', dropna=False, sort=False):
            seen = set()
            seq = 0
            for value in group['item_name'].dropna():
                name = str(value).strip()
                if not name or name in seen:
                    continue
                seen.add(name)
                seq += 1
                items.append({
                    "course_name": str(course_name).strip(),
                    "seq": seq,
                    "item_name": name,
                })

        # ---- 课程（课程 + 班级 合并）----
        courses: List[Dict] = []
        for (course_name, class_name), group in df.groupby(['course_name', 'class_name'], dropna=False):
            teachers: List[str] = []
            for value in group['teacher'].dropna():
                for part in re.split(r'[、,，/\s]+', str(value).strip()):
                    if part and part not in teachers:
                        teachers.append(part)

            counts = [int(float(v)) for v in group['student_count'].dropna()
                      if str(v).strip() not in ('', 'nan')]
            locations = [v for v in (_clean(x) for x in group['location'].dropna()) if v]
            majors = [v for v in (_clean(x) for x in group['major'].dropna()) if v]

            raw_class = _clean(class_name)
            courses.append({
                "course_name": str(course_name).strip(),
                "class_name": normalize_class_name(raw_class),
                "raw_class_name": raw_class,
                "major": majors[0] if majors else None,
                "teacher": "、".join(teachers) or None,
                "student_count": max(counts) if counts else None,
                "location": locations[0] if locations else None,
            })
        return courses, items

    @handle_exception(context="解析实验分组表")
    def parse(self, source, filename: str = "") -> ServiceResult:
        """解析分组表，返回 data = {college, semester, term, courses, items}"""
        name = str(filename or (source if isinstance(source, str) else "")).lower()
        if name.endswith(('.xlsx', '.xls')):
            if hasattr(source, "seek"):
                source.seek(0)
            raw = pd.read_excel(source, header=None, dtype=str)
        else:
            raw = self._read_csv(source)

        if raw.shape[0] <= self.DATA_START_ROW:
            return ServiceResult.fail(
                message="表格为空或格式不正确（未找到数据行）",
                error_code="EMPTY_TABLE"
            )

        college, semester, term = parse_title(raw.iloc[0, 0])
        courses, items = self._extract(raw)
        if not courses:
            return ServiceResult.fail(
                message="未解析到课程，请确认表格为学院实验分组表模板",
                error_code="NO_COURSE_PARSED"
            )

        logger.info(
            "实验分组表解析完成",
            filename=filename,
            semester=semester,
            term=term,
            course_count=len(courses),
            item_count=len(items)
        )
        return ServiceResult.ok(
            data={
                "college": college,
                "semester": semester,
                "term": term,
                "courses": courses,
                "items": items,
            },
            message=f"解析到 {len(courses)} 条课程、{len(items)} 个实验项目"
        )

    # ------------------------------------------------------------------
    # 导入
    # ------------------------------------------------------------------
    @handle_exception(context="导入实验课程")
    def import_courses(
        self,
        courses: List[Dict],
        semester: str,
        term: str,
        college: Optional[str] = None,
        items: Optional[List[Dict]] = None
    ) -> ServiceResult:
        """幂等导入课程与实验项目

        - 课程：按 (学年, 学期, 课程名称, 班级) 更新或新增
        - 实验项目：按 (学年, 课程名称, 实验名称) 更新或新增
        """
        if not semester or not term:
            return ServiceResult.fail(
                message="缺少学年或学期，请先补充",
                error_code="MISSING_SEMESTER"
            )

        # ---------- 课程 ----------
        existing = {}
        for row in experiment_course_service.get_by_semester(semester):
            if str(row.term) == str(term):
                existing[(row.course_name, row.class_name)] = row

        inserted = updated = failed = 0
        for course in courses:
            payload = {
                "semester": semester,
                "term": str(term),
                "course_name": course.get("course_name"),
                "class_name": course.get("class_name"),
                "major": course.get("major"),
                "teacher": course.get("teacher"),
                "student_count": course.get("student_count"),
                "location": course.get("location"),
                "college": college,
            }
            key = (course.get("course_name"), course.get("class_name"))
            raw_key = (course.get("course_name"), course.get("raw_class_name"))
            row = existing.get(key) or existing.get(raw_key)

            if row is None:
                if experiment_course_service.create(payload):
                    inserted += 1
                else:
                    failed += 1
            else:
                fields = {k: v for k, v in payload.items() if v is not None}
                if experiment_course_service.update(row.id, fields):
                    updated += 1
                else:
                    failed += 1

        # ---------- 实验项目 ----------
        # 跨学年去重：同一「课程名 + 实验名」只保留一条（默认方案因此可跨学年复用），
        # 分组表通常是在上一年的表上继续追加，故这里按全量（含往年）做幂等匹配。
        item_created = item_updated = item_skipped = 0
        if items:
            existing_items = {}
            for row in experiment_item_service.get_all_parsed():
                existing_items.setdefault((row.course_name, row.item_name), row)

            seen_in_file = set()
            for item in items:
                key = (item.get("course_name"), item.get("item_name"))
                if key in seen_in_file:
                    item_skipped += 1
                    continue
                seen_in_file.add(key)

                payload = {
                    "semester": semester,
                    "course_name": item.get("course_name"),
                    "seq": item.get("seq"),
                    "item_name": item.get("item_name"),
                }
                row = existing_items.get(key)
                if row is None:
                    if experiment_item_service.create(payload):
                        item_created += 1
                else:
                    # 已存在（往年导入过）：刷新学年与序号，不重复插入
                    if experiment_item_service.update(
                        row.id, {"seq": item.get("seq"), "semester": semester}
                    ):
                        item_updated += 1

        logger.info(
            "课程导入完成",
            inserted=inserted, updated=updated, failed=failed,
            item_created=item_created, item_updated=item_updated, item_skipped=item_skipped
        )
        return ServiceResult.ok(
            data={
                "inserted": inserted, "updated": updated, "failed": failed,
                "item_created": item_created, "item_updated": item_updated,
                "item_skipped": item_skipped,
            },
            message=(
                f"课程：新增 {inserted}、更新 {updated}；"
                f"实验项目：新增 {item_created}、更新 {item_updated}、去重跳过 {item_skipped}；"
                f"失败 {failed}"
            )
        )


# 全局实例
course_import_service = CourseImportService()
