"""Offline unit tests for NOTAM parsing, geometry overlap, and deduplication."""

import io
import unittest
from contextlib import redirect_stdout

from shapely.geometry import Polygon

from service.notam import NotamParser, is_area_overlap, raw as sample_notam_raw, str_to_point
from service.server import classify_data, extract_altitude, parse_point, should_deduplicate


class TestNotamParserAndGeometry(unittest.TestCase):
    """Verify ICAO NOTAM parsing, invalid-format guards, and Shapely geometry logic."""

    def test_notam_parser_multi_area_icao(self):
        parser = NotamParser(sample_notam_raw)
        parser.parse()

        self.assertEqual(parser.notam_id, "B1145/14")
        self.assertEqual(parser.notam_type, "N")
        self.assertEqual(parser.location, ["RPHI", "XXXX", "YYYY"])
        self.assertEqual(parser.lower_limit, 0)
        self.assertEqual(parser.upper_limit, 666)
        self.assertTrue(parser.is_probably_aerospace_notam)
        self.assertEqual(len(parser.sized_areas), 2)

    def test_notam_parser_rejects_non_icao_fdc(self):
        parser = NotamParser("!FDC 4/1234 ZBW PART 1 OF 2")
        buf = io.StringIO()
        with redirect_stdout(buf):
            parser.parse()

        self.assertIsNone(parser.notam_id)
        self.assertEqual(parser.areas, [])
        self.assertIn("not ICAO format", buf.getvalue())

    def test_self_intersection_repair_and_antimeridian_overlap(self):
        # Bow-tie (self-intersecting) coordinates in item E should be repaired into a valid polygon.
        bowtie_notam = (
            "A9999/25 NOTAMN\n"
            "Q) RPHI/QWMLW/IV/BO /W /000/999/0005N00005E\n"
            "A) RPHI B) 2512201100 C) 2512201300\n"
            "E) SPECIAL OPS WI: 000000N0000000E-001000N0001000E-"
            "000000N0001000E-001000N0000000E\n"
            "F) SFC G) UNL"
        )
        parser = NotamParser(bowtie_notam)
        parser.parse()
        self.assertEqual(len(parser.sized_areas), 1)
        repaired = Polygon(parser.sized_areas[0])
        self.assertTrue(repaired.is_valid)
        self.assertGreater(repaired.area, 0)

        # Coordinates formatted with both [NS]...[EW] and ...[NS]...[EW] should decode cleanly.
        lon, lat = str_to_point("S1230W04515")
        self.assertAlmostEqual(lat, -12.5)
        self.assertAlmostEqual(lon, -45.25)

        # Antimeridian wraparound overlap and disjoint separation checks.
        poly_east = [(179.0, 10.0), (179.8, 10.0), (179.8, 12.0), (179.0, 12.0)]
        poly_wrapped = [(-180.5, 10.5), (-180.2, 10.5), (-180.2, 11.5), (-180.5, 11.5)]
        poly_disjoint = [(100.0, 20.0), (101.0, 20.0), (101.0, 21.0), (100.0, 21.0)]

        self.assertTrue(is_area_overlap(poly_east.copy(), poly_wrapped.copy()))
        self.assertFalse(is_area_overlap(poly_east.copy(), poly_disjoint.copy()))


class TestServerAggregationHelpers(unittest.TestCase):
    """Verify point decoding, altitude conversion, deduplication, and window clustering."""

    def test_server_parse_point_and_altitude(self):
        lat1, lon1 = parse_point("N392852E0955438")
        self.assertAlmostEqual(lat1, 39 + 28 / 60 + 52 / 3600)
        self.assertAlmostEqual(lon1, 95 + 54 / 60 + 38 / 3600)

        lat2, lon2 = parse_point("S1230W04515")
        self.assertAlmostEqual(lat2, -12.5)
        self.assertAlmostEqual(lon2, -45.25)

        self.assertEqual(
            extract_altitude(["Q) RPHI/QWMLW/IV/BO /W /000/999/1921N11902E"]),
            ["0 ~ INF 米"],
        )

    def test_server_deduplicate_and_time_classify(self):
        t_win = "20 DEC 11:00 2025 UNTIL 20 DEC 13:00 2025"
        c_outer = "N390000E0960000-N393000E0960000-N393000E0963000-N390000E0963000-N390000E0960000"
        c_inner = "N390200E0960200-N392800E0960200-N392800E0962800-N390200E0962800-N390200E0960200"
        c_far = "N200000E1100000-N203000E1100000-N203000E1103000-N200000E1103000-N200000E1100000"

        self.assertTrue(
            should_deduplicate(
                (c_outer, t_win, "FNS_NOTAM", "A1001/25"),
                (c_inner, t_win, "MSA_NAV", "MSA001"),
            )
        )
        self.assertFalse(
            should_deduplicate(
                (c_outer, t_win, "FNS_NOTAM", "A1001/25"),
                (c_far, t_win, "MSA_NAV", "MSA002"),
            )
        )

        clustered = classify_data({
            "CODE": ["A1", "A2", "B1"],
            "TIME": [
                t_win,
                "20 DEC 11:10 2025 UNTIL 20 DEC 13:05 2025",
                "25 DEC 02:00 2025 UNTIL 25 DEC 04:00 2025",
            ],
        })
        self.assertEqual(sorted(clustered.values(), key=len, reverse=True), [["A1", "A2"], ["B1"]])


if __name__ == "__main__":
    unittest.main()
