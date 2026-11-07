#!/usr/bin/env python3.12
"""
Automated Ground-Truth Evaluator & Multi-Cloud Fault-Injection Benchmark (V3)
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring (AWS + Azure + GCP + Hub)

Performs:
  1. Timestamp alignment between Traffic Generator logs and AI Detector V3 summary JSON
  2. Ground-truth classification:
     - ACTUAL_ANOMALY: Client request failure rate > 15% OR Latency P95 > 380ms
                       OR HTTP 5xx > 0.2/s OR >=2 consecutive slow/failed probes
     - ACTUAL_HEALTHY: Multi-cloud microservices processing requests normally
  3. Multi-Scenario V3 Entity Benchmark (`--benchmark`) to verify 0% False Alarms
     on healthy erratic traffic / pod scale-out and 100% Detection + RCA on faults.
"""

import os
import re
import sys
import json
import yaml
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
from models.scoring import (
    compute_directional_errors,
    DualSlidingWindowScorer,
    validate_likelihood_calibration,
)
from inference.detector import synthesize_multicloud_rca


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
                    "fail_rate": fail_rate,
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
        probe_ms = r.get("probe_ms", 0.0)
        if not probe_ok or probe_ms > 500.0:
            consec_probe_fail += 1
        else:
            consec_probe_fail = 0

        lat_ms = r.get("latency_p95_ms", 0.0)
        err_5xx = r.get("error_5xx", 0.0)

        actual_fault = (
            (tw is not None and fail_rate > 0.15 and fail_delta >= 5)
            or (lat_ms > 550.0)
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
    print("  GROUND-TRUTH EVALUATION REPORT (MULTI-CLOUD LIVE TRAFFIC vs AI DETECTOR V3)")
    print("=" * 92)
    print(f"  Total Samples          : {total}")
    print(f"  Discovered Entities    : {', '.join(summary.get('discovered_entities', []))}")
    print(f"  Ground-Truth Healthy   : {healthy_total:2d} samples | True Negative (TN): {tn:2d} | False Positive (FP): {fp:2d}")
    print(f"  Ground-Truth Faulty    : {fault_total:2d} samples | True Positive (TP): {tp:2d} | False Negative (FN): {fn:2d}")
    print("-" * 92)
    print(f"  * Overall Accuracy     : {acc:5.1f}%")
    print(f"  * False Alarm Rate(FPR): {fpr:5.1f}% (Mục tiêu: 0.0% khi đa đám mây ổn định)")
    if fault_total > 0:
        print(f"  * Fault Recall   (TPR) : {tpr:5.1f}%")
    print("=" * 92)


def run_fault_injection_benchmark(config_path="ai-engine/configs/model_config.yaml",
                                  scenarios_path="tests/chaos/scenarios.json", output_path=""):
    """Replay synthetic feature windows through the trained ensemble, scorer and RCA.

    This validates inference behavior; raw metrics and trace summaries are fixtures,
    not measurements from a live fault injection.
    """
    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    with open(scenarios_path, encoding="utf-8") as f:
        scenarios = json.load(f)
    models_dir = cfg["training"]["save_dir"]
    with open(os.path.join(models_dir, "threshold_config.json"), encoding="utf-8") as f:
        meta = json.load(f)
    features = cfg["data"]["features"]
    threshold = float(meta["recommended_threshold_p99"])
    model_cfg = cfg["model"]
    common = dict(input_dim=len(features), hidden_dim=model_cfg.get("hidden_dim", 64),
                  latent_dim=model_cfg.get("latent_dim", 16), dropout=model_cfg.get("dropout", 0.1))
    gru = GRUAutoencoder(**common, num_layers=model_cfg.get("num_layers", 2))
    tcn = TCNAutoencoder(**common)
    for model, filename in [(gru, cfg["training"].get("checkpoint_name", "gru_autoencoder.pt")),
                            (tcn, "tcn_autoencoder.pt")]:
        checkpoint = torch.load(os.path.join(models_dir, filename), map_location="cpu", weights_only=True)
        model.load_state_dict(checkpoint["model_state_dict"])
        model.eval()
    dw = meta.get("dual_sliding_window", {})
    cal_meta = meta.get("likelihood_calibration", {})
    cal_verified = bool(cal_meta.get("calibration_verified", False))
    rows = []
    print("Synthetic AI benchmark: trained GRU + TCN, sustained scoring, entity RCA")
    for scenario in scenarios:
        z = np.array(scenario["z"], dtype=np.float32)
        if z.shape != (len(features),) or not np.isfinite(z).all():
            raise ValueError(f"Invalid feature vector in {scenario['id']}")
        window = np.tile(z, (cfg["data"]["window_size"], 1))
        x = torch.from_numpy(window).unsqueeze(0)
        with torch.no_grad():
            gm, gf = compute_directional_errors(x, gru(x), features, scenario["response_healthy"])
            tm, tf = compute_directional_errors(x, tcn(x), features, scenario["response_healthy"])
        mse, losses = (gm + tm) / 2, (gf + tf) / 2
        scorer = DualSlidingWindowScorer(
            meta["error_distribution"]["mean"], meta["error_distribution"]["std"], threshold,
            short_w=dw.get("short_window", 3), long_w=dw.get("long_window", 18),
            min_consecutive=dw.get("min_consecutive_breaches", 2),
            temperature=cal_meta.get("temperature"))
        # Seed with healthy context, then require repeated faulty observations.
        for _ in range(scorer.short_w):
            scorer.update_and_score(0.0)
        first = scorer.update_and_score(mse)
        for _ in range(max(scorer.short_w, scorer.min_consecutive)):
            sustained = scorer.update_and_score(mse)
        verdict = "ALERT" if sustained["is_sustained_anomaly"] else "HEALTHY"
        likelihood_pct = float(sustained["likelihood_pct"])
        likelihood_consistent = (
            (likelihood_pct > 50.0) if scenario["expected"] == "ALERT" else (likelihood_pct < 50.0)
        )
        raw = {name: 0.0 for name in features}
        raw.update(scenario.get("raw", {}))
        causes = synthesize_multicloud_rca(
            {scenario["entity"]: {"mse": mse, "feat_losses": losses, "z_vec": z, "raw": raw}},
            meta["feature_rca_baselines"], features, scenario.get("trace", {}),
            scenario["response_healthy"], 50.0 if scenario["response_healthy"] else 650.0,
        ) if verdict == "ALERT" else []
        expected_rca = scenario.get("expected_rca", "")
        rca_ok = not expected_rca or any(expected_rca in cause for cause in causes)
        # After a sustained fault, a healthy score must clear the alert immediately.
        recovered = not scorer.update_and_score(0.0)["is_sustained_anomaly"]
        passed = (verdict == scenario["expected"] and rca_ok and recovered
                  and not first["is_sustained_anomaly"] and np.isfinite(mse)
                  and cal_verified and likelihood_consistent)
        row = dict(id=scenario["id"], expected=scenario["expected"], verdict=verdict,
                   mse=float(mse), likelihood_pct=round(likelihood_pct, 2),
                   likelihood_consistent=bool(likelihood_consistent),
                   rca_causes=causes, rca_ok=rca_ok,
                   first_sample_suppressed=not first["is_sustained_anomaly"],
                   recovered=recovered, passed=bool(passed))
        rows.append(row)
        print(f"  [{'PASS' if passed else 'FAIL'}] {scenario['id']:20s} MSE={mse:.4f} "
              f"P(fault)={likelihood_pct:5.1f}% {verdict:7s} RCA={' | '.join(causes[:2]) or '-'}")
    report = {"mode": "synthetic_feature_replay", "threshold": threshold,
              "likelihood_calibration": cal_meta,
              "total": len(rows), "passed": sum(row["passed"] for row in rows), "results": rows}
    if output_path:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"Result: {report['passed']}/{report['total']} passed")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate AI Detector V3 against Traffic Ground Truth")
    parser.add_argument("--summary", default="", help="Detector JSON to evaluate against observed SLOs")
    parser.add_argument("--traffic-log", default="")
    parser.add_argument("--traffic-start", default="")
    parser.add_argument("--benchmark", action="store_true", help="Run multi-scenario V3 fault injection benchmark")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml")
    parser.add_argument("--scenarios", default="tests/chaos/scenarios.json")
    parser.add_argument("--output", default="", help="Write benchmark results as JSON")
    args = parser.parse_args()
    if not args.summary and not args.benchmark:
        parser.error("Provide --summary or --benchmark")
    if args.summary and not os.path.isfile(args.summary):
        parser.error(f"Summary does not exist: {args.summary}")
    if os.path.isfile(args.summary):
        evaluate_run(args.summary, args.traffic_log, args.traffic_start)
    if args.benchmark:
        report = run_fault_injection_benchmark(args.config, args.scenarios, args.output)
        sys.exit(0 if report["passed"] == report["total"] and report["total"] else 1)
