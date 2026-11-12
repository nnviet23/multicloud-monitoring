#!/usr/bin/env python3.12
"""Log the detector's end-to-end WebUI probe at the detector cadence.

Uses inference.detector.probe_webui_health so recorded latencies match what the
detector sees online; normal-run probe logs calibrate the SLO guard thresholds.
Usage: probe_logger.py <output.csv> <duration_s> [interval_s]
"""
import csv
import os
import signal
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "ai-engine"))
sys.path.insert(0, ROOT)
from inference.detector import probe_webui_health  # noqa: E402

stop = False


def _stop(*_):
    global stop
    stop = True


def main():
    output, duration = sys.argv[1], float(sys.argv[2])
    interval = float(sys.argv[3]) if len(sys.argv) > 3 else 10.0
    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
    end = time.time() + duration
    with open(output, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["timestamp", "datetime", "probe_ok", "probe_code", "probe_ms"])
        while not stop and time.time() < end:
            start = time.time()
            ok, code, ms = probe_webui_health()
            writer.writerow([int(start), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)), int(ok), code, round(ms, 1)])
            f.flush()
            time.sleep(max(0.1, interval - (time.time() - start)))


if __name__ == "__main__":
    main()
