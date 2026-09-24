"""环境自检页面

纯前端测试，用于验证 Streamlit 环境是否正常。
"""
import sys
import os

# 添加项目根目录到Python路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from components.auth import require_auth


def main():
    st.set_page_config(page_title="环境自检", layout="wide")
    st.title("测试页面")
    st.success("如果能看到这个，说明Streamlit环境完全正常！")


if __name__ == "__main__":
    main()