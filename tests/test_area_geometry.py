"""Regression checks for shared NOTAM geometry and altitude filtering."""

import unittest
from unittest.mock import patch

import config
from service.fetch.FNS_NOTAM_SEARCH import parse_current_notams

from service.area_geometry import parse_areas
from service.fetch.aviation_parser import has_unlimited_ceiling, parse_aviation_records
from service.server import app


class TestAreaGeometry(unittest.TestCase):
    def test_circle_uses_published_center_and_radius(self):
        areas = parse_areas(
            "E) DANGER AREA WITHIN A CIRCLE CENTERED AT N210800E1124100 "
            "WITH RADIUS OF 20KM."
        )
        self.assertEqual(len(areas), 1)
        self.assertEqual(areas[0]["type"], "circle")
        self.assertAlmostEqual(areas[0]["center"][0], 21 + 8 / 60)
        self.assertEqual(areas[0]["radiusMeters"], 20_000)

    def test_manual_dms_input_and_separate_areas(self):
        areas = parse_areas(
            "AREA A: N390000E1000000-N391000E1000000-N391000E1010000 "
            "AREA B: N400000E1000000-N401000E1000000-N401000E1010000"
        )
        self.assertEqual(len(areas), 2)
        self.assertTrue(all(area["type"] == "polygon" for area in areas))
        self.assertEqual(areas[0]["points"][0], (39, 100))

    def test_unlimited_altitude_is_required_and_q_line_is_supported(self):
        self.assertTrue(has_unlimited_ceiling("G) SFC-UNL"))
        self.assertTrue(has_unlimited_ceiling("Q) ZGZU/QWMLW/IV/BO/W/000/999/2108N11240E011"))
        self.assertFalse(has_unlimited_ceiling("Q) ZGZU/QWMLW/IV/BO/W/000/200/2108N11240E011"))

    def test_parser_filters_finite_height_notams(self):
        message = (
            "A0001/26 NOTAMN\nQ) ZGZU/QWMLW/IV/BO/W/000/200/2108N11240E011\n"
            "E) CHINA ROCKET LAUNCH AREA N390000E1000000-N391000E1000000-"
            "N391000E1010000\nG) SFC-UNL"
        )
        records = list(parse_aviation_records({"ZGZU": [{"Message": message}]}))
        self.assertEqual(records, [])

    def test_decimal_seconds_and_legacy_manual_formats(self):
        for text in (
            '120000.50N0100000.30E - 121000.25N0100000.30E - 121000.25N0101000.30E',
            '19-14.25N/112-28.12E、19-15.43N/112-56.63E、18-21.26N/112-59.02E',
            'N1200E01000-N1210E01000-N1210E01010',
        ):
            with self.subTest(text=text):
                self.assertEqual(len(parse_areas(text)[0]['points']), 3)
        self.assertAlmostEqual(parse_areas(text)[0]['points'][0][0], 12)
        self.assertEqual(parse_areas('Q) AAAA/QWMLW/IV/BO/W/000/999/1200N01000E010'), [])

    def test_explicit_sector_and_arc(self):
        sector, = parse_areas('PART OF A CIRCLE CENTERED AT N100000E0100000 RADIUS OF 10KM '
                              'FROM 20 DEGREES TO 80 DEGREES CLOCKWISE')
        self.assertEqual((sector['type'], sector['startBearing'], sector['endBearing']), ('sector', 20, 80))
        arc, = parse_areas('N000000E0000000-N001000E0000000 CLOCKWISE VIA A 10NM ARC '
                           'CENTERED ON N000000E0000000 TO N000000E0001000')
        self.assertEqual(arc['type'], 'arcPath')
        self.assertGreater(len(arc['points']), 3)

    def test_three_routes_share_geometry_but_manual_skips_automatic_filter(self):
        raw = ('Q) ZGZU/QWMLW/IV/BO/W/120/999/0000N00000E010\n'
               'E) CHINA ROCKET LAUNCH WITHIN 2.5NM RADIUS OF N120000E0100000')
        notices = {'ZGZU': [{'Number': 'A0001/26', 'transactionID': '101', 'Message': raw,
                             'startDate': '01/01/2026 0000', 'endDate': '01/01/2026 1200'}]}
        data = parse_current_notams(notices, 'DAIP')
        with (patch.multiple(config, FETCH_DINS=False, FETCH_FNS=False, FETCH_DAIP=True,
                             FETCH_MSI=False, FETCH_MSA=False, EXCLUDE_RECTS=[]),
              patch('service.server.daip_current_notams', return_value=data),
              patch('service.fetch.FNS_NOTAM_ARCHIVE_SEARCH.fetch', return_value=notices)):
            client = app.test_client()
            current = client.get('/fetch').get_json()
            archive = client.post('/fetch_archive', json={'date': '2026-01-01', 'region': 'ZGZU'}).get_json()
            manual = client.post('/parse_areas', json={'text': raw.replace('120/999', '120/200')}).get_json()
        self.assertEqual(current['GEOMETRY'], manual['areas'])
        self.assertEqual(archive['GEOMETRY'], manual['areas'])
        self.assertEqual(current['TIME'], ['01 JAN 00:00 2026 UNTIL 01 JAN 12:00 2026'])
        self.assertEqual(current['CODE'], archive['CODE'])
        self.assertEqual(current['GEOMETRY'][0]['radiusMeters'], 4630)

    def test_manual_parse_endpoint_returns_circle_geometry(self):
        response = app.test_client().post(
            "/parse_areas",
            json={"text": "CIRCLE CENTERED AT N210800E1124100 WITH RADIUS OF 20KM"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["areas"][0]["type"], "circle")


if __name__ == "__main__":
    unittest.main()
