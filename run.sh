#!/bin/bash
# =============================================
#  NOTAM 落区绘制工具 - 功能选择脚本
#  选择功能后输出需要运行的命令，不直接执行
# =============================================

print_menu() {
    echo ""
    echo "=============================================="
    echo "  NOTAM 落区绘制工具 - 请选择功能"
    echo "=============================================="
    echo "  1) 安装依赖"
    echo "  2) 测试 FAA 连通性"
    echo "  3) 直接运行应用"
    echo "  4) 打包为 exe (Windows)"
    echo "  0) 退出"
    echo "=============================================="
}

while true; do
    print_menu
    read -r -p "请输入功能序号: " choice
    case "$choice" in
        1)
            echo ""
            echo ">>> 安装 Python 依赖:"
            echo "    pip install -r requirements.txt"
            echo ""
            echo ">>> 说明: 本项目使用系统 Chrome/Edge 作为浏览器会话，"
            echo "    无需执行 playwright install；"
            echo "    若目标机器没有 Chrome/Edge，请先执行:"
            echo "    playwright install chromium"
            ;;
        2)
            echo ""
            echo ">>> 测试 FAA 连通性:"
            echo "    python3 service/fetch/self_test.py"
            echo ""
            echo ">>> 说明: 会启动一个移出屏幕的 Chrome 窗口完成 Akamai 验证，"
            echo "    需在图形界面环境中运行。"
            ;;
        3)
            echo ""
            echo ">>> 直接运行应用:"
            echo "    python3 main.py"
            echo ""
            echo ">>> 说明: 需保持控制台开启。浏览器模式访问"
            echo "    http://127.0.0.1:5000 ；配置 browser_mode=false 时使用桌面窗口模式。"
            ;;
        4)
            echo ""
            echo ">>> 打包为 Windows exe (在 Windows 上执行):"
            echo "    pip install pyinstaller"
            echo "    pyinstaller --onefile --windowed --icon=icon.ico --name=notamChecker main.py"
            echo ""
            echo ">>> 说明: 打包后的 exe 依赖目标机器装有 Chrome 或 Edge"
            echo "    (channel=msedge 时使用 Windows 自带 Edge，无需额外安装)。"
            ;;
        0)
            echo "退出。"
            exit 0
            ;;
        *)
            echo "无效输入，请重新选择。"
            ;;
    esac
    echo ""
    read -r -p "按回车键继续..."
done
