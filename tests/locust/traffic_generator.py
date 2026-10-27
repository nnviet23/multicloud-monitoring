#!/usr/bin/env python3
"""
Standalone TeaStore Dynamic Traffic Generator (Zero external dependencies).
Simulates realistic multi-user browsing behaviors with progressive load ramping.
Phases over total duration:
    - Phase 1 (0h-1h):  Off-peak / Warm-up (10 -> 20 users)
    - Phase 2 (1h-2h):  Normal business hours (20 -> 35 users)
    - Phase 3 (2h-3h):  Peak rush / Flash sale (35 -> 50 users)
    - Phase 4 (3h-4h):  Cooldown / Evening (50 -> 15 users)

Usage:
    python3 traffic_generator.py --duration 14400 --min-users 10 --max-users 50
"""

import argparse
import math
import random
import signal
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

STOP_REQUESTED = False

def handle_signal(sig, frame):
    global STOP_REQUESTED
    print("\n[Traffic Generator] Received stop signal. Shutting down gracefully...")
    STOP_REQUESTED = True

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

def compute_target_users(elapsed, total_duration, min_u, max_u, erratic=False):
    """
    Calculates active concurrent users combining:
      1. 4-phase daily trend (Warm-up -> Normal -> Peak -> Cooldown) or Erratic Regime
      2. Sinusoidal waves (15-min macro wave + 2-min micro wave)
      3. Periodic short flash-bursts
    """
    if erratic:
        # Smooth 25-second initial ramp so k3d nginx LB & Tomcat thread pool warm up cleanly
        if elapsed < 25:
            return max(min_u, min(max_u, int(min_u + (elapsed / 25.0) * 14)))
        # Deterministic pseudo-random erratic regime switching every 25 seconds
        bucket = int(elapsed // 25)
        rng = random.Random(1337 + bucket * 7919)
        regime = rng.choice(["flash_crowd", "sudden_drop", "rollercoaster", "moderate_wave", "burst_spike"])
        if regime == "flash_crowd":
            base = rng.randint(max(min_u, int(max_u * 0.75)), max_u)
        elif regime == "sudden_drop":
            base = rng.randint(min_u, max(min_u + 4, int(max_u * 0.20)))
        elif regime == "burst_spike":
            base = max_u if (int(elapsed) % 25) < 15 else min_u + 3
        elif regime == "rollercoaster":
            sub = int(elapsed % 25)
            base = int(min_u + (max_u - min_u) * abs(math.sin(sub * 0.35)))
        else:
            base = rng.randint(int(max_u * 0.35), int(max_u * 0.70))
        jitter = int(4.0 * math.sin(elapsed * 0.9))
        return max(min_u, min(max_u, base + jitter))

    ratio = min(1.0, max(0.0, elapsed / max(1, total_duration)))
    if ratio < 0.25:
        p = ratio / 0.25
        trend = min_u + p * 10
    elif ratio < 0.50:
        p = (ratio - 0.25) / 0.25
        base = min_u + 10
        target = min(max_u - 15, base + 15)
        trend = base + p * (target - base)
    elif ratio < 0.75:
        p = (ratio - 0.50) / 0.25
        base = min(max_u - 15, min_u + 25)
        if p < 0.7:
            trend = base + (p / 0.7) * (max_u - base)
        else:
            trend = max_u - ((p - 0.7) / 0.3) * 5
    else:
        p = (ratio - 0.75) / 0.25
        start = max_u - 5
        trend = start - p * (start - min_u)

    # Add natural oscillations: 12-min wave (+/- 6 users) + 90-sec wave (+/- 4 users)
    macro_wave = 6.0 * math.sin(2.0 * math.pi * elapsed / 720.0)
    micro_wave = 4.0 * math.sin(2.0 * math.pi * elapsed / 90.0)

    # Periodic 30-second micro-burst every 480 seconds (8 minutes)
    burst = 10.0 if (int(elapsed) % 480) < 30 else 0.0

    users = int(round(trend + macro_wave + micro_wave + burst))
    return max(min_u, min(max_u, users))

class TeaStoreClient:
    def __init__(self, base_url):
        self.base_url = base_url.rstrip("/")
        self.opener = urllib.request.build_opener()

    def request(self, path, params=None, method="GET"):
        url = f"{self.base_url}{path}"
        if params:
            encoded_params = urllib.parse.urlencode(params)
            if method == "GET":
                url = f"{url}?{encoded_params}"
                req = urllib.request.Request(url, method="GET")
            else:
                data = encoded_params.encode("utf-8")
                req = urllib.request.Request(url, data=data, method="POST")
        else:
            req = urllib.request.Request(url, method=method)

        req.add_header("User-Agent", "TeaStore-Bench-Client/1.0")
        req.add_header("Connection", "close")
        for attempt in range(2):
            try:
                with self.opener.open(req, timeout=8) as response:
                    return response.status, len(response.read())
            except urllib.error.HTTPError as e:
                return e.code, 0
            except Exception:
                if attempt == 0:
                    time.sleep(0.25)
        return 0, 0

def user_worker(user_id, base_url, start_time, duration, min_u, max_u, stats, erratic=False):
    client = TeaStoreClient(base_url)
    actions = ["home", "category", "product", "cart_add", "cart_view", "status"]
    weights = [0.25, 0.30, 0.25, 0.10, 0.05, 0.05]
    end_time = start_time + duration

    while not STOP_REQUESTED and time.time() < end_time:
        elapsed = time.time() - start_time
        target_users = compute_target_users(elapsed, duration, min_u, max_u, erratic=erratic)

        # If this worker is above currently active user limit, sleep and idle
        if user_id >= target_users:
            time.sleep(1.0)
            continue

        action = random.choices(actions, weights=weights)[0]
        status_code = 0

        if action == "home":
            status_code, _ = client.request("/")
        elif action == "category":
            cat = random.choice([2, 3, 4, 5, 6])
            page = random.randint(1, 3)
            status_code, _ = client.request("/category", {"page": page, "category": cat})
        elif action == "product":
            pid = random.randint(1, 300)
            status_code, _ = client.request("/product", {"id": pid})
        elif action == "cart_add":
            pid = random.randint(1, 300)
            status_code, _ = client.request("/cartAction", {"addToCart": "", "productid": pid}, method="POST")
        elif action == "cart_view":
            status_code, _ = client.request("/cart")
        elif action == "status":
            status_code, _ = client.request("/status")

        stats["total_requests"] += 1
        if 200 <= status_code < 400:
            stats["successful_requests"] += 1
        else:
            stats["failed_requests"] += 1

        # Human think time (faster & more varied in erratic mode)
        if erratic:
            time.sleep(random.uniform(0.45, 2.1))
        else:
            time.sleep(random.uniform(1.0, 2.5))

def main():
    parser = argparse.ArgumentParser(description="Standalone TeaStore Progressive Traffic Generator")
    parser.add_argument("--url", default="http://localhost:8080/tools.descartes.teastore.webui", help="Target WebUI base URL")
    parser.add_argument("--min-users", type=int, default=10, help="Minimum off-peak concurrent users")
    parser.add_argument("--max-users", type=int, default=50, help="Maximum peak-hour concurrent users")
    parser.add_argument("--duration", type=int, default=14400, help="Duration in seconds (default 14400s = 4h)")
    parser.add_argument("--erratic", action="store_true", help="Enable erratic / unpredictable user behavior mode")
    args = parser.parse_args()

    mode_str = "ERRATIC / UNPREDICTABLE USER LOAD" if args.erratic else "4-PHASE PROGRESSIVE LOAD"
    print("=================================================================")
    print("  TEASTORE DYNAMIC & PROGRESSIVE TRAFFIC GENERATOR")
    print(f"  Target URL:  {args.url}")
    print(f"  Traffic Mode:{mode_str}")
    print(f"  Load Curve:  {args.min_users} (min) <-> {args.max_users} (peak) users")
    print(f"  Duration:    {args.duration}s (~{args.duration/60:.1f} mins)")
    print("=================================================================\n", flush=True)

    stats = {"total_requests": 0, "successful_requests": 0, "failed_requests": 0}
    start_time = time.time()
    end_time = start_time + args.duration

    with ThreadPoolExecutor(max_workers=args.max_users) as executor:
        futures = [
            executor.submit(
                user_worker, i, args.url, start_time, args.duration,
                args.min_users, args.max_users, stats, args.erratic
            )
            for i in range(args.max_users)
        ]

        last_total = 0
        try:
            while not STOP_REQUESTED and time.time() < end_time:
                time.sleep(10)
                elapsed = int(time.time() - start_time)
                remaining = max(0, int(end_time - time.time()))
                current_users = compute_target_users(elapsed, args.duration, args.min_users, args.max_users, erratic=args.erratic)

                current_total = stats["total_requests"]
                qps = (current_total - last_total) / 10.0
                last_total = current_total
                succ = stats["successful_requests"]
                fail = stats["failed_requests"]

                # Determine phase name for friendly logging
                if args.erratic:
                    bucket = int(elapsed // 25)
                    rng = random.Random(1337 + bucket * 7919)
                    phase = f"Erratic: {rng.choice(['Flash-Crowd', 'Sudden-Drop', 'Rollercoaster', 'Moderate-Wave', 'Burst-Spike'])}"
                else:
                    ratio = elapsed / args.duration
                    if ratio < 0.25:
                        phase = "Phase 1: Warm-up"
                    elif ratio < 0.50:
                        phase = "Phase 2: Normal"
                    elif ratio < 0.75:
                        phase = "Phase 3: Peak Rush"
                    else:
                        phase = "Phase 4: Cooldown"

                print(
                    f"[{elapsed:3d}s/{remaining:3d}s left | {phase:22s}] Active Users: {current_users:2d} | "
                    f"QPS: {qps:5.1f} | Total: {current_total:6d} | Success: {succ} | Fail: {fail}",
                    flush=True
                )
        except KeyboardInterrupt:
            handle_signal(None, None)

    print("\n[Traffic Generator] Finished.", flush=True)
    print(f"Final Stats: Total Requests = {stats['total_requests']} (Success: {stats['successful_requests']}, Failed: {stats['failed_requests']})", flush=True)

if __name__ == "__main__":
    main()
