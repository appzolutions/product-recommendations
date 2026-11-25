"""Measure how fast the API answers (proposal Objective 4).

Usage (API must be running):
    python scripts/measure_latency.py                      # local API
    python scripts/measure_latency.py https://your-api.onrender.com --requests 100

It first wakes the API (free hosting sleeps when idle), then calls the
recommendations endpoint many times for random users and prints a summary
you can paste into the report.
"""
import argparse
import statistics
import time

import httpx


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base_url", nargs="?", default="http://localhost:8000")
    parser.add_argument("--requests", type=int, default=50)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")

    with httpx.Client(timeout=120) as client:
        print("Waking the API...")
        t = time.perf_counter()
        client.get(f"{base}/health").raise_for_status()
        print(f"  first response: {(time.perf_counter() - t) * 1000:,.0f} ms (includes wake-up if it was asleep)")

        users = client.get(f"{base}/api/users/sample", params={"limit": 20}).json()["user_ids"]
        total, server = [], []
        for i in range(args.requests):
            user = users[i % len(users)]
            t = time.perf_counter()
            r = client.get(f"{base}/api/users/{user}/recommendations")
            total.append((time.perf_counter() - t) * 1000)
            r.raise_for_status()
            server.append(float(r.headers["X-Process-Time-Ms"]))

    def summary(name, values):
        values = sorted(values)
        p95 = values[max(0, int(len(values) * 0.95) - 1)]
        print(f"{name:32s} median {statistics.median(values):7.1f} ms   95th percentile {p95:7.1f} ms   max {values[-1]:7.1f} ms")

    data_source = httpx.get(f"{base}/health").json()["data_source"]
    print(f"\n{args.requests} requests to {base} (data source: {data_source})")
    summary("Total (network + server)", total)
    summary("Server only (X-Process-Time-Ms)", server)


if __name__ == "__main__":
    main()
