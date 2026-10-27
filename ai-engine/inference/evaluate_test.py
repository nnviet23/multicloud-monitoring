#!/usr/bin/env python3.12
"""
Automated Ground-Truth Evaluator & Fault-Injection Benchmark for Multi-Cloud AI Detector
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring

Performs:
  1. Timestamp alignment between Traffic Generator logs and AI Detector summary JSON
  2. Ground-truth classification:
     - ACTUAL_ANOMALY: Client request failure rate > 15% OR Latency P95 > 400ms
                       OR HTTP 5xx > 0.2/s OR >=2 consecutive probe failures
     - ACTUAL_HEALTHY: Server processing requests normally
  3. Multi-Scenario Fault-Injection Benchmark (--benchmark) to verify 0% False Alarms
     on healthy erratic traffic and 100% Detection + RCA accuracy on real faults.
"""

import os
import re
import sys
import json
import yaml
import joblib
import argparse
import numpy as np
import torch
from datetime import datetime, timedelta

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_root = os.path.abspath(os.path.join(current_dir, ".."))
if ai_engine_root not in sys.path:
    sys.path.insert(0, ai_engine_root)

from models.gru_autoencoder import GRUAutoencoder
from models.tcn_autoencoder import TCNAutoencoder
from inference.detector import compute_directional_errors, DualSlidingWindowScorer

def parse_traffic_log(log_path, start_dt_utc):
    windows = []
    prev_succ = 0
    prev_fail = 0
    pattern = re.compile(
        r"\[\s*(\d+)s/\s*\d+s left\s*\|\s*([^\]]+)\]\s*Active Users:\s*(\d+)\s*\|\s*QPS:\s*([\d.]+)\s*\|\s*Total:\s*(\d+)\s*\|\s*Success:\s*(\d+)\s*\|\s*Fail:\s*(\d+)"
    )
    if not os.path.isfile(log_path):
        return windows

    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            clean = re.sub(r"\x1b\[[0-9;]*m", "", line)
            m = pattern.search(clean)
            if m:
                elapsed = int(m.group(1))
                phase = m.group(2).strip()
                users = int(m.group(3))
                qps = float(m.group(4))
                succ = int(m.group(6))
                fail = int(m.group(7))
                d_succ = succ - prev_succ
                d_fail = fail - prev_fail
                prev_succ = succ
                prev_fail = fail
                total_w = d_succ + d_fail
                fail_rate = (d_fail / total_w) if total_w > 0 else 0.0
                ts = start_dt_utc + timedelta(seconds=elapsed)
                windows.append({
                    "elapsed": elapsed,
                    "timestamp_dt": ts,
                    "phase": phase,
                    "users": users,
                    "client_qps": qps,
                    "ok_delta": d_succ,
                    "fail_delta": d_fail,
                    "fail_rate": fail_rate
                })
    return windows

def find_closest_traffic_window(sample_dt, traffic_windows):
    if not traffic_windows:
        return None
    best = min(traffic_windows, key=lambda w: abs((w["timestamp_dt"] - sample_dt).total_seconds()))
    if abs((best["timestamp_dt"] - sample_dt).total_seconds()) <= 15.0:
        return best
    return None

def evaluate_run(summary_json_path, traffic_log_path="", traffic_start_iso=""):
    with open(summary_json_path, "r", encoding="utf-8") as f:
        summary = json.load(f)

    records = summary.get("records", [])
    if not records:
        print("[Error] No records found in summary JSON.")
        return

    traffic_windows = []
    if traffic_log_path and os.path.isfile(traffic_log_path):
        if traffic_start_iso:
            start_dt = datetime.strptime(traffic_start_iso, "%Y-%m-%dT%H:%M:%SZ")
        else:
            first_dt = datetime.strptime(records[0]["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
            start_dt = first_dt - timedelta(seconds=10)
        traffic_windows = parse_traffic_log(traffic_log_path, start_dt)

    tp, tn, fp, fn = 0, 0, 0, 0
    consec_probe_fail = 0

    for r in records:
        s_dt = datetime.strptime(r["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        tw = find_closest_traffic_window(s_dt, traffic_windows)

        fail_rate = tw["fail_rate"] if tw else 0.0
        fail_delta = tw["fail_delta"] if tw else 0

        probe_ok = r.get("probe_ok", True)
        if not probe_ok:
            consec_probe_fail += 1
        else:
            consec_probe_fail = 0

        lat_ms = r.get("latency_p95_ms", 0.0)
        err_5xx = r.get("error_5xx", 0.0)

        actual_fault = (
            (tw is not None and fail_rate > 0.15 and fail_delta >= 5)
            or (lat_ms > 400.0)
            or (err_5xx > 0.20)
            or (consec_probe_fail >= 2)
        )
        ai_alert = (r["verdict"] == "ALERT")

        if actual_fault and ai_alert:
            tp += 1
        elif not actual_fault and not ai_alert:
            tn += 1
        elif not actual_fault and ai_alert:
            fp += 1
        else:
            fn += 1

    total = len(records)
    healthy_total = tn + fp
    fault_total = tp + fn
    fpr = (fp / healthy_total * 100.0) if healthy_total > 0 else 0.0
    tpr = (tp / fault_total * 100.0) if fault_total > 0 else 100.0
    acc = ((tp + tn) / total * 100.0) if total > 0 else 0.0

    print("=" * 92)
    print("  GROUND-TRUTH EVALUATION REPORT (LIVE TRAFFIC vs AI DETECTOR)")
    print("=" * 92)
    print(f"  Total Samples          : {total}")
    print(f"  Ground-Truth Healthy   : {healthy_total:2d} samples | True Negative (TN): {tn:2d} | False Positive (FP): {fp:2d}")
    print(f"  Ground-Truth Faulty    : {fault_total:2d} samples | True Positive (TP): {tp:2d} | False Negative (FN): {fn:2d}")
    print("-" * 92)
    print(f"  * Overall Accuracy     : {acc:5.1f}%")
    print(f"  * False Alarm Rate(FPR): {fpr:5.1f}% (Mục tiêu: 0.0% khi server ổn định)")
    if fault_total > 0:
        print(f"  * Fault Recall   (TPR) : {tpr:5.1f}%")
    print("=" * 92)

def run_fault_injection_benchmark(config_path="ai-engine/configs/model_config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    models_dir = cfg["training"]["save_dir"]
    scaler = joblib.load(os.path.join(models_dir, "robust_scaler.joblib"))
    with open(os.path.join(models_dir, "threshold_config.json"), "r", encoding="utf-8") as f:
        t_meta = json.load(f)

    features = cfg["data"]["features"]
    threshold = t_meta["recommended_threshold_p99"]
    rca_baselines = t_meta["feature_rca_baselines"]
    device = torch.device("cpu")

    gru_model = GRUAutoencoder(input_dim=len(features)).to(device)
    gru_model.load_state_dict(torch.load(os.path.join(models_dir, "gru_autoencoder.pt"), map_location=device, weights_only=False)["model_state_dict"])
    gru_model.eval()

    tcn_model = TCNAutoencoder(input_dim=len(features)).to(device)
    tcn_model.load_state_dict(torch.load(os.path.join(models_dir, "tcn_autoencoder.pt"), map_location=device, weights_only=False)["model_state_dict"])
    tcn_model.eval()

    # Base healthy window (12 steps x 14 features)
    base_vec = np.array([
        155.0, 0.012, 14.5, 28.0, 56.0, 64.0, 26.5, 0.008, 24.0, 58.0, 6.5, 52.0, 5.0, 165.0
    ], dtype=np.float32)

    scenarios = [
        ("1. Erratic Flash-Crowd (Healthy 220 QPS, CPU 28%)", base_vec.copy(), True, "HEALTHY"),
        ("2. Cold-Start Warm-up (Healthy 12 QPS, WebUI CPU 45%)", np.array([12.0, 0.015, 26.0, 48.0, 54.0, 62.0, 25.0, 0.01, 45.0, 56.0, 5.0, 48.0, 4.0, 25.0], dtype=np.float32), True, "HEALTHY"),
        ("3. Latency Bottleneck & DB Slowdown (LatP95 = 1.95s)", np.array([65.0, 1.950, 38.0, 75.0, 62.0, 70.0, 34.0, 0.04, 42.0, 64.0, 72.0, 78.0, 6.0, 85.0], dtype=np.float32), False, "ALERT"),
        ("4. Azure Persistence Memory Leak (RAM = 98.5%, GC Spike)", np.array([95.0, 0.480, 28.0, 55.0, 88.0, 98.5, 33.0, 0.32, 22.0, 60.0, 48.0, 98.5, 6.0, 110.0], dtype=np.float32), False, "ALERT"),
        ("5. Cross-Cloud WAN Saturation / Anomaly (WAN = 950 KB/s)", np.array([40.0, 0.620, 18.0, 35.0, 58.0, 65.0, 28.0, 0.02, 20.0, 58.0, 15.0, 55.0, 8.0, 950.0], dtype=np.float32), False, "ALERT"),
    ]

    print("\n" + "=" * 92)
    print("  MULTI-SCENARIO AI VERIFICATION BENCHMARK (NORMAL vs FAULT INJECTION)")
    print("=" * 92)
    for name, vec, is_resp_ok, expected in scenarios:
        win_raw = np.tile(vec, (12, 1))
        win_scaled = scaler.transform(win_raw)
        t_in = torch.from_numpy(win_scaled).unsqueeze(0).to(device)
        with torch.no_grad():
            g_mse, g_feat = compute_directional_errors(t_in, gru_model(t_in), features, is_response_healthy=is_resp_ok)
            t_mse, t_feat = compute_directional_errors(t_in, tcn_model(t_in), features, is_response_healthy=is_resp_ok)
            mse = 0.5 * (g_mse + t_mse)
            feat_losses = 0.5 * (g_feat + t_feat)

        verdict = "ALERT" if mse > threshold else "HEALTHY"
        ratios = sorted(
            [(features[i], feat_losses[i] / max(0.01, rca_baselines[features[i]]["rca_trigger_threshold"])) for i in range(len(features))],
            key=lambda x: x[1], reverse=True
        )
        rca_top = ", ".join([f"{k}(x{v:.1f})" for k, v in ratios[:2] if v > 1.0]) if verdict == "ALERT" else "None"
        match_str = "✓ PASS" if verdict == expected else "✗ FAIL"
        print(f"  [{match_str}] {name:52s} | MSE: {mse:6.4f} | Verdict: {verdict:7s} | RCA: {rca_top}")
    print("=" * 92)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate AI Detector against Traffic Ground Truth")
    parser.add_argument("--summary", default="ai-engine/inference/test_runs/detector_verify_summary.json")
    parser.add_argument("--traffic-log", default="ai-engine/inference/test_runs/traffic_verify.log")
    parser.add_argument("--traffic-start", default="")
    parser.add_argument("--benchmark", action="store_true", help="Run multi-scenario fault injection benchmark")
    args = parser.parse_args()
    if os.path.isfile(args.summary):
        evaluate_run(args.summary, args.traffic_log, args.traffic_start)
    if args.benchmark:
        run_fault_injection_benchmark()
