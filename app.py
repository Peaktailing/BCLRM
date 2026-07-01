"""试剂库管理系统 - 主应用入口

启动时自动重定向到欢迎页面（登录页）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st


def main():
    st.switch_page("pages/0_欢迎页面.py")


if __name__ == "__main__":
    main()