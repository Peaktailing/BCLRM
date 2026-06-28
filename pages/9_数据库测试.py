"""测试页面 - 数据库功能测试

该页面用于测试 SQLite 数据库的连接和基本功能。
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from datetime import datetime
from db.database import Database
from db.base_service import BaseService


def test_database_connection():
    """测试数据库连接"""
    try:
        db = Database()
        # 尝试执行一个简单查询
        result = db.execute_query("SELECT 1 as test")
        return True, "数据库连接成功", result
    except Exception as e:
        return False, f"数据库连接失败: {str(e)}", None


def test_table_exists():
    """测试表是否存在"""
    db = Database()
    tables_to_check = [
        'person', 'storage_location', 'storage_requirement',
        'reagent_type', 'supplier', 'manufacturer',
        'controlled_list', 'chemical_info', 'reagent_bottle',
        'borrow_record', 'return_record', 'consumable'
    ]

    results = {}
    for table in tables_to_check:
        exists = db.table_exists(table)
        results[table] = "✓ 存在" if exists else "✗ 不存在"

    return results


def test_crud_operations():
    """测试 CRUD 操作"""
    db = Database()
    results = {
        'create': False,
        'read': False,
        'update': False,
        'delete': False
    }

    try:
        # 测试创建
        test_data = {
            'name': f'测试人员_{datetime.now().strftime("%Y%m%d%H%M%S")}',
            'person_attribute': '测试'
        }
        record_id = db.execute_insert(
            "INSERT INTO person (name, person_attribute) VALUES (?, ?)",
            (test_data['name'], test_data['person_attribute'])
        )
        results['create'] = True
        created_id = record_id

        # 测试读取
        result = db.execute_query(
            "SELECT * FROM person WHERE id = ?",
            (created_id,)
        )
        results['read'] = len(result) > 0

        # 测试更新
        affected = db.execute_update(
            "UPDATE person SET person_attribute = ? WHERE id = ?",
            ('测试更新', created_id)
        )
        results['update'] = affected > 0

        # 测试删除
        affected = db.execute_update(
            "DELETE FROM person WHERE id = ?",
            (created_id,)
        )
        results['delete'] = affected > 0

    except Exception as e:
        return results, f"CRUD 测试出错: {str(e)}"

    return results, "CRUD 测试完成"


def test_query_operations():
    """测试查询操作"""
    db = Database()
    results = {}

    try:
        # 测试统计查询
        count_query = "SELECT COUNT(*) as count FROM person"
        result = db.execute_query(count_query)
        results['人员统计'] = result[0]['count'] if result else 0

        # 测试统计试剂瓶
        count_query = "SELECT COUNT(*) as count FROM reagent_bottle"
        result = db.execute_query(count_query)
        results['试剂瓶统计'] = result[0]['count'] if result else 0

        # 测试统计领用记录
        count_query = "SELECT COUNT(*) as count FROM borrow_record"
        result = db.execute_query(count_query)
        results['领用记录统计'] = result[0]['count'] if result else 0

        # 测试统计归还记录
        count_query = "SELECT COUNT(*) as count FROM return_record"
        result = db.execute_query(count_query)
        results['归还记录统计'] = result[0]['count'] if result else 0

        # 测试可借试剂瓶
        count_query = "SELECT COUNT(*) as count FROM reagent_bottle WHERE borrowable_flag = '可借'"
        result = db.execute_query(count_query)
        results['可借试剂瓶'] = result[0]['count'] if result else 0

        # 测试管控化学品
        count_query = "SELECT COUNT(*) as count FROM controlled_list"
        result = db.execute_query(count_query)
        results['管控化学品数量'] = result[0]['count'] if result else 0

    except Exception as e:
        return {}, f"查询测试出错: {str(e)}"

    return results, "查询测试完成"


def test_base_service():
    """测试 BaseService"""
    from services.base.person_service import PersonService

    service = PersonService()
    results = {}

    try:
        # 测试获取所有记录
        all_records = service.get_all(limit=5)
        results['获取记录'] = f"成功获取 {len(all_records)} 条记录"

        # 测试统计
        total = service.count()
        results['统计'] = f"共 {total} 条记录"

        # 测试不同值
        attributes = service.get_distinct_values('person_attribute')
        results['人员属性'] = ', '.join(attributes) if attributes else '无'

    except Exception as e:
        return {}, f"BaseService 测试出错: {str(e)}"

    return results, "BaseService 测试完成"


def main():
    """主函数"""
    st.set_page_config(
        page_title="数据库测试",
        page_icon="🧪",
        layout="wide"
    )

    st.title("🧪 数据库功能测试页面")
    st.markdown("---")

    # 数据库连接测试
    st.header("1. 数据库连接测试")
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("连接状态")
        success, message, data = test_database_connection()
        if success:
            st.success(message)
            st.json(data)
        else:
            st.error(message)

    with col2:
        st.subheader("数据库信息")
        db = Database()
        st.info(f"数据库路径: {db.db_path}")

    st.markdown("---")

    # 表结构测试
    st.header("2. 数据表结构测试")
    table_results = test_table_exists()

    cols = st.columns(3)
    for idx, (table, status) in enumerate(table_results.items()):
        with cols[idx % 3]:
            if "✓" in status:
                st.success(f"{table}: {status}")
            else:
                st.error(f"{table}: {status}")

    st.markdown("---")

    # CRUD 操作测试
    st.header("3. CRUD 操作测试")
    crud_results, crud_message = test_crud_operations()

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("创建", "✓" if crud_results.get('create') else "✗")
    with col2:
        st.metric("读取", "✓" if crud_results.get('read') else "✗")
    with col3:
        st.metric("更新", "✓" if crud_results.get('update') else "✗")
    with col4:
        st.metric("删除", "✓" if crud_results.get('delete') else "✗")

    if crud_message:
        st.info(crud_message)

    st.markdown("---")

    # 查询操作测试
    st.header("4. 查询统计测试")
    query_results, query_message = test_query_operations()

    cols = st.columns(3)
    for idx, (key, value) in enumerate(query_results.items()):
        with cols[idx % 3]:
            st.metric(key, value)

    st.markdown("---")

    # BaseService 测试
    st.header("5. BaseService 测试")
    service_results, service_message = test_base_service()

    for key, value in service_results.items():
        st.write(f"**{key}**: {value}")

    st.markdown("---")

    # 快速数据查看
    st.header("6. 快速数据查看")

    tabs = st.tabs(["试剂瓶", "领用记录", "归还记录", "管控化学品", "人员"])

    with tabs[0]:
        st.subheader("试剂瓶列表 (前10条)")
        db = Database()
        bottles = db.execute_query(
            "SELECT bottle_number, reagent_name, remaining_quantity, borrowable_flag, storage_location "
            "FROM reagent_bottle ORDER BY id DESC LIMIT 10"
        )
        if bottles:
            st.dataframe(bottles, use_container_width=True)
        else:
            st.info("暂无试剂瓶数据")

    with tabs[1]:
        st.subheader("领用记录 (前10条)")
        db = Database()
        records = db.execute_query(
            "SELECT record_number, reagent_name, user, borrow_time, approved "
            "FROM borrow_record ORDER BY id DESC LIMIT 10"
        )
        if records:
            st.dataframe(records, use_container_width=True)
        else:
            st.info("暂无领用记录")

    with tabs[2]:
        st.subheader("归还记录 (前10条)")
        db = Database()
        records = db.execute_query(
            "SELECT return_number, bottle_number, return_user, return_time, remaining_quantity "
            "FROM return_record ORDER BY id DESC LIMIT 10"
        )
        if records:
            st.dataframe(records, use_container_width=True)
        else:
            st.info("暂无归还记录")

    with tabs[3]:
        st.subheader("管控化学品 (前10条)")
        db = Database()
        chemicals = db.execute_query(
            "SELECT chemical_name, cas, dangerous_type FROM controlled_list LIMIT 10"
        )
        if chemicals:
            st.dataframe(chemicals, use_container_width=True)
        else:
            st.info("暂无管控化学品数据")

    with tabs[4]:
        st.subheader("人员列表")
        db = Database()
        persons = db.execute_query("SELECT name, person_attribute FROM person")
        if persons:
            st.dataframe(persons, use_container_width=True)
        else:
            st.info("暂无人员数据")

    st.markdown("---")
    st.success("✅ 测试完成！")


if __name__ == "__main__":
    main()
