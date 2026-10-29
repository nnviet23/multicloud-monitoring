#!/usr/bin/env python3.12
"""
Multi-Cloud Dynamic Entity Telemetry Collector (V3).
Automatically discovers all active (cloud_provider, service_name) entities from Prometheus
across AWS, Azure, GCP (and any future clouds) using vectorized PromQL queries,
and records per-entity multivariate time-series rows for Universal Autoencoder training.
"""

import argparse
import collections
import csv
import json
import math
import os
import signal
import subprocess
import sys
import time
import urllib.parse
import urllib.request

STOP_REQUESTED = False


def handle_signal(sig, frame):
    global STOP_REQUESTED
    print("\n[Collector] Stop signal received. Finalizing dataset...", flush=True)
    STOP_REQUESTED = True


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

# Vectorized PromQL queries grouped by (cloud_provider, service_name)
# Scales in O(1) queries regardless of the number of pods, services, or clouds!
ENTITY_VECTOR_QUERIES = {
    "discover": 'count by (cloud_provider, service_name) (jvm_memory_used_bytes{jvm_memory_type="heap"})',
    "qps": 'sum by (cloud_provider, service_name) (rate(http_server_request_duration_seconds_count[1m]))',
    "server_latency_p95": 'histogram_quantile(0.95, sum by (le, cloud_provider, service_name) (rate(http_server_request_duration_seconds_bucket[1m])))',
    "client_latency_p95": 'histogram_quantile(0.95, sum by (le, cloud_provider, service_name) (rate(http_client_request_duration_seconds_bucket[1m])))',
    "error_rate_5xx": 'sum by (cloud_provider, service_name) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m]))',
    "max_pod_cpu_pct": 'clamp_max(max by (cloud_provider, service_name) (jvm_cpu_recent_utilization_ratio * jvm_cpu_count) * 100, 100)',
    "max_pod_ram_pct": 'max by (cloud_provider, service_name) (sum by (cloud_provider, service_name, host_name) (jvm_memory_used_bytes{jvm_memory_type="heap"}) / sum by (cloud_provider, service_name, host_name) (jvm_memory_limit_bytes{jvm_memory_type="heap"})) * 100',
    "gc_pause_rate": 'sum by (cloud_provider, service_name) (rate(jvm_gc_duration_seconds_sum[1m]))',
}

CLOUD_VECTOR_QUERIES = {
    "wan_network_io_kbs": 'sum by (cloud_provider) (rate(system_network_io_bytes_total[1m])) / 1024',
    "wan_network_errors": 'sum by (cloud_provider) (rate(system_network_errors_total[1m]))',
}


class PrometheusVectorClient:
    def __init__(self, base_url="http://localhost:9090"):
        self.base_url = base_url.rstrip("/")
        self.pf_proc = None
        self._ensure_connection()

    def _ensure_connection(self):
        try:
            req = urllib.request.Request(f"{self.base_url}/-/ready")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[Prometheus] Connected directly to {self.base_url}", flush=True)
                    return
        except Exception:
            pass

        print(f"[Prometheus] {self.base_url} not reachable. Spawning kubectl port-forward...", flush=True)
        try:
            cmd = [
                "kubectl", "--context", "k3d-hub-k3d", "-n", "monitoring",
                "port-forward", "svc/prometheus-server", "9090:80"
            ]
            self.pf_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            print(f"[Prometheus] Port-forward active (PID: {self.pf_proc.pid})", flush=True)
        except Exception as e:
            print(f"[Warning] Failed to start kubectl port-forward: {e}", flush=True)

    def query_vector(self, promql):
        """Executes an instant PromQL query and returns a list of (metric_labels_dict, float_value)."""
        url = f"{self.base_url}/api/v1/query?" + urllib.parse.urlencode({"query": promql})
        out = []
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=4) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
                if payload.get("status") == "success":
                    results = payload.get("data", {}).get("result", [])
                    for item in results:
                        labels = item.get("metric", {})
                        raw_val = item.get("value", [None, "0"])[1]
                        try:
                            val = float(raw_val)
                            if math.isnan(val) or math.isinf(val):
                                val = 0.0
                        except (ValueError, TypeError):
                            val = 0.0
                        out.append((labels, val))
        except Exception:
            pass
        return out

    def fetch_all_entities_snapshot(self):
        """
        Discovers all active (cloud_provider, service_name) entities and fetches their 8 features
        plus cloud-level WAN metrics in O(1) vectorized queries.
        """
        entities = set()
        for labels, _ in self.query_vector(ENTITY_VECTOR_QUERIES["discover"]):
            cp = labels.get("cloud_provider", "").strip()
            sn = labels.get("service_name", "").strip()
            if cp and sn:
                entities.add((cp, sn))

        metric_maps = {}
        for m_name, promql in ENTITY_VECTOR_QUERIES.items():
            if m_name == "discover":
                continue
            m_dict = {}
            for labels, val in self.query_vector(promql):
                cp = labels.get("cloud_provider", "").strip()
                sn = labels.get("service_name", "").strip()
                if cp and sn:
                    m_dict[(cp, sn)] = max(0.0, val)
            metric_maps[m_name] = m_dict

        cloud_maps = {}
        for c_name, promql in CLOUD_VECTOR_QUERIES.items():
            c_dict = {}
            for labels, val in self.query_vector(promql):
                cp = labels.get("cloud_provider", "").strip()
                if cp:
                    c_dict[cp] = max(0.0, val)
            cloud_maps[c_name] = c_dict

        snapshot = {}
        for cp, sn in sorted(entities):
            snapshot[(cp, sn)] = {
                "qps": metric_maps["qps"].get((cp, sn), 0.0),
                "server_latency_p95": metric_maps["server_latency_p95"].get((cp, sn), 0.0),
                "client_latency_p95": metric_maps["client_latency_p95"].get((cp, sn), 0.0),
                "error_rate_5xx": metric_maps["error_rate_5xx"].get((cp, sn), 0.0),
                "max_pod_cpu_pct": metric_maps["max_pod_cpu_pct"].get((cp, sn), 0.0),
                "max_pod_ram_pct": metric_maps["max_pod_ram_pct"].get((cp, sn), 0.0),
                "gc_pause_rate": metric_maps["gc_pause_rate"].get((cp, sn), 0.0),
                "wan_network_io_kbs": cloud_maps["wan_network_io_kbs"].get(cp, 0.0),
                "wan_network_errors": cloud_maps["wan_network_errors"].get(cp, 0.0),
            }
        return snapshot

    def close(self):
        if self.pf_proc:
            print("[Prometheus] Terminating background port-forward...", flush=True)
            self.pf_proc.terminate()
            self.pf_proc.wait()


def main():
    parser = argparse.ArgumentParser(description="Multi-Cloud Dynamic Entity Metric Collector (V3)")
    parser.add_argument("--prometheus-url", default="http://localhost:9090", help="Prometheus API URL")
    parser.add_argument("--duration", type=int, default=2400, help="Collection duration in seconds (default 2400s = 40m)")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds (default 10s)")
    parser.add_argument("--output", default="ai-engine/data/raw/multicloud_entity_baseline.csv", help="Output CSV path")
    parser.add_argument("--label", type=int, default=0, help="Ground-truth anomaly label (0=normal, 1=anomaly)")
    args = parser.parse_args()

    os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)

    fieldnames = [
        "timestamp",
        "datetime",
        "cycle_id",
        "cloud_provider",
        "service_name",
        "qps",
        "server_latency_p95",
        "client_latency_p95",
        "error_rate_5xx",
        "max_pod_cpu_pct",
        "max_pod_ram_pct",
        "ram_floor_2m_pct",
        "gc_pause_rate",
        "wan_network_io_kbs",
        "wan_network_errors",
        "anomaly_label",
    ]

    print("========================================================================", flush=True)
    print("  MULTI-CLOUD DYNAMIC ENTITY TELEMETRY COLLECTOR (V3)", flush=True)
    print(f"  Target Prometheus : {args.prometheus_url}", flush=True)
    print(f"  Duration          : {args.duration}s (~{args.duration/60:.1f} minutes)", flush=True)
    print(f"  Sampling Interval : {args.interval}s", flush=True)
    print(f"  Output CSV        : {args.output}", flush=True)
    print("========================================================================\n", flush=True)

    client = PrometheusVectorClient(args.prometheus_url)
    ram_history = collections.defaultdict(lambda: collections.deque(maxlen=12))

    csv_file = open(args.output, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()
    csv_file.flush()

    start_time = time.time()
    end_time = start_time + args.duration
    cycle_id = 0
    total_entity_rows = 0

    try:
        while not STOP_REQUESTED and time.time() < end_time:
            loop_start = time.time()
            now_ts = int(loop_start)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(loop_start))
            cycle_id += 1

            snapshot = client.fetch_all_entities_snapshot()
            summary_parts = []

            for (cp, sn), m in snapshot.items():
                ram_history[(cp, sn)].append(m["max_pod_ram_pct"])
                ram_floor = min(ram_history[(cp, sn)])

                row = {
                    "timestamp": now_ts,
                    "datetime": now_iso,
                    "cycle_id": cycle_id,
                    "cloud_provider": cp,
                    "service_name": sn,
                    "qps": round(m["qps"], 4),
                    "server_latency_p95": round(m["server_latency_p95"], 5),
                    "client_latency_p95": round(m["client_latency_p95"], 5),
                    "error_rate_5xx": round(m["error_rate_5xx"], 4),
                    "max_pod_cpu_pct": round(m["max_pod_cpu_pct"], 3),
                    "max_pod_ram_pct": round(m["max_pod_ram_pct"], 3),
                    "ram_floor_2m_pct": round(ram_floor, 3),
                    "gc_pause_rate": round(m["gc_pause_rate"], 5),
                    "wan_network_io_kbs": round(m["wan_network_io_kbs"], 3),
                    "wan_network_errors": round(m["wan_network_errors"], 4),
                    "anomaly_label": args.label,
                }
                writer.writerow(row)
                total_entity_rows += 1
                summary_parts.append(
                    f"{cp}:{sn.replace('teastore-', '')}"
                    f"(QPS={m['qps']:.1f},Srv={m['server_latency_p95']*1000:.0f}ms,"
                    f"CPU={m['max_pod_cpu_pct']:.0f}%,RAM={m['max_pod_ram_pct']:.0f}%[Flr={ram_floor:.0f}%])"
                )

            csv_file.flush()
            elapsed = int(time.time() - start_time)
            remaining = max(0, int(end_time - time.time()))
            print(
                f"[{now_iso}] Cycle #{cycle_id:3d} ({elapsed}s/{remaining}s left) | "
                f"Entities: {len(snapshot)} | Total Rows: {total_entity_rows:4d}",
                flush=True
            )
            if summary_parts:
                print("   └── " + " | ".join(summary_parts), flush=True)

            elapsed_in_loop = time.time() - loop_start
            time.sleep(max(0.1, args.interval - elapsed_in_loop))

    except KeyboardInterrupt:
        handle_signal(None, None)
    finally:
        csv_file.close()
        client.close()
        print(
            f"\n[Collector] Completed {cycle_id} cycles ({total_entity_rows} entity rows) -> {args.output}",
            flush=True
        )


if __name__ == "__main__":
    main()
