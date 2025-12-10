import json
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import requests

ICAO_CODES = [
    "ZBPE", "ZGZU", "ZHWH", "ZJSA", "ZLHW", "ZPKM", "ZSHA", "ZWUQ", "ZYSH",
    "VHHK", "FUCK", "双曲线你为什么要特立独行",
]


def make_headers():
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 13_5_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/139.0.0.0 Safari/537.36"
    ]
    languages = [
        "zh-CN,zh;q=0.9,en;q=0.8",
        "en-US,en;q=0.9,zh;q=0.7",
        "en-GB,en;q=0.8,zh-CN;q=0.6"
    ]
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Accept-Encoding": "gzip, deflate",
        "Accept-Language": random.choice(languages),
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://notams.aim.faa.gov",
        "Referer": "https://notams.aim.faa.gov/notamSearch/nsapp.html",
        "User-Agent": random.choice(user_agents),
    }
    return headers


def fetch_one(icao):
    url = "https://notams.aim.faa.gov/notamSearch/search"
    payload = {
        "searchType": "0",
        "designatorsForLocation": icao,
        "offset": "0",
        "notamsOnly": "false"
    }
    payload1 = {
        "searchType": "4",
        "offset": "0",
        "freeFormText": "AEROSPACE",
        "notamsOnly": "false"
    }
    payload2 = {
        "searchType": "4",
        "offset": "0",
        "freeFormText": "DNG ZONE",
        "notamsOnly": "false"
    }
    if icao == "FUCK":
        payload = payload1
    if icao == "双曲线你为什么要特立独行":
        payload = payload2
    session = requests.Session()
    session.headers.update(make_headers())
    num = 30
    page = 0
    rslt = []
    while num == 30 and page < 100:
        try:
            payload["offset"] = str(page * 30)
            response = session.post(url, data=payload, timeout=7)
            if response.status_code == 200:
                data = response.json()
                num = len(data.get('notamList', []))
                rslt.extend(process_notam_data(data))
            else:
                print(f"[{icao}]-{page} 请求失败，状态码: {response.status_code}")
                raise
        except Exception as e:
            print(f"[{icao}]-{page} 请求错误: {e}")
            raise
        page += 1
    return icao, rslt


def process_notam_data(data):
    results = []
    if isinstance(data, dict) and 'notamList' in data:
        for notam in data['notamList']:
            results.append({
                'Number': notam.get('notamNumber'),
                'Message': notam.get('icaoMessage'),
                'startDate': notam.get('startDate'),
                'endDate': notam.get('endDate'),
                'transactionID': notam.get('transactionID')
            })
    results.sort(key=lambda r: (r.get('Number') is None, str(r.get('Number') or '').upper()))
    return results


def fetch_one_with_retry(icao, max_retries=2):
    """
    带有重试机制的 fetch_one 函数。
    返回 (icao, data, success_status)
    """
    for attempt in range(max_retries):
        try:
            # 直接调用原始的 fetch_one 函数
            icao_code, data = fetch_one(icao)
            # 如果 fetch_one 内部没有抛出异常，我们就认为成功
            return icao_code, data, True
        except Exception as e:
            print(f"[{icao}] 第 {attempt + 1} 次尝试失败: {e}")
            # 等待3s
            time.sleep(3)
            if attempt == max_retries - 1:
                # 最后一次尝试也失败了
                print(f"[{icao}] 在 {max_retries} 次尝试后最终失败。")
                return icao, [], False


def fetch():
    start = time.time()
    results = {}
    success_cnt = 0
    fail_cnt = 0
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_icao = {executor.submit(fetch_one_with_retry, icao): icao for icao in ICAO_CODES}
        for future in as_completed(future_to_icao):
            icao = future_to_icao[future]
            try:
                # 获取结果，包含成功状态
                icao_code, data, was_successful = future.result()

                results[icao_code] = data
                if was_successful:
                    success_cnt += 1
                    print(f"[{icao_code}] 完成，获取 {len(data)} 条 NOTAM")
                else:
                    fail_cnt += 1
                    print(f"[{icao_code}] 最终失败。")

            except Exception as e:
                # 这里的异常捕获是预防 future.result() 本身出错
                # (例如，worker线程崩溃了)
                fail_cnt += 1
                print(f"处理 [{icao}] 的 future 时发生意外错误: {e}")
                results[icao] = []  # 确保即使出错，结果字典中也有这个键

    output_data = {
        "timestamp": start,
        "results": results,
        "stats": {
            "total": len(ICAO_CODES),
            "success": success_cnt,
            "fail": fail_cnt
        }
    }
    output_data["results"] = dict(sorted(results.items()))
    with open("notam_results.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"全部 ICAO 和 自由文字 (FUCK) 检索完成")
    print(f"成功: {success_cnt} / 失败: {fail_cnt}")
    print(f"总耗时：{time.time() - start:.1f} 秒")
    return results


def FNS_NOTAM_SEARCH():
    json_path = "notam_results.json"
    now = time.time()
    results = {}
    if os.path.exists(json_path):
        with open(json_path, "r", encoding="utf-8") as f:
            try:
                data = json.load(f)
                ts = data.get("timestamp", 0)
                stats_obj = data.get('stats', {})  # 如果 'stats' 不存在，返回一个空字典 {}
                failed_cnt = stats_obj.get('fail', 0)
                if now - ts < 600 and "results" in data and failed_cnt == 0:
                    results = data["results"]
                    print("10分钟内爬取过航警，使用已有数据。")
                else:
                    raise Exception("已有数据过期或格式不正确，尝试重新爬取航警。")
            except Exception as e:
                print(e)
                results = fetch()
    else:
        print("未找到已有数据，尝试爬取航警。")
        results = fetch()

    def standardize_coordinate(coord):
        coord = coord.replace(' ', '')
        match1 = re.match(r'^([NS])(\d{4,6})([WE])(\d{5,7})$', coord)
        if match1:
            return coord
        match2 = re.match(r'^(\d{4,6})([NS])(\d{5,7})([WE])$', coord)
        if match2:
            return f"{match2.group(2)}{match2.group(1)}{match2.group(4)}{match2.group(3)}"
        match3 = re.match(r'^(\d{4})([NS])(\d{5})([WE])$', coord)
        if match3:
            return f"{match3.group(2)}{match3.group(1)}{match3.group(4)}{match3.group(3)}"
        return None

    def extract_coordinate_groups(text):
        patterns = [
            r'[NS]\d{6}[WE]\d{7}',
            r'[NS]\d{4}[WE]\d{5}',
            r'\d{6}[NS]\d{7}[WE]',
            r'\d{4}[NS]\d{5}[WE]',
        ]
        combined_pattern = '|'.join(f'({p})' for p in patterns)
        coordinates_with_positions = []

        for match in re.finditer(combined_pattern, text):
            coord = match.group()
            coord = re.sub(r'\s+', '', coord)
            coord = standardize_coordinate(coord)
            if coord:
                coordinates_with_positions.append({
                    'coord': coord,
                    'start': match.start(),
                    'end': match.end()
                })

        groups = []
        current_group = []
        max_gap = 20

        # 处理分组坐标
        for i, coord_info in enumerate(coordinates_with_positions):
            if not current_group:
                current_group.append(coord_info['coord'])
            else:
                prev_end = coordinates_with_positions[i - 1]['end']
                curr_start = coord_info['start']
                gap = curr_start - prev_end

                if gap <= max_gap:
                    current_group.append(coord_info['coord'])
                else:
                    if len(current_group) >= 3:
                        groups.append(current_group)
                    current_group = [coord_info['coord']]

        if len(current_group) >= 3:
            groups.append(current_group)

        return groups

    def parse_time(start_date, end_date):
        if not start_date or not end_date:
            return "00 JAN 00:00 0000 UNTIL 00 JAN 00:00 0000"

        if end_date == "PERM":
            end_date = "12/31/2099 2359"

        months = {
            "01": "JAN", "02": "FEB", "03": "MAR", "04": "APR",
            "05": "MAY", "06": "JUN", "07": "JUL", "08": "AUG",
            "09": "SEP", "10": "OCT", "11": "NOV", "12": "DEC"
        }

        def convert_date(date_str):
            if not date_str or len(date_str) < 14:
                return "00 JAN 00:00 0000"
            month, day, year_time = date_str.split("/")
            year, time = year_time.split(" ")
            hour, minute = time[:2], time[2:]
            return f"{day} {months[month]} {hour}:{minute} {year}"

        return f"{convert_date(start_date)} UNTIL {convert_date(end_date)}"

    data_array = np.array(["CODE", "COORDINATES", "TIME", "TRANSID", "RAWMESSAGE"])

    # 处理每个NOTAM
    debug = False
    for icao, notams in results.items():
        for notam in notams:
            message = notam.get('Message', '')
            if ("A TEMPORARY" in message and "-" in message) or ("AEROSPACE" in message) or (
                    "CHINA" in message and "DNG ZONE" in message and "AERIAL" in message):
                raw_message = message
                message = message.replace(" ", "")
                message = message.replace("\n", "")
                coordinate_groups = extract_coordinate_groups(message)
                time_result = parse_time(notam.get('startDate'), notam.get('endDate'))
                code = notam.get('Number', 'UNKNOWN')
                trans_id = notam.get('transactionID', 'UNKNOWN')
                for i, group in enumerate(coordinate_groups):
                    coordinates_result = '-'.join(group)
                    if len(coordinate_groups) > 1:
                        area_code = f"{code}_AREA{i + 1}"
                    else:
                        area_code = code
                    data_array = np.vstack(
                        [data_array, np.array([area_code, coordinates_result, time_result, trans_id, raw_message])])

    if len(data_array) > 1:
        df = pd.DataFrame(data_array)

        # 按TRANSID排序
        if len(df) > 1 and df.iloc[0, 0] == "CODE":
            header = df.iloc[0]
            data_df = df.iloc[1:]
            data_df_sorted = data_df.sort_values(by=3, ascending=True)
            df = pd.concat([header.to_frame().T, data_df_sorted], ignore_index=True)

        df_unique = df.drop_duplicates(subset=0)
        data_array = df_unique.to_numpy()
        if len(data_array) > 1 and data_array[0, 0] == "CODE":
            data_array = data_array[1:]
        result = {
            "CODE": data_array[:, 0].tolist() if len(data_array) > 0 else [],
            "COORDINATES": data_array[:, 1].tolist() if len(data_array) > 0 else [],
            "TIME": data_array[:, 2].tolist() if len(data_array) > 0 else [],
            "TRANSID": data_array[:, 3].tolist() if len(data_array) > 0 else [],
            "RAWMESSAGE": data_array[:, 4].tolist() if len(data_array) > 0 else [],
        }
    else:
        result = {
            "CODE": [],
            "COORDINATES": [],
            "TIME": [],
            "TRANSID": [],
            "RAWMESSAGE": [],
        }
    return result
# print(FNS_NOTAM_SEARCH())
