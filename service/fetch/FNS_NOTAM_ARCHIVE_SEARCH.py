import re
import time

import numpy as np
import pandas as pd

from service.fetch.faa_browser import get_session

ICAO_CODES = [
    "ZBPE", "ZGZU", "ZHWH", "ZJSA", "ZLHW", "ZPKM", "ZSHA", "ZWUQ", "ZYSH",
    "VHHK",
]


def fetch_one(icao, date):
    payload = {
        "searchType": "5",
        "archiveDate": date,
        "archiveDesignator": icao,
        "offset": "0",
        "notamsOnly": "false"
    }
    session = get_session()
    num = 30
    page = 0
    rslt = []
    print(f"[进度] 开始检索 {icao} 区域的历史航警...")

    while num == 30 and page < 100:
        page_attempts = 0
        max_page_retries = 2
        page_success = False

        while page_attempts <= max_page_retries and not page_success:
            try:
                payload["offset"] = str(page * 30)
                data = session.search(payload)
                num = len(data.get('notamList', []))
                rslt.extend(process_notam_data(data))
                print(f"[进度] {icao} - 第{page + 1}页: 获取 {num} 条 NOTAM")
                page_success = True
            except Exception as e:
                page_attempts += 1
                if page_attempts <= max_page_retries:
                    print(f"[进度] {icao} - 第{page + 1}页: 第{page_attempts}次尝试失败 ({e})，等待2秒后重试...")
                    time.sleep(2)
                else:
                    print(f"[进度] {icao} - 第{page + 1}页: 请求错误，已重试{max_page_retries}次 - {e}")
                    raise

        page += 1

    print(f"[进度] {icao} 检索完成，共获取 {len(rslt)} 条 NOTAM")
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


def fetch_one_with_retry(icao, date, max_retries=2):
    """
    带有重试机制的 fetch_one 函数。
    返回 (icao, data, success_status)
    """
    for attempt in range(max_retries):
        try:
            # 直接调用原始的 fetch_one 函数
            icao_code, data = fetch_one(icao, date)
            # 如果 fetch_one 内部没有抛出异常，我们就认为成功
            return icao_code, data, True
        except Exception as e:
            print(f"[进度] {icao} 第 {attempt + 1} 次尝试失败: {e}")
            # 等待3s
            time.sleep(2)
            if attempt == max_retries - 1:
                # 最后一次尝试也失败了
                print(f"[进度] {icao} 在 {max_retries} 次尝试后最终失败")
                return icao, [], False


def fetch(icao, date, mode=0):
    start = time.time()
    results = {}
    if mode == 0:
        print(f"[进度] 开始批量检索 {len(ICAO_CODES)} 个区域的历史航警...")
        # 构建 queries: {code: payload}
        queries = {}
        for code in ICAO_CODES:
            queries[code] = {
                "searchType": "5",
                "archiveDate": date,
                "archiveDesignator": code,
                "offset": "0",
                "notamsOnly": "false"
            }
        # 浏览器 JS 层 Promise.all() 并行第一批
        session = get_session()
        first_page = session.batch_search(queries)
        sNum = 0
        fNum = 0
        completed = 0
        total = len(ICAO_CODES)
        for code in ICAO_CODES:
            completed += 1
            data = first_page.get(code)
            if data is None:
                fNum += 1
                results[code] = []
                print(f"[进度] ({completed}/{total}) {code} 检索失败")
                continue
            notams = process_notam_data(data)
            results[code] = notams
            # 翻页（如有更多）
            num = len(data.get('notamList', []))
            if num == 30:
                page = 1
                while num == 30 and page < 100:
                    try:
                        payload = dict(queries[code])
                        payload['offset'] = str(page * 30)
                        data_page = session.search(payload)
                        num = len(data_page.get('notamList', []))
                        results[code].extend(process_notam_data(data_page))
                        page += 1
                    except Exception as e:
                        print(f"[进度] {code} - 第{page+1}页翻页错误: {e}")
                        break
            sNum += 1
            print(f"[进度] ({completed}/{total}) {code} 检索完成，获取 {len(results[code])} 条 NOTAM")
        print(f"[进度] 所有区域检索完成！成功: {sNum}, 失败: {fNum}")
    if mode == 1:
        icao_code, data, was_successful = fetch_one_with_retry(icao, date)
        results[icao_code] = data
        if was_successful:
            print(f"[进度] {icao} 检索完成，获取 {len(data)} 条 NOTAM")
        else:
            print(f"[进度] {icao} 检索失败")
    print(f"[进度] 总耗时：{time.time() - start:.1f} 秒")
    return results


def FNS_NOTAM_ARCHIVE_SEARCH(icao, date, mode=0):
    print(f"[进度] ========== 开始历史航警检索 ==========")
    print(
        f"[进度] 日期: {date}, 区域: {icao if mode == 1 else '内陆及近海'}, 模式: {'single' if mode == 1 else 'multi'}")
    results = fetch(icao, date, mode)
    print(f"[进度] 开始解析航警数据...")

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

    data_array = np.array([["CODE", "COORDINATES", "TIME", "TRANSID", "RAWMESSAGE"]])

    # 处理每个NOTAM
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

    if len(data_array) > 1:
        df = pd.DataFrame(data_array[1:], columns=data_array[0])
        df_unique = df.drop_duplicates(subset='COORDINATES')
        data_array_unique = np.vstack([data_array[0], df_unique.to_numpy()])
        if len(data_array_unique) > 1 and data_array_unique[0, 0] == "CODE":
            data_array_unique = data_array_unique[1:]
        result = {
            "CODE": data_array_unique[:, 0].tolist() if len(data_array_unique) > 0 else [],
            "COORDINATES": data_array_unique[:, 1].tolist() if len(data_array_unique) > 0 else [],
            "TIME": data_array_unique[:, 2].tolist() if len(data_array_unique) > 0 else [],
            "TRANSID": data_array_unique[:, 3].tolist() if len(data_array_unique) > 0 else [],
            "RAWMESSAGE": data_array_unique[:, 4].tolist() if len(data_array_unique) > 0 else [],
            "SOURCE": ["FNS_NOTAM"] * len(data_array_unique) if len(data_array_unique) > 0 else [],
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
    print(f"[进度] 解析完成，共获取 {len(result['CODE'])} 条有效航警")
    print(f"[进度] ========== 检索完成 ==========\n")
    return result
# print(FNS_NOTAM_ARCHIVE_SEARCH("ZPKM", "2024-06-01", 0))
