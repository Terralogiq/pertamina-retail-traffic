"""GET /api/sites and /api/config with BigQuery mocked."""
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

from dashboard.api import cache  # noqa: E402
from dashboard.api.main import app  # noqa: E402

LINE = {"type": "LineString", "coordinates": [[106.81, -6.29], [106.82, -6.29]]}


def row(site_id, leg, **kw):
    base = {"site_id": site_id, "name": f"SPBU {site_id}", "place_id": "ChIJ" + site_id,
            "road_name": "Jl. X", "city": "Makassar", "timezone": "Asia/Makassar",
            "lat": -5.14, "lng": 119.49, "selected_route_id": f"r-{site_id}-{leg}",
            "display_name": f"{site_id} {leg}", "side": "spbu_side", "leg": leg,
            "leg_index": 0 if leg == "approach" else 1, "expected_distance_m": 500,
            "expected_polyline": json.dumps(LINE)}
    return {**base, **kw}


class SitesTest(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ, {"DASHBOARD_PASSWORD": "pw", "MAPS_BROWSER_KEY": "browser-key"})
        patcher.start()
        self.addCleanup(patcher.stop)
        cache.default.clear()
        self.addCleanup(cache.default.clear)
        self.client = TestClient(app, base_url="https://testserver")
        self.client.post("/api/login", json={"password": "pw"})

    def test_sites_with_timezone_and_geojson_legs(self):
        rows = [row("74.902.22", "approach"), row("74.902.22", "departure"),
                row("34.121.03", "approach", timezone="Asia/Jakarta")]
        with mock.patch("dashboard.api.bq.query", return_value=rows) as q:
            res = self.client.get("/api/sites")
        self.assertEqual(res.status_code, 200)
        sql = q.call_args.args[0]
        self.assertIn("ST_ASGEOJSON(r.expected_polyline)", sql)
        self.assertIn("s.timezone", sql)
        sites = res.json()
        self.assertEqual([s["site_id"] for s in sites], ["74.902.22", "34.121.03"])
        makassar = sites[0]
        self.assertEqual(makassar["timezone"], "Asia/Makassar")
        self.assertEqual(makassar["location"], {"lat": -5.14, "lng": 119.49})
        self.assertEqual([leg["leg"] for leg in makassar["legs"]], ["approach", "departure"])
        self.assertEqual(makassar["legs"][0]["expected_polyline"], LINE)

    def test_site_without_active_legs_has_empty_legs(self):
        no_leg = dict.fromkeys(("selected_route_id", "display_name", "side", "leg", "leg_index",
                                "expected_distance_m", "expected_polyline"))
        bare = {**row("1", "approach"), **no_leg}
        with mock.patch("dashboard.api.bq.query", return_value=[bare]):
            sites = self.client.get("/api/sites").json()
        self.assertEqual(sites[0]["legs"], [])

    def test_sites_are_cached(self):
        with mock.patch("dashboard.api.bq.query", return_value=[row("1", "approach")]) as q:
            self.client.get("/api/sites")
            self.client.get("/api/sites")
        self.assertEqual(q.call_count, 1)

    def test_sites_need_login(self):
        self.client.cookies.clear()
        with mock.patch("dashboard.api.bq.query") as q:
            self.assertEqual(self.client.get("/api/sites").status_code, 401)
        q.assert_not_called()

    def test_traffic_latest_stub_is_empty(self):
        self.assertEqual(self.client.get("/api/traffic/latest").json(), [])

    def test_config_serves_browser_key(self):
        self.assertEqual(self.client.get("/api/config").json(), {"maps_browser_key": "browser-key"})


if __name__ == "__main__":
    unittest.main()
