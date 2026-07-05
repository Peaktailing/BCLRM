"""从docs目录导入数据

功能：
1. 从化学品信息表.csv导入到chemical_info表
2. 从管控化学品名录.xlsx导入到controlled_list表  
3. 从化学品清单.xlsx导入试剂瓶数据到reagent_bottle表
"""
import pandas as pd
import os
import sys
from datetime import datetime
from pathlib import Path

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from db.database import Database
from services.base.chemical_service import chemical_service
from services.base.controlled_list_service import controlled_list_service
from services.core.reagent_bottle_service import reagent_bottle_service
from services.base.storage_requirement_service import storage_requirement_service
from services.base.reagent_type_service import reagent_type_service
from services.base.storage_location_service import storage_location_service
from services.base.supplier_service import supplier_service
from utils.error_handler import logger


def init_base_data():
    """初始化基础数据表"""
    print("\n" + "=" * 60)
    print("正在初始化基础数据")
    print("=" * 60)
    
    storage_requirements = ['常温', '冷藏(2-8°C)', '冷冻(-20°C)', '避光', '防潮', '通风', '密封']
    for sr in storage_requirements:
        if not storage_requirement_service.get_by_name(sr):
            storage_requirement_service.create({'name': sr})
            print(f"添加存储要求: {sr}")
    
    reagent_types = ['普通固体试剂', '普通液体试剂', '胶体试剂/培养基', '标准品', '气体钢瓶', '生化试剂']
    for rt in reagent_types:
        if not reagent_type_service.get_by_name(rt):
            reagent_type_service.create({'name': rt})
            print(f"添加试剂类型: {rt}")
    
    storage_locations = ['货架A区', '货架B区', '危化品存储柜1', '危化品存储柜2', '冷藏柜', '冷冻柜']
    for sl in storage_locations:
        if not storage_location_service.get_by_name(sl):
            storage_location_service.create({'name': sl})
            print(f"添加存储位置: {sl}")
    
    suppliers = ['国药集团', '阿拉丁', '西格玛', '麦克林', '百灵威', '自制']
    for sp in suppliers:
        if not supplier_service.get_by_name(sp):
            supplier_service.create({'name': sp})
            print(f"添加供应商: {sp}")
    
    print("\n基础数据初始化完成")


def import_chemical_info_from_csv():
    """从化学品信息表.csv导入数据到chemical_info表"""
    print("\n" + "=" * 60)
    print("正在导入化学品信息表 (chemical_info)")
    print("=" * 60)
    
    csv_path = os.path.join(project_root, 'docs', '化学品信息表.csv')
    if not os.path.exists(csv_path):
        print(f"错误: 文件不存在: {csv_path}")
        return 0
    
    df = pd.read_csv(csv_path)
    print(f"读取到 {len(df)} 条记录")
    
    count = 0
    for idx, row in df.iterrows():
        try:
            name = str(row.get('化学品名称', '')).strip()
            if not name:
                continue
            
            cas_number = str(row.get('化学物质CAS编号', '')).strip()
            if cas_number == '-' or cas_number == 'nan':
                cas_number = None
            
            reagent_type_raw = str(row.get('试剂类型', '')).strip()
            if reagent_type_raw in ['固体', '液体']:
                reagent_type = '普通固体试剂' if reagent_type_raw == '固体' else '普通液体试剂'
                if not reagent_type_service.get_by_name(reagent_type):
                    reagent_type_service.create({'name': reagent_type})
            else:
                reagent_type = '普通固体试剂'
            
            storage_req_raw = str(row.get('存储要求', '')).strip()
            if storage_req_raw and storage_req_raw != 'nan':
                storage_req = storage_req_raw
                if not storage_requirement_service.get_by_name(storage_req):
                    storage_requirement_service.create({'name': storage_req})
            else:
                storage_req = '常温'
            
            chemical_data = {
                'name': name,
                'display_name': str(row.get('通用显示名称', '')).strip() or None,
                'formula': str(row.get('化学式', '')).strip() or None,
                'cas_number': cas_number,
                'msds': str(row.get('MSDS', '')).strip() or None,
                'reagent_type': reagent_type,
                'storage_requirement': storage_req,
                'controlled_type': str(row.get('管控试剂类型', '')).strip() or None,
            }
            
            existing = chemical_service.get_by_name(name)
            if existing:
                print(f"跳过已存在: {name}")
                continue
            
            result = chemical_service.create(chemical_data)
            if result:
                count += 1
                if count % 50 == 0:
                    print(f"已导入 {count} 条...")
            else:
                print(f"导入失败: {name}")
                
        except Exception as e:
            logger.error(f"导入化学品信息失败 [行{idx}]: {str(e)}", exception=e)
    
    print(f"\n化学品信息表导入完成: {count} 条记录")
    return count


def import_controlled_list_from_xlsx():
    """从管控化学品名录.xlsx导入数据到controlled_list表"""
    print("\n" + "=" * 60)
    print("正在导入管控化学品名录 (controlled_list)")
    print("=" * 60)
    
    xlsx_path = os.path.join(project_root, 'docs', '管控化学品名录.xlsx')
    if not os.path.exists(xlsx_path):
        print(f"错误: 文件不存在: {xlsx_path}")
        return 0
    
    df = pd.read_excel(xlsx_path)
    print(f"读取到 {len(df)} 条记录")
    
    count = 0
    for idx, row in df.iterrows():
        try:
            chemical_name = str(row.get('化学品名称', '')).strip()
            if not chemical_name:
                continue
            
            cas_number = str(row.get('CAS', '')).strip()
            if cas_number == '-' or cas_number == 'nan':
                cas_number = None
            
            controlled_data = {
                'chemical_name': chemical_name,
                'alias': str(row.get('化学品别名', '')).strip() or None,
                'cas_number': cas_number,
                'dangerous_type': str(row.get('危化品类型', '')).strip() or None,
            }
            
            existing = controlled_list_service.get_by_name(chemical_name)
            if existing:
                print(f"跳过已存在: {chemical_name}")
                continue
            
            result = controlled_list_service.create(controlled_data)
            if result:
                count += 1
                if count % 50 == 0:
                    print(f"已导入 {count} 条...")
            else:
                print(f"导入失败: {chemical_name}")
                
        except Exception as e:
            logger.error(f"导入管控化学品失败 [行{idx}]: {str(e)}", exception=e)
    
    print(f"\n管控化学品名录导入完成: {count} 条记录")
    return count


def parse_specification(spec_str):
    """解析规格字符串，提取数值和单位"""
    spec_str = str(spec_str).strip()
    if not spec_str or spec_str in ['nan', '-']:
        return 500.0, 'g'
    
    import re
    match = re.match(r'^(\d+(?:\.\d+)?)\s*([a-zA-Z]+)$', spec_str)
    if match:
        return float(match.group(1)), match.group(2)
    
    match = re.match(r'^(\d+(?:\.\d+)?)$', spec_str)
    if match:
        return float(match.group(1)), 'g'
    
    return 500.0, 'g'


def import_reagent_bottles_from_xlsx():
    """从化学品清单.xlsx导入试剂瓶数据到reagent_bottle表"""
    print("\n" + "=" * 60)
    print("正在导入试剂瓶信息表 (reagent_bottle)")
    print("=" * 60)
    
    xlsx_path = os.path.join(project_root, 'docs', '化学品清单.xlsx')
    if not os.path.exists(xlsx_path):
        print(f"错误: 文件不存在: {xlsx_path}")
        return 0
    
    df = pd.read_excel(xlsx_path)
    print(f"读取到 {len(df)} 条记录")
    
    count = 0
    bottle_number = 10000
    
    for idx, row in df.iterrows():
        try:
            name = str(row.get('名称', '')).strip()
            if not name:
                continue
            
            spec_str = row.get('规格', '')
            specification, unit = parse_specification(spec_str)
            
            quantity = row.get('数量', 1)
            if pd.isna(quantity) or str(quantity) in ['nan', '-']:
                quantity = 1
            else:
                quantity = int(quantity)
            
            chemical = chemical_service.get_by_name(name)
            if not chemical:
                print(f"警告: 未找到化学品信息: {name}")
                cas_number = None
                reagent_type = None
                storage_req = None
                controlled_type = None
            else:
                cas_number = chemical.cas_number
                reagent_type = chemical.reagent_type
                storage_req = chemical.storage_requirement
                controlled_type = chemical.controlled_type
            
            for i in range(quantity):
                bottle_number += 1
                
                existing = reagent_bottle_service.get_by_bottle_number(bottle_number)
                if existing:
                    print(f"跳过已存在编号: {bottle_number}")
                    bottle_number += 1
                    continue
                
                bottle_data = {
                    'bottle_number': bottle_number,
                    'reagent_name': name,
                    'cas_number': cas_number,
                    'remaining_quantity': specification,
                    'specification': specification,
                    'purity': '分析纯',
                    'reagent_type': reagent_type or ('普通液体试剂' if unit.lower() in ['ml', 'l'] else '普通固体试剂'),
                    'storage_requirement': storage_req or '常温',
                    'is_controlled': 1 if controlled_type else 0,
                    'borrowable_flag': '可借',
                    'borrowable_check': True,
                    'inbound_date': datetime.now().strftime('%Y/%m/%d %H:%M'),
                }
                
                result = reagent_bottle_service.create(bottle_data)
                if result:
                    count += 1
                    if count % 50 == 0:
                        print(f"已导入 {count} 条...")
                else:
                    print(f"导入失败: {name} (编号: {bottle_number})")
                
        except Exception as e:
            logger.error(f"导入试剂瓶信息失败 [行{idx}]: {str(e)}", exception=e)
    
    print(f"\n试剂瓶信息表导入完成: {count} 条记录")
    return count


def update_chemical_controlled_type():
    """根据管控化学品名录更新chemical_info表的controlled_type字段"""
    print("\n" + "=" * 60)
    print("正在更新化学品信息表的管控类型")
    print("=" * 60)
    
    chemicals = chemical_service.get_all_parsed()
    controlled_list = controlled_list_service.get_all_controlled()
    
    controlled_cas_set = set()
    controlled_name_set = set()
    
    for ctrl in controlled_list:
        if ctrl.cas_number:
            controlled_cas_set.add(ctrl.cas_number)
        if ctrl.chemical_name:
            controlled_name_set.add(ctrl.chemical_name)
    
    count = 0
    for chem in chemicals:
        try:
            new_controlled_type = None
            
            if chem.cas_number and chem.cas_number in controlled_cas_set:
                ctrl = controlled_list_service.get_by_cas_number(chem.cas_number)
                if ctrl:
                    new_controlled_type = ctrl.dangerous_type
            
            if not new_controlled_type and chem.name and chem.name in controlled_name_set:
                ctrl = controlled_list_service.get_by_name(chem.name)
                if ctrl:
                    new_controlled_type = ctrl.dangerous_type
            
            if new_controlled_type and new_controlled_type != chem.controlled_type:
                chemical_service.update(chem.id, {'controlled_type': new_controlled_type})
                count += 1
                print(f"更新: {chem.name} -> {new_controlled_type}")
                
        except Exception as e:
            logger.error(f"更新化学品管控类型失败 [{chem.name}]: {str(e)}", exception=e)
    
    print(f"\n更新完成: {count} 条记录")
    return count


def main():
    """主函数：执行所有导入"""
    print("=" * 60)
    print("docs目录数据导入工具")
    print("=" * 60)
    
    db = Database()
    db.init_tables()
    
    init_base_data()
    
    total_imported = 0
    
    total_imported += import_chemical_info_from_csv()
    
    total_imported += import_controlled_list_from_xlsx()
    
    update_chemical_controlled_type()
    
    total_imported += import_reagent_bottles_from_xlsx()
    
    print("\n" + "=" * 60)
    print(f"数据导入完成！共导入 {total_imported} 条记录")
    print("=" * 60)
    
    db.close()


if __name__ == "__main__":
    main()
