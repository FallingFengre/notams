"""
从notams.faa.gov网站爬取航警
"""
import os
import re

import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup


def dinsQueryWeb(icao_codes):
    data_array = np.array(["CODE", "COORDINATES", "TIME"])

    def removeC(text):
        return re.sub(r'[\r\n\[\]...]+', ' ', text)

    def removeC2(text):
        return re.sub(r'[\s+\r\n\[\]...]+', '', text)

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

        # 处理分组坐标，避免将两个落区绘制为一个落区导致混乱，同时避免将非落区的航警中零散的坐标提取为落区
        for i, coord_info in enumerate(coordinates_with_positions):
            if not current_group:
                current_group.append(coord_info['coord'])
            else:
                # 计算与前一个坐标的字符距离
                prev_end = coordinates_with_positions[i - 1]['end']
                curr_start = coord_info['start']
                gap = curr_start - prev_end

                if gap <= max_gap:
                    current_group.append(coord_info['coord'])
                else:
                    if len(current_group) >= 3:  # 只保留至少3个点的组
                        groups.append(current_group)
                    current_group = [coord_info['coord']]

        if len(current_group) >= 3:
            groups.append(current_group)

        return groups

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
    parsed_count = 0
    for td in td_elements:
        pre_tag = td.find('pre')
        if pre_tag:
            text_content = pre_tag.get_text(strip=True)
            text_content = removeC(text_content)
            if "A TEMPORARY" in text_content or "AEROSPACE" in text_content:
                fuck = removeC2(text_content)
                coordinate_groups = extract_coordinate_groups(fuck)
                time_pattern = r"\d{2} [A-Z]{3} \d{2}:\d{2} \d{4} UNTIL \d{2} [A-Z]{3} \d{2}:\d{2} \d{4}"
                time_info = re.search(time_pattern, text_content)
                time_result = time_info.group() if time_info else "00 JAN 00:00 0000 UNTIL 00 JAN 00:00 0000"
                currentText = text_content.split('-', 1)
                code = currentText[0] if currentText else "UNKNOWN"
                for i, group in enumerate(coordinate_groups):
                    coordinates_result = '-'.join(group)
                    if len(coordinate_groups) > 1:
                        area_code = f"{code}_AREA{i + 1}"
                    else:
                        area_code = code
                    data_array = np.vstack([data_array, np.array([area_code, coordinates_result, time_result])])
                    parsed_count += 1

    if len(data_array) > 1:
        df = pd.DataFrame(data_array)
        df_unique = df.drop_duplicates(subset=1)
        data_array = df_unique.to_numpy()
        if len(data_array) > 1 and data_array[0, 0] == "CODE":
            data_array = data_array[1:]
        result = {
            "CODE": data_array[:, 0].tolist() if len(data_array) > 0 else [],
            "COORDINATES": data_array[:, 1].tolist() if len(data_array) > 0 else [],
            "TIME": data_array[:, 2].tolist() if len(data_array) > 0 else [],
        }
    else:
        result = {
            "CODE": [],
            "COORDINATES": [],
            "TIME": [],
        }
    return result
