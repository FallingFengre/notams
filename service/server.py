import base64
import logging
import os
import re
import sys
import traceback
from datetime import datetime
from io import BytesIO
from tkinter import filedialog

import win32clipboard
from PIL import Image
from flask import Flask, jsonify, render_template, send_from_directory
from flask import request

import config
from service.fetch.FNS_NOTAM_ARCHIVE_SEARCH import FNS_NOTAM_ARCHIVE_SEARCH
from service.fetch.FNS_NOTAM_SEARCH import FNS_NOTAM_SEARCH
from service.fetch.dinsQueryWeb import dinsQueryWeb


def parse_point(pt):
    m = re.match(r'([NS])(\d{4,6})([WE])(\d{5,7})', pt)
    if not m:
        return None
    ns, lat_s, ew, lon_s = m.group(1), m.group(2), m.group(3), m.group(4)
    if len(lat_s) == 6:
        deg, minute, sec = int(lat_s[:2]), int(lat_s[2:4]), int(lat_s[4:6])
    else:
        deg, minute, sec = int(lat_s[:2]), int(lat_s[2:4]), 0
    lat = deg + minute / 60.0 + sec / 3600.0
    if ns == 'S':
        lat = -lat
    if len(lon_s) == 7:
        deg, minute, sec = int(lon_s[:3]), int(lon_s[3:5]), int(lon_s[5:7])
    else:
        deg, minute, sec = int(lon_s[:3]), int(lon_s[3:5]), 0
    lon = deg + minute / 60.0 + sec / 3600.0
    if ew == 'W':
        lon = -lon
    return lat, lon


def point_in_rect(pt, rect):
    lat, lon = pt
    return rect['lat_min'] <= lat <= rect['lat_max'] and rect['lon_min'] <= lon <= rect['lon_max']


def point_in_poly(x, y, poly):
    inside = False
    n = len(poly)
    j = n - 1
    for i in range(n):
        xi, yi = poly[i][0], poly[i][1]
        xj, yj = poly[j][0], poly[j][1]
        intersect = ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-16) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


def seg_intersect(a, b, c, d):
    def orient(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])

    def on_seg(p, q, r):
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    o1, o2, o3, o4 = orient(a, b, c), orient(a, b, d), orient(c, d, a), orient(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    if o1 == 0 and on_seg(a, c, b): return True
    if o2 == 0 and on_seg(a, d, b): return True
    if o3 == 0 and on_seg(c, a, d): return True
    if o4 == 0 and on_seg(c, b, d): return True
    return False


def classify_data(data):
    codes = data.get("CODE", [])
    times = data.get("TIME", [])

    # 解析时间区间
    def parse_time(t):
        """
        例子: '25 NOV 04:01 2025 UNTIL 25 NOV 04:41 2025'
        """
        try:
            parts = t.split(" UNTIL ")
            start = datetime.strptime(parts[0], "%d %b %H:%M %Y").timestamp()
            end = datetime.strptime(parts[1], "%d %b %H:%M %Y").timestamp()
            return start, end
        except:
            return None, None

    items = []  # (idx, start_ts, end_ts)
    for i, t in enumerate(times):
        s, e = parse_time(t)
        if s and e:
            items.append((i, s, e))

    if not items:
        return {}

    # 并查集
    parent = {}

    def find(x):
        parent.setdefault(x, x)
        if parent[x] != x:
            parent[x] = find(parent[x])
        return parent[x]

    def union(a, b):
        pa, pb = find(a), find(b)
        if pa != pb:
            parent[pb] = pa

    # 判断重叠并归类
    for i in range(len(items)):
        idx1, s1, e1 = items[i]
        d1 = e1 - s1
        if d1 <= 0:
            continue

        for j in range(i + 1, len(items)):
            idx2, s2, e2 = items[j]
            d2 = e2 - s2
            if d2 <= 0:
                continue

            overlap = max(0, min(e1, e2) - max(s1, s2))
            if overlap <= 0:
                continue

            r1 = overlap / d1
            r2 = overlap / d2

            # 根据窗口长度调整阈值
            max_duration = max(d1, d2)
            if max_duration <= 10800:
                if abs(s2 - s1) > 15 * 60:
                    continue
                min_threshold = 0.4
                max_threshold = 1.6
            else:
                min_threshold = 0.8
                max_threshold = 1.2

            if min_threshold <= r1 <= max_threshold and min_threshold <= r2 <= max_threshold:
                union(idx1, idx2)

    # 输出分组
    groups = {}
    for idx, _, _ in items:
        root = find(idx)
        groups.setdefault(root, []).append(idx)

    classify = {}
    for n, (_, members) in enumerate(groups.items(), 1):
        classify[f"c{n}"] = [codes[m] for m in members]

    return classify


altitude_regex = re.compile(r'Q\) [A-Z]+?/[A-Z]+?/[IVK\s]*?/[NBOMK\s]*?/[AEWK\s]*?/(\d{3}/\d{3})/')


def extract_altitude(raw_message_lst):
    ans = []
    for message in raw_message_lst:
        match = altitude_regex.search(message)
        if match:
            altitudes = match.group(1).split('/')
            lower, upper = int(altitudes[0]), int(altitudes[1])  # 100 feet
            lower_str, upper_str = round(lower * 0.3048) * 100, round(upper * 0.3048) * 100
            if upper == 999:
                upper_str = 'INF'
            ans.append(f"{lower_str} ~ {upper_str} 米")
        else:
            ans.append('None')
    return ans


app = Flask(__name__)
web_path = os.path.normpath('../web/')
app.template_folder = os.path.join(web_path, 'templates')
app.static_folder = os.path.join(web_path, 'static')


class LogCapture:
    def __init__(self):
        self.logs = []
        self.max_logs = 1000

    def add_log(self, message, level='INFO'):
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.logs.append({
            'timestamp': timestamp,
            'level': level,
            'message': str(message)
        })
        if len(self.logs) > self.max_logs:
            self.logs.pop(0)

    def get_logs(self):
        return self.logs


log_capture = LogCapture()


class PrintCapture:
    def __init__(self, original_stdout):
        self.original_stdout = original_stdout

    def write(self, message):
        if message.strip():
            if 'GET /logs' not in message and 'POST /logs/clear' not in message:
                log_capture.add_log(message.strip())
        self.original_stdout.write(message)

    def flush(self):
        self.original_stdout.flush()


original_stdout = sys.stdout
original_stderr = sys.stderr
sys.stdout = PrintCapture(original_stdout)
sys.stderr = PrintCapture(original_stderr)

log = logging.getLogger('werkzeug')
log.setLevel(logging.INFO)


class FlaskLogHandler(logging.Handler):
    def emit(self, record):
        message = self.format(record)
        # 过滤掉/logs相关的请求日志
        if 'GET /logs' not in message and 'POST /logs/clear' not in message:
            log_capture.add_log(message)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/placeholder')
def placeholder():
    """占位页面，用于webview窗口加载"""
    return render_template('placeholder.html')


@app.route('/logs')
def get_logs():
    """获取日志的API端点"""
    return jsonify(log_capture.get_logs())


@app.route('/logs/clear', methods=['POST'])
def clear_logs():
    """清空日志的API端点"""
    log_capture.logs = []
    return jsonify({'status': 'ok'})


@app.route('/statics/<path:filename>')
def load_stat(filename):
    return send_from_directory(app.static_folder, filename)


@app.route('/scripts/<path:filename>')
def load_scripts(filename):
    return send_from_directory(os.path.join(web_path, 'scripts'), filename)


@app.route('/config')
def get_config():
    """获取当前配置信息的API端点"""
    return jsonify({
        'icao_codes': config.ICAO_CODES,
        'server': {
            'host': config.HOST,
            'port': config.PORT
        }
    })


@app.route('/fetch_archive', methods=['POST'])
def fetch_archive():
    try:
        data = request.get_json()
        date = data.get('date')
        region = data.get('region')

        if not date or not region:
            return jsonify({"error": "缺少日期或区域参数"}), 400

        if region == "internal":
            mode = 0
            icao = None
        else:
            mode = 1
            icao = region

        print(f"开始检索历史航警: 日期={date}, 区域={region}, mode={mode}")

        archive_data = FNS_NOTAM_ARCHIVE_SEARCH(icao, date, mode)
        print(archive_data)
        dataDict = {
            "CODE": archive_data.get("CODE", []),
            "COORDINATES": archive_data.get("COORDINATES", []),
            "TIME": archive_data.get("TIME", []),
            "PLATID": archive_data.get("TRANSID", []),
            "RAWMESSAGE": archive_data.get("RAWMESSAGE", []),
            "CLASSIFY": {},
            "NUM": len(archive_data.get("CODE", [])),
        }

        dataDict["CLASSIFY"] = classify_data(dataDict)
        print(dataDict)

        print(f"历史航警检索完成: 获取 {dataDict['NUM']} 条航警")
        return jsonify(dataDict)

    except Exception as e:
        print(f"历史航警检索错误: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route('/fetch')
def fetch():
    try:
        current_config = config.load_config()
        current_icao_codes = current_config.get('ICAO', 'codes', fallback=config.ICAO_CODES)
    except Exception as e:
        current_icao_codes = config.ICAO_CODES

    dataDict = {
        "CODE": [],
        "COORDINATES": [],
        "TIME": [],
        "PLATID": [],
        "ALTITUDE": [],
        "RAWMESSAGE": [],
        "CLASSIFY": {},
        "NUM": 0,
    }
    source_num = 0

    if config.FETCH_DINS:
        dins_data = dinsQueryWeb(current_icao_codes)
        if dins_data.get("CODE"):
            source_num += 1
            dataDict["CODE"].extend(dins_data["CODE"])
            dataDict["COORDINATES"].extend(dins_data["COORDINATES"])
            dataDict["TIME"].extend(dins_data["TIME"])
            dataDict["PLATID"].extend(dins_data["TRANSID"])
            dataDict["RAWMESSAGE"].extend(dins_data["RAWMESSAGE"])
            print(f"爬取来源{source_num}: dinsQueryWeb, 获取 {len(dins_data['CODE'])} 条航警")

    if config.FETCH_FNS:
        FNS_data = FNS_NOTAM_SEARCH()
        if FNS_data.get("CODE"):
            source_num += 1
            fns_code = []
            fns_coord = []
            fns_time = []
            fns_id = []
            fns_raw = []

            for code, coords_str, t, id, raw in zip(FNS_data['CODE'], FNS_data['COORDINATES'], FNS_data['TIME'],
                                                    FNS_data['TRANSID'], FNS_data['RAWMESSAGE']):
                pts = []
                for part in coords_str.split('-'):
                    p = parse_point(part.strip())
                    if p:
                        pts.append(p)
                excluded = False
                for rect in config.EXCLUDE_RECTS:
                    # 1检查落区顶点是否在矩形内
                    if any(point_in_rect(p, rect) for p in pts):
                        excluded = True  # True
                        break
                    # 2检查矩形顶点是否在落区内
                    corners = [(rect['lat_min'], rect['lon_min']), (rect['lat_min'], rect['lon_max']),
                               (rect['lat_max'], rect['lon_min']), (rect['lat_max'], rect['lon_max'])]
                    if any(point_in_poly(c[0], c[1], pts) for c in corners):
                        excluded = True  # True
                        break
                    # 3检查边是否相交
                    rect_edges = [
                        ((rect['lat_min'], rect['lon_min']), (rect['lat_min'], rect['lon_max'])),
                        ((rect['lat_min'], rect['lon_max']), (rect['lat_max'], rect['lon_max'])),
                        ((rect['lat_max'], rect['lon_max']), (rect['lat_max'], rect['lon_min'])),
                        ((rect['lat_max'], rect['lon_min']), (rect['lat_min'], rect['lon_min'])),
                    ]
                    found_intersect = False
                    for i in range(len(pts)):
                        a = pts[i]
                        b = pts[(i + 1) % len(pts)]
                        for edge in rect_edges:
                            if seg_intersect(a, b, edge[0], edge[1]):
                                excluded = False  # True
                                found_intersect = True
                                break
                        if found_intersect:
                            break
                    if excluded:
                        break

                if not excluded:
                    fns_code.append(code)
                    fns_coord.append(coords_str)
                    fns_time.append(t)
                    fns_id.append(id)
                    fns_raw.append(raw)

            if fns_code:
                dataDict["CODE"].extend(fns_code)
                dataDict["COORDINATES"].extend(fns_coord)
                dataDict["TIME"].extend(fns_time)
                dataDict["PLATID"].extend(fns_id)
                dataDict["RAWMESSAGE"].extend(fns_raw)
            print(f"爬取来源{source_num}: FNS_NOTAM_SEARCH, 获取 {len(fns_code)} 条航警")

    dataDict["NUM"] = len(dataDict["CODE"])
    dataDict["CLASSIFY"] = classify_data(dataDict)
    dataDict["ALTITUDE"] = extract_altitude(dataDict["RAWMESSAGE"])
    print(dataDict)
    print(f"使用时请不要关闭控制台，在浏览器中访问 http://{config.WEBVIEW_HOST}:{config.WEBVIEW_PORT} 以开始使用")
    return jsonify(dataDict)


@app.route('/save_image', methods=['POST'])
def save_image():
    try:
        data = request.get_json()
        default_name = data.get('default_name', 'notam_export.png')
        data_url = data.get('data_url')

        if not data_url:
            return jsonify({"error": "缺少 data_url 参数"}), 400

        print("正在保存导出的图片...")

        # 从 data URL 提取 base64 数据
        header, encoded = data_url.split(",", 1)
        data = base64.b64decode(encoded)

        # 弹出“另存为”对话框（在 webview/GUI 环境中正常工作）
        file_path = filedialog.asksaveasfilename(
            title="保存导出的图片",
            initialfile=default_name,
            defaultextension=f".{default_name.split('.')[-1]}",
            filetypes=[
                ("PNG 图片", "*.png"),
                ("JPEG 图片", "*.jpg;*.jpeg"),
                ("所有文件", "*.*")
            ]
        )
        if file_path:
            with open(file_path, 'wb') as f:
                f.write(data)
            try:

                # 从字节数据创建图片对象
                img = Image.open(BytesIO(data))

                # 转换为BMP格式用于剪贴板
                output = BytesIO()
                img.convert('RGB').save(output, 'BMP')
                bmp_data = output.getvalue()[14:]  # 去掉BMP文件头

                # 复制到剪贴板
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, bmp_data)
                win32clipboard.CloseClipboard()

                print("图片已复制到剪贴板")
            except Exception as e:
                print(f"复制到剪贴板失败: {e}")
            return jsonify({"success": True, "filePath": os.path.abspath(file_path)})

        else:
            return jsonify({"success": False, "message": "用户取消保存"})
    except Exception as e:
        print(f"保存图片错误: {e}")
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


def start_flask():
    # 添加Flask日志处理器
    flask_handler = FlaskLogHandler()
    flask_handler.setFormatter(logging.Formatter('%(message)s'))
    log.addHandler(flask_handler)

    app.run(host=config.HOST, port=config.PORT, debug=False, use_reloader=False, threaded=True)
