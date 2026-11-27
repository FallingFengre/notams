import json
import os
import time

import config
from service.fetch.aviation_parser import parse_aviation_records, records_to_columns
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

    return parse_current_notams(results, "FNS_NOTAM")


def parse_current_notams(results, source):
    seen_codes = set()
    records = []
    for record in sorted(parse_aviation_records(results), key=lambda item: str(item['TRANSID'])):
        if record['CODE'] not in seen_codes:
            records.append(record)
            seen_codes.add(record['CODE'])
    return records_to_columns(records, source)
