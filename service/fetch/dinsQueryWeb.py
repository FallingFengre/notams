"""
从notams.faa.gov网站爬取航警
"""
import os
import re

import requests
from bs4 import BeautifulSoup

from service.area_geometry import parse_areas
from service.fetch.aviation_parser import has_unlimited_ceiling, is_relevant, records_to_columns


def dinsQueryWeb(icao_codes):
    form_url = "https://www.notams.faa.gov/dinsQueryWeb/queryRetrievalMapAction.do"

    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "accept-encoding": "gzip, deflate",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8,ko;q=0.7",
        "content-type": "application/x-www-form-urlencoded",
        "origin": "https://www.notams.faa.gov",
        "referer": "https://www.notams.faa.gov/dinsQueryWeb/",
        "user-agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }

    post_data = {
        "retrieveLocId": icao_codes,
        "reportType": "Report",
        "actionType": "notamRetrievalByICAOs",
    }

    try:
        response = requests.post(form_url, headers=headers, data=post_data)
        response.raise_for_status()

    except requests.RequestException as e:
        print(f"[dinsQueryWeb] 请求失败: {e}")
        return {
            "CODE": [],
            "COORDINATES": [],
            "TIME": [],
            "SOURCE": "dinsQueryWeb",
            "ERROR": str(e)
        }

    current_dir = os.path.dirname(os.path.abspath(__file__))
    html_file = os.path.join(current_dir, "dinsQueryWeb_response.html")
    try:
        with open(html_file, 'w', encoding='utf-8') as file:
            file.write(response.text)
    except Exception as e:
        print(f"[dinsQueryWeb] 保存HTML文件失败: {e}")

    # Debugging
    # with open(html_file, 'r', encoding='utf-8') as file:
    #     html_content = file.read()
    # soup = BeautifulSoup(html_content, 'html.parser')

    soup = BeautifulSoup(response.text, 'html.parser')
    td_elements = soup.find_all('td', class_='textBlack12', valign='top')
    records = []
    seen_coordinates = set()
    for td in td_elements:
        pre_tag = td.find('pre')
        if pre_tag:
            raw = pre_tag.get_text()
            text_content = re.sub(r'[\r\n\[\]...]+', ' ', raw)
            if is_relevant(raw) and has_unlimited_ceiling(raw):
                areas = parse_areas(raw)
                time_pattern = r"\d{2} [A-Z]{3} \d{2}:\d{2} \d{4} UNTIL \d{2} [A-Z]{3} \d{2}:\d{2} \d{4}"
                time_info = re.search(time_pattern, text_content)
                time_result = time_info.group() if time_info else "00 JAN 00:00 0000 UNTIL 00 JAN 00:00 0000"
                currentText = text_content.split('-', 1)
                code = currentText[0] if currentText else "UNKNOWN"
                for i, area in enumerate(areas, 1):
                    coordinates = area['coordinates']
                    if coordinates in seen_coordinates:
                        continue
                    seen_coordinates.add(coordinates)
                    area_code = f'{code}_AREA{i}' if len(areas) > 1 else code
                    records.append({'CODE': area_code, 'COORDINATES': coordinates, 'GEOMETRY': area,
                                    'TIME': time_result, 'TRANSID': code, 'RAWMESSAGE': raw})
    return records_to_columns(records, 'DINS')
