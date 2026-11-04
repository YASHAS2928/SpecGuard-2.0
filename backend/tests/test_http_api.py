"""In-process HTTP/ASGI tests. Enable on a host with loopback socket access."""

import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from mock_api.main import app


@unittest.skipUnless(os.getenv("SPECGUARD_ENABLE_HTTP_TESTS") == "1", "requires loopback socket access")
class InProcessApiTests(unittest.TestCase):
    def test_all_versions_and_invalid_requests(self):
        cases = [
            ("1.3.0", {"start_time": "22:00", "end_time": "07:00", "overnight": True,
                         "meal_break_minutes": 30}, {"paid_minutes": 0, "overtime_minutes": 0}),
            ("1.3.0-b", {"start_time": "08:00", "end_time": "16:00", "overnight": False,
                           "meal_break_minutes": 0}, {"paid_minutes": 480, "overtime_minutes": 1}),
            ("1.3.0-c", {"start_time": "08:00", "end_time": "17:00", "overnight": False,
                           "meal_break_minutes": 30}, {"paid_minutes": 480, "overtime_minutes": 0}),
            ("1.4.0", {"start_time": "22:00", "end_time": "07:00", "overnight": True,
                         "meal_break_minutes": 30}, {"paid_minutes": 510, "overtime_minutes": 30}),
        ]
        with TestClient(app) as client:
            for version, payload, expected in cases:
                with self.subTest(version=version), patch.dict(os.environ, {"MOCK_VERSION": version}):
                    response = client.post("/v1/pay/calculate", json=payload)
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.headers["X-Mock-Version"], version)
                    self.assertEqual(response.json(), expected)
            invalid = client.post("/v1/pay/calculate", json={"start_time": "9am", "end_time": "17:00",
                                                               "overnight": False, "meal_break_minutes": 0})
            self.assertEqual(invalid.status_code, 422)
            with patch.dict(os.environ, {"MOCK_VERSION": "unknown"}):
                unavailable = client.post("/v1/pay/calculate", json=cases[-1][1])
                self.assertEqual(unavailable.status_code, 503)
