"""Locust load test for attendance API.

Run:
  locust -f tests/load/locustfile.py --host=http://localhost:8000
  locust -f tests/load/locustfile.py --headless -u 50 -r 5 -t 2m --host=http://localhost:8000
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task


class AttendanceApiUser(HttpUser):
    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        self.token = os.getenv("LOAD_TEST_TOKEN", "")
        self.auth_headers = {"Authorization": f"Bearer {self.token}"} if self.token else {}

    @task(5)
    def health(self) -> None:
        self.client.get("/health")

    @task(3)
    def dashboard_kpis(self) -> None:
        self.client.get("/dashboard/kpis?days=7", headers=self.auth_headers, name="/dashboard/kpis")

    @task(2)
    def reporting_heatmap(self) -> None:
        self.client.get("/reporting/heatmap?days=7", headers=self.auth_headers, name="/reporting/heatmap")

    @task(2)
    def list_attendance(self) -> None:
        self.client.get("/attendance/?limit=100", headers=self.auth_headers, name="/attendance/")

    @task(1)
    def list_devices(self) -> None:
        self.client.get("/fleet/devices", headers=self.auth_headers, name="/fleet/devices")
