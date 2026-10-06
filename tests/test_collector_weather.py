"""Unit tests for collector/weather.py (pure functions only).

No network, no key, no google-cloud-bigquery. The fixture is a real
`currentConditions:lookup` response (site 24.351.97 Front, 2026-10-06), trimmed of nothing.
"""
import json
import os
import sys
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "collector"))

import slots  # noqa: E402
import weather  # noqa: E402

FETCHED = datetime(2026, 10, 7, 12, 29, 58, tzinfo=timezone.utc)
SLOT = slots.slot_time(FETCHED)
REQUEST = {"latitude": -5.4101864, "longitude": 105.3198296, "unitsSystem": "METRIC"}

FIXTURE = {
    "timeZone": {"id": "Asia/Jakarta", "version": ""},
    "weatherCondition": {
        "iconBaseUri": "https://maps.gstatic.com/weather/v1/mostly_cloudy_night",
        "description": {"text": "Mostly cloudy", "languageCode": "en"},
        "type": "MOSTLY_CLOUDY"},
    "temperature": {"unit": "CELSIUS", "degrees": 26.4},
    "feelsLikeTemperature": {"unit": "CELSIUS", "degrees": 29.4},
    "dewPoint": {"unit": "CELSIUS", "degrees": 23},
    "precipitation": {
        "probability": {"type": "RAIN", "percent": 27},
        "snowQpf": {"unit": "MILLIMETERS", "quantity": 0},
        "qpf": {"unit": "MILLIMETERS", "quantity": 0}},
    "airPressure": {"meanSeaLevelMillibars": 1014.56},
    "wind": {
        "direction": {"cardinal": "SOUTH", "degrees": 186},
        "speed": {"unit": "KILOMETERS_PER_HOUR", "value": 2},
        "gust": {"unit": "KILOMETERS_PER_HOUR", "value": 5}},
    "visibility": {"unit": "KILOMETERS", "distance": 16},
    "currentConditionsHistory": {"qpf": {"unit": "MILLIMETERS", "quantity": 1.26}},
    "currentTime": "2026-10-06T17:17:02.467732800Z",
    "isDaytime": False,
    "relativeHumidity": 81,
    "uvIndex": 0,
    "thunderstormProbability": 37,
    "cloudCover": 83,
}


def row(resp=None):
    return weather.weather_row("24.351.97", SLOT, resp if resp is not None else FIXTURE, FETCHED, REQUEST)


class Mapping(unittest.TestCase):
    def test_core_columns(self):
        r = row()
        self.assertEqual(r["site_id"], "24.351.97")
        self.assertEqual(r["slot_time"], "2026-10-07T12:30:00.000000Z")
        self.assertEqual(r["fetched_at"], "2026-10-07T12:29:58.000000Z")
        self.assertEqual(r["temperature_c"], 26.4)
        self.assertEqual(r["dewpoint_c"], 23.0)
        self.assertEqual(r["relative_humidity"], 81.0)
        self.assertEqual(r["precipitation_mm"], 0.0)
        self.assertIs(r["rain_flag"], False)
        self.assertEqual(r["wind_speed_kmh"], 2.0)
        self.assertEqual(r["wind_direction_deg"], 186.0)
        self.assertEqual(r["msl_pressure_hpa"], 1014.56)
        self.assertEqual(r["source"], "google_weather")
        self.assertIsNone(r["forecast_init_time"])
        self.assertIsNone(r["ensemble_stat"])

    def test_demo_columns(self):
        r = row()
        self.assertEqual(r["demo_condition_type"], "MOSTLY_CLOUDY")
        self.assertEqual(r["demo_condition_text"], "Mostly cloudy")
        self.assertEqual(r["demo_icon_uri"], "https://maps.gstatic.com/weather/v1/mostly_cloudy_night")
        self.assertEqual(r["demo_precip_probability"], 27.0)
        self.assertEqual(r["demo_thunderstorm_prob"], 37.0)
        self.assertEqual(r["demo_feels_like_c"], 29.4)
        self.assertEqual(r["demo_uv_index"], 0)
        self.assertIsInstance(r["demo_uv_index"], int)
        self.assertEqual(r["demo_visibility_km"], 16.0)
        self.assertEqual(r["demo_cloud_cover"], 83)
        self.assertIs(r["demo_is_daytime"], False)

    def test_row_has_exactly_the_table_columns(self):
        # weather_slots columns in sql/ddl.sql order (data-schema.md)
        self.assertEqual(list(row()), [
            "site_id", "slot_time", "forecast_init_time", "temperature_c", "dewpoint_c", "relative_humidity",
            "precipitation_mm", "rain_flag", "wind_speed_kmh", "wind_direction_deg", "msl_pressure_hpa",
            "source", "ensemble_stat", "demo_condition_type", "demo_condition_text", "demo_rain_flag", "demo_icon_uri",
            "demo_precip_probability", "demo_thunderstorm_prob", "demo_feels_like_c", "demo_uv_index",
            "demo_visibility_km", "demo_cloud_cover", "demo_is_daytime", "raw", "fetched_at"])

    def test_raw_keeps_the_full_response_and_request(self):
        raw = json.loads(row()["raw"])
        self.assertEqual(raw["response"], FIXTURE)
        self.assertEqual(raw["request"], REQUEST)
        self.assertEqual(raw["response"]["currentConditionsHistory"]["qpf"]["quantity"], 1.26)

    def test_missing_fields_become_null(self):
        r = row({"temperature": {"unit": "CELSIUS", "degrees": 30}})
        self.assertEqual(r["temperature_c"], 30.0)
        for col in ("dewpoint_c", "relative_humidity", "precipitation_mm", "rain_flag", "wind_speed_kmh",
                    "wind_direction_deg", "msl_pressure_hpa", "demo_condition_type", "demo_rain_flag",
                    "demo_uv_index", "demo_visibility_km", "demo_is_daytime"):
            with self.subTest(col=col):
                self.assertIsNone(r[col])


class RainFlag(unittest.TestCase):
    def rain(self, mm):
        resp = json.loads(json.dumps(FIXTURE))
        resp["precipitation"]["qpf"]["quantity"] = mm
        return row(resp)

    def test_threshold_is_strictly_greater_than_0_1(self):
        self.assertIs(self.rain(0.0)["rain_flag"], False)
        self.assertIs(self.rain(0.1)["rain_flag"], False)
        self.assertIs(self.rain(0.11)["rain_flag"], True)
        self.assertIs(self.rain(2.5)["rain_flag"], True)
        self.assertEqual(self.rain(2.5)["precipitation_mm"], 2.5)


class Units(unittest.TestCase):
    def test_temperature(self):
        self.assertEqual(weather.temperature_c({"unit": "CELSIUS", "degrees": 26.4}), 26.4)
        self.assertAlmostEqual(weather.temperature_c({"unit": "FAHRENHEIT", "degrees": 86}), 30.0)
        self.assertAlmostEqual(weather.temperature_c({"unit": "FAHRENHEIT", "degrees": 32}), 0.0)
        self.assertEqual(weather.temperature_c({"degrees": 20}), 20.0)  # no unit = the METRIC default
        self.assertIsNone(weather.temperature_c(None))
        self.assertIsNone(weather.temperature_c({"unit": "CELSIUS"}))

    def test_speed(self):
        self.assertEqual(weather.speed_kmh({"unit": "KILOMETERS_PER_HOUR", "value": 14}), 14.0)
        self.assertAlmostEqual(weather.speed_kmh({"unit": "MILES_PER_HOUR", "value": 10}), 16.09344)
        self.assertIsNone(weather.speed_kmh(None))

    def test_length(self):
        self.assertEqual(weather.length_mm({"unit": "MILLIMETERS", "quantity": 1.5}), 1.5)
        self.assertAlmostEqual(weather.length_mm({"unit": "INCHES", "quantity": 0.1}), 2.54)
        self.assertIsNone(weather.length_mm({"unit": "MILLIMETERS"}))

    def test_distance(self):
        self.assertEqual(weather.distance_km({"unit": "KILOMETERS", "distance": 16}), 16.0)
        self.assertAlmostEqual(weather.distance_km({"unit": "MILES", "distance": 10}), 16.09344)

    def test_unknown_unit_is_an_error_not_a_guess(self):
        with self.assertRaises(ValueError):
            weather.speed_kmh({"unit": "KNOTS", "value": 5})
        with self.assertRaises(ValueError):
            weather.temperature_c({"unit": "KELVIN", "degrees": 300})

    def test_imperial_response_is_converted_in_the_row(self):
        resp = json.loads(json.dumps(FIXTURE))
        resp["temperature"] = {"unit": "FAHRENHEIT", "degrees": 80.0}
        resp["wind"]["speed"] = {"unit": "MILES_PER_HOUR", "value": 10}
        resp["precipitation"]["qpf"] = {"unit": "INCHES", "quantity": 0.1}
        r = row(resp)
        self.assertAlmostEqual(r["temperature_c"], 26.6667, places=3)
        self.assertAlmostEqual(r["wind_speed_kmh"], 16.09344)
        self.assertAlmostEqual(r["precipitation_mm"], 2.54)
        self.assertIs(r["rain_flag"], True)


class Request(unittest.TestCase):
    def test_lookup_url_has_location_and_metric_but_no_key(self):
        url = weather.lookup_url(-5.4101864, 105.3198296)
        self.assertEqual(url, "https://weather.googleapis.com/v1/currentConditions:lookup"
                              "?location.latitude=-5.4101864&location.longitude=105.3198296&unitsSystem=METRIC")
        self.assertNotIn("key", url)

    def test_site_fronts_use_the_approach_legs_destination(self):
        routes = [
            {"site_id": "A", "side": "spbu_side", "leg_index": 1, "dest_lat": 9.0, "dest_lng": 9.0},
            {"site_id": "A", "side": "spbu_side", "leg_index": 0, "dest_lat": 1.0, "dest_lng": 2.0},
            {"site_id": "B", "side": "spbu_side", "leg_index": 0, "dest_lat": 3.0, "dest_lng": 4.0},
        ]
        self.assertEqual(weather.site_fronts(routes), [("A", 1.0, 2.0), ("B", 3.0, 4.0)])

    def test_site_fronts_prefer_the_spbu_side(self):
        routes = [
            {"site_id": "A", "side": "opposite", "leg_index": 0, "dest_lat": 7.0, "dest_lng": 7.0},
            {"site_id": "A", "side": "spbu_side", "leg_index": 0, "dest_lat": 1.0, "dest_lng": 2.0},
        ]
        self.assertEqual(weather.site_fronts(routes), [("A", 1.0, 2.0)])
        self.assertEqual(weather.site_fronts(routes[:1]), [("A", 7.0, 7.0)])


class DemoRainFlag(unittest.TestCase):
    def flag(self, condition, mm=0):
        resp = json.loads(json.dumps(FIXTURE))
        resp["precipitation"]["qpf"]["quantity"] = mm
        if condition is None:
            del resp["weatherCondition"]
        else:
            resp["weatherCondition"]["type"] = condition
        return row(resp)

    def test_light_rain_is_true_even_when_qpf_is_zero(self):
        r = self.flag("LIGHT_RAIN", mm=0)
        self.assertIs(r["demo_rain_flag"], True)
        self.assertIs(r["rain_flag"], False)  # core flag stays qpf-based

    def test_thunderstorm_is_true(self):
        self.assertIs(self.flag("THUNDERSTORM")["demo_rain_flag"], True)

    def test_non_rain_types_are_false(self):
        for t in ("CLOUDY", "MOSTLY_CLOUDY", "CLEAR", "WINDY", "SNOW", "LIGHT_SNOW_SHOWERS", "HAIL"):
            with self.subTest(type=t):
                self.assertIs(self.flag(t)["demo_rain_flag"], False)

    def test_missing_condition_is_null(self):
        self.assertIsNone(self.flag(None)["demo_rain_flag"])

    def test_every_rain_type_is_a_string_in_the_set(self):
        for t in weather.RAIN_CONDITION_TYPES:
            with self.subTest(type=t):
                self.assertIs(self.flag(t)["demo_rain_flag"], True)


class Failures(unittest.TestCase):
    def test_failed_row_has_null_values_and_the_error_in_raw(self):
        r = weather.failed_row("24.351.97", SLOT, "HTTP 500: boom", FETCHED, REQUEST)
        self.assertEqual(r["site_id"], "24.351.97")
        self.assertEqual(r["slot_time"], "2026-10-07T12:30:00.000000Z")
        self.assertEqual(r["source"], "google_weather")
        self.assertEqual(r["fetched_at"], "2026-10-07T12:29:58.000000Z")
        for col in ("temperature_c", "dewpoint_c", "relative_humidity", "precipitation_mm", "rain_flag",
                    "wind_speed_kmh", "wind_direction_deg", "msl_pressure_hpa", "demo_condition_type",
                    "demo_rain_flag"):
            self.assertIsNone(r[col], col)
        self.assertEqual(json.loads(r["raw"]), {"request": REQUEST, "error": "HTTP 500: boom"})

    def test_failed_and_ok_rows_have_the_same_columns(self):
        self.assertEqual(list(weather.failed_row("s", SLOT, "e", FETCHED, REQUEST)), list(row()))


if __name__ == "__main__":
    unittest.main()
