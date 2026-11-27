"""DAIP mobile location search for current NOTAMs."""

import html
import re
import threading
import time
from datetime import datetime
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config
from service.fetch.aviation_parser import is_relevant
from service.fetch.FNS_NOTAM_SEARCH import parse_current_notams

BASE_URL = "https://www.daip.jcs.mil/daip/mobile/"
# DoD Root CA 6 from the PKI/PKE certificate distribution:
# https://dl.dod.cyber.mil/wp-content/uploads/pki-pke/zip/unclass-certificates_pkcs7_DoD.zip
CA_BUNDLE = Path(__file__).with_name("dod-root-ca-6.pem")
REQUEST_SIZE = 30
_lock = threading.Lock()
_cache = None


def _dates(raw, display):
    start = re.search(r"\bB\)\s*(\d{10})", raw)
    end = re.search(r"\bC\)\s*(\d{10}|PERM)", raw)
    if start and end:
        tokens = start[1], end[1]
    else:
        span = re.search(r"\b(\d{10})\s*-\s*(\d{10}|PERM)\b", raw)
        tokens = span.groups() if span else ()
    def format_dates(values, date_format):
        try:
            return tuple(
                value if value == "PERM" else datetime.strptime(value, date_format).strftime("%m/%d/%Y %H%M")
                for value in values
            )
        except ValueError:
            return None
    if tokens:
        dates = format_dates(tokens, "%y%m%d%H%M")
        if dates:
            return dates
    span = re.search(r"(\d{2} [A-Z]{3} \d{2}:\d{2} \d{4})\s+UNTIL\s+(\d{2} [A-Z]{3} \d{2}:\d{2} \d{4}|PERM)", display)
    if span:
        return format_dates(span.groups(), "%d %b %H:%M %Y") or (None, None)
    return None, None


def _map_notices(payload, requested):
    if not isinstance(payload, dict) or payload.get("error") or not isinstance(payload.get("group"), list):
        raise ValueError("DAIP 返回了错误或缺少航警分组")
    groups = payload["group"]
    missing = set(requested) - {g["name"] for g in groups}
    if missing:
        raise ValueError(f"DAIP 响应缺少位置 {', '.join(sorted(missing))}")
    notices = []
    for group in groups:
        for section in group.get("notams") or []:
            for item in section.get("list") or []:
                display = html.unescape(item.get("text") or "")
                raw = html.unescape(item.get("rawtext") or "").strip() or display
                if not is_relevant(raw):
                    continue
                number = re.search(r"\b([A-Z]\d{4}/\d{2})\s+NOTAM", raw)
                number = number[1] if number else item.get("idshow") or item.get("id")
                if not number:
                    raise ValueError("DAIP 航警缺少编号")
                start, end = _dates(raw, display)
                notices.append({
                    "Number": str(number), "Message": raw, "startDate": start, "endDate": end,
                    "transactionID": str(item.get("key") or item.get("xid") or f"{group['name']}:{number}"),
                })
    return notices


def _fetch(locations):
    payload = dict.fromkeys(
        "poa pod alternates route runwayLength runwayWidth airportType notamId acode artcc "
        "tfrsOnly orgLoc lat1 lat2 lng1 lng2 latdir longdir includeRegulatoryNotices briefing "
        "scheduleDate sendTime active sunday monday tuesday wednesday thursday friday saturday".split(), ""
    )
    payload.update(type="LOCATION", radius="10", sort="Criticality")
    notices = []
    with requests.Session() as session:
        session.verify = str(CA_BUNDLE)
        session.headers.update({"Referer": BASE_URL + "index", "X-Requested-With": "XMLHttpRequest",
                                "Accept": "application/json, text/javascript, */*; q=0.01"})
        # Both operations are read-only, including the location POST.
        retry = Retry(total=1, allowed_methods={"GET", "POST"}, status_forcelist=(502, 503, 504))
        session.mount(BASE_URL, HTTPAdapter(max_retries=retry))
        session.get(BASE_URL + "index", timeout=20).raise_for_status()
        for i in range(0, len(locations), REQUEST_SIZE):
            requested = locations[i:i + REQUEST_SIZE]
            payload["locs"] = " ".join(requested)
            response = session.post(BASE_URL + "query", json=payload, timeout=(15, 45))
            response.raise_for_status()
            notices.extend(_map_notices(response.json(), requested))
    return parse_current_notams({"DAIP": notices}, "DAIP")


def current_notams(codes):
    global _cache
    locations = tuple(sorted(set(codes.upper().replace(",", " ").split())))
    if not locations:
        raise ValueError("DAIP 查询位置为空")
    with _lock:
        if _cache and _cache[0] == locations and time.monotonic() - _cache[1] < config.FETCH_EXPIRE_TIME:
            return _cache[2]
        print(f"[DAIP] 正在查询 {len(locations)} 个位置")
        result = _fetch(locations)
        _cache = locations, time.monotonic(), result
        print(f"[DAIP] 解析得到 {len(result['CODE'])} 条区域记录")
        return result
