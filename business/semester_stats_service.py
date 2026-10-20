"""学期用量统计服务（基于领用工单口径）

用量 = 领用量 − 累计归还量（见 business/usage_service.py），
数据源为领用工单，按「课程 + 实验 + 试剂」聚合。

学年划分（如需调整，只改 utils/semester_utils.date_to_semester）：
    以每年 **8 月** 为学年起点，标识形如 ``2025-2026``
"""
from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from business.usage_service import is_effective_order, usage_service
from services.base.experiment_course_service import experiment_course_service
from services.core.borrow_order_service import borrow_order_service
from services.core.return_record_service import return_record_service
from utils.error_handler import logger, ServiceResult, handle_exception
from utils.semester_utils import date_to_semester, parse_date  # noqa: F401（对外兼容导出）


class SemesterStatsService:
    """学期用量统计服务"""

    # ------------------------------------------------------------------
    @handle_exception(context="获取学期列表")
    def list_semesters(self) -> ServiceResult:
        """存在工单的学年（倒序）"""
        data = usage_service.list_semesters()
        logger.info("学年列表查询完成", semester_count=len(data))
        return ServiceResult.ok(data=data, message=f"共 {len(data)} 个学年")

    @handle_exception(context="学期用量汇总")
    def get_usage_summary(self, semester: Optional[str] = None) -> ServiceResult:
        """学年用量汇总：总用量 / 领用人数 / 人均用量 / 工单数 / 归还次数"""
        rows = usage_service.collect(semester)

        usage_by_unit: Dict[str, float] = defaultdict(float)
        for row in rows:
            usage_by_unit[row.get("unit") or "g"] += float(row["usage"])
        total_usage = round(sum(usage_by_unit.values()), 2)
        users = set()
        for row in rows:
            users.update(row["applicants"])
        user_count = len(users)
        avg_per_user = round(total_usage / user_count, 2) if user_count else 0.0

        orders = [
            order for order in borrow_order_service.get_all_parsed()
            if is_effective_order(order)
            and (
                semester is None
                or date_to_semester(getattr(order, "borrow_time", None)) == semester
            )
        ]
        return_count = len([
            record for record in return_record_service.get_all_parsed()
            if semester is None or date_to_semester(getattr(record, "return_time", None)) == semester
        ])

        data = {
            "semester": semester or "全部",
            "total_usage": total_usage,
            "usage_by_unit": {
                unit: round(value, 2) for unit, value in usage_by_unit.items()
            },
            "multiple_units": len(usage_by_unit) > 1,
            "user_count": user_count,
            "avg_per_user": avg_per_user,
            "reagent_count": len({
                row["reagent_name"] for row in rows if row.get("reagent_name")
            }),
            "borrow_count": len(orders),
            "return_count": return_count,
        }
        logger.info("学年用量汇总完成", **data)
        return ServiceResult.ok(data=data, message="统计完成")

    @handle_exception(context="按人用量统计")
    def get_usage_by_user(self, semester: Optional[str] = None) -> ServiceResult:
        """按领用人聚合用量（倒序）"""
        rows = usage_service.usage_by_user(semester)
        logger.info("按人用量统计完成", user_count=len(rows))
        return ServiceResult.ok(data=rows, message=f"共 {len(rows)} 位领用人")

    @handle_exception(context="按月用量统计")
    def get_usage_by_month(self, semester: Optional[str] = None) -> ServiceResult:
        """按月份聚合用量（升序，跟随领用时间）"""
        data = usage_service.usage_by_month(semester)
        logger.info("按月用量统计完成", month_count=len(data))
        return ServiceResult.ok(data=data, message=f"共 {len(data)} 个月份")

    @handle_exception(context="按课程用量统计")
    def get_usage_by_course(self, semester: Optional[str] = None) -> ServiceResult:
        """按实验课程聚合用量与人均（人均 = 课程用量 ÷ 课程人数）"""
        rows = usage_service.collect(semester, only_course=True)

        # 课程分组：按 course_id 聚合
        grouped: Dict[tuple, Dict] = {}
        for row in rows:
            course_id = row.get("course_id")
            unit = row.get("unit") or "g"
            entry = grouped.setdefault((course_id, unit), {
                "course_name": row.get("course_name") or f"课程#{course_id}",
                "unit": unit,
                "usage": 0.0,
                "experiments": set(),
            })
            entry["usage"] += row["usage"]
            if row.get("item_name"):
                entry["experiments"].add(row["item_name"])

        # 课程人数：按 course_id（班级记录）取该班级人数，不能用同名课程总人数，
        # 否则每个班级行都会被他班人数稀释。
        courses = experiment_course_service.get_by_semester(semester)
        students_by_id: Dict[int, int] = {
            course.id: int(course.student_count or 0) for course in courses
        }
        students_by_name: Dict[str, int] = defaultdict(int)
        meta_by_name: Dict[str, Dict] = {}
        for course in courses:
            students_by_name[course.course_name] += int(course.student_count or 0)
            meta_by_name.setdefault(course.course_name, {
                "class_name": course.class_name,
                "teacher": course.teacher,
            })

        result: List[Dict] = []
        for (course_id, unit), entry in grouped.items():
            course_name = entry["course_name"]
            students = (
                students_by_id.get(course_id)
                if course_id is not None
                else students_by_name.get(course_name, 0)
            ) or 0
            usage = round(entry["usage"], 2)
            meta = meta_by_name.get(course_name, {})
            result.append({
                "课程": course_name,
                "班级": meta.get("class_name") or "-",
                "单位": unit,
                "教师": meta.get("teacher") or "-",
                "课程人数": students,
                "实验数": len(entry["experiments"]),
                "用量": usage,
                "人均用量": round(usage / students, 2) if students else None,
            })
        result.sort(key=lambda item: item["用量"], reverse=True)

        logger.info("按课程用量统计完成", course_count=len(result))
        return ServiceResult.ok(data=result, message=f"共 {len(result)} 门课程")

    @handle_exception(context="按试剂用量统计")
    def get_usage_by_reagent(self, semester: Optional[str] = None) -> ServiceResult:
        """按试剂聚合用量与人均

        人均用量 = 该试剂用量 ÷ 全体领用人数（各试剂分别汇总；
        分母沿用页面既有口径“全体领用人数”，不是该试剂自己的领用人数）。
        """
        rows = usage_service.collect(semester)

        users = set()
        for row in rows:
            users.update(row.get("applicants") or [])
        user_count = len(users)

        grouped: Dict[str, Dict] = {}
        for row in rows:
            name = row.get("reagent_name") or "（未命名试剂）"
            unit = row.get("unit") or "g"
            entry = grouped.setdefault((name, unit), {
                "unit": unit,
                "usage": 0.0,
                "order_count": 0,
                "applicants": set(),
                "experiments": set(),
            })
            entry["usage"] += float(row["usage"])
            entry["order_count"] += int(row.get("order_count") or 0)
            entry["applicants"].update(row.get("applicants") or [])
            if row.get("item_name"):
                entry["experiments"].add(row["item_name"])

        result: List[Dict] = []
        for (name, unit), entry in grouped.items():
            usage = round(entry["usage"], 2)
            result.append({
                "试剂名称": name,
                "单位": unit,
                "用量": usage,
                "人均用量": round(usage / user_count, 2) if user_count else None,
                "领用人次": len(entry["applicants"]),
                "涉及实验": len(entry["experiments"]),
                "领用次数": entry["order_count"],
            })
        result.sort(key=lambda item: item["用量"], reverse=True)

        logger.info(
            "按试剂用量统计完成",
            reagent_count=len(result), user_count=user_count
        )
        return ServiceResult.ok(
            data=result,
            message=f"共 {len(result)} 种试剂（人均按 {user_count} 位领用人折算）"
        )

    @handle_exception(context="按课程-实验-试剂用量统计")
    def get_usage_by_course_item_reagent(self, semester: Optional[str] = None) -> ServiceResult:
        """按「课程 → 实验 → 试剂」聚合用量（**不分班级**）

        合并规则：同一「课程 + 实验名称 + 试剂名称」合并为一行，不再按班级拆开；
        用量与人数均取各班级的**平均值**：
            平均用量 = 合计用量 ÷ 班级数
            班级平均人数 = 各班级人数之和 ÷ 班级数
            人均用量 = 平均用量 ÷ 班级平均人数（等价于 合计用量 ÷ 总人数）
        """
        rows = usage_service.collect(semester, only_course=True)

        # 各课程（按班级记录）的人数与教师；指定学年时只取该学年的班级
        courses = experiment_course_service.get_by_semester(semester)
        student_counts_by_name: Dict[str, List[int]] = defaultdict(list)
        teacher_by_name: Dict[str, str] = {}
        for course in courses:
            student_counts_by_name[course.course_name].append(int(course.student_count or 0))
            teacher_by_name.setdefault(course.course_name, course.teacher or "-")

        # 合并：课程 + 实验名 + 试剂名（不含班级）
        grouped: Dict[tuple, Dict] = {}
        for row in rows:
            course_name = row.get("course_name") or "（未关联课程）"
            key = (
                course_name,
                row.get("item_name") or "-",
                row.get("reagent_name") or "-",
                row.get("unit") or "g",
            )
            entry = grouped.setdefault(key, {
                "unit": row.get("unit") or "g",
                "usage": 0.0,
                "class_count": 0,
                "order_count": 0,
            })
            entry["usage"] += float(row["usage"])
            entry["class_count"] += 1
            entry["order_count"] += int(row.get("order_count") or 0)

        result: List[Dict] = []
        for (course_name, item_name, reagent_name, unit), entry in grouped.items():
            counts = [c for c in student_counts_by_name.get(course_name, []) if c > 0]
            avg_students = round(sum(counts) / len(counts)) if counts else 0
            class_count = entry["class_count"] or 1
            avg_usage = round(entry["usage"] / class_count, 2)
            result.append({
                "课程": course_name,
                "教师": teacher_by_name.get(course_name, "-"),
                "实验": item_name,
                "试剂": reagent_name,
                "单位": entry["unit"],
                "平均用量": avg_usage,
                "班级平均人数": avg_students,
                "人均用量": round(avg_usage / avg_students, 4) if avg_students else None,
                "班级数": class_count,
                "合计用量": round(entry["usage"], 2),
                "领用次数": entry["order_count"],
            })

        result.sort(key=lambda item: (item["课程"], item["实验"], -item["平均用量"]))

        logger.info("按课程-实验-试剂用量统计完成", row_count=len(result))
        return ServiceResult.ok(
            data=result,
            message=f"共 {len(result)} 条「课程-实验-试剂」记录（已按实验名合并、不分班级）"
        )


# 全局实例
semester_stats_service = SemesterStatsService()
