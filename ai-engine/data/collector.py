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
import os
import signal
import sys
import time

STOP_REQUESTED = False


def handle_signal(sig, frame):
    global STOP_REQUESTED
    print("\n[Collector] Stop signal received. Finalizing dataset...", flush=True)
    STOP_REQUESTED = True


# Vectorized PromQL queries grouped by (cloud_provider, service_name)
# Scales in O(1) queries regardless of the number of pods, services, or clouds!
# Dual-compatible with both OpenTelemetry SemConv v1.x (jvm_*) and v2.x (process_runtime_jvm_*)
ACTIVE_JVM_PODS = (
    '(sum by (cloud_provider, service_name, host_name) (rate(jvm_cpu_time_seconds_total[30s]) or rate(process_runtime_jvm_cpu_time_seconds_total[30s])) > 0)'
    ' or (sum by (cloud_provider, service_name, host_name) (rate(http_server_request_duration_seconds_count[30s]) or rate(http_server_duration_milliseconds_count[30s])) > 0)'
    ' or (sum by (cloud_provider, service_name, host_name) (rate(http_client_request_duration_seconds_count[30s]) or rate(http_client_duration_milliseconds_count[30s])) > 0)'
)

ENTITY_VECTOR_QUERIES = {
    "discover": (
        f'(count by (cloud_provider, service_name) ((jvm_memory_used_bytes{{jvm_memory_type="heap"}} or process_runtime_jvm_memory_usage_bytes{{type="heap"}} or process_runtime_jvm_memory_usage_bytes) and on (cloud_provider, service_name, host_name) ({ACTIVE_JVM_PODS})))'
        ' or (count by (cloud_provider, service_name) (jvm_memory_used_bytes{jvm_memory_type="heap"} or process_runtime_jvm_memory_usage_bytes{type="heap"} or process_runtime_jvm_memory_usage_bytes))'
    ),
    "qps": 'sum by (cloud_provider, service_name) (rate(http_server_request_duration_seconds_count[1m]) or rate(http_server_duration_milliseconds_count[1m]))',
    "server_latency_p95": 'histogram_quantile(0.95, sum by (le, cloud_provider, service_name) (rate(http_server_request_duration_seconds_bucket[1m]) or rate(http_server_duration_milliseconds_bucket[1m])))',
    "client_latency_p95": 'histogram_quantile(0.95, sum by (le, cloud_provider, service_name) (rate(http_client_request_duration_seconds_bucket[1m]) or rate(http_client_duration_milliseconds_bucket[1m])))',
    "error_rate_5xx": 'sum by (cloud_provider, service_name) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m]) or rate(http_server_request_duration_seconds_count{http_status_code=~"5.."}[1m]))',
    # Busiest pod's CPU as % of ONE core, from the cumulative CPU-time counter.
    # The former gauge form (jvm_cpu_recent_utilization_ratio * jvm_cpu_count) read
    # 100-300% for pods using ~0.05 core on a 16-core host, so it saturated at the
    # clamp and carried no signal. TeaStore pods have no CPU limit; 100 == 1 busy core.
    "max_pod_cpu_pct": (
        f'(clamp_max(max by (cloud_provider, service_name) (sum by (cloud_provider, service_name, host_name) (rate(jvm_cpu_time_seconds_total[1m]) or rate(process_runtime_jvm_cpu_time_seconds_total[1m])) and on (cloud_provider, service_name, host_name) ({ACTIVE_JVM_PODS})) * 100, 100))'
        ' or (clamp_max(max by (cloud_provider, service_name) (sum by (cloud_provider, service_name, host_name) (rate(jvm_cpu_time_seconds_total[1m]) or rate(process_runtime_jvm_cpu_time_seconds_total[1m]))) * 100, 100))'
    ),
    "max_pod_ram_pct": (
        f'(max by (cloud_provider, service_name) ((sum by (cloud_provider, service_name, host_name) (jvm_memory_used_bytes{{jvm_memory_type="heap"}} or process_runtime_jvm_memory_usage_bytes{{type="heap"}} or process_runtime_jvm_memory_usage_bytes) / sum by (cloud_provider, service_name, host_name) (jvm_memory_limit_bytes{{jvm_memory_type="heap"}} or process_runtime_jvm_memory_limit_bytes{{type="heap"}} or process_runtime_jvm_memory_limit_bytes)) and on (cloud_provider, service_name, host_name) ({ACTIVE_JVM_PODS})) * 100)'
        ' or (max by (cloud_provider, service_name) ((sum by (cloud_provider, service_name) (jvm_memory_used_bytes{jvm_memory_type="heap"} or process_runtime_jvm_memory_usage_bytes{type="heap"} or process_runtime_jvm_memory_usage_bytes) / sum by (cloud_provider, service_name) (jvm_memory_limit_bytes{jvm_memory_type="heap"} or process_runtime_jvm_memory_limit_bytes{type="heap"} or process_runtime_jvm_memory_limit_bytes)) * 100))'
    ),
    "gc_pause_rate": 'sum by (cloud_provider, service_name) (rate(jvm_gc_duration_seconds_sum[1m]) or rate(process_runtime_jvm_gc_duration_seconds_sum[1m]))',
}

RAM_FLOOR_WINDOW_SECONDS = 120.0

CLOUD_VECTOR_QUERIES = {
    "wan_network_io_kbs": 'sum by (cloud_provider) (rate(system_network_io_bytes_total[1m])) / 1024',
    "wan_network_errors": 'sum by (cloud_provider) (rate(system_network_errors_total[1m]))',
}


def load_live_client(prometheus_url):
    """Return the detector's Prometheus client so training rows use the serving feature path.

    The detector replaces the 1m-rate latency/5xx values with fresh histogram
    deltas, skips cycles with failed queries and clamps GC pause rate while heap
    is low. Collecting through the same client keeps training and serving
    features identical (no training/serving skew).
    """
    ai_engine_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    if ai_engine_root not in sys.path:
        sys.path.insert(0, ai_engine_root)
    from inference.detector import PrometheusVectorClient, EXCLUDED_INFRA_SERVICES  # noqa: WPS433
    return PrometheusVectorClient(prometheus_url), EXCLUDED_INFRA_SERVICES


def main():
    parser = argparse.ArgumentParser(description="Multi-Cloud Dynamic Entity Metric Collector (V3)")
    parser.add_argument("--prometheus-url", default="http://localhost:9090", help="Prometheus API URL")
    parser.add_argument("--duration", type=int, default=2400, help="Collection duration in seconds (default 2400s = 40m)")
    parser.add_argument("--interval", type=int, default=10, help="Polling interval in seconds (default 10s)")
    parser.add_argument("--output", default="ai-engine/data/raw/multicloud_entity_baseline.csv", help="Output CSV path")
    parser.add_argument("--label", type=int, default=0, help="Ground-truth anomaly label (0=normal, 1=anomaly)")
    parser.add_argument("--summary-out", default="", help="Optional JSON file recording skipped cycles and coverage")
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
        # Provenance: whether latency came from a fresh histogram delta (as the
        # detector prefers) or from the 1m-rate fallback, and absent series.
        "server_latency_source",
        "client_latency_source",
        "missing_metrics",
        "anomaly_label",
    ]

    print("========================================================================", flush=True)
    print("  MULTI-CLOUD DYNAMIC ENTITY TELEMETRY COLLECTOR (V3)", flush=True)
    print(f"  Target Prometheus : {args.prometheus_url}", flush=True)
    print(f"  Duration          : {args.duration}s (~{args.duration/60:.1f} minutes)", flush=True)
    print(f"  Sampling Interval : {args.interval}s", flush=True)
    print(f"  Output CSV        : {args.output}", flush=True)
    print("  Feature path      : inference.detector.PrometheusVectorClient (serving parity)", flush=True)
    print("========================================================================\n", flush=True)

    client, excluded_services = load_live_client(args.prometheus_url)
    # Registered after importing the detector, which installs its own handlers.
    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    csv_file = open(args.output, "w", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    writer.writeheader()
    csv_file.flush()

    start_time = time.time()
    end_time = start_time + args.duration
    cycle_id = 0
    total_entity_rows = 0
    skipped_cycles = []
    entity_rows = collections.Counter()

    try:
        while not STOP_REQUESTED and time.time() < end_time:
            loop_start = time.time()
            now_ts = int(loop_start)
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(loop_start))
            cycle_id += 1

            entities, entity_metrics, cloud_wan = client.collect_all_entities()
            if client.query_failures or not entities:
                # A failed query must never become a row of zeros: record the gap instead.
                skipped_cycles.append({"cycle_id": cycle_id, "timestamp": now_ts, "datetime": now_iso,
                                       "reason": "query_failure" if client.query_failures else "no_entities",
                                       "failed_queries": len(client.query_failures)})
                print(f"[{now_iso}] Cycle #{cycle_id:3d} SKIPPED ({skipped_cycles[-1]['reason']}, "
                      f"{len(client.query_failures)} failed queries)", flush=True)
            summary_parts = []
            for key in entities if not client.query_failures else []:
                cp, sn = key
                if sn in excluded_services or sn.startswith("unknown_service"):
                    continue
                m = entity_metrics[key]
                eid = f"{cp}:{sn}"
                fast = client.fast_metrics.get(eid, {})
                presence = client.metric_presence.get(key, set())
                missing = sorted({"max_pod_cpu_pct", "max_pod_ram_pct", "gc_pause_rate", "qps"} - presence)
                wan = cloud_wan.get(cp, {})
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
                    "ram_floor_2m_pct": round(m["ram_floor_2m_pct"], 3),
                    "gc_pause_rate": round(m["gc_pause_rate"], 5),
                    "wan_network_io_kbs": round(wan.get("wan_network_io_kbs", 0.0), 3),
                    "wan_network_errors": round(wan.get("wan_network_errors", 0.0), 4),
                    "server_latency_source": "histogram_delta" if fast.get("server") else "rate_1m",
                    "client_latency_source": "histogram_delta" if fast.get("client") else "rate_1m",
                    "missing_metrics": ";".join(missing),
                    "anomaly_label": args.label,
                }
                writer.writerow(row)
                total_entity_rows += 1
                entity_rows[eid] += 1
                summary_parts.append(
                    f"{cp}:{sn.replace('teastore-', '')}"
                    f"(QPS={m['qps']:.1f},Srv={m['server_latency_p95']*1000:.0f}ms,"
                    f"CPU={m['max_pod_cpu_pct']:.0f}%,RAM={m['max_pod_ram_pct']:.0f}%[Flr={m['ram_floor_2m_pct']:.0f}%])"
                )

            csv_file.flush()
            elapsed = int(time.time() - start_time)
            remaining = max(0, int(end_time - time.time()))
            print(
                f"[{now_iso}] Cycle #{cycle_id:3d} ({elapsed}s/{remaining}s left) | "
                f"Entities: {len(summary_parts)} | Total Rows: {total_entity_rows:4d}",
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
        if args.summary_out:
            with open(args.summary_out, "w", encoding="utf-8") as f:
                json.dump({"output": args.output, "interval_seconds": args.interval,
                           "cycles": cycle_id, "entity_rows": total_entity_rows,
                           "rows_per_entity": dict(sorted(entity_rows.items())),
                           "skipped_cycles": skipped_cycles,
                           "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start_time)),
                           "ended_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}, f, indent=2)
        print(
            f"\n[Collector] Completed {cycle_id} cycles ({total_entity_rows} entity rows, "
            f"{len(skipped_cycles)} skipped cycles) -> {args.output}",
            flush=True
        )


if __name__ == "__main__":
    main()
