"""Common filtering and area extraction for current and archived aviation NOTAMs."""

import re

from service.area_geometry import parse_areas


def is_relevant(message):
    text = (message or '').upper()
    return (('A TEMPORARY' in text and '-' in text)
            or 'AEROSPACE' in text or 'AER0SPACE' in text
            or all(word in text for word in ('CHINA', 'AERIAL', 'DNG ZONE'))
            or all(word in text for word in ('CHINA', 'ROCKET', 'LAUNCH')))


def has_unlimited_ceiling(message):
    # A finite upper limit in either field rules out a conflicting notice.
    qualifier = re.search(r'\bQ\)\s*[^\r\n]+', message, re.I)
    fields = qualifier[0].split('/') if qualifier else []
    q_upper = fields[6].strip() if len(fields) >= 7 else ''
    if re.fullmatch(r'\d{3}', q_upper) and q_upper != '999':
        return False
    upper = re.search(r'(?<![A-Z0-9])G\)\s*([^\r\n]+)', message, re.I)
    if upper:
        return bool(re.match(r'(?:SFC\s*[-–]\s*)?(?:UNL|UNLIMITED)\b', upper[1].strip(), re.I))
    return q_upper == '999'


def parse_aviation_records(results):
    """Expand each accepted notice into one record per drawable area."""
    for notices in results.values():
        for notice in notices:
            message = notice.get('Message') or ''
            if not is_relevant(message) or not has_unlimited_ceiling(message):
                continue
            areas = parse_areas(message)
            if not areas:
                continue
            time_value = _format_time(notice.get('startDate'), notice.get('endDate'))
            code = notice.get('Number', 'UNKNOWN')
            transaction = notice.get('transactionID', 'UNKNOWN')
            for index, area in enumerate(areas, 1):
                area_code = f'{code}_AREA{index}' if len(areas) > 1 else code
                yield {
                    'CODE': area_code, 'COORDINATES': area['coordinates'], 'GEOMETRY': area,
                    'TIME': time_value, 'TRANSID': transaction, 'RAWMESSAGE': message,
                }


def _format_time(start_date, end_date):
    if not start_date or not end_date:
        return '00 JAN 00:00 0000 UNTIL 00 JAN 00:00 0000'
    if end_date == 'PERM':
        end_date = '12/31/2099 2359'

    months = ('JAN', 'FEB', 'MAR', 'APR', 'MAY', 'JUN', 'JUL', 'AUG', 'SEP', 'OCT', 'NOV', 'DEC')

    def convert(date):
        if len(date) < 14:
            return '00 JAN 00:00 0000'
        month, day, year_time = date.split('/')
        year, clock = year_time.split(' ')
        return f'{day} {months[int(month) - 1]} {clock[:2]}:{clock[2:]} {year}'

    return f'{convert(start_date)} UNTIL {convert(end_date)}'


def records_to_columns(records, source):
    result = {key: [] for key in ('CODE', 'COORDINATES', 'GEOMETRY', 'TIME', 'TRANSID', 'RAWMESSAGE', 'SOURCE')}
    for record in records:
        for key, value in record.items():
            result[key].append(value)
        result['SOURCE'].append(source)
    return result
