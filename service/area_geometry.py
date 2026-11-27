"""Parse published boundaries and manually pasted coordinates into map geometry."""

import html
import math
import re
import unicodedata


def _component(width):
    return rf'(?:\d{{1,{width}}}[-°]\s*\d{{1,2}}\.\d+|\d{{{width}}}\s*\d{{2}}(?:\s*\d{{2}}(?:\.\d+)?)?)'


_LAT, _LON = _component(2), _component(3)
_SEPARATOR = r'[\s,/]*'
_COORDINATE = re.compile(
    rf'(?<!\d)(?:([NS])\s*({_LAT}){_SEPARATOR}([EW])\s*({_LON})'
    rf'|({_LAT})\s*([NS]){_SEPARATOR}({_LON})\s*([EW]))(?!\d|\.\d)'
)
_POINT = re.compile(r'@(\d+)@')
_CENTRE = r'CENT(?:ER|RE)(?:ED|D)?\s*(?:(?:AT|ON)\s*)?(?:POSITION\s*)?'
_RADIUS = r'(?P<radius>\d+(?:\.\d+)?)\s*(?P<unit>NM|KM|M|海里|公里|千米|米)(?![A-Z])'
_CIRCLES = (
    re.compile(rf'{_CENTRE}@(?P<point>\d+)@[\s,]*(?:WITH\s+)?(?:A\s+)?RADIUS\s*(?:OF\s*)?{_RADIUS}'),
    re.compile(rf'{_RADIUS}\s+RADIUS\s+(?:OF\s+)?(?:{_CENTRE})?@(?P<point>\d+)@'),
    re.compile(rf'@(?P<point>\d+)@\s*(?:为|作)中心[\s,]*{_RADIUS}\s*(?:为|作)半径\s*(?:的)?圆'),
)
_UNITS = {'NM': 1852, 'KM': 1000, 'M': 1, '海里': 1852, '公里': 1000, '千米': 1000, '米': 1}
_EARTH_RADIUS_METERS = 6_371_008.8
_AREA_LABEL = re.compile(r'\b(?:AREA|ZONE)\s+[A-Z0-9]+\s*[:.)]|(?:区域|落区)\s*[一二三四五六七八九十\d]+\s*[:、.]')
_CURVED_BOUNDARY = re.compile(r'\b(?:ARC|SECTOR)\b|PARTS? OF A CIRCLE')

_DIRECTION = r'(?P<direction>COUNTER[ -]?CLOCKWISE|ANTI[ -]?CLOCKWISE|CLOCKWISE)'
_SECTOR = re.compile(
    rf'(?:SECTOR|PARTS? OF A CIRCLE)[^@]*?{_CENTRE}@(?P<center>\d+)@'
    rf'[^@]*?RADIUS\s*(?:OF\s*)?{_RADIUS}\s+(?:FROM|FM)\s+(?P<start>\d+(?:\.\d+)?)'
    rf'\s*(?:DEG(?:REES?)?|°)?\s+TO\s+(?P<end>\d+(?:\.\d+)?)\s*(?:DEG(?:REES?)?|°)\s*{_DIRECTION}'
)
_ARC = re.compile(
    rf'{_DIRECTION}\s+(?:(?:VIA|ON)\s+)?(?:A\s+)?{_RADIUS}\s+ARC\s+'
    rf'{_CENTRE}@(?P<center>\d+)@\s*[,;]?\s*TO\s+@(?P<end>\d+)@'
)


def _degrees(token, width):
    token = ''.join(token.split())
    if '-' in token or '°' in token:
        degree, minutes = re.split('[-°]', token)
        seconds = 0
    else:
        degree, minutes = token[:width], token[width:width + 2]
        seconds = float(token[width + 2:] or 0)
    degree, minutes = int(degree), float(minutes)
    limit = 90 if width == 2 else 180
    if minutes >= 60 or seconds >= 60 or degree > limit or (degree == limit and (minutes or seconds)):
        raise ValueError('Invalid coordinate')
    return degree + minutes / 60 + seconds / 3600


def _compact(point, minutes_only=False):
    parts = []
    for value, width, positive, negative in zip(point, (2, 3), 'NE', 'SW'):
        degree, remainder = divmod(round(abs(value) * 3600), 3600)
        minute, second = divmod(remainder, 60)
        parts.append(f'{positive if value >= 0 else negative}{degree:0{width}d}{minute:02d}')
        if not minutes_only:
            parts.append(f'{second:02d}')
    return ''.join(parts)


def _destination(center, distance, bearing):
    lat, lon = map(math.radians, center)
    angle = distance / _EARTH_RADIUS_METERS
    bearing = math.radians(bearing)
    new_lat = math.asin(math.sin(lat) * math.cos(angle) + math.cos(lat) * math.sin(angle) * math.cos(bearing))
    new_lon = lon + math.atan2(math.sin(bearing) * math.sin(angle) * math.cos(lat),
                               math.cos(angle) - math.sin(lat) * math.sin(new_lat))
    return math.degrees(new_lat), (math.degrees(new_lon) + 180) % 360 - 180


def _bearing(center, point):
    lat, lon = map(math.radians, center)
    target_lat, target_lon = map(math.radians, point)
    delta = target_lon - lon
    return math.degrees(math.atan2(math.sin(delta) * math.cos(target_lat),
                                   math.cos(lat) * math.sin(target_lat) - math.sin(lat) * math.cos(target_lat) * math.cos(delta))) % 360


def _arc_vertices(center, radius, start, end, direction):
    sign = 1 if direction == 'CLOCKWISE' else -1
    sweep = (sign * (end - start)) % 360
    steps = max(1, math.ceil(sweep / 5))
    return [_destination(center, radius, start + sign * sweep * i / steps) for i in range(steps + 1)]


def _curved_area(section, points):
    sector = _SECTOR.search(section)
    if sector and len(_POINT.findall(section)) == 1:
        center = points[int(sector['center'])]
        radius = float(sector['radius']) * _UNITS[sector['unit']]
        start, end = float(sector['start']), float(sector['end'])
        if not (0 < radius < math.pi * _EARTH_RADIUS_METERS and 0 <= start <= 360 and 0 <= end <= 360 and start % 360 != end % 360):
            return None
        vertices = [center, *_arc_vertices(center, radius, start, end, sector['direction'])]
        return {'type': 'sector', 'center': center, 'radiusMeters': radius, 'startBearing': start,
                'endBearing': end, 'direction': sector['direction'], 'points': vertices,
                'vertices': [center, vertices[1], vertices[-1]],
                'coordinates': '-'.join(map(_compact, vertices))}

    arc = _ARC.search(section)
    if arc and len(re.findall(r'\bARC\b', section)) == 1:
        before = [points[int(i)] for i in _POINT.findall(section[:arc.start()])]
        after = [points[int(i)] for i in _POINT.findall(section[arc.end():])]
        center, end = points[int(arc['center'])], points[int(arc['end'])]
        radius = float(arc['radius']) * _UNITS[arc['unit']]
        if not before or not 0 < radius < math.pi * _EARTH_RADIUS_METERS or before[-1] == end:
            return None
        curve = _arc_vertices(center, radius, _bearing(center, before[-1]), _bearing(center, end), arc['direction'])
        vertices = [*before, *curve[1:-1], end, *after]
        if len(set(vertices)) >= 3:
            return {'type': 'arcPath', 'center': center, 'radiusMeters': radius, 'direction': arc['direction'],
                    'points': vertices, 'vertices': [*before, end, *after],
                    'coordinates': '-'.join(map(_compact, vertices))}
    return None


def _polygon_areas(text, points, labels):
    groups = [[]]
    end = 0
    for token in _POINT.finditer(text):
        gap = re.sub(r'\s+', '', text[end:token.start()])
        if len(gap) > 20 and groups[-1]:
            groups.append([])
        groups[-1].append(int(token[1]))
        end = token.end()
    for group in groups:
        vertices = [points[index] for index in group]
        if len(set(vertices)) >= 3:
            yield {'type': 'polygon', 'points': vertices,
                   'coordinates': '-'.join(labels[index] for index in group)}


def parse_areas(text):
    """Return areas in the order described, preserving the published vertex order."""
    text = unicodedata.normalize('NFKC', html.unescape(text)).upper()
    text = re.sub(r'\{[^}]*\}|%[^%]*%|@', ' ', text)
    body = re.search(r'(?<![A-Z0-9])E\)\s*(.*?)(?=\s+[FG]\)|\s+CREATED:|\Z)', text, re.S)
    if body:
        text = body[1]
    elif re.search(r'\bQ\)', text):
        return []

    points, labels = [], []

    def tokenize(match):
        ns, lat, ew, lon = match.groups()[:4]
        if ns is None:
            lat, ns, lon, ew = match.groups()[4:]
        try:
            point = (_degrees(lat, 2) * (-1 if ns == 'S' else 1),
                     _degrees(lon, 3) * (-1 if ew == 'W' else 1))
        except ValueError:
            return ' INVALID_COORDINATE '
        minutes_only = len(''.join(lat.split())) == 4 and len(''.join(lon.split())) == 5
        points.append(point)
        labels.append(_compact(point, minutes_only))
        return f'@{len(points) - 1}@'

    areas = []
    for section in _AREA_LABEL.split(_COORDINATE.sub(tokenize, text)):
        if 'INVALID_COORDINATE' in section:
            continue
        if _CURVED_BOUNDARY.search(section):
            curved_area = _curved_area(section, points)
            if curved_area:
                areas.append(curved_area)
            continue
        circles = sorted((match for pattern in _CIRCLES for match in pattern.finditer(section)),
                         key=lambda match: match.start())
        end = 0
        for match in circles:
            if match.start() < end:
                continue
            areas.extend(_polygon_areas(section[end:match.start()], points, labels))
            center = points[int(match['point'])]
            radius = float(match['radius']) * _UNITS[match['unit']]
            if 0 < radius < math.pi * _EARTH_RADIUS_METERS:
                # Approximate the boundary for consumers of the legacy polygon field.
                boundary = [_compact(_destination(center, radius, angle)) for angle in range(0, 360, 5)]
                areas.append({'type': 'circle', 'center': center, 'radiusMeters': radius,
                              'coordinates': '-'.join(boundary)})
            end = match.end()
        areas.extend(_polygon_areas(section[end:], points, labels))
    return areas
