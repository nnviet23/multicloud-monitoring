#!/usr/bin/env python3
"""
Multi-Cloud Observability Metric Collector.
Extracts real-time multivariate time-series metrics from Prometheus on Hub.
Outputs structured CSV datasets ready for GRU / TCN Autoencoder training.

Usage:
    python3 collector.py --duration 14400 --interval 10 --output ../data/raw/normal_baseline_4h.csv
"""

import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

STOP_REQUESTED = False

def handle_signal(sig, frame):
    global STOP_REQUESTED
    print("\n[Collector] Stop signal received. Finalizing dataset...")
    STOP_REQUESTED = True

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# Prometheus Queries for Multivariate Time-Series Features
METRIC_QUERIES = {
    # 1. HTTP Traffic & Performance
    "latency_p50": 'histogram_quantile(0.50, sum by (le) (rate(http_server_request_duration_seconds_bucket[1m])))',
    "latency_p95": 'histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket[1m])))',
    "latency_p99": 'histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket[1m])))',
    "throughput_qps": 'sum(rate(http_server_request_duration_seconds_count[1m]))',
    "error_rate_5xx": 'sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m])) or vector(0)',

    # 2. Key Microservices Breakdown (AWS Compute & Azure Data)
    "webui_qps": 'sum(rate(http_server_request_duration_seconds_count{service_name=~".*webui.*"}[1m])) or vector(0)',
    "persistence_qps": 'sum(rate(http_server_request_duration_seconds_count{service_name=~".*persistence.*"}[1m])) or vector(0)',
    "webui_latency_p95": 'histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{service_name=~".*webui.*"}[1m]))) or vector(0)',
    "persistence_latency_p95": 'histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{service_name=~".*persistence.*"}[1m]))) or vector(0)',

    # 3. Microservice Runtime (% CPU & % RAM so với giới hạn cấp phát của từng Pod)
    # LƯU Ý: Chuẩn hóa hoàn toàn về tỷ lệ phần trăm (0% -> 100%) để AI khái quát hóa trên mọi quy mô
    "app_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio * jvm_cpu_count) * 100, 100) or vector(0)',
    "max_pod_cpu_pct": 'clamp_max(max(jvm_cpu_recent_utilization_ratio * jvm_cpu_count) * 100, 100) or vector(0)',
    "app_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{jvm_memory_type="heap"})) * 100 or vector(0)',
    "max_pod_ram_pct": 'max(sum by (service_name, host_name) (jvm_memory_used_bytes{jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{jvm_memory_type="heap"})) * 100 or vector(0)',
    "jvm_threads_live": 'avg(jvm_thread_count) or vector(0)',
    "jvm_gc_pause_rate": 'sum(rate(jvm_gc_duration_seconds_sum[1m])) or vector(0)',

    # 4. Chi tiết từng Microservice cố định (CPU % & RAM % theo Service)
    "webui_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-webui"} * jvm_cpu_count{service_name="teastore-webui"}) * 100, 100) or vector(0)',
    "webui_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-webui", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-webui", jvm_memory_type="heap"})) * 100 or vector(0)',
    "persistence_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-persistence"} * jvm_cpu_count{service_name="teastore-persistence"}) * 100, 100) or vector(0)',
    "persistence_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-persistence", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-persistence", jvm_memory_type="heap"})) * 100 or vector(0)',
    "auth_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-auth"} * jvm_cpu_count{service_name="teastore-auth"}) * 100, 100) or vector(0)',
    "auth_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-auth", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-auth", jvm_memory_type="heap"})) * 100 or vector(0)',
    "image_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-image"} * jvm_cpu_count{service_name="teastore-image"}) * 100, 100) or vector(0)',
    "image_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-image", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-image", jvm_memory_type="heap"})) * 100 or vector(0)',
    "recommender_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-recommender"} * jvm_cpu_count{service_name="teastore-recommender"}) * 100, 100) or vector(0)',
    "recommender_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-recommender", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-recommender", jvm_memory_type="heap"})) * 100 or vector(0)',
    "registry_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-registry"} * jvm_cpu_count{service_name="teastore-registry"}) * 100, 100) or vector(0)',
    "registry_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-registry", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-registry", jvm_memory_type="heap"})) * 100 or vector(0)',

    # 5. Cross-Cloud WAN Transit (Lưu lượng mạng giữa AWS và Azure trên bridge network)
    "wan_network_io_kbs": 'sum(rate(system_network_io_bytes_total[1m])) / 1024 or vector(0)',
    "wan_network_errors": 'sum(rate(system_network_errors_total[1m])) or vector(0)',
}

class PrometheusClient:
    def __init__(self, base_url="http://localhost:9090"):
        self.base_url = base_url.rstrip("/")
        self.pf_proc = None
        self._ensure_connection()

    def _ensure_connection(self):
        """Checks if Prometheus is accessible. If not, auto-launches kubectl port-forward."""
        try:
            req = urllib.request.Request(f"{self.base_url}/-/ready")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[Prometheus] Connected directly to {self.base_url}")
                    return
        except Exception:
            pass

        print(f"[Prometheus] {self.base_url} not reachable. Spawning kubectl port-forward...")
        try:
            cmd = [
                "kubectl", "--context", "k3d-hub-k3d", "-n", "monitoring",
                "port-forward", "svc/prometheus-server", "9090:80"
            ]
            self.pf_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            print(f"[Prometheus] port-forward active (PID: {self.pf_proc.pid})")
        except Exception as e:
            print(f"[Warning] Failed to start kubectl port-forward: {e}")

    def query_instant(self, query):
        """Executes an instant PromQL query and returns a single float scalar."""
        url = f"{self.base_url}/api/v1/query?{urllib.parse.urlencode({'query': query})}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=4) as response:
                payload = json.loads(response.read().decode("utf-8"))
                if payload.get("status") == "success":
                    results = payload.get("data", {}).get("result", [])
                    if results:
                        val = results[0].get("value", [None, 0])[1]
                        if val is None or val == "NaN" or val == "+Inf" or val == "-Inf":
                            return 0.0
                        return float(val)
                return 0.0
        except Exception:
            return 0.0

    def close(self):
        if self.pf_proc:
            print("[Prometheus] Terminating background port-forward...")
            self.pf_proc.terminate()
            self.pf_proc.wait()

def main():
    parser = argparse.ArgumentParser(description="Multi-Cloud Observability Metric Collector")
    parser.add_argument("--prometheus-url", default="http://localhost:9090", help="Prometheus API URL")
    parser.add_argument("--duration", type=int, default=14400, help="Duration in seconds (default 14400s = 4h)")
    parser.add_argument("--interval", type=int, default=10, help="Sampling interval in seconds (default 10s)")
    parser.add_argument("--output", default="ai-engine/data/raw/normal_baseline_4h.csv", help="Path to output CSV file")
    parser.add_argument("--label", type=int, default=0, help="Ground truth anomaly label (0=normal, 1=anomaly)")
    args = parser.parse_args()

    # Ensure parent dir exists
    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    print("=======================================================")
    print("  MULTI-CLOUD OBSERVABILITY METRIC COLLECTOR")
    print(f"  Target:     {args.prometheus_url}")
    print(f"  Duration:   {args.duration}s (~{args.duration/3600:.1f} hours)")
    print(f"  Interval:   {args.interval}s")
    print(f"  Output CSV: {args.output}")
    print(f"  Label:      {args.label} (0=Normal, 1=Anomaly)")
    print("=======================================================\n")

    client = PrometheusClient(args.prometheus_url)
    fieldnames = ["timestamp", "datetime"] + list(METRIC_QUERIES.keys()) + ["anomaly_label"]

    file_exists = os.path.isfile(args.output)
    header_matches = False
    if file_exists:
        with open(args.output, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            header_matches = (first_line == ",".join(fieldnames))

    mode = "a" if (file_exists and header_matches) else "w"
    csv_file = open(args.output, mode, newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)

    if mode == "w":
        writer.writeheader()
        csv_file.flush()

    start_time = time.time()
    end_time = start_time + args.duration
    sample_count = 0

    try:
        while not STOP_REQUESTED and time.time() < end_time:
            loop_start = time.time()
            now_ts = int(loop_start)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(loop_start))

            row = {
                "timestamp": now_ts,
                "datetime": now_iso,
                "anomaly_label": args.label
            }

            # Query all defined metrics
            for key, query in METRIC_QUERIES.items():
                val = client.query_instant(query)
                row[key] = round(val, 4)

            writer.writerow(row)
            csv_file.flush()
            sample_count += 1

            elapsed = int(time.time() - start_time)
            remaining = max(0, int(end_time - time.time()))

            # Print status row
            print(
                f"[{now_iso}] ({elapsed}s/{remaining}s left) Samples: {sample_count:4d} | "
                f"QPS: {row['throughput_qps']:5.1f} | LatencyP95: {row['latency_p95']:6.3f}s | "
                f"AppCPU: {row['app_cpu_pct']:5.1f}% (Max:{row['max_pod_cpu_pct']:5.1f}%) | "
                f"AppRAM: {row['app_ram_pct']:5.1f}% (Max:{row['max_pod_ram_pct']:5.1f}%) | Error: {row['error_rate_5xx']}"
            )
            print(
                f"   └── Services (CPU/RAM%): "
                f"webui: {row['webui_cpu_pct']:4.1f}%/{row['webui_ram_pct']:4.1f}% | "
                f"persistence: {row['persistence_cpu_pct']:4.1f}%/{row['persistence_ram_pct']:4.1f}% | "
                f"image: {row['image_cpu_pct']:4.1f}%/{row['image_ram_pct']:4.1f}% | "
                f"auth: {row['auth_cpu_pct']:4.1f}%/{row['auth_ram_pct']:4.1f}% | "
                f"recommender: {row['recommender_cpu_pct']:4.1f}%/{row['recommender_ram_pct']:4.1f}% | "
                f"registry: {row['registry_cpu_pct']:4.1f}%/{row['registry_ram_pct']:4.1f}%"
            )

            # Sleep remaining time to keep exact sampling interval
            elapsed_in_loop = time.time() - loop_start
            sleep_duration = max(0.1, args.interval - elapsed_in_loop)
            time.sleep(sleep_duration)

    except KeyboardInterrupt:
        handle_signal(None, None)
    finally:
        csv_file.close()
        client.close()
        print(f"\n[Collector] Finished. Total {sample_count} samples recorded to: {args.output}")

if __name__ == "__main__":
    main()

