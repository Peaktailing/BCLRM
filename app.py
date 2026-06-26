"""试剂库管理系统 - 主应用入口

系统启动时自动重定向到欢迎页面。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st

def main():
    """主函数：系统入口，自动重定向到欢迎页面"""
    # 直接重定向到欢迎页面
    st.switch_page("pages/0_欢迎页面.py")

if __name__ == "__main__":
    main()
