#!/usr/bin/env python3
"""Terminal live dashboard — polls /metrics while events stream in."""

import os
import time

import httpx
from rich.console import Console
from rich.live import Live
from rich.table import Table

API = os.getenv("STORE_INTEL_API", "http://127.0.0.1:8000")
STORE = os.getenv("STORE_ID", "STORE_BLR_002")
INTERVAL = float(os.getenv("DASHBOARD_INTERVAL", "2"))


def render_metrics() -> Table:
    table = Table(title=f"Store Intelligence — {STORE}")
    table.add_column("Metric")
    table.add_column("Value")
    try:
        response = httpx.get(f"{API}/stores/{STORE}/metrics", timeout=5)
        response.raise_for_status()
        data = response.json()
        table.add_row("Unique visitors", str(data["unique_visitors"]))
        table.add_row("Conversion rate", f"{data['conversion_rate']:.2%}")
        table.add_row("Queue depth", str(data["queue_depth"]))
        table.add_row("Abandonment rate", f"{data['abandonment_rate']:.2%}")
        health = httpx.get(f"{API}/health", timeout=5).json()
        table.add_row("API status", health["status"])
        if health.get("warnings"):
            table.add_row("Warnings", ", ".join(health["warnings"]))
    except Exception as exc:
        table.add_row("Error", str(exc))
    return table


def main() -> None:
    console = Console()
    with Live(render_metrics(), console=console, refresh_per_second=2) as live:
        while True:
            time.sleep(INTERVAL)
            live.update(render_metrics())


if __name__ == "__main__":
    main()
