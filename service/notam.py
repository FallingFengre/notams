import html
import math
import re
from datetime import datetime
from typing import List, Literal, Tuple

from shapely.geometry import Polygon

regex_notam_id = re.compile(r"[A-Z]\d{4}/\d{2}")
regex_linebreaks = re.compile(r"\r\n|\n|\\r\\n|\\n")
regex_created_source = re.compile(r"^CREATED:.+?SOURCE:.+?$", re.S | re.M)
regex_useless_log = re.compile(r"[0-9A-Z]+\sSEQUENCE\sCHECK.+?$", re.S)
regex_item_q = re.compile(r'^Q\) ([A-Z]*?)/([A-Z]*?)/([IVK\s]*?)/([NBOMK\s]*?)/([AEWK\s]*?)/(\d{3})/(\d{3})/?(.*?)$')
regex_item_q_coord = re.compile(r"^(\d{4})([NS])(\d{5})([EW])(\d*)$")

p_num = "|".join([
    r"\d+\s\d+\s\d+\.\d{0,3}",
    r"\d+\s\d+\s\d+",
    r"\d+\s\d+",
    r"\d+\.\d{0,3}",
    r"\d+",
])
p_sep = r"\s*?[\-,]?\s*?"
p_single_coord = "|".join([
    rf"\b(?:{p_num})\s?[NS](?:{p_sep})?(?:{p_num})\s?[EW]\b",
    rf"\b[NS]\s?(?:{p_num})(?:{p_sep})?[EW]\s?(?:{p_num})\b"
])
regex_single_coord = re.compile(p_single_coord, re.S)

p_area_sep = r"(?:\s*?(?:[\-;,]|TO|[IVX]+\.?)?\s*?)"
p_area = rf"(?:{p_single_coord})(?:{p_area_sep}(?:{p_single_coord}))*"
regex_area = re.compile(p_area, re.S)

regex_area_coords_1 = re.compile(rf"^([\d.]+)([NS])(?:{p_sep})([\d.]+)([WE])$")
regex_area_coords_2 = re.compile(rf"^([NS])([\d.]+)(?:{p_sep})([WE])([\d.]+)$")
regex_lat = re.compile(r"^(\d\d)\s?(\d\d)?\s?(\d+(?:\.\d+)?)?$")
regex_lon = re.compile(r"^(\d{3})\s?(\d\d)?\s?(\d+(?:\.\d+)?)?$")

# types
Point = Tuple[float, float]  # (lon, lat) 经纬度
Area = List[Point]  # 多边形区域顶点列表


# 判断地球上两个区域是否有交集 (重叠、相交、边角接)
def is_area_overlap(area_a: Area, area_b: Area) -> bool:
    """
    测试数据
    重叠项: 1-2,1-4,2-3,2-4,3-4,3-5,10-11,12-13
    边界相接项: 7-8, 8-9, 6-11
    1: 010803N1001451E-003845S1020633E-023404S1023605E-031624S1013260E-041907S0993845E-015214S0983844E-001310N0972258E-010313N0994346E-010803N1001451E
    2: 042212N0983622E-022937N1003956E-002737S0992446E-005327N0972130E-033347N0971604E-042212N0983622E
    3: 043336N0990116E-013631N1013315E-004925N0975107E-035345N0960552E-043336N0990116E
    4: 052423N0974524E-022937N1003956E-002737S0992446E-005327N0972130E-033135N0962056E-052423N0974524E
    5: 054645N0941023E-055030N0961839E-052825N0973540E-034601N0961740E-045028N0941058E-054645N0941023E
    6: 094909N0822708E-084126N0851626E-071501N0845829E-082048N0820440E-094909N0822708E
    7: 105726N0771933E-105446N0772957E-104614N0773644E-105443N0771832E-105726N0771933E
    8: 105847N0771518E-105726N0771933E-105443N0771832E-105708N0771322E-105847N0771518E
    9: 110541N0771515E-110212N0771915E-105219N0770747E-105708N0770522E-110541N0771515E
    10: 113500N0813000E-120500N0820000E-105000N0825500E-102000N0822500E-113500N0813000E
    11: 113960N0814960E-120960N0822500E-110000N0832500E-090712N0841200E-093138N0831055E-103500N0824500E-113960N0814960E
    12: 212023S1652060E-212901S1653454E-213805S1652758E-213126S1651222E-212023S1652060E
    13: 212023S1652060E-213548S1654512E-214319S1654020E-213126S1651222E-212023S1652060E
    """
    # 闭合
    if area_a[0] != area_a[-1]:
        area_a.append(area_a[0])
    if area_b[0] != area_b[-1]:
        area_b.append(area_b[0])
    if not area_a or not area_b or len(set(area_a)) < 3 or len(set(area_b)) < 3:
        return False  # 无效多边形

    # 将经度标准化到 [-180, 180)
    def norm_lon(lon: float) -> float:
        return (lon + 180) % 360 - 180

    norm_a = [(norm_lon(lon), lat) for lon, lat in area_a]
    norm_b = [(norm_lon(lon), lat) for lon, lat in area_b]

    try:
        base_a = Polygon(norm_a)
        base_b = Polygon(norm_b)
    except Exception:
        return False  # 无效多边形
    if base_a.is_empty or base_b.is_empty:
        return False
    if base_a.intersects(base_b):
        return True

    # 覆盖环绕情况
    alter_a_1 = Polygon([(lon + 360, lat) for lon, lat in norm_a])
    alter_a_2 = Polygon([(lon - 360, lat) for lon, lat in norm_a])
    return base_b.intersects(alter_a_1) or base_b.intersects(alter_a_2)


# 判断 area 与指定区域列表是否有交集
def is_area_legal(area: Area, banned_areas: List[Area]) -> bool:
    for banned in banned_areas:
        if is_area_overlap(area, banned):
            return False
    return True


# 坐标转换, (lon, lat) 转 DMS[NS]DMS[WE], 毫秒精度丢失
def point_to_str(point: Point) -> str:
    lon, lat = point
    lon_d = int(abs(lon))
    lon_m = int((abs(lon) - lon_d) * 60)
    lon_s = round((abs(lon) - lon_d - lon_m / 60) * 3600)
    ew = "E" if lon >= 0 else "W"
    lat_d = int(abs(lat))
    lat_m = int((abs(lat) - lat_d) * 60)
    lat_s = round((abs(lat) - lat_d - lat_m / 60) * 3600)
    ns = "N" if lat >= 0 else "S"
    return f"{lat_d:02d}{lat_m:02d}{lat_s:02d}{ns}{lon_d:03d}{lon_m:02d}{lon_s:02d}{ew}"


# 坐标转换, DMS 转 (lon, lat), 若不合法则返回 (math.nan, math.nan)
# 支持原始精度: DMS, DM, D, DMS.m
# 支持两种顺序: DMS[NS]DMS[WE], [NS]DMS[WE]DMS
def str_to_point(coord: str) -> Point:
    coord = re.sub(r"\s", "", coord)
    match_1 = regex_area_coords_1.match(coord)
    match_2 = regex_area_coords_2.match(coord)
    lat_str, ns, lon_str, ew = "", "", "", ""
    if not match_1 and not match_2:
        return math.nan, math.nan
    if match_1:
        lat_str, ns, lon_str, ew = [g.strip() for g in match_1.groups()]
    elif match_2:
        ns, lat_str, ew, lon_str = [g.strip() for g in match_2.groups()]
    # lat
    lat_d, lat_m, lat_s = regex_lat.match(lat_str).groups()
    lat_d = int(lat_d) if lat_d else 0
    lat_m = int(lat_m) if lat_m else 0
    lat_s = float(lat_s) if lat_s else 0.0
    lat = (lat_d + lat_m / 60.0 + lat_s / 3600.0) * (1 if ns == "N" else -1)
    # lon
    lon_d, lon_m, lon_s = regex_lon.match(lon_str).groups()
    lon_d = int(lon_d) if lon_d else 0
    lon_m = int(lon_m) if lon_m else 0
    lon_s = float(lon_s) if lon_s else 0.0
    lon = (lon_d + lon_m / 60.0 + lon_s / 3600.0) * (1 if ew == "E" else -1)
    return lon, lat


class NotamParser:
    """
    NOTAM 解析器, 支持解析 ICAO 格式 NOTAM, 不支持解析 Domestic 格式
    字段定义参考 CAAC 标准, FAA 标准作为补充参考
    处理一些非标准 NOTAM 时可能会打印报错。如：B0178/25, A3726/25, A3750/25, V4093

    DOC:
    CAAC 规范 MH/T 4030-2011: https://www.caac.gov.cn/XXGK/XXGK/BZGF/HYBZ/201708/t20170804_45905.html
    CAAC 规范 MH/T 4031-2011: https://www.caac.gov.cn/XXGK/XXGK/BZGF/HYBZ/201708/t20170804_45907.html
    https://github.com/slavak/PyNotam
    https://pilotinstitute.com/what-are-notams-notices-to-air-missions-explained/
    https://www.faa.gov/air_traffic/flight_info/aeronav/notams/media/ICAO_NOTAM_Format_Example.pdf
    https://www.faa.gov/air_traffic/flight_info/aeronav/notams/media/2021-09-07_ICAO_NOTAM_101_Presentation_for_Airport_Operators.pdf
    https://amc.namem.gov.mn/wp-content/uploads/2022/12/Doc%208400-AMD-33%20(2018).pdf
    https://www.faa.gov/air_traffic/publications/atpubs/notam_html/appendix_b.html
    """

    def __init__(self, raw: str):
        self.raw: str = raw.strip()

        # 字段列表
        self.header: str | None = None  # notam header
        self.item_q: str | None = None  # qualifier line
        self.item_a: str | None = None  # location
        self.item_b: str | None = None  # start of activity
        self.item_c: str | None = None  # end of activity
        self.item_d: str | None = None  # schedule
        self.item_e: str | None = None  # condition
        self.item_f: str | None = None  # lower limit
        self.item_g: str | None = None  # upper limit

        # header 项
        # notam id, 形如 B0667/21, id=series+number/year
        # 各地区有不同的 series 分配规则, FAA 标准和 CAAC 标准完全不同
        self.notam_id: str | None = None
        self.notam_type: Literal["N", "R", "C"] | None = None  # notam 类型: N=NEW, R=REPLACE, C=CANCEL
        self.notam_id_discard: str | None = None  # 被取消或被替换的 notam id, 仅在 type=R/C 时存在

        # Q 项
        self.fir: str | None = None  # FIR ICAO code
        self.code: str | None = None  # notam q-code
        self.code_subject: str | None = None  # notam subject, 取 code 的 2-3 位
        self.code_status: str | None = None  # notam status, 取 code 的 4-5 位
        # 飞行类型 (traffic), 签发目的 (purpose), 影响范围 (scope) 值定义参考 MH/T 4030-2011
        self.traffic: List[Literal["I", "V", "K"]] = []
        self.purpose: List[Literal["N", "B", "O", "M", "K"]] = []
        self.scope: List[Literal["A", "E", "W", "K"]] = []
        # 高度限制, 单位百英尺, 范围 [0, 999], 999 表示无上限, 0 表示地面
        self.lower_limit: int | None = None
        self.upper_limit: int | None = None
        # 高度限制, 单位米, 可能和 F/G 项中的数值有微小差别, math.inf 表示无上限, 0 表示地面
        self.lower_limit_meter: int | float | None = None
        self.upper_limit_meter: int | float | None = None
        # 点的坐标或区域的近似中心. 格式 (lon, lat)
        self.center_coord: Point | None = None
        # 半径, 单位海里
        self.radius: int | None = None

        # A 项, 受影响的地点 ICAO code 列表
        self.location: List[str] = []

        # B/C 项, 起止时间 (UTC), datetime.max 表示永久 (PERM)
        self.start_time: datetime | None = None
        self.end_time: datetime | None = None

        # D 项, 分段时间. 专有名词参考 MH/T 4030-2011
        self.schedule: str | None = None

        # E 项, 航行通告正文

        # F/G 项, 高度限制的文字描述, 专有名词参考 MH/T 4030-2011
        self.lower_limit_str: str | None = None
        self.upper_limit_str: str | None = None

        # 其他信息
        # 无使用意义的航警, 如: checklist, trigger, NOTAMC 等
        self.is_useless_notam: bool = False
        # 是否可能为航天活动相关航警, 可能包含其他情况, False 时表示基本不可能是航天活动
        self.is_probably_aerospace_notam: bool = False
        # 正文中包含的坐标数量
        self.coord_count: int = 0
        # 正文中分析出的坐标分组, 每个 area 都是坐标列表, 至少包含 1 个坐标 (lon, lat), 包含闭合或非闭合情况
        self.areas: List[Area] = []
        # 有面积的合法 area 列表, 已修复自交等问题
        self.sized_areas: List[Area] = []

    def parse(self):
        try:
            if not self._is_icao_format():
                raise Exception("not ICAO format")
            steps = [
                # pre process
                (self._cleanup, "cleanup failed"),
                (self._split, "split failed"),
                # parse
                (self._parse_header, "parse header failed"),
                (self._parse_item_q, "parse item Q failed"),
                (self._parse_item_a, "parse item A failed"),
                (self._parse_item_b_and_c, "parse item B/C failed"),
                (self._parse_item_d, "parse item D failed"),
                (self._parse_item_e, "parse item E failed"),
                (self._parse_item_f_and_g, "parse item F/G failed"),
                # post process
                (self._check_useless, "check useless failed"),
                (self._check_aerospace, "check aerospace failed"),
                (self._count_coords, "count coords failed"),
                (self._match_areas, "match areas failed"),
            ]
            for func, msg in steps:
                try:
                    func()
                except Exception as e:
                    raise Exception(msg) from e
        except Exception as e:
            print(f"Failed parsing NOTAM: {self.raw.replace("\n", " ")[:50]}... Error: {e}")
            pass

    def _is_icao_format(self) -> bool:
        """
        检测是否为 ICAO 格式 NOTAM
        """
        if self.raw.strip().startswith("!"):
            return False
        return True

    def _cleanup(self):
        """
        清理 NOTAM 原文, 去除多余内容
        """
        self.raw = self.raw.strip()
        if self.raw.startswith("(") and self.raw.endswith(")"):
            self.raw = self.raw[1:-1].strip()
        self.raw = html.unescape(self.raw)
        self.raw = regex_linebreaks.sub("\n", self.raw)
        self.raw = regex_created_source.sub("", self.raw)
        self.raw = regex_useless_log.sub("", self.raw)

    def _split(self):
        """
        按照 NOTAM 项拆分 NOTAM 原文
        """
        notam_parts = []
        tail = self.raw
        for char in "QABCDEFG":
            ans = re.split(rf"(?<=\s)(?={char}\))", tail, maxsplit=1, flags=re.S)
            if len(ans) == 2:
                head, tail = ans[0], ans[1]
            else:
                head, tail = None, ans[0]
            notam_parts.append(head)
        notam_parts.append(tail)
        notam_parts = [part.strip() for part in notam_parts if part and part.strip()]
        self.header = notam_parts[0]
        for part in notam_parts[1:]:
            setattr(self, f"item_{part[0].lower()}", part)

    def _parse_header(self):
        if not self.header:
            return
        self.notam_id = self.header.split("NOTAM")[0].strip()
        if "NOTAMN" in self.header:
            self.notam_type = "N"
        elif "NOTAMR" in self.header:
            self.notam_type = "R"
            self.notam_id_discard = self.header.split("NOTAMR")[1].strip()
        elif "NOTAMC" in self.header:
            self.notam_type = "C"
            self.notam_id_discard = self.header.split("NOTAMC")[1].strip()

    def _parse_item_q(self):
        if not self.item_q:
            return
        match = regex_item_q.match(self.item_q)
        if not match:
            raise ValueError("Invalid item Q format")
        self.fir = match.group(1) if match.group(1) else None
        self.code = match.group(2) if match.group(2) else None
        self.code_subject = self.code[1:3] if self.code else None
        self.code_status = self.code[3:5] if self.code else None
        self.traffic = [i for i in match.group(3) if i.strip()]
        self.purpose = [i for i in match.group(4) if i.strip()]
        self.scope = [i for i in match.group(5) if i.strip()]
        self.lower_limit = int(match.group(6))
        self.upper_limit = int(match.group(7))
        self.lower_limit_meter = math.floor(self.lower_limit * 0.3048) * 100
        self.upper_limit_meter = math.ceil(self.upper_limit * 0.3048) * 100
        if self.upper_limit == 999:
            self.upper_limit_meter = math.inf
        coord = match.group(8)
        if coord:
            match = regex_item_q_coord.match(coord.strip())
            if match:
                lat_str, ns, lon_str, ew, radius = match.groups()
                if radius:
                    self.radius = int(radius)
                lat = int(lat_str[:2]) + int(lat_str[2:]) / 60.0
                lon = int(lon_str[:3]) + int(lon_str[3:]) / 60.0
                if ns == "S":
                    lat = -lat
                if ew == "W":
                    lon = -lon
                self.center_coord = (lon, lat)

    def _parse_item_a(self):
        if not self.item_a:
            return
        s = self.item_a.lstrip("A)").split("PART")[0]
        self.location = [icao for icao in s.split(" ") if icao]

    def _parse_item_b_and_c(self):
        if self.item_b:
            start = self.item_b.lstrip("B)").rstrip("EST").strip()
            if start.isdigit():
                self.start_time = datetime.strptime(start, "%y%m%d%H%M")
        if self.item_c:
            if "PERM" in self.item_c:
                self.end_time = datetime.max
            else:
                end = self.item_c.lstrip("C)").rstrip("EST").strip()  # EST=estimated
                if end.isdigit():
                    self.end_time = datetime.strptime(end, "%y%m%d%H%M")

    def _parse_item_d(self):
        if self.item_d:
            self.schedule = self.item_d.lstrip("D)").strip()

    def _parse_item_e(self):
        if not self.item_e:
            return

    def _parse_item_f_and_g(self):
        if self.item_f:
            self.lower_limit_str = self.item_f.lstrip("F)").strip()
        if self.item_g:
            self.upper_limit_str = self.item_g.lstrip("G)").strip().split('\n')[0].strip()

    def _check_useless(self):
        """
        检测没必要分析的 NOTAM, 如 checklist, trigger 等
        这一方法必须在所有字段解析完成后调用
        """
        # trigger
        if self.item_e and "TRIGGER NOTAM" in self.item_e:
            self.is_useless_notam = True
        # checklist
        if self.item_e and "CHECKLIST" in self.item_e:
            self.is_useless_notam = True
        if self.code == "QKKKK":
            self.is_useless_notam = True
        # NOTAMC
        if self.notam_type == "C":
            self.is_useless_notam = True

    def _check_aerospace(self):
        """
        检测是否可能为航天活动相关的 NOTAM, 这一方法必须在 _check_useless 后调用
        参考 MH/T 4031-2011
        参考 International NOTAM (Q) Codes
        """
        if (
                self.is_useless_notam
                or self.code_subject is None
                or self.code_status is None
                or self.item_e is None
        ):
            return
        if self.code_status == "AM":
            return
        if self.end_time == datetime.max:
            self.is_useless_notam = True
        if not re.match(r"^A|^R|^W|^X", self.code_subject):
            return
        if self.code_subject in ["RM", "RO"]:
            return
        if re.match(r"^A[^DFUT]", self.code_subject):
            return
        if re.match(r"^W[^MRS]", self.code_subject):
            return
        words = [
            r"MIL",
            r"MOA",
            r"FORCES",
            r"DEFENCE",
            r"AIR FORCE",
            r"NAVAL",
            r"FRNG",
            r"COMBAT",
            r"BALLOONS?",
            r"ADS\-B",
            r"RADAR",
            r"VOLCANO",
            r"FIREWORK",
            r"MISSILES?",
        ]
        if re.search(rf"\b(?:{'|'.join(words)})\b", self.item_e):
            return
        # check if contains a coordinate
        if not regex_single_coord.search(self.item_e):
            return
        self.is_probably_aerospace_notam = True

    def _count_coords(self):
        """
        计算 NOTAM 正文中包含的坐标数量, 这一方法必须在 parse 结束后调用
        """
        if self.item_e:
            matches = regex_single_coord.findall(self.item_e)
            self.coord_count = len(matches)

    def _match_areas(self):
        """
        分析 NOTAM 正文中的 area 信息, 这一方法必须在 _count_coords 后调用
        当 coord_count = 0 时, 跳过
        当 coord_count = 1 时, 不进行分析, 可直接使用 center_coord 和 radius 作为 area 信息
        """

        # 极角排序, 对 is_valid=False 的 area 尝试修复自交问题, 可能造成形状影响
        def reorder_points(area: Area) -> Area:
            points = list(set(area))
            cx = sum(p[0] for p in points) / len(points)
            cy = sum(p[1] for p in points) / len(points)

            def angle(p):
                return math.atan2(p[1] - cy, p[0] - cx)

            ans = sorted(points, key=angle)
            if ans[0] != ans[-1]:
                ans.append(ans[0])
            return ans

        if self.coord_count < 2 or not self.item_e:
            return
        for match in regex_area.finditer(self.item_e):
            area_str = match.group(0)
            coords = []
            for coord_match in regex_single_coord.finditer(area_str):
                coord_str = coord_match.group(0).replace("\n", "")
                lon, lat = str_to_point(coord_str)
                if not math.isnan(lon) and not math.isnan(lat):
                    coords.append((lon, lat))
            # 简单坐标组
            if len(coords):
                self.areas.append(coords)
            # 有面积的坐标组
            if len(set(coords)) >= 3:
                area = coords.copy()
                # 闭合处理
                if area[0] != area[-1]:
                    area.append(area[0])
                # 几何修复
                try:
                    poly = Polygon(area)
                    if not poly.is_valid:
                        self.sized_areas.append(reorder_points(area))
                    else:
                        self.sized_areas.append(area)
                except Exception:
                    pass


raw = """
B1145/14 NOTAMN
Q) RPHI/QWMLW/IV/BO /W /000/666/1921N11902E
A)RPHI XXXX YYYY B) 1412201100 C) 1412221500 EST
D) DAILY 0100-0430 0600-0900
E)SPECIAL OPS (AEROSPACE FLT ACT) WILL BE CONDUCTED BY CHINA.
EST FALL AREA OF UNBURNED DEBRIS WI:
193600N 1183100E -
193300N1193400E -
19 06 00N 1193300E -
1909N 118 3000E -
19 36N 11831E
(78NM NORTHWEST OF LAOAG AP).
EST FALL AREA OF UNBURNED DEBRIS WI:
191100N1241800E      190500N 1251500E;
183900.00N 1251200E TO
N18 44 00 E124 16 00 -
N191100E124180000
(158NM NORTHEAST OF TUGUEGARAO AP).
F)SFC G) FT666
XXXXXXXXXXXX
"""


def test_parse_notam(raw: str):
    notam = NotamParser(raw)
    notam.parse()

    # 可能是航天活动相关 NOTAM 且有航警区域
    if notam.is_probably_aerospace_notam and len(notam.sized_areas) > 0:
        print(f"航警信息: {notam.notam_id} {notam.item_q}")
        print(f"起止时间: {notam.start_time} ~ {notam.end_time}")  # UTC 时间
        print(f"时间计划: {notam.schedule}")  # UTC 时间
        print(f"高度范围: {notam.lower_limit_meter} ~ {notam.upper_limit_meter} 米")

        legal_areas = [area for area in notam.sized_areas if is_area_legal(area, [])]

        print("航警区域 (lon, lat) 格式:")
        for area in legal_areas:
            print(area)
        print("航警区域 DMS 格式:")
        for area in legal_areas:
            print("-".join([point_to_str(p) for p in area]))

# test_parse_notam(raw)
