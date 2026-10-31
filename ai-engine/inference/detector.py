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
     into Universal GRU + TCN Autoencoders + Isolation Forest.
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
import math
import time
import json
import yaml
import signal
import urllib.request
import urllib.parse
import subprocess
import argparse
import joblib
import numpy as np
import torch

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_root = os.path.abspath(os.path.join(current_dir, ".."))
if ai_engine_root not in sys.path:
    sys.path.insert(0, ai_engine_root)

from models.gru_autoencoder import GRUAutoencoder
from models.tcn_autoencoder import TCNAutoencoder
from models.scoring import (
    UPPER_BOUND_SATURATION_METRICS,
    ACTIVE_RESOURCE_METRICS,
    EXOGENOUS_WORKLOAD_METRICS,
    DualSlidingWindowScorer,
    compute_directional_errors,
    compute_batch_directional_errors,
    validate_likelihood_calibration,
)
from data.collector import (
    ENTITY_VECTOR_QUERIES,
    CLOUD_VECTOR_QUERIES,
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

STOP_REQUESTED = False


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
    except Exception:
        lat_ms = (time.time() - t0) * 1000.0
        return False, 0, lat_ms


class PrometheusVectorClient:
    def __init__(self, base_url="http://localhost:9090"):
        self.base_url = base_url.rstrip("/")
        self.pf_proc = None
        self.ram_history = {}
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

        print(f"[Prometheus] {self.base_url} not reachable. Spawning kubectl port-forward...")
        try:
            cmd = [
                "kubectl", "--context", "k3d-hub-k3d", "-n", "monitoring",
                "port-forward", "svc/prometheus-server", "9090:80"
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
        except Exception:
            pass
        return []

    def discover_entities(self):
        results = self.query_vector(ENTITY_VECTOR_QUERIES["discover"])
        entities = set()
        for item in results:
            metric = item.get("metric", {})
            cp = metric.get("cloud_provider", "").strip()
            sn = metric.get("service_name", "").strip()
            if cp and sn and sn.startswith("teastore-"):
                entities.add((cp, sn))
        return sorted(entities)

    def collect_all_entities(self):
        entities = self.discover_entities()
        entity_metrics = {
            e: {col: 0.0 for col in ENTITY_FEATURE_COLS}
            for e in entities
        }

        for col, promql in ENTITY_VECTOR_QUERIES.items():
            if col == "discover":
                continue
            results = self.query_vector(promql)
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
                    except (ValueError, KeyError, IndexError):
                        pass

        # Compute 2-minute rolling RAM floor per entity (20 samples @ 6s)
        for key, mdict in entity_metrics.items():
            hist = self.ram_history.setdefault(key, [])
            hist.append(mdict["max_pod_ram_pct"])
            if len(hist) > 20:
                hist.pop(0)
            mdict["ram_floor_2m_pct"] = float(min(hist))

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

        return entities, entity_metrics, cloud_wan

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
        }
        try:
            now_sec = int(time.time())
            start_sec = now_sec - 20
            q_str = f'{{ resource.service.name = "teastore-webui" && duration > {int(min_duration_ms)}ms }}'
            params = urllib.parse.urlencode({
                "q": q_str,
                "start": start_sec,
                "end": now_sec + 5,
                "limit": limit,
            })
            url = f"{self.base_url}/api/search?{params}"
            with urllib.request.urlopen(url, timeout=3.0) as resp:
                search_res = json.loads(resp.read().decode("utf-8"))
            traces = search_res.get("traces", [])
            if not traces:
                fallback_url = f"{self.base_url}/api/search?limit={limit}&start={start_sec}&end={now_sec + 5}"
                with urllib.request.urlopen(fallback_url, timeout=3.0) as resp:
                    traces = json.loads(resp.read().decode("utf-8")).get("traces", [])

            # Sort traces prioritizing full multi-cloud traces (with recommender & persistence) and newest startTime
            def trace_sort_key(tr):
                s_stats = tr.get("serviceStats", {})
                has_rec = 1 if "teastore-recommender" in s_stats else 0
                has_per = 1 if "teastore-persistence" in s_stats else 0
                st_nano = int(tr.get("startTimeUnixNano", 0) or 0)
                return (has_rec + has_per, st_nano)

            traces.sort(key=trace_sort_key, reverse=True)

            for tr_meta in traces[:6]:
                tid = tr_meta.get("traceID")
                if not tid:
                    continue
                t_url = f"{self.base_url}/api/traces/{tid}"
                with urllib.request.urlopen(t_url, timeout=3.0) as resp:
                    t_data = json.loads(resp.read().decode("utf-8"))
                self._decompose_single_trace(t_data, summary)
                summary["traces_inspected"] += 1
        except Exception:
            pass
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

                    if db_sys == "mysql" or name.upper().startswith("SELECT "):
                        summary["db_time_ms"] = max(summary["db_time_ms"], dur_ms)

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
    """
    def __init__(self, baselines_path, scale_floors, warmup_samples=30, clip_z=10.0):
        self.baselines_path = baselines_path
        self.scale_floors = scale_floors
        self.warmup_samples = warmup_samples
        self.clip_z = clip_z
        self.calibration_buffers = {}
        with open(baselines_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.entities = data.get("entities", data)
        self.raw_data = data

    def is_calibrated(self, entity_id):
        return entity_id in self.entities

    def update_or_standardize(self, entity_id, raw_feature_dict):
        if entity_id not in self.entities:
            buf = self.calibration_buffers.setdefault(entity_id, [])
            buf.append(dict(raw_feature_dict))
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
                    feat_stats[col] = {
                        "median": round(med, 6),
                        "iqr": round(iqr, 6),
                        "scale": round(iqr, 6),
                    }
                self.entities[entity_id] = {
                    "cloud_provider": cp,
                    "service_name": sn,
                    "sample_count": len(buf),
                    "features": feat_stats,
                }
                if "entities" in self.raw_data:
                    self.raw_data["entities"] = self.entities
                else:
                    self.raw_data[entity_id] = self.entities[entity_id]
                try:
                    with open(self.baselines_path, "w", encoding="utf-8") as f:
                        json.dump(self.raw_data, f, indent=2)
                except Exception:
                    pass
                print(f"[Auto-Calibrator] Completed 30-sample calibration for new entity: {entity_id}")
            else:
                # Provisional standardization using current buffer median + scale floor
                z_vec = []
                for col in ENTITY_FEATURE_COLS:
                    vals = np.array([b[col] for b in buf], dtype=np.float64)
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
        if wan_ms >= 65.0:
            candidates.append(
                f"[CROSS_CLOUD_WAN_DELAY] {link_name} (T_WAN={wan_ms:.0f}ms)"
            )

    if trace_summary.get("db_time_ms", 0.0) >= 80.0:
        candidates.append(
            f"[DATABASE_BOTTLENECK] azure:teastore-persistence -> MariaDB (T_DB={trace_summary['db_time_ms']:.0f}ms)"
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


def parse_args():
    parser = argparse.ArgumentParser(description="Multi-Cloud Real-Time Anomaly Detector & Trace RCA Engine (V3)")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to config YAML")
    parser.add_argument("--interval", type=int, default=6, help="Inference polling interval in seconds")
    parser.add_argument("--max-samples", type=int, default=0, help="Stop automatically after N cycles (0 = infinite)")
    parser.add_argument("--summary-out", default="", help="Optional path to save JSON test summary")
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
    iso_path = cfg["baseline"]["isolation_forest"]["save_path"]

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

    iso_forest = joblib.load(iso_path) if os.path.isfile(iso_path) else None
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
    likelihood_calibrated = bool(cal_meta.get("calibration_verified", False))

    global_scorer = DualSlidingWindowScorer(
        base_mean=err_dist["mean"],
        base_std=err_dist["std"],
        threshold=threshold_p99,
        short_w=dw_cfg.get("short_window", 2),
        long_w=dw_cfg.get("long_window", 15),
        min_consecutive=dw_cfg.get("min_consecutive_breaches", 2),
        temperature=cal_meta.get("temperature"),
    )

    print("=" * 88)
    print("  MULTI-CLOUD REAL-TIME ANOMALY DETECTOR & TRACE RCA ENGINE (V3 ENTITY-INVARIANT)")
    print("=" * 88)
    print(f"  * Deep Models      : Universal GRU + {'TCN Autoencoder' if tcn_model else 'Single'} + IsolationForest")
    print(f"  * Entity Vector    : {len(features)} universal features per (cloud_provider, service_name)")
    print(f"  * Window Buffer    : {window_size} steps | Dual-Window (Short={global_scorer.short_w}, Long={global_scorer.long_w})")
    print(f"  * Decision Bound   : {threshold_p99:.4f} | Calibrated Likelihood: {'VERIFIED' if likelihood_calibrated else 'UNVERIFIED'}")
    print("=" * 88)

    prom_client = PrometheusVectorClient()
    tempo_analyzer = TempoTraceAnalyzer()
    entity_buffers = {}
    sample_idx = 0
    consecutive_probe_failures = 0
    consecutive_slow_probes = 0

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
            probe_ok, probe_code, probe_ms = probe_webui_health()
            trace_summary = tempo_analyzer.analyze_recent_traces(min_duration_ms=40, limit=12)

            if probe_ok:
                consecutive_probe_failures = 0
            else:
                consecutive_probe_failures += 1

            if probe_ms > 500.0 or not probe_ok:
                consecutive_slow_probes += 1
            else:
                consecutive_slow_probes = 0

            webui_raw = entity_metrics.get(("aws", "teastore-webui"), {})
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
                and max(trace_summary.get("wan_links", {}).values(), default=0.0) < 60.0
            )

            entity_results = {}
            for (cp, sn) in entities:
                eid = f"{cp}:{sn}"
                if eid not in stats_summary["discovered_entities"]:
                    stats_summary["discovered_entities"].append(eid)

                raw_dict = dict(entity_metrics[(cp, sn)])
                # Fuse Tempo cross-cloud WAN transit lag (>32ms excess over 20ms baseline) into spoke client_latency_p95
                ent_wan_ms = trace_summary.get("entity_wan_ms", {}).get(eid, 0.0)
                if ent_wan_ms > 32.0:
                    excess_wan_sec = (ent_wan_ms - 22.0) / 1000.0
                    raw_dict["client_latency_p95"] = max(raw_dict["client_latency_p95"], excess_wan_sec)

                z_vec, is_cal = calibrator.update_or_standardize(eid, raw_dict)

                buf = entity_buffers.setdefault(eid, [])
                if len(buf) == 0:
                    for _ in range(window_size):
                        buf.append(z_vec.copy())
                else:
                    buf.append(z_vec.copy())
                    if len(buf) > window_size:
                        buf.pop(0)

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

            # Max entity MSE drives global anomaly scoring so a localized fault in any cloud is caught immediately
            if entity_results:
                worst_entity_id, worst_entity = max(entity_results.items(), key=lambda kv: kv[1]["mse"])
                max_entity_mse = worst_entity["mse"]
            else:
                worst_entity_id = "none"
                max_entity_mse = 0.0

            dw_res = global_scorer.update_and_score(max_entity_mse)

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
                guard_reasons.append(f"End-to-End Multi-Cloud Probe Timeout ({consecutive_probe_failures}x)")
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
            if not dw_res["is_sustained_anomaly"] and not guard_triggered:
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
                if guard_triggered:
                    print(f"   ├── SLO Guard Trigger: {', '.join(guard_reasons)}", flush=True)

                top_causes = synthesize_multicloud_rca(
                    entity_results=entity_results,
                    rca_baselines=rca_baselines,
                    features=features,
                    trace_summary=trace_summary,
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
            stats_summary["records"].append({
                "sample": sample_idx,
                "timestamp": now_iso,
                "entity_count": len(entities),
                "qps": round(total_qps, 2),
                "webui_qps": round(webui_qps, 2),
                "latency_p95_ms": round(webui_lat_ms, 2),
                "probe_ok": probe_ok,
                "probe_ms": round(probe_ms, 1),
                "error_5xx": round(total_5xx, 4),
                "worst_entity": worst_entity_id,
                "instant_mse": round(max_entity_mse, 5),
                "short_window_mse": round(dw_res["short_mean_mse"], 5),
                "likelihood_pct": round(dw_res["likelihood_pct"], 2),
                "likelihood_calibrated": likelihood_calibrated,
                "verdict": verdict,
                "model_alert": bool(dw_res["is_sustained_anomaly"]),
                "guard_reasons": guard_reasons,
                "traces_inspected": trace_summary.get("traces_inspected", 0),
                "rca_causes": top_causes,
                "tempo_wan_links": {k: round(v, 2) for k, v in trace_summary.get("wan_links", {}).items()},
                "tempo_self_times": {k: round(v, 2) for k, v in trace_summary.get("self_times", {}).items()},
                "entity_mse_map": {k: round(v["mse"], 5) for k, v in entity_results.items()},
            })

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
        prom_client.close()
        tempo_analyzer.close()
        print("[Detector] Shutdown complete.", flush=True)


if __name__ == "__main__":
    main()
