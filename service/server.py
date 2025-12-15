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
from service.fetch.MSA_NAV_SEARCH import MSA_NAV_SEARCH
from service.fetch.MSI_NAV_SEARCH import MSI_NAV_SEARCH


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


def coords_to_polygon(coords_str):
    """
    将坐标字符串转换为多边形点列表
    """
    pts = []
    for part in coords_str.split('-'):
        p = parse_point(part.strip())
        if p:
            pts.append(p)
    return pts


def polygon_area(poly):
    """
    计算多边形面积（使用Shoelace公式）
    """
    if len(poly) < 3:
        return 0
    n = len(poly)
    area = 0
    for i in range(n):
        j = (i + 1) % n
        area += poly[i][0] * poly[j][1]
        area -= poly[j][0] * poly[i][1]
    return abs(area) / 2


def polygons_overlap_ratio(poly1, poly2):
    """
    估算两个多边形的重叠比例
    使用采样点方法：检查一个多边形的点在另一个多边形内的比例
    返回: (poly1内点在poly2中的比例, poly2内点在poly1中的比例)
    """
    if len(poly1) < 3 or len(poly2) < 3:
        return 0, 0
    
    # 方法1: 检查顶点互相包含
    poly1_in_poly2 = sum(1 for p in poly1 if point_in_poly(p[0], p[1], poly2))
    poly2_in_poly1 = sum(1 for p in poly2 if point_in_poly(p[0], p[1], poly1))
    
    ratio1 = poly1_in_poly2 / len(poly1) if poly1 else 0
    ratio2 = poly2_in_poly1 / len(poly2) if poly2 else 0
    
    # 如果顶点没有互相包含，检查边是否相交
    if ratio1 == 0 and ratio2 == 0:
        # 检查边相交
        has_intersection = False
        for i in range(len(poly1)):
            a = poly1[i]
            b = poly1[(i + 1) % len(poly1)]
            for j in range(len(poly2)):
                c = poly2[j]
                d = poly2[(j + 1) % len(poly2)]
                if seg_intersect(a, b, c, d):
                    has_intersection = True
                    break
            if has_intersection:
                break
        
        if has_intersection:
            # 边相交，估算为部分重叠
            return 0.3, 0.3
    
    return ratio1, ratio2


def parse_time_range(t):
    """
    解析时间字符串，返回所有时间段的起止时间戳列表
    """
    try:
        time_segments = t.split(';')
        ranges = []
        
        for segment in time_segments:
            segment = segment.strip()
            if not segment:
                continue
            parts = segment.split(" UNTIL ")
            if len(parts) == 2:
                start = datetime.strptime(parts[0], "%d %b %H:%M %Y").timestamp()
                end = datetime.strptime(parts[1], "%d %b %H:%M %Y").timestamp()
                ranges.append((start, end))
        
        return ranges
    except:
        return []


def time_overlap_ratio(time1, time2):
    ranges1 = parse_time_range(time1)
    ranges2 = parse_time_range(time2)
    
    if not ranges1 or not ranges2:
        return 0, 0
    
    # 计算每个时间串的总时长
    duration1 = sum(e - s for s, e in ranges1)
    duration2 = sum(e - s for s, e in ranges2)
    
    if duration1 <= 0 or duration2 <= 0:
        return 0, 0
    
    # 计算重叠时长
    total_overlap = 0
    for s1, e1 in ranges1:
        for s2, e2 in ranges2:
            overlap = max(0, min(e1, e2) - max(s1, s2))
            total_overlap += overlap
    
    ratio1 = min(1.0, total_overlap / duration1)
    ratio2 = min(1.0, total_overlap / duration2)
    
    return ratio1, ratio2


def should_deduplicate(existing_entry, new_entry, coord_threshold=0.8, time_threshold=0.6):
    exist_coords, exist_time, exist_source, exist_code = existing_entry
    new_coords, new_time, new_source, new_code = new_entry
    
    # CODE完全相同，直接去重
    if exist_code == new_code:
        return True
    
    # 解析坐标为多边形
    poly1 = coords_to_polygon(exist_coords)
    poly2 = coords_to_polygon(new_coords)
    
    if not poly1 or not poly2:
        return False
    
    # 计算坐标重叠
    coord_ratio1, coord_ratio2 = polygons_overlap_ratio(poly1, poly2)
    
    # 如果坐标重叠不够，不去重
    if coord_ratio1 < coord_threshold and coord_ratio2 < coord_threshold:
        return False
    
    # 计算时间重叠
    time_ratio1, time_ratio2 = time_overlap_ratio(exist_time, new_time)
    
    # 如果时间重叠也达标，则去重
    if time_ratio1 >= time_threshold or time_ratio2 >= time_threshold:
        return True
    
    return False


def classify_data(data):
    codes = data.get("CODE", [])
    times = data.get("TIME", [])

    # 解析时间区间（支持多段时间窗口，用分号分隔）
    def parse_time(t):
        try:
            # 分割多段时间窗口
            time_segments = t.split(';')
            all_starts = []
            all_ends = []
            
            for segment in time_segments:
                segment = segment.strip()
                if not segment:
                    continue
                parts = segment.split(" UNTIL ")
                if len(parts) == 2:
                    start = datetime.strptime(parts[0], "%d %b %H:%M %Y").timestamp()
                    end = datetime.strptime(parts[1], "%d %b %H:%M %Y").timestamp()
                    all_starts.append(start)
                    all_ends.append(end)
            
            if all_starts and all_ends:
                # 返回整体范围的最早开始和最晚结束
                return min(all_starts), max(all_ends)
            return None, None
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
            ans.append('0')
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
        "SOURCE": [],
        "CLASSIFY": {},
        "NUM": 0,
    }
    source_num = 0
    
    # 用于去重：存储已添加的条目信息
    # 去重优先级: FNS > MSA > MSI > DINS
    # 格式: [(coords_str, time_str, source, code), ...]
    added_entries = []

    if config.FETCH_DINS:
        dins_data = dinsQueryWeb(current_icao_codes)
        if dins_data.get("CODE"):
            source_num += 1
            for i, code in enumerate(dins_data["CODE"]):
                coords = dins_data["COORDINATES"][i]
                time_str = dins_data["TIME"][i]
                source = dins_data.get("SOURCE", ["DINS"] * len(dins_data["CODE"]))[i] if "SOURCE" in dins_data else "DINS"
                new_entry = (coords, time_str, source, code)
                
                # 检查是否与已有条目重复
                is_duplicate = False
                for existing in added_entries:
                    if should_deduplicate(existing, new_entry):
                        is_duplicate = True
                        print(f"[去重] {code} 被 {existing[3]} 覆盖")
                        break
                
                if not is_duplicate:
                    dataDict["CODE"].append(code)
                    dataDict["COORDINATES"].append(coords)
                    dataDict["TIME"].append(time_str)
                    dataDict["PLATID"].append(dins_data["TRANSID"][i])
                    dataDict["RAWMESSAGE"].append(dins_data["RAWMESSAGE"][i])
                    dataDict["SOURCE"].append(source)
                    added_entries.append(new_entry)
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
            fns_source = []

            for idx, (code, coords_str, t, id, raw) in enumerate(zip(FNS_data['CODE'], FNS_data['COORDINATES'], FNS_data['TIME'],
                                                    FNS_data['TRANSID'], FNS_data['RAWMESSAGE'])):
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
                    src = FNS_data.get("SOURCE", ["FNS_NOTAM"] * len(FNS_data["CODE"]))[idx] if "SOURCE" in FNS_data else "FNS_NOTAM"
                    fns_source.append(src)

            if fns_code:
                for i, code in enumerate(fns_code):
                    coords = fns_coord[i]
                    time_str = fns_time[i]
                    source = fns_source[i]
                    new_entry = (coords, time_str, source, code)
                    
                    # 检查是否与已有条目重复
                    is_duplicate = False
                    for existing in added_entries:
                        if should_deduplicate(existing, new_entry):
                            is_duplicate = True
                            print(f"[去重] {code} 被 {existing[3]} 覆盖")
                            break
                    
                    if not is_duplicate:
                        dataDict["CODE"].append(code)
                        dataDict["COORDINATES"].append(coords)
                        dataDict["TIME"].append(time_str)
                        dataDict["PLATID"].append(fns_id[i])
                        dataDict["RAWMESSAGE"].append(fns_raw[i])
                        dataDict["SOURCE"].append(source)
                        added_entries.append(new_entry)
            print(f"爬取来源{source_num}: FNS_NOTAM_SEARCH, 获取 {len(fns_code)} 条航警")

    # 中国海事局海警
    if config.FETCH_MSA:
        try:
            msa_data = MSA_NAV_SEARCH()
            if msa_data.get("CODE"):
                source_num += 1
                for i, code in enumerate(msa_data["CODE"]):
                    coords = msa_data["COORDINATES"][i]
                    time_str = msa_data["TIME"][i]
                    source = msa_data.get("SOURCE", ["MSA_NAV"] * len(msa_data["CODE"]))[i] if "SOURCE" in msa_data else "MSA_NAV"
                    new_entry = (coords, time_str, source, code)
                    
                    # 检查是否与已有条目重复
                    is_duplicate = False
                    for existing in added_entries:
                        if should_deduplicate(existing, new_entry):
                            is_duplicate = True
                            print(f"[去重] {code} 被 {existing[3]} 覆盖")
                            break
                    
                    if not is_duplicate:
                        dataDict["CODE"].append(code)
                        dataDict["COORDINATES"].append(coords)
                        dataDict["TIME"].append(time_str)
                        dataDict["PLATID"].append(msa_data["TRANSID"][i])
                        dataDict["RAWMESSAGE"].append(msa_data["RAWMESSAGE"][i])
                        dataDict["SOURCE"].append(source)
                        added_entries.append(new_entry)
                print(f"爬取来源{source_num}: MSA_NAV_SEARCH, 获取 {len(msa_data['CODE'])} 条海警")
        except Exception as e:
            print(f"[错误] MSA海警爬取失败: {e}")
            traceback.print_exc()

    # U.S. Maritime Administration海警
    if config.FETCH_MSI:
        try:
            msi_data = MSI_NAV_SEARCH()
            if msi_data.get("CODE"):
                source_num += 1
                for i, code in enumerate(msi_data["CODE"]):
                    coords = msi_data["COORDINATES"][i]
                    time_str = msi_data["TIME"][i]
                    source = msi_data.get("SOURCE", ["MSI_NAV"] * len(msi_data["CODE"]))[i] if "SOURCE" in msi_data else "MSI_NAV"
                    new_entry = (coords, time_str, source, code)
                    
                    # 检查是否与已有条目重复
                    is_duplicate = False
                    for existing in added_entries:
                        if should_deduplicate(existing, new_entry):
                            is_duplicate = True
                            print(f"[去重] {code} 被 {existing[3]} 覆盖")
                            break
                    
                    if not is_duplicate:
                        dataDict["CODE"].append(code)
                        dataDict["COORDINATES"].append(coords)
                        dataDict["TIME"].append(time_str)
                        dataDict["PLATID"].append(msi_data["TRANSID"][i])
                        dataDict["RAWMESSAGE"].append(msi_data["RAWMESSAGE"][i])
                        dataDict["SOURCE"].append(source)
                        added_entries.append(new_entry)
                print(f"爬取来源{source_num}: MSI_NAV_SEARCH, 获取 {len(msi_data['CODE'])} 条海警")
        except Exception as e:
            print(f"[错误] MSI海警爬取失败: {e}")
            traceback.print_exc()

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
