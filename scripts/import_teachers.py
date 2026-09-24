"""从实验课程表导入人员到人员表（person）

用法：
    python scripts/import_teachers.py                    # 只导入授课教师
    python scripts/import_teachers.py --admins 张三,李四   # 额外把指定人员设为实验员（管理员）

规则：
- 授课教师（experiment_course.teacher）→ 角色 teacher；已存在的用户不覆盖其角色
- 实验员（--admins 指定，实验准备人员）→ 角色 admin；已存在则更新为 admin
- 新用户初始密码为空，首次登录使用默认初始密码（config.settings.DEFAULT_INITIAL_PASSWORD）
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from db.database import db
from services.base.experiment_course_service import experiment_course_service
from services.base.person_service import person_service

_ROLE_LABELS = {
    "super_admin": "超级管理员",
    "admin": "管理员（实验员）",
    "teacher": "教师",
    "user": "普通用户",
}


def collect_teachers():
    """从课程表收集去重后的授课教师姓名"""
    names = []
    for course in experiment_course_service.get_by_semester(None):
        for part in re.split(r'[、,，/\s]+', str(course.teacher or '').strip()):
            if part and part not in names:
                names.append(part)
    return names


def import_teacher(name: str):
    """授课教师：不存在才创建，已存在保持原角色（避免误降级超管）"""
    existing = person_service.get_by_name(name)
    if existing:
        return "exists", existing.role
    return ("created", "teacher") if person_service.create(
        {"name": name, "role": "teacher"}
    ) else ("failed", None)


def import_admin(name: str):
    """实验员（管理员）：创建或更新角色为 admin"""
    existing = person_service.get_by_name(name)
    if existing:
        if existing.role == "super_admin":
            return "skipped_admin", "super_admin"     # 不把超管降级
        return ("updated", "admin") if person_service.update(
            existing.id, {"role": "admin"}
        ) else ("failed", None)
    return ("created", "admin") if person_service.create(
        {"name": name, "role": "admin"}
    ) else ("failed", None)


def main():
    admins = []
    if "--admins" in sys.argv:
        index = sys.argv.index("--admins")
        if index + 1 < len(sys.argv):
            admins = [
                x.strip() for x in re.split(r'[,，\s]+', sys.argv[index + 1]) if x.strip()
            ]

    db.init_tables()

    # ---------- 授课教师 ----------
    teachers = collect_teachers()
    print(f"从课程表收集到授课教师 {len(teachers)} 人：{'、'.join(teachers)}")

    created = exists = failed = 0
    for name in teachers:
        status, role = import_teacher(name)
        if status == "created":
            created += 1
            print(f"  ➕ 教师 {name}（{_ROLE_LABELS.get(role, role)}）")
        elif status == "exists":
            exists += 1
            print(f"  ⏭ 已存在 {name}（当前角色：{_ROLE_LABELS.get(role, role)}）")
        else:
            failed += 1
            print(f"  ❌ 添加失败 {name}")

    # ---------- 实验员（管理员） ----------
    admin_created = admin_updated = 0
    if admins:
        print(f"\n实验员（管理员）名单：{'、'.join(admins)}")
        for name in admins:
            status, role = import_admin(name)
            if status == "created":
                admin_created += 1
                print(f"  ➕ 实验员 {name}（管理员）")
            elif status == "updated":
                admin_updated += 1
                print(f"  🔄 {name} 角色更新为管理员")
            elif status == "skipped_admin":
                print(f"  ⏭ {name} 是超级管理员，保持不变")
            else:
                failed += 1
                print(f"  ❌ 设置失败 {name}")
    else:
        print("\n（未指定实验员名单；如需导入请加 --admins 姓名1,姓名2）")

    print(
        f"\n✅ 完成：教师新增 {created} 人、已存在 {exists} 人"
        f"；实验员新增 {admin_created} 人、更新 {admin_updated} 人；失败 {failed} 人"
    )


if __name__ == "__main__":
    main()
