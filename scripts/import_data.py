"""从 Excel 导入数据到 SQLite 数据库

该脚本用于将 Excel 测试文件中的数据导入到 SQLite 数据库中。
"""
import pandas as pd
import os
import sys
from datetime import datetime
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.database import Database
from utils.error_handler import logger


def excel_date_to_string(excel_date):
    """将 Excel 日期数字转换为字符串格式

    Excel 使用序列号表示日期，如 45565 表示 2024-10-13
    """
    if pd.isna(excel_date):
        return None

    try:
        # 如果是数字类型，转换为日期
        if isinstance(excel_date, (int, float)):
            # Excel 日期基准：1899-12-30
            from datetime import datetime, timedelta
            base_date = datetime(1899, 12, 30)
            actual_date = base_date + timedelta(days=int(excel_date))
            return actual_date.strftime('%Y/%m/%d %H:%M')
        # 如果已经是字符串，直接返回
        return str(excel_date)
    except Exception:
        return str(excel_date)


def import_person_data(db, df):
    """导入人员信息数据"""
    print("\n正在导入人员信息表...")
    sheet_name = '人员信息表'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('姓名')):
            continue

        fields = {
            'name': str(row.get('姓名', '')),
            'gender': str(row.get('性别', '')) if not pd.isna(row.get('性别')) else None,
            'person_id': str(row.get('人员', '')) if not pd.isna(row.get('人员')) else None,
            'feishu_person': str(row.get('飞书人员', '')) if not pd.isna(row.get('飞书人员')) else None,
            'person_attribute': str(row.get('人员属性', '')) if not pd.isna(row.get('人员属性')) else None,
            'student_id_work_id': str(row.get('学号/工号', '')) if not pd.isna(row.get('学号/工号')) else None,
        }

        try:
            query = """
                INSERT OR IGNORE INTO person
                (name, gender, person_id, feishu_person, person_attribute, student_id_work_id)
                VALUES (?, ?, ?, ?, ?, ?)
            """
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入人员信息失败 [行{idx}]: {str(e)}", exception=e)

    print(f"人员信息表导入完成: {count} 条记录")


def import_storage_location(db, df):
    """导入存储位置数据"""
    print("\n正在导入存储位置表...")
    sheet_name = '存储位置'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('存储位置')):
            continue

        fields = {
            'name': str(row.get('存储位置', '')),
        }

        try:
            query = "INSERT OR IGNORE INTO storage_location (name) VALUES (?)"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入存储位置失败 [行{idx}]: {str(e)}", exception=e)

    print(f"存储位置表导入完成: {count} 条记录")


def import_storage_requirement(db, df):
    """导入存储要求数据"""
    print("\n正在导入存储要求表...")
    sheet_name = '存储要求'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('存储要求')):
            continue

        fields = {
            'name': str(row.get('存储要求', '')),
            'description': str(row.get('具体要求', '')) if not pd.isna(row.get('具体要求')) else None,
        }

        try:
            query = "INSERT OR IGNORE INTO storage_requirement (name, description) VALUES (?, ?)"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入存储要求失败 [行{idx}]: {str(e)}", exception=e)

    print(f"存储要求表导入完成: {count} 条记录")


def import_reagent_type(db, df):
    """导入试剂类型数据"""
    print("\n正在导入试剂类型表...")
    sheet_name = '试剂类型表'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('试剂类型')):
            continue

        fields = {
            'name': str(row.get('试剂类型', '')),
        }

        try:
            query = "INSERT OR IGNORE INTO reagent_type (name) VALUES (?)"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入试剂类型失败 [行{idx}]: {str(e)}", exception=e)

    print(f"试剂类型表导入完成: {count} 条记录")


def import_supplier(db, df):
    """导入供应商数据"""
    print("\n正在导入供应商表...")
    sheet_name = '试剂供应商'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('供应商名称')):
            continue

        fields = {
            'name': str(row.get('供应商名称', '')),
            'contact': str(row.get('联系人', '')) if not pd.isna(row.get('联系人')) else None,
            'phone': str(row.get('联系电话', '')) if not pd.isna(row.get('联系电话')) else None,
        }

        try:
            query = "INSERT OR IGNORE INTO supplier (name, contact, phone) VALUES (?, ?, ?)"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入供应商失败 [行{idx}]: {str(e)}", exception=e)

    print(f"供应商表导入完成: {count} 条记录")


def import_manufacturer(db, df):
    """导入生产商数据"""
    print("\n正在导入生产商表...")
    sheet_name = '试剂生产商'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('品牌名')):
            continue

        fields = {
            'brand_name': str(row.get('品牌名', '')),
            'full_name': str(row.get('企业全名', '')) if not pd.isna(row.get('企业全名')) else None,
            'website': str(row.get('官网地址', '')) if not pd.isna(row.get('官网地址')) else None,
        }

        try:
            query = "INSERT OR IGNORE INTO manufacturer (brand_name, full_name, website) VALUES (?, ?, ?)"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入生产商失败 [行{idx}]: {str(e)}", exception=e)

    print(f"生产商表导入完成: {count} 条记录")


def import_controlled_list(db, df):
    """导入管控化学品名录数据"""
    print("\n正在导入管控化学品名录...")
    sheet_name = '管控化学品名录'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('化学品名称')):
            continue

        fields = {
            'chemical_name': str(row.get('化学品名称', '')),
            'alias': str(row.get('化学品别名', '')) if not pd.isna(row.get('化学品别名')) else None,
            'cas': str(row.get('CAS', '')) if not pd.isna(row.get('CAS')) else None,
            'dangerous_type': str(row.get('危化品类型', '')) if not pd.isna(row.get('危化品类型')) else None,
        }

        try:
            query = """
                INSERT OR IGNORE INTO controlled_list
                (chemical_name, alias, cas, dangerous_type)
                VALUES (?, ?, ?, ?)
            """
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入管控化学品失败 [行{idx}]: {str(e)}", exception=e)

    print(f"管控化学品名录导入完成: {count} 条记录")


def import_reagent_bottle(db, df):
    """导入试剂瓶信息数据"""
    print("\n正在导入试剂瓶信息表...")
    sheet_name = '试剂瓶信息表'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('试剂瓶编号')):
            continue

        fields = {
            'bottle_number': int(row.get('试剂瓶编号')),
            'reagent_name': str(row.get('试剂名称', '')) if not pd.isna(row.get('试剂名称')) else None,
            'remaining_quantity': float(row.get('剩余量', 0)) if not pd.isna(row.get('剩余量')) else None,
            'purity': str(row.get('纯度', '')) if not pd.isna(row.get('纯度')) else None,
            'reagent_type': str(row.get('试剂类型', '')) if not pd.isna(row.get('试剂类型')) else None,
            'is_controlled': 1 if str(row.get('是否管控', '')) == 'true' else 0,
            'storage_requirement': str(row.get('存储要求', '')) if not pd.isna(row.get('存储要求')) else None,
            'specification': float(row.get('规格（重量）', 0)) if not pd.isna(row.get('规格（重量）')) else None,
            'cas_number': str(row.get('试剂CAS编号', '')) if not pd.isna(row.get('试剂CAS编号')) else None,
            'unit_price': float(row.get('采购单价', 0)) if not pd.isna(row.get('采购单价')) else None,
            'supplier': str(row.get('供应商', '')) if not pd.isna(row.get('供应商')) else None,
            'production_date': excel_date_to_string(row.get('生产日期')),
            'inbound_date': excel_date_to_string(row.get('入库日期')),
            'unseal_date': excel_date_to_string(row.get('启封日期')),
            'last_borrow_time': excel_date_to_string(row.get('最后借出时间')),
            'last_return_time': excel_date_to_string(row.get('最后归还时间')),
            'last_return_record_no': int(row.get('最后归还记录号', 0)) if not pd.isna(row.get('最后归还记录号')) else None,
            'storage_location': str(row.get('存储位置', '')) if not pd.isna(row.get('存储位置')) else None,
            'borrowable_flag': str(row.get('可借标记', '可借')),
            'barcode': str(row.get('条码', '')) if not pd.isna(row.get('条码')) else None,
        }

        try:
            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['?' for _ in fields])
            query = f"INSERT OR IGNORE INTO reagent_bottle ({columns}) VALUES ({placeholders})"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入试剂瓶信息失败 [行{idx}]: {str(e)}", exception=e)

    print(f"试剂瓶信息表导入完成: {count} 条记录")


def import_borrow_record(db, df):
    """导入领用记录数据"""
    print("\n正在导入领用记录表...")
    sheet_name = '领用记录表'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('记录编号')):
            continue

        fields = {
            'record_number': str(row.get('记录编号', '')),
            'bottle_number': int(row.get('试剂瓶编号', 0)) if not pd.isna(row.get('试剂瓶编号')) else None,
            'reagent_name': str(row.get('试剂名称', '')) if not pd.isna(row.get('试剂名称')) else None,
            'user': str(row.get('领用人', '')),
            'cas_number': str(row.get('试剂CAS编码', '')) if not pd.isna(row.get('试剂CAS编码')) else None,
            'production_date': excel_date_to_string(row.get('生产日期')),
            'is_controlled': 1 if str(row.get('是否管控试剂', '')) == 'true' else 0,
            'borrow_time': excel_date_to_string(row.get('领用时间')),
            'approver': str(row.get('审批人', '')) if not pd.isna(row.get('审批人')) else None,
            'approved': 1 if str(row.get('是否通过审批', '')) == 'true' else 0,
            'is_violation': 1 if str(row.get('是否违规借出管控试剂', '')) == 'true' else 0,
        }

        try:
            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['?' for _ in fields])
            query = f"INSERT OR IGNORE INTO borrow_record ({columns}) VALUES ({placeholders})"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入领用记录失败 [行{idx}]: {str(e)}", exception=e)

    print(f"领用记录表导入完成: {count} 条记录")


def import_return_record(db, df):
    """导入归还记录数据"""
    print("\n正在导入归还记录表...")
    sheet_name = '归还记录表'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('归还记录编号')):
            continue

        fields = {
            'return_number': int(row.get('归还记录编号', 0)),
            'bottle_number': int(row.get('试剂瓶编号', 0)) if not pd.isna(row.get('试剂瓶编号')) else None,
            'return_user': str(row.get('归还人', '')),
            'return_time': excel_date_to_string(row.get('归还时间')),
            'remaining_quantity': float(row.get('归还时余量', 0)) if not pd.isna(row.get('归还时余量')) else None,
            'last_update_time': excel_date_to_string(row.get('最后更新时间')),
            'modifier': str(row.get('修改人', '')) if not pd.isna(row.get('修改人')) else None,
        }

        try:
            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['?' for _ in fields])
            query = f"INSERT OR IGNORE INTO return_record ({columns}) VALUES ({placeholders})"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入归还记录失败 [行{idx}]: {str(e)}", exception=e)

    print(f"归还记录表导入完成: {count} 条记录")


def import_consumable(db, df):
    """导入耗材信息数据"""
    print("\n正在导入耗材信息表...")
    sheet_name = '耗材信息表'

    if sheet_name not in df.keys():
        print(f"警告: 未找到工作表 '{sheet_name}'")
        return

    data = df[sheet_name]
    if data.empty:
        print(f"警告: '{sheet_name}' 为空表")
        return

    count = 0
    for idx, row in data.iterrows():
        if pd.isna(row.get('耗材编号')):
            continue

        fields = {
            'consumable_number': str(row.get('耗材编号', '')),
            'consumable_name': str(row.get('耗材名称', '')),
            'stock_quantity': int(row.get('库存数量', 0)) if not pd.isna(row.get('库存数量')) else 0,
            'unit_price': float(row.get('单价', 0)) if not pd.isna(row.get('单价')) else None,
            'supplier': str(row.get('供应商', '')) if not pd.isna(row.get('供应商')) else None,
            'last_update_time': excel_date_to_string(row.get('最近更新时间')),
        }

        try:
            columns = ', '.join(fields.keys())
            placeholders = ', '.join(['?' for _ in fields])
            query = f"INSERT OR IGNORE INTO consumable ({columns}) VALUES ({placeholders})"
            db.execute_insert(query, tuple(fields.values()))
            count += 1
        except Exception as e:
            logger.error(f"导入耗材信息失败 [行{idx}]: {str(e)}", exception=e)

    print(f"耗材信息表导入完成: {count} 条记录")


def main():
    """主函数：导入所有数据"""
    print("=" * 60)
    print("Excel 数据导入工具")
    print("=" * 60)

    # Excel 文件路径
    excel_file = os.path.join(project_root, 'docs', '试剂库存管理-运行测试版V0.7.0.1-食品教研室.xlsx')

    if not os.path.exists(excel_file):
        print(f"错误: Excel 文件不存在: {excel_file}")
        return

    print(f"\nExcel 文件: {excel_file}")

    # 初始化数据库
    db = Database()
    db.init_tables()

    # 读取 Excel 文件
    print("\n正在读取 Excel 文件...")
    try:
        df = pd.read_excel(excel_file, sheet_name=None)
        print(f"成功读取 {len(df)} 个工作表")
    except Exception as e:
        print(f"错误: 无法读取 Excel 文件: {str(e)}")
        logger.error(f"读取Excel失败: {str(e)}", exception=e)
        return

    # 导入基础数据表
    import_person_data(db, df)
    import_storage_location(db, df)
    import_storage_requirement(db, df)
    import_reagent_type(db, df)
    import_supplier(db, df)
    import_manufacturer(db, df)
    import_controlled_list(db, df)

    # 导入核心业务表
    import_reagent_bottle(db, df)
    import_borrow_record(db, df)
    import_return_record(db, df)
    import_consumable(db, df)

    print("\n" + "=" * 60)
    print("数据导入完成！")
    print("=" * 60)

    # 关闭数据库连接
    db.close()


if __name__ == "__main__":
    main()