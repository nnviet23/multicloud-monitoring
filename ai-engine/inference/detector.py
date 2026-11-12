#!/usr/bin/env python3.12
"""
Multi-Cloud Real-Time Anomaly Detector & Cross-Cloud Trace RCA Engine (V3)
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring (AWS + Azure + GCP + Hub)

Key Architectural Capabilities (V3):
  1. Dynamic Multi-Cloud Entity Auto-Discovery:
     Automatically discovers all active `(cloud_provider, service_name)` entities
     from Prometheus without hardcoded service lists.
  2. Per-Entity Z-Score Standardization & Online Auto-Calibration:
     Applies entity-specific baseline standardization (and 30-sample online calibration
     for newly added clouds/microservices) before feeding 8-feature entity windows
     into Universal GRU + TCN Autoencoders, each entity scored by its own dual-window scorer.
  3. Pod Scale-Out Invariance:
     Uses `max_pod_cpu_pct`, `max_pod_ram_pct`, `ram_floor_2m_pct`, and response-aware
     damping so scaling pods (1 -> N replicas) never causes false alarms.
  4. Tempo Distributed Trace Span Decomposition (`TempoTraceAnalyzer`):
     Decomposes distributed traces across AWS, Azure, and GCP into:
       - T_WAN(Cloud_A -> Cloud_B) = T_client_span(A -> B) - T_server_span(B)
       - T_self(Cloud:Service)     = T_server_span(S) - sum(T_child_client_spans(S))
       - T_DB(Azure:MariaDB)       = sum(T_mysql_spans)
"""

import os
import sys
import html
import math
import time
import json
import yaml
import signal
import threading
import http.server
import urllib.request
import urllib.error
import urllib.parse
import subprocess
import argparse
import numpy as np
import torch

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_root = os.path.abspath(os.path.join(current_dir, ".."))
if ai_engine_root not in sys.path:
    sys.path.insert(0, ai_engine_root)

from models.gru_autoencoder import GRUAutoencoder
from models.tcn_autoencoder import TCNAutoencoder
from inference.streaming import HistogramDeltas, LatencyRecovery, TraceEvidence
from models.scoring import (
    UPPER_BOUND_SATURATION_METRICS,
    ACTIVE_RESOURCE_METRICS,
    EXOGENOUS_WORKLOAD_METRICS,
    DualSlidingWindowScorer,
    MultiEntityScorer,
    compute_directional_errors,
    compute_batch_directional_errors,
    validate_likelihood_calibration,
)
from data.collector import (
    ENTITY_VECTOR_QUERIES,
    CLOUD_VECTOR_QUERIES,
    ACTIVE_JVM_PODS,
    RAM_FLOOR_WINDOW_SECONDS,  # shared with training data collection
)

ENTITY_FEATURE_COLS = [
    "qps",
    "server_latency_p95",
    "client_latency_p95",
    "error_rate_5xx",
    "max_pod_cpu_pct",
    "max_pod_ram_pct",
    "ram_floor_2m_pct",
    "gc_pause_rate",
]

EXCLUDED_INFRA_SERVICES = {
    "otel-collector",
    "otel-collector-spoke",
    "otel-collector-hub",
    "otel-collector-edge",
    "otel-collector-gateway",
    "prometheus",
    "tempo",
    "loki",
    "grafana",
    "minio",
    "pyrra",
    "robusta",
    "coredns",
}

STOP_REQUESTED = False

# Wall-clock budget for per-trace fetches so one detector cycle cannot stall on Tempo.
TEMPO_TRACE_FETCH_BUDGET_SECONDS = 4.0


def handle_signal(sig, frame):
    global STOP_REQUESTED
    print("\n[Detector] Stopping Multi-Cloud V3 Anomaly Detector gracefully...")
    STOP_REQUESTED = True


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def probe_webui_health(url="http://localhost:8080/tools.descartes.teastore.webui/product?id=7", timeout=4.5):
    """
    Active end-to-end synthetic HTTP probe hitting the `/product?id=7` endpoint,
    which exercises the full multi-cloud call graph:
      AWS (teastore-webui, teastore-image, teastore-registry)
      -> Azure (teastore-persistence, teastore-auth, MariaDB)
      -> GCP (teastore-recommender)
    """
    t0 = time.time()
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "AI-Detector-MultiCloud-Probe/3.0", "Connection": "close"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read(512)
            lat_ms = (time.time() - t0) * 1000.0
            return (200 <= resp.status < 400), resp.status, lat_ms
    except urllib.error.HTTPError as error:
        return False, error.code, (time.time() - t0) * 1000.0
    except Exception:
        lat_ms = (time.time() - t0) * 1000.0
        return False, 0, lat_ms


class PrometheusVectorClient:
    def __init__(self, base_url="http://localhost:9090"):
        self.base_url = base_url.rstrip("/")
        self.pf_proc = None
        self.ram_history = {}
        self.histograms = HistogramDeltas()
        self.fast_metrics = {}
        self.client_entities = set()
        self.error_counters = {}
        self.query_failures = []
        self.metric_presence = {}
        self._ensure_connection()

    def _ensure_connection(self):
        try:
            req = urllib.request.Request(f"{self.base_url}/-/ready")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[Prometheus] Connected directly to {self.base_url}")
                    return
        except Exception:
            pass

        if self.base_url not in ("http://localhost:9090", "http://127.0.0.1:9090"):
            print(f"[Prometheus] Custom endpoint unavailable: {self.base_url}", flush=True)
            return
        print(f"[Prometheus] {self.base_url} not reachable. Spawning kubectl port-forward...")
        try:
            cmd = [
                "kubectl", "--context", "k3d-hub-k3d", "-n", "monitoring",
                "port-forward", "svc/prometheus", "9090:9090"
            ]
            self.pf_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(3)
            print(f"[Prometheus] Port-forward active (PID: {self.pf_proc.pid})")
        except Exception as e:
            print(f"[Warning] Failed to start Prometheus port-forward: {e}")

    def query_vector(self, promql):
        url = f"{self.base_url}/api/v1/query?" + urllib.parse.urlencode({"query": promql})
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=4) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("status") == "success":
                    return res.get("data", {}).get("result", [])
                self.query_failures.append(promql)
        except Exception:
            self.query_failures.append(promql)
        return []

    def discover_entities(self):
        results = self.query_vector(ENTITY_VECTOR_QUERIES["discover"])
        entities = set()
        for item in results:
            metric = item.get("metric", {})
            cp = metric.get("cloud_provider", "").strip()
            sn = metric.get("service_name", "").strip()
            if cp and sn and sn not in EXCLUDED_INFRA_SERVICES and not sn.startswith("unknown_service"):
                entities.add((cp, sn))
        return sorted(entities)

    def collect_all_entities(self):
        self.query_failures = []
        self.metric_presence = {}
        entities = self.discover_entities()
        if self.query_failures:
            self.fast_metrics = {}
            return [], {}, {}
        entity_metrics = {
            e: {col: 0.0 for col in ENTITY_FEATURE_COLS}
            for e in entities
        }

        for col, promql in ENTITY_VECTOR_QUERIES.items():
            if col == "discover":
                continue
            results = self.query_vector(promql)
            if self.query_failures:
                self.fast_metrics = {}
                return entities, entity_metrics, {}
            for item in results:
                m = item.get("metric", {})
                cp = m.get("cloud_provider", "").strip()
                sn = m.get("service_name", "").strip()
                key = (cp, sn)
                if key in entity_metrics:
                    try:
                        val = float(item["value"][1])
                        if not math.isnan(val) and not math.isinf(val):
                            entity_metrics[key][col] = max(0.0, val)
                            self.metric_presence.setdefault(key, set()).add(col)
                    except (ValueError, KeyError, IndexError):
                        pass

        # Rolling RAM floor over a fixed wall-clock horizon, matching the collector
        # (12 samples x 10s = 120s). A sample-count window would change meaning
        # whenever the detector polling interval differs from the training interval.
        now = time.time()
        for key, mdict in entity_metrics.items():
            hist = self.ram_history.setdefault(key, [])
            hist.append((now, mdict["max_pod_ram_pct"]))
            while hist and now - hist[0][0] > RAM_FLOOR_WINDOW_SECONDS:
                hist.pop(0)
            mdict["ram_floor_2m_pct"] = float(min(value for _, value in hist))
            if mdict["ram_floor_2m_pct"] < 68.0 and mdict["max_pod_ram_pct"] < 68.0:
                mdict["gc_pause_rate"] = min(mdict["gc_pause_rate"], 0.005)
            elif mdict["ram_floor_2m_pct"] >= 73.0:
                mdict["gc_pause_rate"] = min(mdict["gc_pause_rate"], 0.045)

        cloud_wan = {}
        for col, promql in CLOUD_VECTOR_QUERIES.items():
            results = self.query_vector(promql)
            for item in results:
                m = item.get("metric", {})
                cp = m.get("cloud_provider", "").strip()
                if cp:
                    cloud_wan.setdefault(cp, {"wan_network_io_kbs": 0.0, "wan_network_errors": 0.0})
                    try:
                        val = float(item["value"][1])
                        if not math.isnan(val) and not math.isinf(val):
                            cloud_wan[cp][col] = max(0.0, val)
                    except (ValueError, KeyError, IndexError):
                        pass

        self._collect_fresh_histograms(entities, entity_metrics)
        return entities, entity_metrics, cloud_wan

    def _collect_fresh_histograms(self, entities, metrics):
        now = time.time()
        self.fast_metrics = {}
        for side in ("server", "client"):
            dimensions = "le, cloud_provider, service_name" + (", http_response_status_code, http_status_code" if side == "server" else "")
            query = (f"sum by ({dimensions}) (http_{side}_request_duration_seconds_bucket "
                     f"and on (cloud_provider, service_name, host_name) ({ACTIVE_JVM_PODS}))")
            failures_before = len(self.query_failures)
            rows = self.query_vector(query)
            if len(self.query_failures) > failures_before:
                continue
            grouped, errors = {}, {}
            for item in rows:
                labels = item.get("metric", {})
                key = (labels.get("cloud_provider"), labels.get("service_name"))
                if key not in metrics:
                    continue
                try:
                    bound, count = float(labels["le"]), float(item["value"][1])
                except (KeyError, ValueError, IndexError):
                    continue
                if not math.isfinite(count) or count < 0:
                    continue
                buckets = grouped.setdefault(key, {})
                buckets[bound] = buckets.get(bound, 0.0) + count
                status_code = labels.get("http_response_status_code") or labels.get("http_status_code", "")
                if side == "server" and math.isinf(bound) and status_code.startswith("5"):
                    errors[key] = errors.get(key, 0.0) + count
            for key in entities:
                eid = ":".join(key)
                if side == "client" and key in grouped:
                    self.client_entities.add(eid)
                observation = self.histograms.update((eid, side), grouped.get(key, {}), now)
                entry = self.fast_metrics.setdefault(eid, {})
                entry[side] = observation
                entry["client_required"] = eid in self.client_entities
                if observation:
                    metrics[key][f"{side}_latency_p95"] = observation["value"]
                if side == "server" and key in grouped:
                    count = errors.get(key, 0.0)
                    previous = self.error_counters.get(eid)
                    if previous is None or count < previous[0]:
                        self.error_counters[eid] = (count, now, 0.0)
                        if count == 0.0:
                            metrics[key]["error_rate_5xx"] = 0.0
                    elif observation and observation.get("fresh"):
                        rate = (count - previous[0]) / max(0.001, now - previous[1])
                        self.error_counters[eid] = (count, now, rate)
                        metrics[key]["error_rate_5xx"] = rate
                    elif observation:
                        metrics[key]["error_rate_5xx"] = previous[2]

    def close(self):
        if self.pf_proc:
            self.pf_proc.terminate()
            self.pf_proc.wait()


class TempoTraceAnalyzer:
    """
    Connects to Grafana Tempo HTTP API (`/api/search` and `/api/traces/<traceID>`)
    to perform mathematical span decomposition across clouds:
      - T_WAN(src_cloud -> dst_cloud) = max(0, T_client_span - T_server_span)
      - T_self(cloud:service)         = max(0, T_server_span - sum(T_child_client_spans))
      - T_DB(azure:mariadb)           = SQL query span duration
    """
    def __init__(self, base_url="http://localhost:3200"):
        self.base_url = base_url.rstrip("/")
        self.pf_proc = None
        self.evidence = TraceEvidence()
        self._ensure_connection()

    def _ensure_connection(self):
        try:
            req = urllib.request.Request(f"{self.base_url}/api/search?limit=1")
            with urllib.request.urlopen(req, timeout=2) as resp:
                if resp.status == 200:
                    print(f"[Tempo] Connected directly to {self.base_url}")
                    return
        except Exception:
            pass

        if self.base_url not in ("http://localhost:3200", "http://127.0.0.1:3200"):
            print(f"[Tempo] Custom endpoint unavailable: {self.base_url}", flush=True)
            return
        print(f"[Tempo] {self.base_url} not reachable. Spawning kubectl port-forward...")
        try:
            cmd = [
                "kubectl", "--context", "k3d-hub-k3d", "-n", "monitoring",
                "port-forward", "svc/tempo", "3200:3200"
            ]
            self.pf_proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            time.sleep(2.5)
            print(f"[Tempo] Port-forward active (PID: {self.pf_proc.pid})")
        except Exception as e:
            print(f"[Warning] Failed to start Tempo port-forward: {e}")

    def analyze_recent_traces(self, min_duration_ms=20, limit=12):
        """
        Fetches recent distributed traces and decomposes latency into:
          - wan_links: dict of `"src_cloud->dst_cloud (dst_service)"` -> max_wan_lag_ms
          - entity_wan_ms: dict of `"cloud:service"` -> max_wan_lag_ms
          - self_times: dict of `"cloud:service"` -> max_self_time_ms
          - server_times: dict of `"cloud:service"` -> max_server_span_ms
          - db_time_ms: max SQL query duration in ms
        """
        summary = {
            "traces_inspected": 0,
            "wan_links": {},
            "entity_wan_ms": {},
            "self_times": {},
            "server_times": {},
            "db_time_ms": 0.0,
            "db_entity": "",
            "db_target": "MariaDB",
            "tempo_ok": True,
            "tempo_errors": [],
        }
        try:
            now_sec = int(time.time())
            start_sec = now_sec - 45
            q_str = f'{{ duration > {int(min_duration_ms)}ms }}'
            params = urllib.parse.urlencode({
                "q": q_str,
                "start": start_sec,
                "end": now_sec + 5,
                "limit": max(24, limit),
            })
            url = f"{self.base_url}/api/search?{params}"
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                search_res = json.loads(resp.read().decode("utf-8"))
            traces = search_res.get("traces", [])
            if not traces:
                fallback_url = f"{self.base_url}/api/search?limit={limit}&start={start_sec}&end={now_sec + 5}"
                with urllib.request.urlopen(fallback_url, timeout=3.0) as resp:
                    traces = json.loads(resp.read().decode("utf-8")).get("traces", [])

            # Sort traces prioritizing multi-service traces and newest startTime
            def trace_sort_key(tr):
                s_stats = tr.get("serviceStats", {})
                span_breadth = len(s_stats)
                st_nano = int(tr.get("startTimeUnixNano", 0) or 0)
                return (span_breadth, st_nano)

            traces.sort(key=trace_sort_key, reverse=True)

            fetch_deadline = time.time() + TEMPO_TRACE_FETCH_BUDGET_SECONDS
            for tr_meta in traces[:12]:
                tid = tr_meta.get("traceID")
                if not tid:
                    continue
                remaining = fetch_deadline - time.time()
                if remaining <= 0:
                    summary["tempo_errors"].append("trace fetch budget exhausted")
                    break
                t_url = f"{self.base_url}/api/traces/{tid}"
                try:
                    with urllib.request.urlopen(t_url, timeout=min(3.0, remaining)) as resp:
                        t_data = json.loads(resp.read().decode("utf-8"))
                except Exception as err:
                    # One unreadable trace must not discard evidence from the others.
                    summary["tempo_errors"].append(f"trace {tid}: {type(err).__name__}")
                    continue
                local = {"wan_links": {}, "entity_wan_ms": {}, "self_times": {},
                         "server_times": {}, "db_time_ms": 0.0, "db_entity": "", "db_target": "MariaDB"}
                self._decompose_single_trace(t_data, local)
                start = int(tr_meta.get("startTimeUnixNano", 0) or 0) / 1e9
                observed_at = start + float(tr_meta.get("durationMs", 0) or 0) / 1000
                self.evidence.observe(local, tid, observed_at, now_sec)
                # Old traces remain RCA evidence, never a current guard or model feature.
                if now_sec - observed_at <= 20:
                    for name in ("wan_links", "entity_wan_ms", "self_times", "server_times"):
                        for key, value in local[name].items():
                            summary[name][key] = max(summary[name].get(key, 0.0), value)
                    db_ent = local.get("db_entity") or "azure:teastore-persistence"
                    if observed_at > self.evidence.cleared_at.get(db_ent, -math.inf):
                        if local["db_time_ms"] >= summary["db_time_ms"]:
                            summary["db_time_ms"] = local["db_time_ms"]
                            summary["db_entity"] = db_ent
                            summary["db_target"] = local.get("db_target") or "MariaDB"
                summary["traces_inspected"] += 1
        except Exception as err:
            # Search failure: record it so RCA without trace evidence is visible, not silent.
            summary["tempo_ok"] = False
            summary["tempo_errors"].append(f"search: {type(err).__name__}: {err}")
        return summary

    def _decompose_single_trace(self, t_data, summary):
        spans_by_id = {}
        children_by_parent = {}

        for batch in t_data.get("batches", []):
            res_attrs = {
                a["key"]: list(a["value"].values())[0]
                for a in batch.get("resource", {}).get("attributes", [])
                if a.get("value")
            }
            cp = str(res_attrs.get("cloud.provider", "unknown"))
            sn = str(res_attrs.get("service.name", "unknown"))
            entity_id = f"{cp}:{sn}"

            scope_list = batch.get("scopeSpans") or batch.get("instrumentationLibrarySpans") or []
            for sc in scope_list:
                for sp in sc.get("spans", []):
                    sid = sp.get("spanId")
                    if not sid:
                        continue
                    pid = sp.get("parentSpanId") or ""
                    kind = sp.get("kind", "")
                    name = sp.get("name", "")
                    st_ms = int(sp.get("startTimeUnixNano", 0)) / 1e6
                    et_ms = int(sp.get("endTimeUnixNano", 0)) / 1e6
                    dur_ms = max(0.0, et_ms - st_ms)
                    sattrs = {
                        a["key"]: list(a["value"].values())[0]
                        for a in sp.get("attributes", [])
                        if a.get("value")
                    }
                    db_sys = str(sattrs.get("db.system", ""))
                    span_obj = {
                        "span_id": sid,
                        "parent_id": pid,
                        "cloud": cp,
                        "service": sn,
                        "entity_id": entity_id,
                        "kind": kind,
                        "name": name,
                        "start_ms": st_ms,
                        "end_ms": et_ms,
                        "dur_ms": dur_ms,
                        "db_system": db_sys,
                    }
                    spans_by_id[sid] = span_obj
                    if pid:
                        children_by_parent.setdefault(pid, []).append(span_obj)

                    if bool(db_sys) or name.upper().startswith(("SELECT ", "INSERT ", "UPDATE ", "DELETE ")):
                        if dur_ms >= summary["db_time_ms"]:
                            summary["db_time_ms"] = dur_ms
                            summary["db_entity"] = entity_id
                            summary["db_target"] = "MariaDB" if db_sys.lower() in ("", "mysql", "mariadb") else db_sys

        # Compute T_WAN and T_self across all SERVER spans
        server_spans = [sp for sp in spans_by_id.values() if sp["kind"] == "SPAN_KIND_SERVER"]
        for sp in server_spans:
            sid = sp["span_id"]
            entity_id = sp["entity_id"]
            srv_dur = sp["dur_ms"]
            summary["server_times"][entity_id] = max(
                summary["server_times"].get(entity_id, 0.0), srv_dur
            )

            # Method A: Direct parent CLIENT span matching
            pid = sp["parent_id"]
            if pid and pid in spans_by_id:
                parent_sp = spans_by_id[pid]
                if parent_sp["kind"] == "SPAN_KIND_CLIENT":
                    wan_lag = max(0.0, parent_sp["dur_ms"] - srv_dur)
                    link_key = f"{parent_sp['cloud']}->{sp['cloud']} ({sp['entity_id']})"
                    summary["wan_links"][link_key] = max(
                        summary["wan_links"].get(link_key, 0.0), wan_lag
                    )

            # Exclusive self-execution time
            child_client_sum = 0.0
            for ch in children_by_parent.get(sid, []):
                if ch["kind"] == "SPAN_KIND_CLIENT":
                    child_client_sum += ch["dur_ms"]
            self_ms = max(0.0, srv_dur - child_client_sum)
            summary["self_times"][entity_id] = max(
                summary["self_times"].get(entity_id, 0.0), self_ms
            )

        # Method B: Sequential Inter-Span Transit Gap Decomposition within Root Request Span
        root_candidates = [sp for sp in server_spans if not sp["parent_id"] or sp["service"] == "teastore-webui"]
        if root_candidates:
            root_sp = max(root_candidates, key=lambda x: x["dur_ms"])
            child_srvs = sorted(
                [
                    sp for sp in server_spans
                    if sp["span_id"] != root_sp["span_id"]
                    and sp["start_ms"] >= root_sp["start_ms"] - 5.0
                    and sp["end_ms"] <= root_sp["end_ms"] + 5.0
                ],
                key=lambda x: x["start_ms"],
            )
            if child_srvs:
                total_children_dur = sum(c["dur_ms"] for c in child_srvs)
                total_remote_wan_wait = 0.0
                for idx, csp in enumerate(child_srvs):
                    prev_end = root_sp["start_ms"] if idx == 0 else child_srvs[idx - 1]["end_ms"]
                    next_start = root_sp["end_ms"] if idx == len(child_srvs) - 1 else child_srvs[idx + 1]["start_ms"]
                    pre_gap = max(0.0, csp["start_ms"] - prev_end)
                    post_gap = max(0.0, next_start - csp["end_ms"])
                    # min(pre_gap, post_gap) isolates the symmetric request+response transit delay of csp's cloud
                    isolated_wan_ms = min(pre_gap, post_gap)
                    if csp["cloud"] != root_sp["cloud"]:
                        total_remote_wan_wait += pre_gap
                        summary["entity_wan_ms"][csp["entity_id"]] = max(
                            summary["entity_wan_ms"].get(csp["entity_id"], 0.0), isolated_wan_ms
                        )
                    link_key = f"{root_sp['cloud']}->{csp['cloud']} ({csp['entity_id']})"
                    summary["wan_links"][link_key] = max(
                        summary["wan_links"].get(link_key, 0.0), isolated_wan_ms
                    )
                root_self_ms = max(0.0, root_sp["dur_ms"] - total_children_dur - total_remote_wan_wait)
                summary["self_times"][root_sp["entity_id"]] = min(
                    summary["self_times"].get(root_sp["entity_id"], root_sp["dur_ms"]),
                    root_self_ms,
                )

    def close(self):
        if self.pf_proc:
            self.pf_proc.terminate()
            self.pf_proc.wait()


class EntityCalibrator:
    """
    Manages per-entity z-score standardization using `entity_baselines.json`,
    and performs automatic 30-sample online calibration whenever a brand-new
    `(cloud_provider, service_name)` entity joins the topology.

    The trained baseline file is never modified. Online calibrations are written to
    a separate runtime overlay (`<name>.runtime.json`) that is merged on start-up,
    so model artifacts stay identical to what training produced.
    """
    def __init__(self, baselines_path, scale_floors, warmup_samples=30, clip_z=10.0, runtime_path=None):
        self.baselines_path = baselines_path
        root, ext = os.path.splitext(baselines_path)
        self.runtime_path = runtime_path or f"{root}.runtime{ext or '.json'}"
        self.scale_floors = scale_floors
        self.warmup_samples = warmup_samples
        self.clip_z = clip_z
        self.calibration_buffers = {}
        self.rejected_samples = {}
        with open(baselines_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.entities = dict(data.get("entities", data))
        self.runtime_entities = {}
        if os.path.isfile(self.runtime_path):
            try:
                with open(self.runtime_path, "r", encoding="utf-8") as f:
                    overlay = json.load(f).get("entities", {})
                for eid, meta in overlay.items():
                    if eid not in self.entities:
                        self.entities[eid] = meta
                        self.runtime_entities[eid] = meta
            except (OSError, ValueError) as err:
                print(f"[Auto-Calibrator] Ignoring unreadable runtime overlay {self.runtime_path}: {err}", flush=True)

    def _persist_runtime_overlay(self):
        payload = {
            "source": "online_auto_calibration",
            "base_baselines": os.path.basename(self.baselines_path),
            "entities": self.runtime_entities,
        }
        try:
            with open(self.runtime_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except OSError as err:
            print(f"[Auto-Calibrator] Failed to write runtime overlay {self.runtime_path}: {err}", flush=True)

    def is_calibrated(self, entity_id):
        return entity_id in self.entities

    def _find_service_fallback(self, entity_id):
        _, _, sn = entity_id.partition(":")
        for k, v in self.entities.items():
            if not k.startswith("__") and k.endswith(f":{sn}") and isinstance(v, dict) and "features" in v:
                return v["features"]
        return None

    def update_or_standardize(self, entity_id, raw_feature_dict, response_healthy=None):
        """
        `response_healthy` is the caller's independent health signal (end-to-end probe,
        5xx). When it is False the sample is not used for calibration, so an entity that
        appears during an incident cannot learn the fault as its baseline.
        """
        if entity_id not in self.entities:
            fallback_meta = self._find_service_fallback(entity_id)
            buf = self.calibration_buffers.setdefault(entity_id, [])
            physically_plausible = (
                raw_feature_dict.get("max_pod_cpu_pct", 0.0) < 80.0
                and raw_feature_dict.get("server_latency_p95", 0.0) < 0.25
                and raw_feature_dict.get("error_rate_5xx", 0.0) <= 0.05
            )
            accept = fallback_meta is None or physically_plausible
            if response_healthy is not None:
                accept = accept and bool(response_healthy)
            if accept:
                buf.append(dict(raw_feature_dict))
            else:
                self.rejected_samples[entity_id] = self.rejected_samples.get(entity_id, 0) + 1
            if len(buf) >= self.warmup_samples:
                # Finalize online calibration for new entity
                cp, sn = entity_id.split(":", 1)
                feat_stats = {}
                for col in ENTITY_FEATURE_COLS:
                    vals = np.array([b[col] for b in buf], dtype=np.float64)
                    med = float(np.median(vals))
                    q25 = float(np.percentile(vals, 25))
                    q75 = float(np.percentile(vals, 75))
                    iqr = max(float(q75 - q25), float(np.std(vals)), float(self.scale_floors.get(col, 1e-3)))
                    if fallback_meta and col in fallback_meta:
                        iqr = max(iqr, float(fallback_meta[col].get("scale", iqr)))
                    feat_stats[col] = {
                        "median": round(med, 6),
                        "iqr": round(iqr, 6),
                        "scale": round(iqr, 6),
                    }
                meta = {
                    "cloud_provider": cp,
                    "service_name": sn,
                    "sample_count": len(buf),
                    "rejected_unhealthy_samples": self.rejected_samples.get(entity_id, 0),
                    "fallback_service_baseline": fallback_meta is not None,
                    "calibrated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "features": feat_stats,
                }
                self.entities[entity_id] = meta
                self.runtime_entities[entity_id] = meta
                self._persist_runtime_overlay()
                self.calibration_buffers.pop(entity_id, None)
                print(f"[Auto-Calibrator] Completed {len(buf)}-sample calibration for new entity: {entity_id}")
            elif fallback_meta:
                z_vec = []
                for col in ENTITY_FEATURE_COLS:
                    mu = float(fallback_meta[col]["median"])
                    sc = max(float(fallback_meta[col]["scale"]), float(self.scale_floors.get(col, 1e-3)))
                    z = np.clip((raw_feature_dict[col] - mu) / sc, -self.clip_z, self.clip_z)
                    z_vec.append(float(z))
                return np.array(z_vec, dtype=np.float32), True
            else:
                # Provisional standardization using current buffer median + scale floor
                z_vec = []
                for col in ENTITY_FEATURE_COLS:
                    vals = np.array([b[col] for b in buf], dtype=np.float64) if buf else np.array([raw_feature_dict[col]], dtype=np.float64)
                    med = float(np.median(vals))
                    sc = max(float(np.std(vals)), float(self.scale_floors.get(col, 1.0)))
                    z = np.clip((raw_feature_dict[col] - med) / sc, -self.clip_z, self.clip_z)
                    z_vec.append(float(z))
                return np.array(z_vec, dtype=np.float32), False

        f_meta = self.entities[entity_id]["features"]
        z_vec = []
        for col in ENTITY_FEATURE_COLS:
            mu = float(f_meta[col]["median"])
            sc = max(float(f_meta[col]["scale"]), float(self.scale_floors.get(col, 1e-3)))
            z = np.clip((raw_feature_dict[col] - mu) / sc, -self.clip_z, self.clip_z)
            z_vec.append(float(z))
        return np.array(z_vec, dtype=np.float32), True


def synthesize_multicloud_rca(
    entity_results,
    rca_baselines,
    features,
    trace_summary,
    probe_ok,
    probe_ms,
):
    """
    Combines Per-Entity Autoencoder Reconstruction Residuals + Z-Scores + Tempo Trace Span Decomposition
    to pinpoint the exact cloud, microservice, and physical root cause category.
    """
    candidates = []

    # 1. Check Tempo Span Decomposition for explicit Cross-Cloud WAN delay or Database bottleneck
    for link_name, wan_ms in sorted(trace_summary.get("wan_links", {}).items(), key=lambda x: x[1], reverse=True):
        path = link_name.split(" (", 1)[0].split("->")
        if (wan_ms >= 65.0 and len(path) == 2 and path[0] != path[1]
                and TraceEvidence.supported(link_name, entity_results)):
            evidence = trace_summary.get("wan_evidence", {}).get(link_name)
            detail = f", trace_age={evidence['age_seconds']:.0f}s" if evidence else ""
            candidates.append(
                f"[CROSS_CLOUD_WAN_DELAY] {link_name} (T_WAN={wan_ms:.0f}ms{detail})"
            )

    if trace_summary.get("db_time_ms", 0.0) >= 80.0:
        db_ev = trace_summary.get("db_evidence")
        db_ent = (db_ev.get("entity") if db_ev else None) or trace_summary.get("db_entity") or "azure:teastore-persistence"
        db_tgt = (db_ev.get("target") if db_ev else None) or trace_summary.get("db_target") or "MariaDB"
        detail = f", trace_age={db_ev['age_seconds']:.0f}s" if db_ev else ""
        candidates.append(
            f"[DATABASE_BOTTLENECK] {db_ent} -> {db_tgt} (T_DB={trace_summary['db_time_ms']:.0f}ms{detail})"
        )

    # 2. Rank entities by their AI reconstruction MSE & z-score profile
    ranked_entities = sorted(
        entity_results.items(),
        key=lambda kv: kv[1]["mse"],
        reverse=True,
    )

    for eid, res in ranked_entities:
        raw = res["raw"]
        z_map = {features[i]: float(res["z_vec"][i]) for i in range(len(features))}
        feat_losses = res["feat_losses"]

        # Check specific physical signatures on each anomalous or high-latency entity
        srv_lat_ms = raw["server_latency_p95"] * 1000.0

        # WAN attribution requires trace evidence from the cross-cloud link above.
        # A slow WebUI and an anomalous downstream service can also be caused by
        # CPU, GC or database stalls; they do not establish a network fault.

        # Signature B: Memory Leak / GC Stall
        if z_map.get("ram_floor_2m_pct", 0.0) > 2.5 and z_map.get("gc_pause_rate", 0.0) > 1.5:
            candidates.append(
                f"[MEMORY_LEAK_GC_STALL] {eid} (RAM_Floor={raw['ram_floor_2m_pct']:.1f}%, GC={raw['gc_pause_rate']:.3f}s/s)"
            )

        # Signature C: Service CPU Bottleneck
        if raw["max_pod_cpu_pct"] > 90.0 and srv_lat_ms > 150.0 and z_map.get("max_pod_cpu_pct", 0.0) > 2.0:
            self_ms = trace_summary.get("self_times", {}).get(eid, srv_lat_ms)
            candidates.append(
                f"[SERVICE_CPU_BOTTLENECK] {eid} (CPU={raw['max_pod_cpu_pct']:.1f}%, T_self={self_ms:.0f}ms)"
            )

        # Signature D: Top feature reconstruction residuals per entity
        f_ratios = []
        for idx, fname in enumerate(features):
            trig = rca_baselines.get(fname, {}).get("rca_trigger_threshold", 0.35)
            ratio = float(feat_losses[idx]) / max(0.01, trig)
            if ratio > 1.2:
                f_ratios.append((fname, ratio))
        f_ratios.sort(key=lambda x: x[1], reverse=True)
        for fname, ratio in f_ratios[:2]:
            candidates.append(f"[{eid}] {fname} (lệch x{ratio:.1f})")

    # Deduplicate while preserving order
    deduped = []
    for c in candidates:
        if c not in deduped:
            deduped.append(c)
    return deduped[:4]


class PrometheusMetricsServer:
    """
    Lightweight, embedded HTTP server serving Prometheus metrics at /metrics
    Zero additional third-party dependencies required.
    """
    def __init__(self, port=9108):
        self.port = port
        self.server = None
        self.thread = None
        self.payload = ""
        self._lock = threading.Lock()
        if port and port > 0:
            self._start()

    def update_metrics(self, payload: str):
        with self._lock:
            self.payload = payload

    def _start(self):
        parent = self

        class MetricsHandler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/metrics", "/metrics/"):
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; version=0.0.4; charset=utf-8")
                    self.end_headers()
                    with parent._lock:
                        data = parent.payload.encode("utf-8")
                    self.wfile.write(data)
                elif self.path in ("/-/healthy", "/healthz"):
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(b"OK\n")
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, format, *args):
                pass  # Suppress HTTP access logging

        try:
            self.server = http.server.ThreadingHTTPServer(("0.0.0.0", self.port), MetricsHandler)
            self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name="PrometheusMetricsServer")
            self.thread.start()
            print(f"[AIOps-Metrics] Prometheus Exporter active at http://0.0.0.0:{self.port}/metrics", flush=True)
        except Exception as err:
            print(f"[Warning] Failed to start Prometheus Metrics Server on port {self.port}: {err}", flush=True)

    def close(self):
        if self.server:
            try:
                self.server.shutdown()
                self.server.server_close()
            except Exception:
                pass


DETECTOR_VERDICTS = ("HEALTHY", "TRANSIENT_SPIKE_SUPPRESSED", "ALERT", "UNKNOWN")


def _label(value):
    """Escape a Prometheus exposition label value."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def format_prometheus_metrics(sample_record, entity_results, trace_summary, probe_ms, probe_ok):
    lines = []
    lines.append("# HELP ai_anomaly_likelihood_percent Calibrated anomaly probability (0-100) from each entity's own scorer")
    lines.append("# TYPE ai_anomaly_likelihood_percent gauge")
    for eid, res in sorted(entity_results.items()):
        if res.get("likelihood_pct") is None:
            continue
        cp, _, sn = eid.partition(":")
        lines.append(f'ai_anomaly_likelihood_percent{{cloud_provider="{_label(cp)}",service_name="{_label(sn)}",'
                     f'model="gru_tcn_ensemble"}} {res["likelihood_pct"]:.2f}')

    lines.append("# HELP ai_reconstruction_error Directional reconstruction MSE, mean of GRU and TCN autoencoders")
    lines.append("# TYPE ai_reconstruction_error gauge")
    for eid, res in sorted(entity_results.items()):
        cp, _, sn = eid.partition(":")
        mse = res.get("mse", 0.0)
        lines.append(f'ai_reconstruction_error{{cloud_provider="{_label(cp)}",service_name="{_label(sn)}",'
                     f'model="gru_tcn_ensemble"}} {mse:.6f}')

    lines.append("# HELP ai_entity_sustained_anomaly 1 when the entity's own scorer reports a sustained anomaly")
    lines.append("# TYPE ai_entity_sustained_anomaly gauge")
    for eid, res in sorted(entity_results.items()):
        cp, _, sn = eid.partition(":")
        lines.append(f'ai_entity_sustained_anomaly{{cloud_provider="{_label(cp)}",service_name="{_label(sn)}"}} '
                     f'{1 if res.get("sustained") else 0}')

    lines.append("# HELP ai_rca_component_latency_ms Decomposed latency from Tempo distributed trace spans")
    lines.append("# TYPE ai_rca_component_latency_ms gauge")
    for link, lag in trace_summary.get("wan_links", {}).items():
        lines.append(f'ai_rca_component_latency_ms{{component="wan",target="{_label(link)}"}} {lag:.2f}')
    for ent, st in trace_summary.get("self_times", {}).items():
        cp, _, sn = ent.partition(":")
        lines.append(f'ai_rca_component_latency_ms{{cloud_provider="{_label(cp)}",service_name="{_label(sn)}",component="self"}} {st:.2f}')
    db_entity = trace_summary.get("db_entity")
    if db_entity:
        cp, _, sn = db_entity.partition(":")
        lines.append(f'ai_rca_component_latency_ms{{cloud_provider="{_label(cp)}",service_name="{_label(sn)}",'
                     f'component="db",target="{_label(trace_summary.get("db_target") or "")}"}} '
                     f'{trace_summary.get("db_time_ms", 0.0):.2f}')

    lines.append("# HELP ai_detector_verdict Current detector verdict (1=active)")
    lines.append("# TYPE ai_detector_verdict gauge")
    verdict = sample_record.get("verdict", "HEALTHY")
    for name in DETECTOR_VERDICTS:
        lines.append(f'ai_detector_verdict{{verdict="{name}"}} {1 if verdict == name else 0}')

    lines.append("# HELP ai_detector_model_alert 1 when the autoencoder scorer alone reports a sustained anomaly")
    lines.append("# TYPE ai_detector_model_alert gauge")
    lines.append(f'ai_detector_model_alert {1 if sample_record.get("model_alert") else 0}')
    lines.append("# HELP ai_detector_guard_alert 1 when a deterministic SLO guard rule fired")
    lines.append("# TYPE ai_detector_guard_alert gauge")
    lines.append(f'ai_detector_guard_alert {1 if sample_record.get("guard_reasons") else 0}')

    lines.append("# HELP ai_tempo_query_ok 0 when the Tempo trace search failed this cycle (RCA lacks trace evidence)")
    lines.append("# TYPE ai_tempo_query_ok gauge")
    lines.append(f'ai_tempo_query_ok {1 if trace_summary.get("tempo_ok", True) else 0}')

    lines.append("# HELP ai_probe_latency_ms Synthetic end-to-end multi-cloud probe latency")
    lines.append("# TYPE ai_probe_latency_ms gauge")
    status_label = "ok" if probe_ok else "failed"
    lines.append(f'ai_probe_latency_ms{{status="{status_label}"}} {probe_ms:.2f}')

    return "\n".join(lines) + "\n"


RCA_RECOMMENDATIONS = (
    ("CROSS_CLOUD_WAN_DELAY", "Check the inter-cluster link / edge traffic shaping on the reported path."),
    ("DATABASE_BOTTLENECK", "Inspect slow queries and connection pool saturation on the database."),
    ("MEMORY_LEAK_GC_STALL", "Inspect heap usage and GC logs; consider a heap dump of the reported service."),
    ("SERVICE_CPU_BOTTLENECK", "Check CPU limits/throttling and scale-out of the reported service."),
)


def format_telegram_alert(entity_id, likelihood_pct, mse, verdict, causes, trace_summary, guard_reasons=None):
    """Builds an HTML-mode Telegram message. All dynamic text is escaped, so RCA strings
    containing `_`, `[`, `<` or `*` cannot break Telegram's entity parser."""
    esc = html.escape
    causes = list(causes or [])
    causes_text = "\n".join(f"  • {esc(c)}" for c in causes) if causes else "  • Uncorrelated deviation (no RCA signature matched)"
    wan_links = trace_summary.get("wan_links", {})
    top_wan = max(wan_links.values()) if wan_links else 0.0
    top_self = trace_summary.get("self_times", {}).get(entity_id, 0.0)
    db_ms = trace_summary.get("db_time_ms", 0.0)
    joined = " ".join(causes)
    recommendations = [text for tag, text in RCA_RECOMMENDATIONS if tag in joined]
    lines = [
        "🚨 <b>[AI-OPS ALERT] Multi-Cloud Anomaly Detected</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"📍 <b>Target Entity</b>: <code>{esc(entity_id)}</code>",
        f"📊 <b>Likelihood</b>: <code>{likelihood_pct:.1f}%</code> (MSE: <code>{mse:.4f}</code>)",
        f"⚡ <b>Verdict</b>: <code>{esc(verdict)}</code>",
    ]
    if guard_reasons:
        lines.append(f"🛡️ <b>SLO Guard</b>: {esc(', '.join(guard_reasons))}")
    lines += [
        "",
        f"🔍 <b>Root Cause Evidence (RCA)</b>:\n{causes_text}",
        "",
        "⏱️ <b>Tempo Trace Decomposition</b>:",
        f"  • Cross-Cloud WAN Lag: <code>{top_wan:.1f}ms</code>",
        f"  • Microservice Self-Exec: <code>{top_self:.1f}ms</code>",
        f"  • Database Query Time: <code>{db_ms:.1f}ms</code>",
    ]
    if not trace_summary.get("tempo_ok", True):
        lines.append("  • ⚠️ Tempo unavailable this cycle: trace evidence missing")
    if recommendations:
        lines += ["━━━━━━━━━━━━━━━━━━━━━━━━━━", "💡 <b>Recommendation</b>:"]
        lines += [f"  • {esc(text)}" for text in recommendations]
    return "\n".join(lines)


class TelegramAlertSink:
    """
    Sends structured AIOps alerts with Root Cause Analysis to Telegram Bot channel.
    Rate-limited per entity to avoid channel spam during sustained outages.
    """
    def __init__(self, token=None, chat_id=None, cooldown_seconds=60):
        self.token = token or os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.environ.get("TELEGRAM_CHAT_ID")
        self.cooldown_seconds = cooldown_seconds
        self.last_sent = {}

        if not self.token or self.token.startswith("CHANGE_ME"):
            self._load_env_fallback()

        self.configured = bool(self.token and self.chat_id
                               and not self.token.startswith("CHANGE_ME")
                               and not str(self.chat_id).startswith("CHANGE_ME"))
        if self.configured:
            print(f"[AIOps-Telegram] Alert Sink configured (Chat ID: {self.chat_id})", flush=True)
        else:
            print("[AIOps-Telegram] Alert Sink disabled (token/chat_id unconfigured or placeholder)", flush=True)

    def _load_env_fallback(self):
        try:
            env_path = os.path.abspath(os.path.join(ai_engine_root, "..", ".env"))
            if os.path.isfile(env_path):
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("TELEGRAM_BOT_TOKEN="):
                            self.token = line.split("=", 1)[1].strip().strip('"').strip("'")
                        elif line.startswith("TELEGRAM_CHAT_ID="):
                            self.chat_id = line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass

    def send_alert(self, entity_id, likelihood_pct, mse, verdict, causes, trace_summary, guard_reasons=None):
        if not self.configured:
            return
        now = time.time()
        last = self.last_sent.get(entity_id, 0.0)
        if now - last < self.cooldown_seconds:
            return

        msg = format_telegram_alert(entity_id, likelihood_pct, mse, verdict, causes, trace_summary, guard_reasons)

        try:
            url = f"https://api.telegram.org/bot{self.token}/sendMessage"
            payload = json.dumps({
                "chat_id": self.chat_id,
                "text": msg,
                "parse_mode": "HTML",
            }).encode("utf-8")
            req = urllib.request.Request(
                url, data=payload,
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                if resp.status == 200:
                    self.last_sent[entity_id] = now
                    print(f"[AIOps-Telegram] Alert dispatched successfully for {entity_id}", flush=True)
        except Exception as e:
            print(f"[AIOps-Telegram] Failed to send Telegram alert: {e}", flush=True)


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-Cloud Real-Time Anomaly Detector & Trace RCA Engine (V3)")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to config YAML")
    parser.add_argument("--interval", type=int, default=10, help="Inference polling interval in seconds (10s = training sampling interval)")
    parser.add_argument("--max-samples", type=int, default=0, help="Stop automatically after N cycles (0 = infinite)")
    parser.add_argument("--summary-out", default="", help="Optional path to save JSON test summary")
    parser.add_argument("--metrics-port", type=int, default=9108, help="Prometheus metrics exporter port (default 9108, 0 to disable)")
    parser.add_argument("--telegram-token", default="", help="Telegram Bot Token for alerts")
    parser.add_argument("--telegram-chat-id", default="", help="Telegram Chat ID for alerts")
    parser.add_argument("--telegram-cooldown", type=int, default=60, help="Cooldown in seconds between alerts for same entity")
    return parser.parse_args()


def main():
    args = parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    models_dir = cfg["training"]["save_dir"]
    gru_ckpt_path = os.path.join(models_dir, cfg["training"].get("checkpoint_name", "gru_autoencoder.pt"))
    tcn_ckpt_path = os.path.join(models_dir, "tcn_autoencoder.pt")
    baselines_path = os.path.join(models_dir, "entity_baselines.json")
    threshold_path = os.path.join(models_dir, "threshold_config.json")

    for p in [gru_ckpt_path, baselines_path, threshold_path]:
        if not os.path.isfile(p):
            print(f"[ERROR] Required V3 model artifact not found: {p}. Please run preprocess.py & train.py first!")
            sys.exit(1)

    with open(threshold_path, "r", encoding="utf-8") as f:
        threshold_meta = json.load(f)

    threshold_p99 = float(threshold_meta["recommended_threshold_p99"])
    rca_baselines = threshold_meta["feature_rca_baselines"]
    err_dist = threshold_meta["error_distribution"]
    dw_cfg = threshold_meta.get("dual_sliding_window", {})

    # The IsolationForest artifact produced by train.py is an offline baseline only;
    # it is intentionally not part of the online verdict.
    features = cfg["data"]["features"]
    window_size = int(cfg["data"]["window_size"])
    scale_floors = cfg["data"].get("physical_scale_floors", cfg["data"].get("scale_floors", {}))
    warmup_samples = int(cfg["data"].get("auto_calibration_samples", 30))
    device = torch.device("cpu")

    calibrator = EntityCalibrator(
        baselines_path=baselines_path,
        scale_floors=scale_floors,
        warmup_samples=warmup_samples,
        clip_z=10.0,
    )

    gru_model = GRUAutoencoder(
        input_dim=len(features),
        hidden_dim=cfg["model"].get("hidden_dim", 64),
        latent_dim=cfg["model"].get("latent_dim", 16),
        num_layers=cfg["model"].get("num_layers", 2),
    ).to(device)
    gru_ckpt = torch.load(gru_ckpt_path, map_location=device, weights_only=False)
    gru_model.load_state_dict(gru_ckpt["model_state_dict"])
    gru_model.eval()

    tcn_model = None
    if os.path.isfile(tcn_ckpt_path):
        tcn_model = TCNAutoencoder(
            input_dim=len(features),
            hidden_dim=cfg["model"].get("hidden_dim", 64),
            latent_dim=cfg["model"].get("latent_dim", 16),
        ).to(device)
        tcn_ckpt = torch.load(tcn_ckpt_path, map_location=device, weights_only=False)
        tcn_model.load_state_dict(tcn_ckpt["model_state_dict"])
        tcn_model.eval()

    cal_meta = threshold_meta.get("likelihood_calibration", {})
    likelihood_calibrated = bool(cal_meta.get("calibration_verified", False)
        and cal_meta.get("score_input") == "min(current_mse,short_mean_mse)")

    def make_scorer():
        return DualSlidingWindowScorer(
            base_mean=err_dist["mean"],
            base_std=err_dist["std"],
            threshold=threshold_p99,
            short_w=dw_cfg.get("short_window", 3),
            long_w=dw_cfg.get("long_window", 18),
            min_consecutive=dw_cfg.get("min_consecutive_breaches", 2),
            temperature=cal_meta.get("temperature"),
        )

    # One scorer per entity: consecutive breaches must come from the same entity,
    # and one entity's error history never leaks into another's likelihood.
    entity_scorers = MultiEntityScorer(make_scorer)
    reference_scorer = make_scorer()

    print("=" * 88)
    print("  MULTI-CLOUD REAL-TIME ANOMALY DETECTOR & TRACE RCA ENGINE (V3 ENTITY-INVARIANT)")
    print("=" * 88)
    print(f"  * Deep Models      : GRU{' + TCN' if tcn_model else ''} Autoencoder ensemble (per-entity scoring)")
    print(f"  * Entity Vector    : {len(features)} universal features per (cloud_provider, service_name)")
    print(f"  * Window Buffer    : {window_size} steps | Dual-Window (Short={reference_scorer.short_w}, Long={reference_scorer.long_w})")
    print(f"  * Decision Bound   : {threshold_p99:.4f} | Calibrated Likelihood: {'VERIFIED' if likelihood_calibrated else 'UNVERIFIED'}")
    print("=" * 88)

    endpoints = cfg.get("observability_endpoints", {})
    prom_client = PrometheusVectorClient(endpoints.get("prometheus_url", "http://localhost:9090"))
    tempo_analyzer = TempoTraceAnalyzer(endpoints.get("tempo_url", "http://localhost:3200"))
    metrics_server = PrometheusMetricsServer(port=args.metrics_port) if args.metrics_port > 0 else None
    alert_sink = TelegramAlertSink(
        token=args.telegram_token,
        chat_id=args.telegram_chat_id,
        cooldown_seconds=args.telegram_cooldown,
    )
    entity_buffers = {}
    recovery = LatencyRecovery()
    sample_idx = 0
    consecutive_probe_failures = 0
    consecutive_slow_probes = 0
    # Records are only needed for --summary-out; an unbounded list would grow forever
    # in the default infinite (--max-samples 0) mode.
    keep_records = bool(args.summary_out)

    stats_summary = {
        "total_samples": 0,
        "healthy_count": 0,
        "transient_spike_count": 0,
        "alert_count": 0,
        "likelihood_calibrated": likelihood_calibrated,
        "discovered_entities": [],
        "records": [],
    }

    try:
        while not STOP_REQUESTED:
            loop_start = time.time()
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(loop_start))
            sample_idx += 1

            entities, entity_metrics, cloud_wan = prom_client.collect_all_entities()
            discovered_ids = {":".join(entity) for entity in entities}
            discovered_services = {sn for _, sn in entities}
            explicit_required = cfg.get("inference", {}).get("required_entities")
            if explicit_required:
                missing_entities = sorted(set(explicit_required) - discovered_ids)
            else:
                missing_entities = sorted(
                    eid for eid in calibrator.entities
                    if not eid.startswith("__")
                    and eid not in discovered_ids
                    and eid.split(":", 1)[-1] not in discovered_services
                )
            telemetry_ok = bool(entities) and not missing_entities and not prom_client.query_failures and all(
                {"max_pod_cpu_pct", "max_pod_ram_pct"} <= prom_client.metric_presence.get(entity, set())
                for entity in entities)
            probe_ok, probe_code, probe_ms = probe_webui_health(endpoints.get(
                "webui_probe_url", "http://localhost:8080/tools.descartes.teastore.webui/product?id=7"))
            trace_summary = tempo_analyzer.analyze_recent_traces(min_duration_ms=40, limit=12)

            if probe_ok:
                consecutive_probe_failures = 0
            else:
                consecutive_probe_failures += 1

            if probe_ms > 500.0 or not probe_ok:
                consecutive_slow_probes += 1
            else:
                consecutive_slow_probes = 0

            entrypoint_key = next(
                (k for k in entities if k == ("aws", "teastore-webui") or k[1].endswith(("webui", "frontend", "gateway"))),
                max(entities, key=lambda k: entity_metrics[k].get("qps", 0.0), default=None),
            )
            webui_raw = entity_metrics.get(entrypoint_key, {}) if entrypoint_key else {}
            webui_qps = webui_raw.get("qps", 0.0)
            webui_lat_ms = webui_raw.get("server_latency_p95", 0.0) * 1000.0
            total_qps = sum(m.get("qps", 0.0) for m in entity_metrics.values())
            total_5xx = sum(m.get("error_rate_5xx", 0.0) for m in entity_metrics.values())
            total_wan_drops = sum(w.get("wan_network_errors", 0.0) for w in cloud_wan.values())

            is_cluster_response_healthy = (
                probe_ok
                and probe_ms < 480.0
                and webui_lat_ms < 520.0
                and total_5xx <= 0.05
                and total_wan_drops == 0.0
            )

            entity_results = {}
            refreshed_entities = []
            cpu_refreshed_entities = []
            db_caller_entity = trace_summary.get("db_entity") or "azure:teastore-persistence"
            for (cp, sn) in entities if telemetry_ok else []:
                eid = f"{cp}:{sn}"
                if eid not in stats_summary["discovered_entities"]:
                    stats_summary["discovered_entities"].append(eid)

                raw_dict = dict(entity_metrics[(cp, sn)])
                # Fuse Tempo cross-cloud WAN transit lag (>32ms excess over 20ms baseline) into spoke client_latency_p95
                ent_wan_ms = trace_summary.get("entity_wan_ms", {}).get(eid, 0.0)
                fresh = prom_client.fast_metrics.get(eid, {})
                if ent_wan_ms > 32.0 and not fresh.get("client"):
                    excess_wan_sec = (ent_wan_ms - 22.0) / 1000.0
                    raw_dict["client_latency_p95"] = max(raw_dict["client_latency_p95"], excess_wan_sec)
                if eid == db_caller_entity and trace_summary.get("db_time_ms", 0.0) >= 80.0:
                    raw_dict["server_latency_p95"] = max(
                        raw_dict["server_latency_p95"],
                        trace_summary["db_time_ms"] / 1000.0,
                    )

                z_vec, is_cal = calibrator.update_or_standardize(
                    eid, raw_dict,
                    response_healthy=is_cluster_response_healthy and raw_dict["error_rate_5xx"] <= 0.05,
                )

                buf = entity_buffers.setdefault(eid, [])
                if len(buf) == 0:
                    for _ in range(window_size):
                        buf.append(z_vec.copy())
                else:
                    buf.append(z_vec.copy())
                    if len(buf) > window_size:
                        buf.pop(0)

                confirmed = recovery.update(
                    eid, fresh.get("server"), fresh.get("client"),
                    probe_ok and telemetry_ok, probe_ms, raw_dict["error_rate_5xx"],
                    client_required=fresh.get("client_required", False))
                if confirmed and raw_dict["server_latency_p95"] < 0.25:
                    tempo_analyzer.evidence.forget(eid, loop_start)
                latency_indices = [features.index(name) for name in ("server_latency_p95", "client_latency_p95", "error_rate_5xx")]
                if confirmed and any(row[index] > 2.0 for row in buf for index in latency_indices):
                    recovery.refresh_latency_history(buf, z_vec, features,
                        include_errors=(recovery.state[eid]["count"] >= recovery.confirmations
                                        or recovery.state[eid]["probes"] >= recovery.confirmations))
                    refreshed_entities.append(eid)
                if recovery.refresh_cpu_history(buf, z_vec, features, raw_dict["max_pod_cpu_pct"],
                                                 confirmed and bool(fresh.get("server", {}).get("fresh") if fresh.get("server") else False)):
                    cpu_refreshed_entities.append(eid)

                win_np = np.array(buf, dtype=np.float32)
                tensor_in = torch.from_numpy(win_np).unsqueeze(0).to(device)

                entity_healthy = (
                    is_cluster_response_healthy
                    and raw_dict["server_latency_p95"] < 0.50
                    and raw_dict["client_latency_p95"] < 0.05
                    and raw_dict["error_rate_5xx"] <= 0.05
                )

                with torch.no_grad():
                    rec_gru = gru_model(tensor_in)
                    g_mse, g_feat = compute_directional_errors(
                        tensor_in, rec_gru, features, is_response_healthy=entity_healthy
                    )
                    if tcn_model is not None:
                        rec_tcn = tcn_model(tensor_in)
                        t_mse, t_feat = compute_directional_errors(
                            tensor_in, rec_tcn, features, is_response_healthy=entity_healthy
                        )
                        e_mse = 0.5 * (g_mse + t_mse)
                        e_feat = 0.5 * (g_feat + t_feat)
                    else:
                        e_mse = g_mse
                        e_feat = g_feat

                entity_results[eid] = {
                    "mse": float(e_mse),
                    "feat_losses": e_feat,
                    "z_vec": z_vec,
                    "raw": raw_dict,
                    "calibrated": is_cal,
                }

            # Each entity is scored by its own dual-window scorer. A repeated export
            # (same histogram timestamps and resource readings) is not new evidence.
            if entity_results:
                worst_entity_id, worst_entity = max(entity_results.items(), key=lambda kv: kv[1]["mse"])
                max_entity_mse = worst_entity["mse"]
            else:
                worst_entity_id = "none"
                max_entity_mse = 0.0

            observations = {}
            for eid, res in entity_results.items():
                fast = prom_client.fast_metrics.get(eid, {})
                token = (*(fast[side].get("observed_at") if fast.get(side) else None for side in ("server", "client")),
                         *(res["raw"].get(name) for name in ("max_pod_cpu_pct", "max_pod_ram_pct",
                                                              "ram_floor_2m_pct", "gc_pause_rate")))
                observations[eid] = (res["mse"], token)
            per_entity_scores = entity_scorers.update(observations) if telemetry_ok else {}
            for eid, score in per_entity_scores.items():
                entity_results[eid]["likelihood_pct"] = score["likelihood_pct"]
                entity_results[eid]["sustained"] = score["is_sustained_anomaly"]
            dw_res = MultiEntityScorer.aggregate(per_entity_scores)
            alert_entity_id = dw_res["entity"] or worst_entity_id

            rca_trace_summary = dict(trace_summary)
            evidence = tempo_analyzer.evidence.active(entity_results, time.time())
            db_evidence = tempo_analyzer.evidence.active_db(entity_results, time.time())
            rca_trace_summary["wan_evidence"] = evidence
            rca_trace_summary["db_evidence"] = db_evidence
            rca_trace_summary["wan_links"] = {**trace_summary["wan_links"],
                                             **{key: value["delay_ms"] for key, value in evidence.items()}}
            if db_evidence:
                rca_trace_summary["db_time_ms"] = max(
                    rca_trace_summary.get("db_time_ms", 0.0),
                    db_evidence["db_time_ms"],
                )

            # Guard rules for deterministic multi-cloud SLO violations (e.g. sustained WAN delay or 5xx)
            guard_triggered = False
            guard_reasons = []
            if total_5xx > 0.20:
                guard_triggered = True
                guard_reasons.append(f"HTTP 5xx error rate ({total_5xx:.2f}/s)")
            if total_wan_drops > 0.0:
                guard_triggered = True
                guard_reasons.append("Cross-cloud WAN packet drop")
            if consecutive_probe_failures >= 2:
                guard_triggered = True
                guard_reasons.append(f"End-to-End Multi-Cloud Probe Failure (HTTP {probe_code}, {consecutive_probe_failures}x)")
            if consecutive_slow_probes >= 2 and (
                max(trace_summary.get("wan_links", {}).values(), default=0.0) >= 65.0
                or probe_ms >= 500.0
                or webui_lat_ms >= 550.0
            ):
                guard_triggered = True
                guard_reasons.append(
                    f"Sustained Cross-Cloud Latency SLO Breach (Probe={probe_ms:.0f}ms, WebUI_P95={webui_lat_ms:.0f}ms)"
                )

            probe_tag = f"OK({probe_ms:.0f}ms)" if probe_ok else f"FAIL({probe_ms:.0f}ms)"
            print(
                f"\n[{now_iso}] Sample #{sample_idx:4d} | Entities: {len(entities)} | TotalQPS: {total_qps:5.1f} "
                f"(WebUI: {webui_qps:4.1f}) | WebUI_P95: {webui_lat_ms:5.1f}ms | Probe: {probe_tag} | "
                f"WorstEntity: {worst_entity_id} (MSE={max_entity_mse:.4f})",
                flush=True,
            )

            verdict = "HEALTHY"
            top_causes = []
            if not telemetry_ok and not guard_triggered:
                verdict = "UNKNOWN"
                print("   └── Telemetry unavailable/incomplete; AI health is UNKNOWN", flush=True)
            elif not dw_res["is_sustained_anomaly"] and not guard_triggered:
                if dw_res["is_transient_spike"] or not probe_ok:
                    verdict = "TRANSIENT_SPIKE_SUPPRESSED"
                    stats_summary["transient_spike_count"] += 1
                    status_text = "\033[93m[~ TRANSIENT SPIKE - DAO ĐỘNG TỨC THỜI (ĐÃ LỌC BÁO ĐỘNG GIẢ)]\033[0m"
                else:
                    verdict = "HEALTHY"
                    stats_summary["healthy_count"] += 1
                    status_text = "\033[92m[✓ HEALTHY - ĐA ĐÁM MÂY HOẠT ĐỘNG BÌNH THƯỜNG]\033[0m"
                print(f"   ├── AI Health Status : {status_text}", flush=True)
                print(
                    f"   └── Max Entity MSE: {max_entity_mse:.4f} ({worst_entity_id}) | "
                    f"Short-Window MSE: {dw_res['short_mean_mse']:.4f} (Ngưỡng < {threshold_p99:.4f}) | "
                    f"Likelihood: {dw_res['likelihood']*100:.1f}%",
                    flush=True,
                )
            else:
                verdict = "ALERT"
                stats_summary["alert_count"] += 1
                status_text = "\033[91m[⚠ ALERT - PHÁT HIỆN BẤT THƯỜNG XUYÊN ĐÁM MÂY!]\033[0m"
                print(f"   ├── AI Health Status : {status_text}", flush=True)
                print(
                    f"   ├── Max Entity MSE: \033[91m{max_entity_mse:.4f}\033[0m ({worst_entity_id}) | "
                    f"Short-Window MSE: {dw_res['short_mean_mse']:.4f} (Ngưỡng {threshold_p99:.4f}) | "
                    f"Likelihood: {dw_res['likelihood']*100:.1f}%",
                    flush=True,
                )
                if dw_res["sustained_entities"]:
                    print(f"   ├── Model Sustained  : {', '.join(dw_res['sustained_entities'])}", flush=True)
                if guard_triggered:
                    print(f"   ├── SLO Guard Trigger: {', '.join(guard_reasons)}", flush=True)
                if not trace_summary.get("tempo_ok", True):
                    print("   ├── Tempo unavailable: RCA has no trace evidence this cycle", flush=True)

                top_causes = synthesize_multicloud_rca(
                    entity_results=entity_results,
                    rca_baselines=rca_baselines,
                    features=features,
                    trace_summary=rca_trace_summary,
                    probe_ok=probe_ok,
                    probe_ms=probe_ms,
                )
                if not top_causes and guard_reasons:
                    top_causes = list(guard_reasons)

                if trace_summary.get("wan_links"):
                    wan_str = ", ".join(
                        f"{k}: {v:.1f}ms"
                        for k, v in sorted(trace_summary["wan_links"].items(), key=lambda x: x[1], reverse=True)[:3]
                    )
                    print(f"   ├── Tempo Trace WAN  : {wan_str}", flush=True)
                if trace_summary.get("self_times"):
                    self_str = ", ".join(
                        f"{k}: {v:.1f}ms"
                        for k, v in sorted(trace_summary["self_times"].items(), key=lambda x: x[1], reverse=True)[:3]
                    )
                    print(f"   ├── Tempo Self-Exec  : {self_str}", flush=True)

                print("   └── \033[93m[RCA - KHOANH VÙNG NGUYÊN NHÂN GỐC RỄ XUYÊN CLOUD]:\033[0m", flush=True)
                if top_causes:
                    print(f"       👉 {', '.join(top_causes)}", flush=True)
                else:
                    print(f"       👉 Bất thường tại thực thể {worst_entity_id}", flush=True)

            stats_summary["total_samples"] = sample_idx
            rec = {
                "sample": sample_idx,
                "timestamp": now_iso,
                "entity_count": len(entities),
                "qps": round(total_qps, 2),
                "webui_qps": round(webui_qps, 2),
                "latency_p95_ms": round(webui_lat_ms, 2),
                "probe_ok": probe_ok,
                "probe_code": probe_code,
                "probe_ms": round(probe_ms, 1),
                "error_5xx": round(total_5xx, 4),
                "worst_entity": worst_entity_id,
                "alert_entity": alert_entity_id,
                "model_sustained_entities": dw_res["sustained_entities"],
                "instant_mse": round(max_entity_mse, 5),
                "short_window_mse": round(dw_res["short_mean_mse"], 5),
                "likelihood_pct": round(dw_res["likelihood_pct"], 2) if telemetry_ok else None,
                "window_likelihood_pct": dw_res.get("window_likelihood_pct") if telemetry_ok else None,
                "likelihood_calibrated": likelihood_calibrated,
                "verdict": verdict,
                "model_alert": bool(dw_res["is_sustained_anomaly"]),
                "telemetry_complete": telemetry_ok,
                "query_failures": len(prom_client.query_failures),
                "missing_entities": missing_entities,
                "latency_history_refreshed": refreshed_entities,
                "cpu_history_refreshed": cpu_refreshed_entities,
                "fast_metrics": prom_client.fast_metrics,
                "rca_evidence": evidence,
                "guard_reasons": guard_reasons,
                "traces_inspected": trace_summary.get("traces_inspected", 0),
                "tempo_ok": trace_summary.get("tempo_ok", True),
                "tempo_errors": trace_summary.get("tempo_errors", []),
                "rca_causes": top_causes,
                "tempo_wan_links": {k: round(v, 2) for k, v in trace_summary.get("wan_links", {}).items()},
                "tempo_self_times": {k: round(v, 2) for k, v in trace_summary.get("self_times", {}).items()},
                "entity_mse_map": {k: round(v["mse"], 5) for k, v in entity_results.items()},
                "entity_likelihood_pct": {k: v["likelihood_pct"] for k, v in entity_results.items()
                                          if v.get("likelihood_pct") is not None},
            }
            if keep_records:
                stats_summary["records"].append(rec)

            if metrics_server:
                prom_text = format_prometheus_metrics(rec, entity_results, trace_summary, probe_ms, probe_ok)
                metrics_server.update_metrics(prom_text)

            if verdict == "ALERT" and alert_sink.configured:
                alert_result = entity_results.get(alert_entity_id, {})
                alert_sink.send_alert(
                    entity_id=alert_entity_id,
                    likelihood_pct=float(alert_result.get("likelihood_pct", dw_res.get("likelihood_pct", 0.0)) or 0.0),
                    mse=float(alert_result.get("mse", max_entity_mse)),
                    verdict=verdict,
                    causes=top_causes,
                    trace_summary=rca_trace_summary,
                    guard_reasons=guard_reasons,
                )

            if args.max_samples > 0 and sample_idx >= args.max_samples:
                print(f"\n[Detector] Reached target {args.max_samples} samples. Finishing run...", flush=True)
                break

            elapsed = time.time() - loop_start
            sleep_sec = max(0.1, args.interval - elapsed)
            time.sleep(sleep_sec)

    except KeyboardInterrupt:
        handle_signal(None, None)
    finally:
        if args.summary_out:
            os.makedirs(os.path.dirname(os.path.abspath(args.summary_out)), exist_ok=True)
            with open(args.summary_out, "w", encoding="utf-8") as f:
                json.dump(stats_summary, f, indent=2)
            print(f"[Detector] Saved V3 test summary JSON to {args.summary_out}", flush=True)
        if metrics_server:
            metrics_server.close()
        prom_client.close()
        tempo_analyzer.close()
        print("[Detector] Shutdown complete.", flush=True)


if __name__ == "__main__":
    main()
