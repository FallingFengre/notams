import re
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
import requests

# 调试模式：True时不过滤过期航警
DEBUG = True


def make_headers():
    return {
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    }


def preprocess_text(text):
    """预处理文本，去除多余空格、换行等"""
    text = re.sub(r'{[^}]+}', '', text)
    text = re.sub(r'%[^%]+%', '', text)
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def parse_coordinates(text):
    # 预处理：去除多余空格但保留坐标间的分隔
    text = preprocess_text(text)
    text_no_space = text.replace(' ', '')
    
    coords = []
    
    # 格式1: DD-MM.mmN DDD-MM.mmE (空格分隔)
    pattern1 = r'(\d{1,3})-(\d{1,2})\.(\d{1,2})([NS])\s+(\d{1,3})-(\d{1,2})\.(\d{1,2})([WE])'
    matches1 = re.findall(pattern1, text)
    
    # 格式2: DD-MM.mmN/DDD-MM.mmE (斜杠分隔)
    pattern2 = r'(\d{1,3})-(\d{1,2})\.(\d{1,2})([NS])/(\d{1,3})-(\d{1,2})\.(\d{1,2})([WE])'
    matches2 = re.findall(pattern2, text)
    
    # 格式3: DD-MM.mmNDDD-MM.mmE (无分隔)
    pattern3 = r'(\d{1,3})-(\d{1,2})\.(\d{1,2})([NS])(\d{1,3})-(\d{1,2})\.(\d{1,2})([WE])'
    matches3 = re.findall(pattern3, text_no_space)
    
    all_matches = matches1 + matches2 + matches3
    
    for match in all_matches:
        lat_deg, lat_min_int, lat_min_dec, lat_dir, lon_deg, lon_min_int, lon_min_dec, lon_dir = match
        
        # 转换分钟小数为秒
        lat_min = int(lat_min_int)
        lat_sec = round(int(lat_min_dec) * 60 / 100)
        lon_min = int(lon_min_int)
        lon_sec = round(int(lon_min_dec) * 60 / 100)
        
        # 格式化为 NDDMMSS EDDDMMSS
        formatted_lat = f"{lat_dir}{int(lat_deg):02d}{lat_min:02d}{lat_sec:02d}"
        formatted_lon = f"{lon_dir}{int(lon_deg):03d}{lon_min:02d}{lon_sec:02d}"
        
        coords.append(formatted_lat + formatted_lon)
    
    return coords


def parse_msa_time(time_str, publish_date):
    time_str = preprocess_text(time_str)
    
    # 尝试解析发布日期获取年份
    try:
        pub_date = datetime.strptime(publish_date, "%Y-%m-%d")
    except:
        pub_date = datetime.now()
    
    default_year = pub_date.year
    
    # 模式1: 完整日期 YYYY年MM月DD日HHMM时至HHMM时
    pattern1 = r'(\d{4})年(\d{1,2})月(\d{1,2})日(\d{2})(\d{2})时至(\d{2})(\d{2})时'
    match1 = re.search(pattern1, time_str)
    if match1:
        year, month, day, start_h, start_m, end_h, end_m = match1.groups()
        start_dt = datetime(int(year), int(month), int(day), int(start_h), int(start_m))
        end_dt = datetime(int(year), int(month), int(day), int(end_h), int(end_m))
        # 如果结束时间小于开始时间，说明跨天
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        return format_time_utc(start_dt, end_dt)
    
    # 模式2: 完整日期范围 YYYY年MM月DD日至YYYY年MM月DD日
    pattern2 = r'(\d{4})年(\d{1,2})月(\d{1,2})日至(\d{4})年(\d{1,2})月(\d{1,2})日'
    match2 = re.search(pattern2, time_str)
    if match2:
        y1, m1, d1, y2, m2, d2 = match2.groups()
        start_dt = datetime(int(y1), int(m1), int(d1), 0, 0)
        end_dt = datetime(int(y2), int(m2), int(d2), 23, 59)
        return format_time_utc(start_dt, end_dt)
    
    # 模式3: 完整日期 YYYY年MM月DD日至MM月DD日
    pattern3 = r'(\d{4})年(\d{1,2})月(\d{1,2})日至(\d{1,2})月(\d{1,2})日'
    match3 = re.search(pattern3, time_str)
    if match3:
        y1, m1, d1, m2, d2 = match3.groups()
        start_dt = datetime(int(y1), int(m1), int(d1), 0, 0)
        # 判断是否跨年
        year2 = int(y1) if int(m2) >= int(m1) else int(y1) + 1
        end_dt = datetime(year2, int(m2), int(d2), 23, 59)
        return format_time_utc(start_dt, end_dt)
    
    # 模式4: MM月DD日HHMM时至DD日HHMM时 (跨天)
    pattern4 = r'(\d{1,2})月(\d{1,2})日(\d{2})(\d{2})时至(\d{1,2})日(\d{2})(\d{2})时'
    match4 = re.search(pattern4, time_str)
    if match4:
        m1, d1, h1, min1, d2, h2, min2 = match4.groups()
        year = infer_year(int(m1), pub_date)
        start_dt = datetime(year, int(m1), int(d1), int(h1), int(min1))
        # 判断结束日期的月份
        end_month = int(m1) if int(d2) >= int(d1) else int(m1) + 1
        if end_month > 12:
            end_month = 1
            year += 1
        end_dt = datetime(year, end_month, int(d2), int(h2), int(min2))
        return format_time_utc(start_dt, end_dt)
    
    # 模式5: MM月DD日HHMM时至HHMM时 (同一天)
    pattern5 = r'(\d{1,2})月(\d{1,2})日(\d{2})(\d{2})时至(\d{2})(\d{2})时'
    match5 = re.search(pattern5, time_str)
    if match5:
        m1, d1, h1, min1, h2, min2 = match5.groups()
        year = infer_year(int(m1), pub_date)
        start_dt = datetime(year, int(m1), int(d1), int(h1), int(min1))
        end_dt = datetime(year, int(m1), int(d1), int(h2), int(min2))
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        return format_time_utc(start_dt, end_dt)
    
    # 模式6: 自YYYY年MM月DD日HHMM时至HHMM时
    pattern6 = r'自(\d{4})年(\d{1,2})月(\d{1,2})日(\d{2})(\d{2})时至(\d{2})(\d{2})时'
    match6 = re.search(pattern6, time_str)
    if match6:
        year, month, day, h1, min1, h2, min2 = match6.groups()
        start_dt = datetime(int(year), int(month), int(day), int(h1), int(min1))
        end_dt = datetime(int(year), int(month), int(day), int(h2), int(min2))
        if end_dt < start_dt:
            end_dt += timedelta(days=1)
        return format_time_utc(start_dt, end_dt)
    
    return None


def infer_year(month, pub_date):
    if pub_date.month <= month:
        return pub_date.year
    else:
        return pub_date.year + 1


def format_time_utc(start_dt, end_dt):
    # 北京时间转UTC (减8小时)
    start_utc = start_dt - timedelta(hours=8)
    end_utc = end_dt - timedelta(hours=8)
    
    months = ['JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 
              'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC']
    
    start_str = f"{start_utc.day:02d} {months[start_utc.month-1]} {start_utc.hour:02d}:{start_utc.minute:02d} {start_utc.year}"
    end_str = f"{end_utc.day:02d} {months[end_utc.month-1]} {end_utc.hour:02d}:{end_utc.minute:02d} {end_utc.year}"
    
    return f"{start_str} UNTIL {end_str}"


def extract_article_id(href):
    """从href中提取articleId"""
    match = re.search(r'articleId=([a-f0-9\-]+)', href)
    if match:
        return match.group(1)
    return None


def MSA_NAV_SEARCH():
    print("[进度] 开始获取中国海事局海警...")
    
    result = {
        "CODE": [],
        "COORDINATES": [],
        "TIME": [],
        "TRANSID": [],
        "RAWMESSAGE": [],
        "SOURCE": [],
    }
    
    base_url = "https://www.msa.gov.cn"
    index_url = f"{base_url}/page/channelArticles.do?channelids=9C219298-B27F-460E-995A-99401B3FF6AF"
    
    try:
        # 1. 获取目录页
        response = requests.get(index_url, headers=make_headers(), timeout=15)
        response.encoding = 'utf-8'
        
        if response.status_code != 200:
            print(f"[错误] 获取目录页失败，状态码: {response.status_code}")
            return result
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # 2. 查找包含"火箭"关键词的航警链接
        rocket_links = []
        for li in soup.find_all('li'):
            link = li.find('a', href=True)
            if link:
                span = link.find('span')
                if span and '火箭' in span.get_text():
                    href = link.get('href')
                    title = span.get_text().strip()
                    # 获取发布日期
                    date_span = li.find_all('span')
                    pub_date = None
                    for s in date_span:
                        date_match = re.search(r'\[(\d{4}-\d{2}-\d{2})\]', s.get_text())
                        if date_match:
                            pub_date = date_match.group(1)
                            break
                    
                    rocket_links.append({
                        'href': href,
                        'title': title,
                        'pub_date': pub_date or datetime.now().strftime('%Y-%m-%d')
                    })
        
        print(f"[进度] 找到 {len(rocket_links)} 条含'火箭'关键词的海警")
        
        # 3. 爬取每个航警详情页
        for link_info in rocket_links:
            href = link_info['href']
            pub_date = link_info['pub_date']
            
            # 构建完整URL
            if href.startswith('/'):
                detail_url = base_url + href
            else:
                detail_url = href
            
            article_id = extract_article_id(href)
            
            try:
                detail_response = requests.get(detail_url, headers=make_headers(), timeout=15)
                detail_response.encoding = 'utf-8'
                
                if detail_response.status_code != 200:
                    print(f"[警告] 获取详情页失败: {detail_url}")
                    continue
                
                detail_soup = BeautifulSoup(detail_response.text, 'html.parser')
                
                # 4. 解析正文
                content_div = detail_soup.find('div', {'class': 'text', 'id': 'ch_p'})
                if not content_div:
                    print(f"[警告] 未找到正文内容: {detail_url}")
                    continue
                
                # 获取正文文本
                raw_text = content_div.get_text(separator=' ', strip=True)
                # 移除"收藏"、"打印本页"、"关闭窗口"等
                raw_text = re.sub(r'收藏.*?关闭窗口', '', raw_text)
                raw_text = preprocess_text(raw_text)
                
                # 5. 解析航警编号
                code_match = re.search(r'([沪浙苏鲁粤闽琼桂辽冀津京深港澳台渤黄东南]{1,2}航警\d+/\d+)', raw_text)
                code = code_match.group(1) if code_match else link_info['title']
                
                # 6. 解析时间
                time_str = parse_msa_time(raw_text, pub_date)
                if not time_str:
                    print(f"[警告] 无法解析时间: {raw_text[:100]}")
                    continue
                
                # 检查是否过期 (非DEBUG模式)
                if not DEBUG:
                    try:
                        # 解析结束时间
                        end_part = time_str.split(' UNTIL ')[1]
                        end_match = re.match(r'(\d{2}) ([A-Z]+) (\d{2}):(\d{2}) (\d{4})', end_part)
                        if end_match:
                            day, mon, hour, minute, year = end_match.groups()
                            months = {'JAN':1,'FEB':2,'MAR':3,'APR':4,'MAY':5,'JUN':6,
                                     'JUL':7,'AUG':8,'SEP':9,'OCT':10,'NOV':11,'DEC':12}
                            end_dt = datetime(int(year), months[mon], int(day), int(hour), int(minute))
                            if end_dt < datetime.utcnow():
                                print(f"[过滤] 已过期航警: {code}")
                                continue
                    except Exception as e:
                        print(f"[警告] 检查过期时间失败: {e}")
                
                # 7. 解析坐标
                coords = parse_coordinates(raw_text)
                if len(coords) < 3:
                    print(f"[警告] 坐标点不足: {code}, 找到 {len(coords)} 个")
                    continue
                
                coordinates_str = '-'.join(coords)
                
                # 8. 添加到结果
                result["CODE"].append(code)
                result["COORDINATES"].append(coordinates_str)
                result["TIME"].append(time_str)
                result["TRANSID"].append(article_id or '')
                result["RAWMESSAGE"].append(raw_text)
                result["SOURCE"].append("MSA_NAV")
                
                print(f"[进度] 解析成功: {code}")
                
            except Exception as e:
                print(f"[错误] 解析航警详情失败: {e}")
                continue
        
        print(f"[进度] 中国海事局海警爬取完成，获取 {len(result['CODE'])} 条有效海警")
        
    except Exception as e:
        print(f"[错误] 爬取中国海事局海警失败: {e}")
    
    return result


if __name__ == "__main__":
    result = MSA_NAV_SEARCH()
    print(result)
