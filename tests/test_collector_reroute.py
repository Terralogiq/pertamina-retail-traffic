"""Pure reroute check: distance more than 10% longer or shorter, or geometry outside a 30 m buffer."""
import unittest

from collector import reroute
from collector.traffic import decode_polyline

# Site 1 expected approach: (-5.41371, 105.32234) -> (-5.4101864, 105.3198296)
EXPECTED_LINE = [(-5.41371, 105.32234), (-5.4101864, 105.3198296)]


class RerouteTest(unittest.TestCase):
    def test_no_reroute_when_exact(self):
        self.assertFalse(reroute.is_rerouted(500, 500, EXPECTED_LINE, EXPECTED_LINE))

    def test_no_reroute_at_10_percent(self):
        self.assertFalse(reroute.is_rerouted(500, 550, EXPECTED_LINE, EXPECTED_LINE))

    def test_reroute_over_10_percent(self):
        self.assertTrue(reroute.is_rerouted(500, 551, EXPECTED_LINE, EXPECTED_LINE))

    def test_no_reroute_at_minus_10_percent(self):
        self.assertFalse(reroute.is_rerouted(500, 450, EXPECTED_LINE, EXPECTED_LINE))

    def test_reroute_when_shorter_than_10_percent(self):
        self.assertTrue(reroute.is_rerouted(500, 449, EXPECTED_LINE, EXPECTED_LINE))

    def test_no_reroute_within_10_percent_either_way(self):
        for actual in (460, 499, 501, 540):
            self.assertFalse(reroute.is_rerouted(500, actual, EXPECTED_LINE, EXPECTED_LINE))

    def test_reroute_when_polyline_leaves_buffer(self):
        actual = [(-5.41371, 105.32234), (-5.41400, 105.32300)]  # >30 m off the expected line
        self.assertTrue(reroute.is_rerouted(500, 500, actual, EXPECTED_LINE))

    def test_no_reroute_when_polyline_stays_inside_buffer(self):
        # A point 20 m perpendicular from the midpoint of the expected line.
        actual = [(-5.41371, 105.32234), (-5.411948, 105.321085)]
        self.assertFalse(reroute.is_rerouted(500, 500, actual, EXPECTED_LINE))

    def test_missing_values_never_reroute(self):
        self.assertFalse(reroute.is_rerouted(None, 600, EXPECTED_LINE, EXPECTED_LINE))
        self.assertFalse(reroute.is_rerouted(500, None, EXPECTED_LINE, EXPECTED_LINE))
        self.assertFalse(reroute.is_rerouted(500, 500, None, EXPECTED_LINE))
        self.assertFalse(reroute.is_rerouted(500, 500, EXPECTED_LINE, None))

    def test_decode_from_wkt(self):
        """The expected polyline arrives as a WKT LINESTRING; decode it via the collector helper."""
        wkt = "LINESTRING(105.32234 -5.41371, 105.3198296 -5.4101864)"
        pts = [(float(lat), float(lng)) for lng, lat in (
            coord.split() for coord in wkt.replace("LINESTRING(", "").replace(")", "").split(", ")
        )]
        self.assertEqual(pts, EXPECTED_LINE)


if __name__ == "__main__":
    unittest.main()
