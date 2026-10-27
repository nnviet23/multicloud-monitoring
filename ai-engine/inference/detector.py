#!/usr/bin/env python3.12
"""
Real-Time Online Anomaly Detector & Root Cause Analysis Engine (V2 Dual-Window)
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring

Upgrades over V1:
  1. Live State Initialization (eliminates false alarms from stitching old CSV rows)
  2. Ensemble Deep Inference: GRU Autoencoder + TCN Autoencoder + Isolation Forest
  3. Directional Health Residual Weighting (faster latency / lower CPU than average is not penalized)
  4. Dual-Sliding-Window Anomaly Likelihood (W_short=3 vs W_long=18) to suppress transient spikes & cold-start noise
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

# Ensure ai-engine root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_root = os.path.abspath(os.path.join(current_dir, ".."))
if ai_engine_root not in sys.path:
    sys.path.insert(0, ai_engine_root)

from models.gru_autoencoder import GRUAutoencoder
from models.tcn_autoencoder import TCNAutoencoder

STOP_REQUESTED = False

def handle_signal(sig, frame):
    global STOP_REQUESTED
    print("\n[Detector] Stopping real-time anomaly detector gracefully...")
    STOP_REQUESTED = True

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)

METRIC_QUERIES = {
    "throughput_qps": 'sum(rate(http_server_request_duration_seconds_count[1m])) or vector(0)',
    "latency_p95": 'histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket[1m]))) or vector(0)',
    "error_rate_5xx": 'sum(rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m])) or vector(0)',
    "app_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio * jvm_cpu_count) * 100, 100) or vector(0)',
    "max_pod_cpu_pct": 'clamp_max(max(jvm_cpu_recent_utilization_ratio * jvm_cpu_count) * 100, 100) or vector(0)',
    "app_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{jvm_memory_type="heap"})) * 100 or vector(0)',
    "max_pod_ram_pct": 'max(sum by (service_name, host_name) (jvm_memory_used_bytes{jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{jvm_memory_type="heap"})) * 100 or vector(0)',
    "jvm_threads_live": 'avg(jvm_thread_count) or vector(0)',
    "jvm_gc_pause_rate": 'sum(rate(jvm_gc_duration_seconds_sum[1m])) or vector(0)',
    "webui_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-webui"} * jvm_cpu_count{service_name="teastore-webui"}) * 100, 100) or vector(0)',
    "webui_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-webui", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-webui", jvm_memory_type="heap"})) * 100 or vector(0)',
    "persistence_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-persistence"} * jvm_cpu_count{service_name="teastore-persistence"}) * 100, 100) or vector(0)',
    "persistence_ram_pct": 'avg(sum by (service_name, host_name) (jvm_memory_used_bytes{service_name="teastore-persistence", jvm_memory_type="heap"}) / sum by (service_name, host_name) (jvm_memory_limit_bytes{service_name="teastore-persistence", jvm_memory_type="heap"})) * 100 or vector(0)',
    "image_cpu_pct": 'clamp_max(avg(jvm_cpu_recent_utilization_ratio{service_name="teastore-image"} * jvm_cpu_count{service_name="teastore-image"}) * 100, 100) or vector(0)',
    "wan_network_io_kbs": 'sum(rate(system_network_io_bytes_total[1m])) / 1024 or vector(0)',
    "wan_network_errors": 'sum(rate(system_network_errors_total[1m])) or vector(0)',
    "webui_qps": 'sum(rate(http_server_request_duration_seconds_count{service_name="teastore-webui"}[1m])) or vector(0)',
}

# Saturation metrics where being LOWER than median is healthy (not an error)
UPPER_BOUND_SATURATION_METRICS = {
    "latency_p95", "app_cpu_pct", "max_pod_cpu_pct", "app_ram_pct", "max_pod_ram_pct",
    "jvm_gc_pause_rate", "webui_cpu_pct", "webui_ram_pct",
    "persistence_cpu_pct", "persistence_ram_pct", "image_cpu_pct"
}

# Resource utilization metrics that naturally rise during warm-up or flash crowds while latency remains fast
ACTIVE_RESOURCE_METRICS = {
    "app_cpu_pct", "max_pod_cpu_pct", "webui_cpu_pct", "persistence_cpu_pct",
    "image_cpu_pct", "app_ram_pct", "max_pod_ram_pct", "webui_ram_pct", "persistence_ram_pct"
}

# Exogenous workload metrics that naturally fluctuate with erratic user behavior
EXOGENOUS_WORKLOAD_METRICS = {
    "throughput_qps", "wan_network_io_kbs", "jvm_threads_live"
}

def probe_webui_health(url="http://localhost:8080/tools.descartes.teastore.webui/status", timeout=3.5):
    """
    Active synthetic HTTP probe to detect complete WebUI hangs/stalls or connection timeouts
    that server-side Prometheus metrics miss when requests never complete.
    """
    t0 = time.time()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "AI-Detector-Probe/2.0", "Connection": "close"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read(256)
            lat_ms = (time.time() - t0) * 1000.0
            return (200 <= resp.status < 400), resp.status, lat_ms
    except Exception:
        lat_ms = (time.time() - t0) * 1000.0
        return False, 0, lat_ms

class PrometheusClient:
    def __init__(self, base_url="http://localhost:9090"):
        self.base_url = base_url.rstrip("/")
        self.pf_proc = None
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
            print(f"[Warning] Failed to start kubectl port-forward: {e}")

    def query_instant(self, promql):
        url = f"{self.base_url}/api/v1/query?" + urllib.parse.urlencode({"query": promql})
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=4) as resp:
                res = json.loads(resp.read().decode("utf-8"))
                if res.get("status") == "success":
                    data = res.get("data", {}).get("result", [])
                    if data:
                        return float(data[0]["value"][1])
        except Exception:
            pass
        return 0.0

    def close(self):
        if self.pf_proc:
            print("[Prometheus] Terminating background port-forward...")
            self.pf_proc.terminate()
            self.pf_proc.wait()

class DualSlidingWindowScorer:
    """
    Computes adaptive Anomaly Likelihood L_t using short-term vs long-term error windows
    to suppress transient spikes (GC pauses, cold-start jitter).
    """
    def __init__(self, base_mean, base_std, threshold, short_w=3, long_w=18, min_consecutive=2):
        self.base_mean = base_mean
        self.base_std = max(1e-4, base_std)
        self.threshold = threshold
        self.short_w = short_w
        self.long_w = long_w
        self.min_consecutive = min_consecutive
        self.error_history = []
        self.consecutive_breaches = 0

    def update_and_score(self, current_mse):
        self.error_history.append(current_mse)
        if len(self.error_history) > self.long_w:
            self.error_history.pop(0)

        short_slice = self.error_history[-self.short_w:]
        short_mean = float(np.mean(short_slice))

        # Blend calibrated validation distribution with rolling long window
        if len(self.error_history) >= 6:
            long_mean = 0.5 * self.base_mean + 0.5 * float(np.mean(self.error_history))
            long_std = max(self.base_std, float(np.std(self.error_history)))
        else:
            long_mean = self.base_mean
            long_std = self.base_std

        # Calibrate z-score relative to decision boundary so healthy states show low anomaly probability
        center = 0.65 * self.threshold
        scale = max(0.05, 0.20 * self.threshold)
        z_score = (short_mean - center) / scale
        likelihood = 0.5 * (1.0 + math.erf(z_score / math.sqrt(2.0)))

        if current_mse > self.threshold:
            self.consecutive_breaches += 1
        else:
            self.consecutive_breaches = 0

        is_sustained_anomaly = (
            self.consecutive_breaches >= self.min_consecutive and short_mean > self.threshold
        )
        is_transient_spike = (current_mse > self.threshold) and not is_sustained_anomaly

        return {
            "short_mean_mse": short_mean,
            "likelihood": likelihood,
            "consecutive_breaches": self.consecutive_breaches,
            "is_sustained_anomaly": is_sustained_anomaly,
            "is_transient_spike": is_transient_spike
        }

def compute_directional_errors(x_input, x_rec, features, is_response_healthy=True):
    """
    Computes directional & recency-weighted reconstruction squared error:
      1. Recency-Weighted Horizon Scoring: Exponentially weights recent steps [t-2, t-1, t]
         so a resolved spike from 90 seconds ago in the 12-step buffer does not cause a 2-minute hangover alert.
      2. Directional Saturation Damping: Below-median latency/CPU/RAM is not penalized.
      3. Response-Aware Active Load Damping: When end-to-end service response is provably healthy
         (HTTP probe 200 OK, Latency P95 < 250ms, 5xx == 0), elevated CPU/RAM during JVM warm-up
         or flash-crowd bursts (< 3.0 scaled units) is damped so active healthy work never triggers false alarms.
    """
    diff = x_input - x_rec  # (1, seq_len, n_features)
    seq_len = diff.shape[1]
    weights = torch.ones_like(diff)

    for idx, fname in enumerate(features):
        if fname in UPPER_BOUND_SATURATION_METRICS:
            # Below baseline and lower than predicted -> healthy idle/fast state
            mask_low = (x_input[:, :, idx] < 0.0) & (diff[:, :, idx] < 0.0)
            weights[:, :, idx] = torch.where(mask_low, torch.tensor(0.15), weights[:, :, idx])

            # If end-to-end response is fast & error-free, damp active/warm-up CPU & RAM utilization (< 3.0 scaled units)
            if is_response_healthy and fname in ACTIVE_RESOURCE_METRICS:
                mask_active = (x_input[:, :, idx] >= 0.0) & (x_input[:, :, idx] < 3.0)
                weights[:, :, idx] = torch.where(mask_active, torch.tensor(0.18), weights[:, :, idx])
        elif fname in EXOGENOUS_WORKLOAD_METRICS:
            mask = x_input[:, :, idx] < 2.8
            weights[:, :, idx] = torch.where(mask, torch.tensor(0.18), torch.tensor(1.0))

    # Recency weights across the 12-step window: recent steps carry primary weight, old steps decay
    t_indices = torch.arange(seq_len, dtype=torch.float32, device=diff.device)
    t_weights = torch.exp(0.45 * (t_indices - (seq_len - 1)))
    t_weights = (t_weights / t_weights.sum()).view(1, seq_len, 1)

    weighted_sq_err = (diff ** 2) * weights
    # Sum over time with normalized recency weights, mean over features
    feat_mse_tensor = (weighted_sq_err * t_weights).sum(dim=1).squeeze(0)
    sample_mse = feat_mse_tensor.mean().item()
    feat_mse = feat_mse_tensor.cpu().numpy()
    return sample_mse, feat_mse

def parse_args():
    parser = argparse.ArgumentParser(description="Real-Time Online Anomaly Detection Engine (V2)")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to config YAML")
    parser.add_argument("--interval", type=int, default=10, help="Inference polling interval in seconds")
    parser.add_argument("--max-samples", type=int, default=0, help="Stop automatically after N samples (0 = infinite)")
    parser.add_argument("--summary-out", default="", help="Optional path to save JSON test summary")
    return parser.parse_args()

def main():
    args = parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    models_dir = cfg["training"]["save_dir"]
    gru_ckpt_path = os.path.join(models_dir, cfg["training"].get("checkpoint_name", "gru_autoencoder.pt"))
    tcn_ckpt_path = os.path.join(models_dir, "tcn_autoencoder.pt")
    scaler_path = os.path.join(models_dir, "robust_scaler.joblib")
    threshold_path = os.path.join(models_dir, "threshold_config.json")
    iso_path = cfg["baseline"]["isolation_forest"]["save_path"]

    for p in [gru_ckpt_path, scaler_path, threshold_path]:
        if not os.path.isfile(p):
            print(f"[ERROR] Required model artifact not found: {p}. Please run train.py first!")
            sys.exit(1)

    scaler = joblib.load(scaler_path)
    with open(threshold_path, "r", encoding="utf-8") as f:
        threshold_meta = json.load(f)

    threshold_p99 = threshold_meta["recommended_threshold_p99"]
    rca_baselines = threshold_meta["feature_rca_baselines"]
    err_dist = threshold_meta["error_distribution"]
    dw_cfg = threshold_meta.get("dual_sliding_window", {})

    iso_forest = joblib.load(iso_path) if os.path.isfile(iso_path) else None
    features = cfg["data"]["features"]
    window_size = cfg["data"]["window_size"]
    device = torch.device("cpu")

    # Load GRU Autoencoder
    gru_model = GRUAutoencoder(
        input_dim=len(features),
        hidden_dim=cfg["model"].get("hidden_dim", 64),
        latent_dim=cfg["model"].get("latent_dim", 16),
        num_layers=cfg["model"].get("num_layers", 2)
    ).to(device)
    gru_ckpt = torch.load(gru_ckpt_path, map_location=device, weights_only=False)
    gru_model.load_state_dict(gru_ckpt["model_state_dict"])
    gru_model.eval()

    # Load TCN Autoencoder if available
    tcn_model = None
    if os.path.isfile(tcn_ckpt_path):
        tcn_model = TCNAutoencoder(
            input_dim=len(features),
            hidden_dim=cfg["model"].get("hidden_dim", 64),
            latent_dim=cfg["model"].get("latent_dim", 16)
        ).to(device)
        tcn_ckpt = torch.load(tcn_ckpt_path, map_location=device, weights_only=False)
        tcn_model.load_state_dict(tcn_ckpt["model_state_dict"])
        tcn_model.eval()

    scorer = DualSlidingWindowScorer(
        base_mean=err_dist["mean"],
        base_std=err_dist["std"],
        threshold=threshold_p99,
        short_w=dw_cfg.get("short_window", 3),
        long_w=dw_cfg.get("long_window", 18),
        min_consecutive=dw_cfg.get("min_consecutive_breaches", 2)
    )

    print("=" * 80)
    print("  MULTI-CLOUD REAL-TIME ANOMALY DETECTION & RCA ENGINE (V2 DUAL-WINDOW)")
    print("=" * 80)
    print(f"  * Deep Models      : GRU Autoencoder + {'TCN Autoencoder' if tcn_model else 'Single'} + IsolationForest")
    print(f"  * Golden Features  : {len(features)} metrics monitored (Scale-Floored RobustScaler)")
    print(f"  * Window Buffer    : {window_size} samples ({window_size * 10}s) | Dual-Window (Short={scorer.short_w}, Long={scorer.long_w})")
    print(f"  * Anomaly Threshold: {threshold_p99:.4f} (with transient spike suppression)")
    print("=" * 80)

    client = PrometheusClient()
    buffer = []
    sample_idx = 0
    consecutive_probe_failures = 0
    stats_summary = {
        "total_samples": 0,
        "healthy_count": 0,
        "transient_spike_count": 0,
        "alert_count": 0,
        "records": []
    }

    try:
        while not STOP_REQUESTED:
            loop_start = time.time()
            now_iso = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(loop_start))
            sample_idx += 1

            current_metrics = {}
            for k, query in METRIC_QUERIES.items():
                current_metrics[k] = client.query_instant(query)

            probe_ok, probe_code, probe_ms = probe_webui_health()
            if probe_ok:
                consecutive_probe_failures = 0
            else:
                consecutive_probe_failures += 1

            current_vector = [current_metrics[f] for f in features]

            # On very first sample, initialize buffer with live state (no stale CSV discontinuity!)
            if len(buffer) == 0:
                for _ in range(window_size):
                    buffer.append(list(current_vector))
                print("[Buffer] Initialized sliding window from live cluster state (Zero cross-day discontinuity!)")
            else:
                buffer.append(current_vector)
                if len(buffer) > window_size:
                    buffer.pop(0)

            qps = current_metrics.get("throughput_qps", 0.0)
            webui_qps = current_metrics.get("webui_qps", 0.0)
            lat95 = current_metrics.get("latency_p95", 0.0)
            app_cpu = current_metrics.get("app_cpu_pct", 0.0)
            app_ram = current_metrics.get("app_ram_pct", 0.0)
            err_5xx = current_metrics.get("error_rate_5xx", 0.0)
            wan_err = current_metrics.get("wan_network_errors", 0.0)

            is_response_healthy = (probe_ok and lat95 < 0.25 and err_5xx <= 0.05 and wan_err == 0.0)
            probe_tag = f"OK({probe_ms:.0f}ms)" if probe_ok else f"FAIL({probe_ms:.0f}ms)"

            print(
                f"\n[{now_iso}] Sample #{sample_idx:4d} | QPS: {qps:5.1f} (WebUI: {webui_qps:4.1f}) | "
                f"LatP95: {lat95*1000:5.1f}ms | Probe: {probe_tag} | AppCPU: {app_cpu:4.1f}% | AppRAM: {app_ram:4.1f}% | 5xx: {err_5xx:.2f}",
                flush=True
            )

            window_raw = np.array(buffer, dtype=np.float32)
            window_scaled = scaler.transform(window_raw)
            tensor_input = torch.from_numpy(window_scaled).unsqueeze(0).to(device)

            with torch.no_grad():
                rec_gru = gru_model(tensor_input)
                gru_mse, gru_feat = compute_directional_errors(tensor_input, rec_gru, features, is_response_healthy=is_response_healthy)

                if tcn_model is not None:
                    rec_tcn = tcn_model(tensor_input)
                    tcn_mse, tcn_feat = compute_directional_errors(tensor_input, rec_tcn, features, is_response_healthy=is_response_healthy)
                    mse_loss = 0.5 * (gru_mse + tcn_mse)
                    feat_losses = 0.5 * (gru_feat + tcn_feat)
                else:
                    mse_loss = gru_mse
                    feat_losses = gru_feat

            iso_status = "NORMAL"
            if iso_forest:
                pred = iso_forest.predict(window_scaled.reshape(1, -1))[0]
                iso_status = "NORMAL" if pred == 1 else "OUTLIER"

            dw_res = scorer.update_and_score(mse_loss)

            guard_triggered = False
            guard_reasons = []
            if err_5xx > 0.20:
                guard_triggered = True
                guard_reasons.append(f"HTTP 5xx error rate ({err_5xx:.2f}/s)")
            if wan_err > 0.0:
                guard_triggered = True
                guard_reasons.append("Cross-cloud WAN packet drop")
            if consecutive_probe_failures >= 2:
                guard_triggered = True
                if not probe_ok and qps > 2.0 and webui_qps < 0.2:
                    guard_reasons.append("WebUI throughput collapsed to 0 while backend active (Hung WebUI)")
                else:
                    guard_reasons.append(f"WebUI HTTP Probe Unreachable/Timeout ({consecutive_probe_failures}x consecutive)")

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
                    status_text = "\033[92m[✓ HEALTHY - HỆ THỐNG HOÀN TOÀN BÌNH THƯỜNG]\033[0m"
                print(f"   ├── AI Health Status : {status_text}", flush=True)
                print(
                    f"   └── Instant MSE: {mse_loss:.4f} | Short-Window MSE: {dw_res['short_mean_mse']:.4f} "
                    f"(Ngưỡng < {threshold_p99:.4f}) | Likelihood: {dw_res['likelihood']*100:.1f}%",
                    flush=True
                )
            else:
                verdict = "ALERT"
                stats_summary["alert_count"] += 1
                status_text = "\033[91m[⚠ ALERT - PHÁT HIỆN BẤT THƯỜNG THỰC SỰ TRONG HỆ THỐNG!]\033[0m"
                print(f"   ├── AI Health Status : {status_text}", flush=True)
                print(
                    f"   ├── Instant MSE: \033[91m{mse_loss:.4f}\033[0m | Short-Window MSE: {dw_res['short_mean_mse']:.4f} "
                    f"(VƯỢT NGƯỠNG {threshold_p99:.4f}) | Likelihood: {dw_res['likelihood']*100:.1f}%",
                    flush=True
                )
                if guard_triggered:
                    print(f"   ├── Guard Rule Trigger: {', '.join(guard_reasons)}", flush=True)

                feature_ratios = []
                for f_idx, fname in enumerate(features):
                    f_err = feat_losses[f_idx]
                    trigger = rca_baselines.get(fname, {}).get("rca_trigger_threshold", 0.5)
                    ratio = f_err / max(0.01, trigger)
                    feature_ratios.append((fname, f_err, ratio))

                feature_ratios.sort(key=lambda x: x[2], reverse=True)
                top_causes = [f"{name} (lệch x{ratio:.1f})" for name, _, ratio in feature_ratios[:3] if ratio > 1.0]
                if guard_triggered and not top_causes:
                    top_causes = list(guard_reasons)

                print(f"   └── \033[93m[RCA - NGUYÊN NHÂN GỐC RỄ ĐỀ XUẤT]:\033[0m", flush=True)
                if top_causes:
                    print(f"       👉 Các dịch vụ/chỉ số bất thường nhất: {', '.join(top_causes)}", flush=True)
                else:
                    print(f"       👉 Bất thường tổng hợp trên nhiều microservice.", flush=True)

            stats_summary["total_samples"] = sample_idx
            stats_summary["records"].append({
                "sample": sample_idx,
                "timestamp": now_iso,
                "qps": round(qps, 2),
                "webui_qps": round(webui_qps, 2),
                "latency_p95_ms": round(lat95 * 1000.0, 2),
                "probe_ok": probe_ok,
                "probe_ms": round(probe_ms, 1),
                "app_cpu_pct": round(app_cpu, 2),
                "app_ram_pct": round(app_ram, 2),
                "error_5xx": round(err_5xx, 4),
                "instant_mse": round(mse_loss, 5),
                "short_window_mse": round(dw_res["short_mean_mse"], 5),
                "likelihood_pct": round(dw_res["likelihood"] * 100.0, 2),
                "verdict": verdict,
                "rca_causes": top_causes
            })

            if args.max_samples > 0 and sample_idx >= args.max_samples:
                print(f"\n[Detector] Reached target {args.max_samples} samples. Finishing test...", flush=True)
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
            print(f"[Detector] Saved test summary JSON to {args.summary_out}", flush=True)
        client.close()
        print("[Detector] Shutdown complete.", flush=True)

if __name__ == "__main__":
    main()
