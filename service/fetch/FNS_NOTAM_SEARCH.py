import json
import os
import re
import time

import numpy as np
import pandas as pd

import config
from service.fetch.faa_browser import get_session

ICAO_CODES = [
    "ZBPE", "ZGZU", "ZHWH", "ZJSA", "ZLHW", "ZPKM", "ZSHA", "ZWUQ", "ZYSH",
    "VHHK", "FUCK", "双曲线你为什么要特立独行","FUCK2","FUCKFAA"
]

# 构建每个 icao 对应的 payload（含分页 key）
def _build_payload(icao):
    if icao == "FUCK":
        return {"searchType": "4", "freeFormText": "AEROSPACE", "notamsOnly": "false"}
    if icao == "双曲线你为什么要特立独行":
        return {"searchType": "4", "freeFormText": "DNG ZONE", "notamsOnly": "false"}
    if icao == "FUCK2":
        return {"searchType": "4", "freeFormText": "ROCKET LAUNCH", "notamsOnly": "false"}
    if icao == "FUCKFAA":
        return {"searchType": "4", "freeFormText": "AER0SPACE", "notamsOnly": "false"}
    return {"searchType": "0", "designatorsForLocation": icao, "notamsOnly": "false"}


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


def fetch():
    """批量并行获取所有 ICAO NOTAM，在浏览器 JS 层 Promise.all() 并行。"""
    start = time.time()
    results = {}
    success_cnt = 0
    fail_cnt = 0

    session = get_session()

    # 准备 queries: {icao: payload}（第 1 页）
    queries = {}
    for icao in ICAO_CODES:
        queries[icao] = _build_payload(icao)

    # 批量请求第 1 页（浏览器 JS 中 Promise.all 并行）
    page_results = session.batch_search(queries)

    # 检查哪些需要下一页（num=30 的继续）
    for icao, data in page_results.items():
        if data is None:
            fail_cnt += 1
            results[icao] = []
            print(f"[{icao}] 最终失败。")
            continue
        notams = process_notam_data(data)
        results[icao] = notams
        num = len(data.get('notamList', []))
        # 如果第一页满了（30 条），继续翻页
        if num == 30:
            page = 1
            while num == 30 and page < 100:
                try:
                    payload = dict(queries[icao])
                    payload['offset'] = str(page * 30)
                    data_page = session.search(payload)
                    num = len(data_page.get('notamList', []))
                    results[icao].extend(process_notam_data(data_page))
                    page += 1
                except Exception as e:
                    print(f"[{icao}]-{page} 分页错误: {e}")
                    break
        success_cnt += 1
        print(f"[{icao}] 完成，获取 {len(results[icao])} 条 NOTAM")

    output_data = {
        "timestamp": start,
        "results": results,
        "stats": {"total": len(ICAO_CODES), "success": success_cnt, "fail": fail_cnt}
    }
    output_data["results"] = dict(sorted(results.items()))
    with open("notam_results.json", "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"全部 ICAO 和 自由文字检索完成")
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
                stats_obj = data.get('stats', {})
                failed_cnt = stats_obj.get('fail', 0)
                if now - ts < config.FETCH_EXPIRE_TIME and "results" in data and failed_cnt == 0:
                    results = data["results"]
                    print(f"{config.FETCH_EXPIRE_TIME / 60} 分钟内爬取过航警，使用已有数据。")
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

    debug = False
    for icao, notams in results.items():
        for notam in notams:
            message = notam.get('Message', '')
            if (("A TEMPORARY" in message and "-" in message) or ("AEROSPACE" in message) or ("AER0SPACE" in message)
                or ("CHINA" in message and "AERIAL" in message and "DNG ZONE" in message)
                 or ("CHINA" in message and "ROCKET" in message and "LAUNCH" in message)):
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

    if data_array.ndim > 1:
        df = pd.DataFrame(data_array)

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
            "SOURCE": ["FNS_NOTAM"] * len(data_array) if len(data_array) > 0 else [],
        }
    else:
        result = {
            "CODE": [],
            "COORDINATES": [],
            "TIME": [],
            "TRANSID": [],
            "RAWMESSAGE": [],
            "SOURCE": [],
        }
    return result
