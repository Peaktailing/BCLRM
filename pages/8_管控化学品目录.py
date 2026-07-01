"""管控化学品目录查看页面

专门用于查看管控化学品名录的页面，显示所有管控化学品数据。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from business.query_service import query_service
from components.auth import init_auth, require_login, render_auth_sidebar

def main():
    """主函数：管控化学品目录查看页面"""
    st.set_page_config(page_title="管控化学品目录", layout="wide")
    st.title("📋 管控化学品目录")

    init_auth()
    if not require_login():
        st.stop()
    render_auth_sidebar()

    # 页面说明
    st.info("📋 本页面用于查看管控化学品名录，数据为只读。")

    # 获取所有管控化学品（从业务层获取）
    _result = query_service.get_all_controlled_chemicals()
    all_controlled = _result.data if _result.is_success() else []

    if all_controlled:
        # 显示统计
        st.markdown(f"**共 {len(all_controlled)} 条记录**")

        # 表格数据
        table_data = []
        for item in all_controlled:
            table_data.append({
                "化学品名称": item.chemical_name or "-",
                "别名": item.alias or "-",
                "CAS号": item.cas_number or "-",
                "危化品类型": item.dangerous_type or "-"
            })

        st.dataframe(table_data, use_container_width=True, hide_index=True, height=600)
    else:
        st.info("暂无管控化学品数据")

if __name__ == "__main__":
    main()
