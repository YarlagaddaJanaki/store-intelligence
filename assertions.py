"""
Example assertions from the hiring challenge.
Run: python assertions.py (API must be running on :8000)
"""

import httpx

API = "http://127.0.0.1:8000"
STORE = "STORE_BLR_002"


def assert_metrics_ok():
    r = httpx.get(f"{API}/stores/{STORE}/metrics", timeout=10)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "unique_visitors" in body
    assert "conversion_rate" in body
    assert 0 <= body["conversion_rate"] <= 1


def assert_funnel_ok():
    r = httpx.get(f"{API}/stores/{STORE}/funnel", timeout=10)
    assert r.status_code == 200
    stages = {s["stage"]: s["count"] for s in r.json()["stages"]}
    assert stages["Entry"] >= stages["Purchase"]


def assert_health_ok():
    r = httpx.get(f"{API}/health", timeout=10)
    assert r.status_code == 200
    assert "status" in r.json()


if __name__ == "__main__":
    assert_health_ok()
    assert_metrics_ok()
    assert_funnel_ok()
    print("All example assertions passed.")
