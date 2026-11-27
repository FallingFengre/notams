import socket
import sys
import threading
import time
import webbrowser

import config
from service.server import start_flask


def run_browser_mode(host, port):
    url = f"http://{host}:{port}"
    try:
        webbrowser.open(url)
        print(f"使用时请不要关闭控制台，在浏览器中访问 {url} 以开始使用")
        print("按 Ctrl-C 可退出程序")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("收到中断信号，程序退出")
    finally:
        sys.exit(0)


def wait_for_server(host, port, timeout=5):
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(0.1)
            result = sock.connect_ex((host, port))
            sock.close()
            if result == 0:
                return True
            time.sleep(0.05)
        except:
            time.sleep(0.05)
    return False


if __name__ == '__main__':
    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()

    HOST, PORT = config.HOST, config.PORT
    WEBVIEW_HOST, WEBVIEW_PORT = config.WEBVIEW_HOST, config.WEBVIEW_PORT

    print("正在启动服务器...")
    if wait_for_server(HOST, PORT):
        print(f"服务器已就绪，启动窗口...")
    else:
        print("服务器启动超时，仍然尝试打开窗口...")
        time.sleep(0.5)

    if config.BROWSER_MODE:
        run_browser_mode(WEBVIEW_HOST, WEBVIEW_PORT)
    else:
        try:
            import webview
            window = webview.create_window(
                'NOTAM落区绘制工具',
                f"http://{WEBVIEW_HOST}:{WEBVIEW_PORT}/placeholder",
                width=1400,
                height=900,
                min_size=(800, 600)
            )
            webview.start()
        except ImportError:
            print("未检测到 pywebview，自动切换为浏览器模式...")
            run_browser_mode(WEBVIEW_HOST, WEBVIEW_PORT)
        except KeyboardInterrupt:
            pass
        finally:
            print("窗口已关闭，程序退出")
            sys.exit(0)
