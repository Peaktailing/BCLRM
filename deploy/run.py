#!/usr/bin/env python3
"""试剂库管理系统 - PyInstaller 启动入口

此脚本被 PyInstaller 打包为可执行文件。
启动时自动设置工作目录、初始化数据库并启动 Streamlit 服务。
"""
import os
import sys
import subprocess
import socket
import webbrowser
import time


def get_base_dir():
    """获取可执行文件所在目录"""
    if getattr(sys, 'frozen', False):
        # PyInstaller 打包后
        return sys._MEIPASS
    else:
        return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def find_free_port(start_port=8501, max_attempts=100):
    """查找可用端口"""
    for port in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('localhost', port))
                return port
            except OSError:
                continue
    return start_port


def main():
    base_dir = get_base_dir()
    os.chdir(base_dir)
    sys.path.insert(0, base_dir)

    # 查找可用端口
    port = find_free_port(8501)

    print("=" * 60)
    print("  试剂库管理系统 v0.88")
    print("  化学实验室试剂全生命周期管理")
    print("=" * 60)
    print(f"\n正在启动服务，请稍候...")
    print(f"服务地址: http://localhost:{port}")
    print()

    # 启动 Streamlit
    try:
        cmd = [
            sys.executable, '-m', 'streamlit', 'run', 'app.py',
            '--server.port', str(port),
            '--server.address', '0.0.0.0',
            '--server.headless', 'true',
            '--browser.serverAddress', 'localhost',
        ]

        process = subprocess.Popen(
            cmd,
            cwd=base_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        # 等待服务启动
        time.sleep(3)

        # 尝试打开浏览器
        try:
            webbrowser.open(f"http://localhost:{port}")
        except Exception:
            pass

        print(f"\n✓ 服务已启动！")
        print(f"  请在浏览器中打开: http://localhost:{port}")
        print(f"  按 Ctrl+C 停止服务\n")

        # 输出 streamlit 日志
        for line in process.stdout:
            print(line, end='')

    except KeyboardInterrupt:
        print("\n正在停止服务...")
        process.terminate()
        process.wait()
        print("服务已停止。")
    except Exception as e:
        print(f"\n启动失败: {e}")
        print("\n请确保已安装所有依赖:")
        print("  pip install -r requirements.txt")
        input("\n按 Enter 键退出...")
        sys.exit(1)


if __name__ == '__main__':
    main()