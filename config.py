import configparser
import os

# 是否使用 dins/fns 数据源
FETCH_DINS = False
FETCH_FNS = True
# 本地航警数据过期时间，单位秒
FETCH_EXPIRE_TIME = 600

EXCLUDE_RECTS = [
    # {'lat_min': 39.303183, 'lat_max': 40.856476, 'lon_min': 101.300003, 'lon_max': 105.242712},
    {'lat_min': 36.263957, 'lat_max': 45.841384, 'lon_min': 73.570446, 'lon_max': 90.944820},
    {'lat_min': 34.90, 'lat_max': 43.76, 'lon_min': 79.93, 'lon_max': 90.70},
    {'lat_min': 40.12, 'lat_max': 42.09, 'lon_min': 89.95, 'lon_max': 96.50},
]

ICAO_CODES_DEFAULT = " ".join([
    "ZBPE", "ZGZU", "ZHWH", "ZJSA", "ZLHW", "ZPKM", "ZSHA", "ZWUQ", "ZYSH", "VVTS", "WSJC", "WIIF", "YMMM", "WMFC",
    "RPHI", "AYPM", "AGGG", "ANAU", "NFFF", "KZAK", "VYYF", "VCCF", "VOMF", "WAAF", "RJJJ", "RCAA", "YBBB", "VVGL",
    "VVHN", "VVHM", "RCSP", "VVHM", "WIIF"
])


def load_config():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config_file = os.path.join(current_dir, 'config.ini')
    config = configparser.ConfigParser()
    if not os.path.exists(config_file):
        config['ICAO'] = {
            'codes': ICAO_CODES_DEFAULT
        }
        config['SERVER'] = {
            'host': '127.0.0.1',
            'port': '5000',
            'browser_mode': 'false'
        }
        config['WEBVIEW'] = {
            'host': '127.0.0.1',
            'port': '5000'
        }
        with open(config_file, 'w', encoding='utf-8') as f:
            f.write('# FIR/ICAO配置，填写你需要获取的航警所在的飞行情报区（FIR）代码或机场ICAO代码\n')
            config.write(f)
    config.read(config_file, encoding='utf-8')
    return config


config = load_config()
ICAO_CODES = config.get('ICAO', 'codes', fallback=ICAO_CODES_DEFAULT)

# Flask 服务器绑定配置
HOST = config.get('SERVER', 'host', fallback='127.0.0.1')
PORT = config.getint('SERVER', 'port', fallback=5000)

# 是否使用浏览器模式（默认webview模式）
BROWSER_MODE = config.getboolean('SERVER', 'browser_mode', fallback=False)

# pywebview 窗口连接配置（可以与服务器绑定地址不同）
WEBVIEW_HOST = config.get('WEBVIEW', 'host', fallback=HOST)
WEBVIEW_PORT = config.getint('WEBVIEW', 'port', fallback=PORT)
