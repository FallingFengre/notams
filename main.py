import socket
import sys
import threading
import time
import webbrowser

import config
from service.server import start_flask


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
    display_host = HOST
    if HOST in ('0.0.0.0', '::'):
        display_host = '127.0.0.1'
    base_url = f"http://{display_host}:{PORT}"

    print("正在启动服务器...")
    if wait_for_server(HOST, PORT):
        print(f"服务器已就绪，在浏览器中打开 {base_url} ...")
    else:
        print("服务器启动超时，仍然尝试打开网页...")
        time.sleep(0.5)

    try:
        opened = webbrowser.open(base_url)
        if not opened:
            print(f"无法自动打开浏览器，请手动访问 {base_url}")
        else:
            print(f"已自动在浏览器中打开 {base_url}")
        print("按 Ctrl-C 可退出程序")
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("收到中断信号，程序退出")
    finally:
        sys.exit(0)
