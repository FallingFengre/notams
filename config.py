import configparser
import os

# 实时查询使用 DAIP。FAA 历史查询由 /fetch_archive 单独调用。
FETCH_DINS = False
FETCH_DAIP = True
FETCH_FNS = False
FETCH_MSA = False  # 中国海事局
FETCH_MSI = False  # U.S. Maritime Administration

# 本地航警数据过期时间，单位秒
FETCH_EXPIRE_TIME = 600
MSI_FETCH_EXPIRE_TIME = 600
# MSI爬取配置
# navArea: 4=NAVAREA IV, 12=NAVAREA VII, A=HYDROLANT, P=HYDROPAC, C=HYDROARC
MSI_NAV_AREAS = ['4', '12', 'A', 'P', 'C']
# dncRegion: 201-229 对应 DNC01-DNC29
MSI_DNC_REGIONS = []

EXCLUDE_RECTS = [
    # {'lat_min': 39.303183, 'lat_max': 40.856476, 'lon_min': 101.300003, 'lon_max': 105.242712},
    {'lat_min': 36.263957, 'lat_max': 45.841384, 'lon_min': 73.570446, 'lon_max': 90.944820},
    {'lat_min': 34.90, 'lat_max': 43.76, 'lon_min': 79.93, 'lon_max': 90.70},
    {'lat_min': 40.12, 'lat_max': 42.09, 'lon_min': 89.95, 'lon_max': 96.50},
    {'lat_min': 41.81, 'lat_max': 54.43, 'lon_min': 111.16, 'lon_max': 134.76},
    {'lat_min': 39.84, 'lat_max': 40.04, 'lon_min': 119.48, 'lon_max': 119.79},
    {'lat_min': 41.33, 'lat_max': 45.44, 'lon_min': 107.65, 'lon_max': 113.50}
]

ICAO_CODES_DEFAULT = (
    "AGGG AYPM DGAC EGGX FAJO FIMM KZAK LPPO MDCS MKJK MMFO MMFR MTEG "
    "MUFH NFFF NTTT NZZC NZZO RCAA RCSP RJJJ RKRR RPHI SCIZ SCTZ SMPM "
    "SOOO TNCF TTZP VCCF VECF VHHK VOMF VVGL VVHM VVHN VVTS VYYF WAAF "
    "WIIF WMFC WSJC YBBB YMMM ZBPE ZGZU ZHWH ZJSA ZLHW ZPKM ZSHA ZWUQ "
    "ZYSH"
)


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

# Camoufox 无头浏览器会话配置（用于加载 FAA 公开查询页与请求重试）
# channel: 保留兼容字段（无头模式无需指定浏览器通道）
# window_x/window_y: 保留兼容字段（无头模式无窗口）
# page_wait_seconds: 打开页面后等待会话初始化与页面就绪的时间（秒）
# max_retries: 请求失败后的重试次数
PW_CHANNEL = config.get('PLAYWRIGHT', 'channel', fallback='auto')
PW_WINDOW_X = config.getint('PLAYWRIGHT', 'window_x', fallback=-32000)
PW_WINDOW_Y = config.getint('PLAYWRIGHT', 'window_y', fallback=-32000)
PW_PAGE_WAIT = config.getint('PLAYWRIGHT', 'page_wait_seconds', fallback=10)
PW_MAX_RETRIES = config.getint('PLAYWRIGHT', 'max_retries', fallback=3)
