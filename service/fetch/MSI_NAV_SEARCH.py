"""
从U.S. Maritime Administration (NGA MSI)爬取海警
https://msi.nga.mil/
"""
import re
import json
import os
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

import config

# 调试模式：True时不过滤过期航警
DEBUG = False

MONTHS = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
          'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
MONTHS_REV = {v:k for k,v in MONTHS.items()}

# 黑名单落区坐标（需要屏蔽的落区）
BLACKLIST_AREAS = [
    # HYDROLANT 1997/25(57,61,71) - 印度洋大范围落区
    ['S085300E0922800', 'S074600E0892700', 'S301200E0610900', 
     'S404500W0022100', 'S425600W0022400', 'S321600E0631000']
]


def make_headers():
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }


def preprocess_text(text):
    """预处理文本，去除多余空格、换行等"""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_coordinates_msi(text):
    """
    解析MSI海警的坐标
    格式：38-18.00N 074-57.00W 或 02-16.03S 044-12.87W
    转换为：N381800W0745700 格式
    """
    coords = []
    
    # 匹配 DD-MM.mmN/S DDD-MM.mmE/W 格式
    pattern = r'(\d{1,2})-(\d{2})\.(\d{2})([NS])\s+(\d{2,3})-(\d{2})\.(\d{2})([EW])'
    matches = re.findall(pattern, text)
    
    for match in matches:
        lat_deg, lat_min, lat_dec, lat_dir, lon_deg, lon_min, lon_dec, lon_dir = match
        
        # 转换小数分钟为秒
        lat_sec = round(int(lat_dec) * 60 / 100)
        lon_sec = round(int(lon_dec) * 60 / 100)
        
        # 格式化
        formatted_lat = f"{lat_dir}{int(lat_deg):02d}{int(lat_min):02d}{lat_sec:02d}"
        formatted_lon = f"{lon_dir}{int(lon_deg):03d}{int(lon_min):02d}{lon_sec:02d}"
        
        coords.append(formatted_lat + formatted_lon)
    
    return coords


def parse_cancel_time(msg_text, created_on):
    """
    解析取消时间
    格式：CANCEL THIS MSG 231000Z DEC 25
    返回datetime对象，如果没有则返回None
    """
    pattern = r'CANCEL\s+THIS\s+MSG\s+(\d{2})(\d{4})Z\s+([A-Z]+)\s+(\d{2})'
    match = re.search(pattern, msg_text, re.IGNORECASE)
    
    if not match:
        return None
    
    day, time, month_str, year_short = match.groups()
    hour = int(time[:2])
    minute = int(time[2:])
    
    month = MONTHS.get(month_str.upper(), 1)
    
    # 两位年份转换
    year = 2000 + int(year_short)
    
    try:
        return datetime(year, month, int(day), hour, minute)
    except:
        return None


def parse_msg_code(msg_text, msg_type):
    """
    解析航警编号
    格式：NAVAREA IV 1376/25(GEN) 或 HYDROLANT 2117/25(57)
    """
    escaped_type = re.escape(msg_type)
    pattern = rf'({escaped_type}\s+\d+/\d+(?:\([A-Z0-9]+\))?)'
    match = re.search(pattern, msg_text, re.IGNORECASE)
    
    if match:
        return match.group(1).strip()
    
    pattern2 = r'([A-Z]+\s+[IVX]*\s*\d+/\d+(?:\([A-Z0-9]+\))?)'
    match2 = re.search(pattern2, msg_text)
    if match2:
        return match2.group(1).strip()
    
    return msg_type


def format_window(start_dt, end_dt):
    """格式化时间窗口"""
    start_str = f"{start_dt.day:02d} {MONTHS_REV[start_dt.month]} {start_dt.hour:02d}:{start_dt.minute:02d} {start_dt.year}"
    end_str = f"{end_dt.day:02d} {MONTHS_REV[end_dt.month]} {end_dt.hour:02d}:{end_dt.minute:02d} {end_dt.year}"
    return f"{start_str} UNTIL {end_str}"


def get_base_year(created_on):
    """从createdOn获取基准年份"""
    base_year = 2025
    if created_on:
        year_match = re.search(r'(\d{4})$', created_on)
        if year_match:
            base_year = int(year_match.group(1))
    return base_year


def parse_time_segment(time_text, base_year):
    """
    解析单个时间段文本
    返回时间窗口列表
    
    支持的格式：
    1. 180500Z TO 180900Z DEC - 简单单日
    2. 180500Z TO 180900Z DEC, ALTERNATE 0500Z TO 0900Z DAILY 19 THRU 23 DEC - 主窗口+每日重复备用
    3. 150243Z TO 150726Z DEC, ALTERNATE 160217Z TO 160700Z, 170151Z TO 170634Z... DEC - 主窗口+逐个备用
    4. 2002Z TO 2132Z DAILY 04 NOV THRU 30 NOV - 每日重复
    5. 0451Z TO 0612Z DAILY 17 DEC THRU 16 JAN 26 - 跨月跨年每日重复
    6. HHMMZ TO HHMMZ DAILY DD THRU DD MON - 每日重复格式（月份在后）
    7. DAILY DD MON THRU DD MON (YY): HHMMZ TO HHMMZ - 前置DAILY格式
    """
    time_text = preprocess_text(time_text)
    time_windows = []
    
    # 模式7: DAILY DD MON THRU DD MON (YY): (跟随HHMMZ TO HHMMZ) - 前置DAILY格式
    pattern_daily_prefix = r'DAILY\s+(\d{1,2})\s+([A-Z]{3})\s+THRU\s+(\d{1,2})\s+([A-Z]{3})(?:\s+(\d{2}))?:?\s*(\d{4})Z\s+TO\s+(\d{4})Z'
    daily_prefix_match = re.search(pattern_daily_prefix, time_text, re.IGNORECASE)
    if daily_prefix_match:
        start_day, start_mon, end_day, end_mon, year_short, start_time, end_time = daily_prefix_match.groups()
        
        start_hour, start_min = int(start_time[:2]), int(start_time[2:])
        end_hour, end_min = int(end_time[:2]), int(end_time[2:])
        start_month = MONTHS.get(start_mon.upper(), 1)
        end_month = MONTHS.get(end_mon.upper(), start_month)
        
        start_year = base_year
        end_year = base_year
        if year_short:
            end_year = 2000 + int(year_short)
            if end_month < start_month:
                start_year = end_year - 1
            else:
                start_year = end_year
        else:
            if end_month < start_month:
                end_year = base_year + 1
        
        try:
            current_date = datetime(start_year, start_month, int(start_day))
            end_date = datetime(end_year, end_month, int(end_day))
            
            while current_date <= end_date:
                start_dt = current_date.replace(hour=start_hour, minute=start_min)
                end_dt = current_date.replace(hour=end_hour, minute=end_min)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                time_windows.append(format_window(start_dt, end_dt))
                current_date += timedelta(days=1)
        except Exception as e:
            print(f"[警告] DAILY前置格式解析异常: {e}")
        
        if time_windows:
            return time_windows
    
    # 模式6: HHMMZ TO HHMMZ DAILY DD THRU DD MON - 月份在后的每日重复格式
    pattern_daily_reversed = r'(\d{4})Z\s+TO\s+(\d{4})Z\s+DAILY\s+(\d{1,2})\s+THRU\s+(\d{1,2})\s+([A-Z]{3})(?:\s+(\d{2}))?'
    daily_reversed_match = re.search(pattern_daily_reversed, time_text, re.IGNORECASE)
    if daily_reversed_match:
        start_time, end_time, start_day, end_day, month_str, year_short = daily_reversed_match.groups()
        
        start_hour, start_min = int(start_time[:2]), int(start_time[2:])
        end_hour, end_min = int(end_time[:2]), int(end_time[2:])
        month = MONTHS.get(month_str.upper(), 12)
        year = base_year
        if year_short:
            year = 2000 + int(year_short)
        
        try:
            for day in range(int(start_day), int(end_day) + 1):
                start_dt = datetime(year, month, day, start_hour, start_min)
                end_dt = datetime(year, month, day, end_hour, end_min)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                time_windows.append(format_window(start_dt, end_dt))
        except Exception as e:
            print(f"[警告] DAILY反转格式解析异常: {e}")
        
        if time_windows:
            return time_windows
    
    # 模式5: HHMMZ TO HHMMZ DAILY DD MON THRU DD MON (YY) - 每日重复格式
    pattern_daily_full = r'(\d{4})Z\s+TO\s+(\d{4})Z\s+DAILY\s+(\d{1,2})\s+([A-Z]{3})\s+THRU\s+(\d{1,2})\s+([A-Z]{3})(?:\s+(\d{2}))?'
    daily_match = re.search(pattern_daily_full, time_text, re.IGNORECASE)
    if daily_match:
        start_time, end_time, start_day, start_mon, end_day, end_mon, year_short = daily_match.groups()
        
        start_hour, start_min = int(start_time[:2]), int(start_time[2:])
        end_hour, end_min = int(end_time[:2]), int(end_time[2:])
        start_month = MONTHS.get(start_mon.upper(), 1)
        end_month = MONTHS.get(end_mon.upper(), start_month)
        
        start_year = base_year
        end_year = base_year
        if year_short:
            end_year = 2000 + int(year_short)
            if end_month < start_month:
                start_year = end_year - 1
            else:
                start_year = end_year
        else:
            if end_month < start_month:
                end_year = base_year + 1
        
        try:
            current_date = datetime(start_year, start_month, int(start_day))
            end_date = datetime(end_year, end_month, int(end_day))
            
            while current_date <= end_date:
                start_dt = current_date.replace(hour=start_hour, minute=start_min)
                end_dt = current_date.replace(hour=end_hour, minute=end_min)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)
                time_windows.append(format_window(start_dt, end_dt))
                current_date += timedelta(days=1)
        except Exception as e:
            print(f"[警告] DAILY解析异常: {e}")
        
        if time_windows:
            return time_windows
    
    # 查找主窗口 DDHHMMZ TO DDHHMMZ MON
    main_pattern = r'(\d{6})Z\s+TO\s+(\d{6})Z\s+([A-Z]{3})(?:\s+(\d{2}))?'
    main_match = re.search(main_pattern, time_text, re.IGNORECASE)
    
    current_month = None
    current_year = base_year
    
    if main_match:
        start_code, end_code, month_str, year_short = main_match.groups()
        start_day = int(start_code[:2])
        start_hour = int(start_code[2:4])
        start_min = int(start_code[4:6])
        end_day = int(end_code[:2])
        end_hour = int(end_code[2:4])
        end_min = int(end_code[4:6])
        current_month = MONTHS.get(month_str.upper(), 12)
        
        if year_short:
            current_year = 2000 + int(year_short)
        
        try:
            start_dt = datetime(current_year, current_month, start_day, start_hour, start_min)
            end_dt = datetime(current_year, current_month, end_day, end_hour, end_min)
            if end_dt <= start_dt:
                if end_day < start_day:
                    next_month = current_month + 1 if current_month < 12 else 1
                    next_year = current_year + 1 if current_month == 12 else current_year
                    end_dt = datetime(next_year, next_month, end_day, end_hour, end_min)
                else:
                    end_dt += timedelta(days=1)
            time_windows.append(format_window(start_dt, end_dt))
        except Exception as e:
            print(f"[警告] 主窗口解析异常: {e}")
    
    # 查找ALTERNATE部分
    alternate_match = re.search(r'ALTERNATE\s+(.+?)(?:\d+\.\s|CANCEL|$)', time_text, re.IGNORECASE | re.DOTALL)
    if alternate_match:
        alt_text = alternate_match.group(1)
        
        # 检查是否是 DAILY X THRU Y 格式
        daily_alt_pattern = r'(\d{4})Z\s+TO\s+(\d{4})Z\s+DAILY\s+(\d{1,2})\s+THRU\s+(\d{1,2})\s+([A-Z]{3})(?:\s+(\d{2}))?'
        daily_alt_match = re.search(daily_alt_pattern, alt_text, re.IGNORECASE)
        
        if daily_alt_match:
            start_time, end_time, start_day, end_day, month_str, year_short = daily_alt_match.groups()
            start_hour, start_min = int(start_time[:2]), int(start_time[2:])
            end_hour, end_min = int(end_time[:2]), int(end_time[2:])
            month = MONTHS.get(month_str.upper(), current_month or 12)
            year = current_year
            if year_short:
                year = 2000 + int(year_short)
            
            try:
                for day in range(int(start_day), int(end_day) + 1):
                    start_dt = datetime(year, month, day, start_hour, start_min)
                    end_dt = datetime(year, month, day, end_hour, end_min)
                    if end_dt <= start_dt:
                        end_dt += timedelta(days=1)
                    time_windows.append(format_window(start_dt, end_dt))
            except Exception as e:
                print(f"[警告] DAILY备用窗口解析异常: {e}")
        else:
            # 逐个列出的备用窗口
            time_pairs_with_month = re.findall(
                r'(\d{6})Z\s+TO\s+(\d{6})Z(?:[,\s]+(?:AND\s+)?)?([A-Z]{3})?(?:\s+(\d{2}))?',
                alt_text, re.IGNORECASE
            )
            
            last_month = current_month or 12
            last_year = current_year
            
            month_info = {}
            for i, (sc, ec, mon, yr) in enumerate(time_pairs_with_month):
                if mon:
                    month_info[i] = (MONTHS.get(mon.upper(), last_month), 2000 + int(yr) if yr else current_year)
            
            for i in range(len(time_pairs_with_month) - 1, -1, -1):
                if i in month_info:
                    last_month, last_year = month_info[i]
                else:
                    month_info[i] = (last_month, last_year)
            
            for i, (start_code, end_code, _, _) in enumerate(time_pairs_with_month):
                month, year = month_info.get(i, (current_month or 12, current_year))
                
                start_day = int(start_code[:2])
                start_hour = int(start_code[2:4])
                start_min = int(start_code[4:6])
                end_day = int(end_code[:2])
                end_hour = int(end_code[2:4])
                end_min = int(end_code[4:6])
                
                try:
                    start_dt = datetime(year, month, start_day, start_hour, start_min)
                    end_dt = datetime(year, month, end_day, end_hour, end_min)
                    if end_dt <= start_dt:
                        if end_day < start_day:
                            next_month = month + 1 if month < 12 else 1
                            next_year = year + 1 if month == 12 else year
                            end_dt = datetime(next_year, next_month, end_day, end_hour, end_min)
                        else:
                            end_dt += timedelta(days=1)
                    time_windows.append(format_window(start_dt, end_dt))
                except Exception as e:
                    print(f"[警告] 备用窗口解析异常: {e}")
    
    return time_windows


def check_against_blacklist(coords):
    """
    检查坐标是否与黑名单落区重叠
    返回True表示需要屏蔽
    """
    if not coords or len(coords) < 3:
        return False
    
    for blacklist_coords in BLACKLIST_AREAS:
        if len(blacklist_coords) < 3:
            continue
        
        # 简单检查：如果有超过50%的点相同，则认为重叠
        match_count = sum(1 for c in coords if c in blacklist_coords)
        overlap_ratio = match_count / len(coords)
        
        if overlap_ratio > 0.5:
            return True
    
    return False


def extract_areas_with_time(msg_text, base_year):
    """
    提取多个区域及其各自的时间
    返回: [(area_number, coords_list, time_str), ...]
    区域编号从1开始，按解析顺序递增
    """
    areas = []
    area_counter = 1
    
    # 检查是否有前置DAILY格式（在所有区域之前）
    prefix_daily_pattern = r'(DAILY\s+\d{1,2}\s+[A-Z]{3}\s+THRU\s+\d{1,2}\s+[A-Z]{3}(?:\s+\d{2})?):'
    prefix_match = re.search(prefix_daily_pattern, msg_text, re.IGNORECASE)
    prefix_daily_text = prefix_match.group(1) if prefix_match else None
    
    # 尝试匹配带独立时间的多区域格式（时间在区域描述中）
    area_with_time_pattern = r'[A-Z]\.\s+(\d{4}Z\s+TO\s+\d{4}Z)\s+IN\s+AREAS?\s+BOUND\s+BY\s+((?:\d{1,2}-\d{2}\.\d{2}[NS]\s+\d{2,3}-\d{2}\.\d{2}[EW][,.\s]*)+)'
    area_time_matches = re.findall(area_with_time_pattern, msg_text, re.IGNORECASE | re.DOTALL)
    
    if area_time_matches:
        for time_section, coord_text in area_time_matches:
            coords = parse_coordinates_msi(coord_text)
            if len(coords) >= 3:
                # 检查黑名单
                if check_against_blacklist(coords):
                    print(f"[过滤] 匹配黑名单落区，已屏蔽")
                    continue
                
                # 组合前置DAILY和具体时间窗口
                full_time_text = f"{prefix_daily_text}: {time_section}" if prefix_daily_text else time_section
                time_windows = parse_time_segment(full_time_text, base_year)
                time_str = ';'.join(time_windows) if time_windows else None
                areas.append((area_counter, coords, time_str))
                area_counter += 1
        
        if areas:
            return areas
    
    # 尝试旧格式：时间信息在"IN AREA"之前
    old_format_pattern = r'[A-Z]\.\s+(.+?IN\s+AREAS?\s+BOUND\s+BY\s+)((?:\d{1,2}-\d{2}\.\d{2}[NS]\s+\d{2,3}-\d{2}\.\d{2}[EW][,.\s]*)+)'
    old_format_matches = re.findall(old_format_pattern, msg_text, re.IGNORECASE | re.DOTALL)
    
    if old_format_matches:
        for time_section, coord_text in old_format_matches:
            coords = parse_coordinates_msi(coord_text)
            if len(coords) >= 3:
                # 检查黑名单
                if check_against_blacklist(coords):
                    print(f"[过滤] 匹配黑名单落区，已屏蔽")
                    continue
                
                time_windows = parse_time_segment(time_section, base_year)
                time_str = ';'.join(time_windows) if time_windows else None
                areas.append((area_counter, coords, time_str))
                area_counter += 1
        
        if areas:
            return areas
    
    # 尝试匹配简单的多区域格式
    simple_area_pattern = r'[A-Z]\.\s+((?:\d{1,2}-\d{2}\.\d{2}[NS]\s+\d{2,3}-\d{2}\.\d{2}[EW][,.\s]*)+)'
    simple_matches = re.findall(simple_area_pattern, msg_text, re.IGNORECASE)
    
    if simple_matches:
        overall_time_windows = parse_time_segment(msg_text, base_year)
        overall_time_str = ';'.join(overall_time_windows) if overall_time_windows else None
        
        for coord_text in simple_matches:
            coords = parse_coordinates_msi(coord_text)
            if len(coords) >= 3:
                # 检查黑名单
                if check_against_blacklist(coords):
                    print(f"[过滤] 匹配黑名单落区，已屏蔽")
                    continue
                
                areas.append((area_counter, coords, overall_time_str))
                area_counter += 1
        
        if areas:
            return areas
    
    # 没有区域标记
    coords = parse_coordinates_msi(msg_text)
    if len(coords) >= 3:
        # 检查黑名单
        if check_against_blacklist(coords):
            print(f"[过滤] 匹配黑名单落区，已屏蔽")
            return []
        
        time_windows = parse_time_segment(msg_text, base_year)
        time_str = ';'.join(time_windows) if time_windows else None
        areas.append((1, coords, time_str))
    
    return areas


def fetch_url_with_retry(url, max_retries=3):
    """
    带重试机制的URL请求
    """
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=make_headers(), timeout=20)
            if response.status_code == 200:
                return response.json()
            else:
                print(f"[警告] 请求失败，状态码: {response.status_code}，重试 {attempt + 1}/{max_retries}")
        except Exception as e:
            print(f"[错误] 请求异常: {e}，重试 {attempt + 1}/{max_retries}")
            if attempt == max_retries - 1:
                raise
    return None


def process_single_url(url, base_cache_time):
    """
    处理单个URL的海警数据
    """
    local_result = {
        "CODE": [],
        "COORDINATES": [],
        "TIME": [],
        "TRANSID": [],
        "RAWMESSAGE": [],
        "SOURCE": [],
    }
    
    try:
        print(f"[进度] 请求: {url}")
        data = fetch_url_with_retry(url)
        
        if not data:
            return local_result
        
        smaps = data.get('smaps', [])
        print(f"[进度] 获取到 {len(smaps)} 条海警")
        
        for smap in smaps:
            category = smap.get('category', '')
            
            # 只处理火箭发射和太空碎片相关
            if category not in ['ROCKET LAUNCHING', 'SPACE DEBRIS']:
                continue
            
            msg_text = smap.get('msgText', '')
            msg_id = smap.get('msgID', '')
            msg_type = smap.get('msgType', '')
            created_on = smap.get('createdOn', '')
            
            if not msg_text:
                continue
            
            # 检查取消时间（非DEBUG模式）
            if not DEBUG:
                cancel_time = parse_cancel_time(msg_text, created_on)
                if cancel_time and cancel_time < datetime.utcnow():
                    print(f"[过滤] 已过期海警: {msg_id}")
                    continue
            
            # 解析编号
            code = parse_msg_code(msg_text, msg_type)
            base_year = get_base_year(created_on)
            
            # 提取区域坐标和时间
            areas = extract_areas_with_time(msg_text, base_year)
            
            if not areas:
                print(f"[警告] 未找到有效坐标: {msg_id}")
                continue
            
            # 为每个区域创建一条记录（使用临时数字编号）
            temp_areas = []
            for area_number, coords, time_str in areas:
                if not time_str:
                    print(f"[警告] 无法解析时间: {code} AREA {area_number}")
                    continue
                
                temp_areas.append((area_number, coords, time_str))
            
            # 后处理：如果只有一个区域，不添加AREA后缀
            if len(temp_areas) == 1:
                area_number, coords, time_str = temp_areas[0]
                coordinates_str = '-'.join(coords)
                
                local_result["CODE"].append(code)
                local_result["COORDINATES"].append(coordinates_str)
                local_result["TIME"].append(time_str)
                local_result["TRANSID"].append(msg_id)
                local_result["RAWMESSAGE"].append(msg_text)
                local_result["SOURCE"].append("MSI_NAV")
                
                print(f"[进度] 解析成功: {code}")
            else:
                # 多个区域，添加AREA后缀
                for area_number, coords, time_str in temp_areas:
                    area_code = f"{code} AREA {area_number}"
                    coordinates_str = '-'.join(coords)
                    
                    local_result["CODE"].append(area_code)
                    local_result["COORDINATES"].append(coordinates_str)
                    local_result["TIME"].append(time_str)
                    local_result["TRANSID"].append(msg_id)
                    local_result["RAWMESSAGE"].append(msg_text)
                    local_result["SOURCE"].append("MSI_NAV")
                    
                    print(f"[进度] 解析成功: {area_code}")
    
    except Exception as e:
        print(f"[错误] 处理URL失败 {url}: {e}")
        import traceback
        traceback.print_exc()
    
    return local_result


def MSI_NAV_SEARCH():
    """
    爬取U.S. Maritime Administration海警（支持缓存和多线程）
    """
    print("[进度] 开始爬取U.S. Maritime Administration海警...")
    
    # 缓存文件路径
    cache_file = 'msi_result.json'
    cache_timeout = config.MSI_FETCH_EXPIRE_TIME
    
    # 检查缓存
    if os.path.exists(cache_file) and not DEBUG:
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2000-01-01'))
            if (datetime.now() - cache_time).total_seconds() < cache_timeout:
                print(f"[进度] 使用缓存数据（缓存时间: {cache_time}）")
                result = cache_data.get('data', {})
                print(f"[进度] U.S. Maritime Administration海警爬取完成，获取 {len(result.get('CODE', []))} 条有效海警")
                return result
        except Exception as e:
            print(f"[警告] 读取缓存失败: {e}")
    
    result = {
        "CODE": [],
        "COORDINATES": [],
        "TIME": [],
        "TRANSID": [],
        "RAWMESSAGE": [],
        "SOURCE": [],
    }
    
    urls = []
    
    # 构建navArea URLs
    for nav_area in config.MSI_NAV_AREAS:
        url = f"https://msi.nga.mil/api/publications/smaps?navArea={nav_area}&status=active&category=14&output=html"
        urls.append(url)
    
    # 构建dncRegion URLs
    for dnc_region in config.MSI_DNC_REGIONS:
        url = f"https://msi.nga.mil/queryResults?publications/smaps?dncRegion={dnc_region}&status=active&category=14&output=html"
        urls.append(url)
    
    # 使用线程池并行请求
    base_cache_time = datetime.now()
    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_url = {executor.submit(process_single_url, url, base_cache_time): url for url in urls}
        
        for future in as_completed(future_to_url):
            url = future_to_url[future]
            try:
                local_result = future.result()
                # 合并结果
                for key in result.keys():
                    result[key].extend(local_result[key])
            except Exception as e:
                print(f"[错误] 线程执行失败 {url}: {e}")
    
    print(f"[进度] U.S. Maritime Administration海警爬取完成，获取 {len(result['CODE'])} 条有效海警")
    
    # 保存到缓存
    try:
        cache_data = {
            'timestamp': datetime.now().isoformat(),
            'data': result
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(cache_data, f, ensure_ascii=False, indent=2)
        print(f"[进度] 数据已缓存到 {cache_file}")
    except Exception as e:
        print(f"[警告] 保存缓存失败: {e}")
    
    return result


if __name__ == "__main__":
    DEBUG = True
    result = MSI_NAV_SEARCH()
    print(f"\n总共获取 {len(result['CODE'])} 条海警")
    for i in range(min(5, len(result['CODE']))):
        print(f"\n--- 海警 {i+1} ---")
        print(f"CODE: {result['CODE'][i]}")
        print(f"TIME: {result['TIME'][i][:100]}...")
        print(f"COORDINATES: {result['COORDINATES'][i][:80]}...")
