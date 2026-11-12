#!/usr/bin/env python3.12
"""Replay recorded real telemetry through a trained model version (model-only metrics).

Sources
  * normal runs: collector CSVs (experiments/raw/<run>/metrics/entity_features.csv);
    every sample is labelled normal.
  * fault runs: tests/chaos runner outputs (detector.json + events.json). Samples
    `settle` seconds after a fault phase starts are labelled fault; samples
    `settle` seconds after baseline/recovery phases start are labelled normal;
    the transitions in between are not scored.

Each entity keeps its own window buffer and DualSlidingWindowScorer exactly as the
online detector does (MultiEntityScorer). SLO guards, Tempo fusion beyond what the
detector already recorded, and latency-history refresh are not replayed, so these
are *model-only* numbers.
"""
import argparse
import json
import math
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd
import torch
import yaml

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.gru_autoencoder import GRUAutoencoder  # noqa: E402
from models.tcn_autoencoder import TCNAutoencoder  # noqa: E402
from models.scoring import DualSlidingWindowScorer, MultiEntityScorer, compute_batch_directional_errors  # noqa: E402
from models.guards import GuardLimits  # noqa: E402

# Entity a fault is expected to be localised to (any one of them counts).
FAULT_TARGETS = {
    "gcp_wan_delay": ["gcp:teastore-recommender"],
    "azure_wan_delay": ["azure:teastore-auth", "azure:teastore-persistence"],
    "aws_wan_delay": ["aws:teastore-webui", "aws:teastore-image", "aws:teastore-registry"],
    "cpu": ["gcp:teastore-recommender"],
    "db_lock": ["azure:teastore-persistence"],
    "memory_leak": ["azure:teastore-persistence"],
    "http_5xx": ["aws:teastore-webui"],
    "webui_outage": ["aws:teastore-webui"],
}


def epoch(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()


class ModelBundle:
    def __init__(self, config_path, models_dir=None):
        with open(config_path, encoding="utf-8") as f:
            self.cfg = yaml.safe_load(f)
        self.models_dir = models_dir or self.cfg["training"]["save_dir"]
        self.features = self.cfg["data"]["features"]
        self.window = int(self.cfg["data"]["window_size"])
        self.floors = self.cfg["data"]["physical_scale_floors"]
        with open(os.path.join(self.models_dir, "threshold_config.json"), encoding="utf-8") as f:
            self.meta = json.load(f)
        self.limits = GuardLimits(self.meta.get("slo_guards"))
        with open(os.path.join(self.models_dir, "entity_baselines.json"), encoding="utf-8") as f:
            self.baselines = json.load(f)
        m = self.cfg["model"]
        common = dict(input_dim=len(self.features), hidden_dim=m.get("hidden_dim", 64), latent_dim=m.get("latent_dim", 16))
        self.models = []
        for cls, name, extra in ((GRUAutoencoder, self.cfg["training"].get("checkpoint_name", "gru_autoencoder.pt"),
                                  {"num_layers": m.get("num_layers", 2)}),
                                 (TCNAutoencoder, "tcn_autoencoder.pt", {})):
            path = os.path.join(self.models_dir, name)
            if not os.path.isfile(path):
                continue
            ckpt = torch.load(path, map_location="cpu", weights_only=False)
            hp = {k: ckpt[k] for k in ("hidden_dim", "latent_dim") if k in ckpt}
            model = cls(**{**common, **hp, **extra})
            model.load_state_dict(ckpt["model_state_dict"])
            model.eval()
            self.models.append(model)

    def entity_meta(self, eid):
        if eid in self.baselines:
            return self.baselines[eid]["features"]
        service = eid.split(":", 1)[-1]
        for key, value in self.baselines.items():
            if not key.startswith("__") and key.endswith(":" + service):
                return value["features"]
        return self.baselines["__default__"]["features"]

    def standardize(self, eid, raw):
        meta = self.entity_meta(eid)
        out = np.zeros(len(self.features), dtype=np.float32)
        for j, name in enumerate(self.features):
            scale = max(float(meta[name]["scale"]), float(self.floors.get(name, 1e-3)), 1e-6)
            out[j] = np.clip((float(raw[name]) - float(meta[name]["median"])) / scale, -10.0, 10.0)
        return out

    def scorer_factory(self, threshold=None):
        dist = self.meta["error_distribution"]
        dw = self.meta.get("dual_sliding_window", {})
        temperature = self.meta.get("likelihood_calibration", {}).get("temperature")
        thr = float(threshold if threshold is not None else self.meta["recommended_threshold_p99"])

        def make():
            return DualSlidingWindowScorer(dist["mean"], dist["std"], thr, short_w=dw.get("short_window", 3),
                                           long_w=dw.get("long_window", 18),
                                           min_consecutive=dw.get("min_consecutive_breaches", 2),
                                           temperature=temperature if threshold is None else None)
        return make

    def window_errors(self, windows, healthy):
        if not len(windows):
            return np.zeros(0), np.zeros((0, len(self.features)))
        x = torch.from_numpy(np.asarray(windows, dtype=np.float32))
        sample, feat = [], []
        with torch.no_grad():
            for model in self.models:
                s, f = compute_batch_directional_errors(x.numpy(), model(x).numpy(), self.features, healthy_mask=healthy)
                sample.append(s)
                feat.append(f)
        return np.mean(sample, axis=0), np.mean(feat, axis=0)


def samples_from_csv(path, limits=None):
    """Collector CSV -> ordered samples (one per cycle), all labelled normal.

    Entity response health uses the detector's per-entity limits; the cluster-level
    probe is assumed healthy (the run is fault-free).
    """
    limits = limits or GuardLimits()
    df = pd.read_csv(path)
    run = os.path.basename(os.path.dirname(os.path.dirname(path))) if path.endswith("metrics/entity_features.csv") else path
    samples = []
    for ts, cycle in df.sort_values("timestamp").groupby("timestamp", sort=True):
        entities = {}
        for row in cycle.itertuples(index=False):
            raw = row._asdict()
            if any(m in str(raw.get("missing_metrics", "") or "").split(";") for m in ("max_pod_cpu_pct", "max_pod_ram_pct")):
                continue
            eid = f"{raw['cloud_provider']}:{raw['service_name']}"
            healthy = (raw["server_latency_p95"] < limits.entity(eid, "server_healthy_s")
                       and raw["client_latency_p95"] < limits.entity(eid, "client_healthy_s")
                       and raw["error_rate_5xx"] <= 0.05)
            entities[eid] = {"raw": raw, "healthy": bool(healthy), "token": None}
        if entities:
            samples.append({"t": float(ts), "entities": entities, "label": 0, "phase": "normal"})
    return run, samples


def samples_from_chaos(directory, settle):
    records = json.load(open(os.path.join(directory, "detector.json"), encoding="utf-8")).get("records", [])
    phases = json.load(open(os.path.join(directory, "events.json"), encoding="utf-8"))["phases"]
    samples = []
    for rec in records:
        feats = rec.get("entity_features")
        if not feats or not rec.get("telemetry_complete", False):
            continue
        t = epoch(rec["timestamp"])
        label, phase_id = None, None
        for ph in phases:
            if ph.get("end") and epoch(ph["start"]) <= t < epoch(ph["end"]):
                phase_id = ph["id"]
                if t >= epoch(ph["start"]) + settle:
                    label = 1 if ph["id"] in FAULT_TARGETS else 0
        fast = rec.get("fast_metrics", {})
        entities = {}
        for eid, raw in feats.items():
            f = fast.get(eid, {})
            token = (*(f[side].get("observed_at") if f.get(side) else None for side in ("server", "client")),
                     *(raw.get(n) for n in ("max_pod_cpu_pct", "max_pod_ram_pct", "ram_floor_2m_pct", "gc_pause_rate")))
            entities[eid] = {"raw": raw, "healthy": bool(rec.get("entity_response_healthy", {}).get(eid, True)), "token": token}
        samples.append({"t": t, "entities": entities, "label": label, "phase": phase_id or "unphased"})
    return os.path.basename(os.path.normpath(directory)), samples, phases


def replay(bundle, samples, threshold=None):
    """Score samples in time order; returns per-sample aggregate verdicts."""
    buffers, windows, healthy, index = {}, [], [], []
    for i, sample in enumerate(samples):
        for eid, ent in sorted(sample["entities"].items()):
            z = bundle.standardize(eid, ent["raw"])
            buf = buffers.setdefault(eid, [z.copy() for _ in range(bundle.window)])
            buf.append(z)
            del buf[0]
            windows.append(np.stack(buf))
            healthy.append(ent["healthy"])
            index.append((i, eid))
    errors, _ = bundle.window_errors(np.asarray(windows), np.asarray(healthy))
    per_sample = {}
    for (i, eid), err in zip(index, errors):
        per_sample.setdefault(i, {})[eid] = float(err)
    scorer = MultiEntityScorer(bundle.scorer_factory(threshold))
    out = []
    for i, sample in enumerate(samples):
        obs = {eid: (per_sample[i][eid], sample["entities"][eid]["token"]) for eid in per_sample.get(i, {})}
        agg = MultiEntityScorer.aggregate(scorer.update(obs))
        out.append({"t": sample["t"], "label": sample["label"], "phase": sample["phase"],
                    "alert": bool(agg["is_sustained_anomaly"]), "entities": agg["sustained_entities"],
                    "max_mse": max(per_sample.get(i, {0: 0.0}).values()),
                    "worst": max(per_sample.get(i, {"none": 0.0}).items(), key=lambda kv: kv[1])[0]})
    return out


def episodes(flags):
    return sum(1 for prev, cur in zip([False] + flags, flags) if cur and not prev)


def summarize_normal(name, scored, interval):
    flags = [s["alert"] for s in scored if s["label"] == 0]
    hours = len(flags) * interval / 3600.0
    return {"source": name, "samples": len(flags), "alert_samples": int(sum(flags)),
            "false_positive_rate": round(sum(flags) / max(1, len(flags)), 5),
            "alert_episodes": episodes(flags), "episodes_per_hour": round(episodes(flags) / max(hours, 1e-9), 3),
            "max_mse_p99": round(float(np.percentile([s["max_mse"] for s in scored], 99)), 4) if scored else None}


def summarize_faults(name, scored, phases, settle):
    rows = []
    normal = [s for s in scored if s["label"] == 0]
    for ph in phases:
        if ph["id"] not in FAULT_TARGETS or not ph.get("end"):
            continue
        start, end = epoch(ph["start"]), epoch(ph["end"])
        # Detection may land up to `settle` s after the fault ends (span/export lag).
        window = [s for s in scored if start <= s["t"] < end + settle]
        scored_phase = [s for s in window if s["label"] == 1]
        first = next((s["t"] for s in window if s["alert"]), None)
        targets = FAULT_TARGETS[ph["id"]]
        localized = any(any(t in s["entities"] for t in targets) for s in window if s["alert"])
        rows.append({"fault": ph["id"], "samples": len(scored_phase),
                     "detected": first is not None, "localized": localized,
                     "detection_seconds": round(first - start, 1) if first else None,
                     "recall_samples": round(sum(s["alert"] for s in scored_phase) / max(1, len(scored_phase)), 3)})
    return {"source": name, "faults": rows,
            "normal_phase_samples": len(normal), "normal_phase_alert_samples": int(sum(s["alert"] for s in normal))}


def evaluate(bundle, normal_csvs, chaos_dirs, settle=30, interval=10, threshold=None):
    report = {"models_dir": bundle.models_dir,
              "threshold": float(threshold if threshold is not None else bundle.meta["recommended_threshold_p99"]),
              "normal": [], "chaos": []}
    for path in normal_csvs:
        name, samples = samples_from_csv(path, bundle.limits)
        report["normal"].append(summarize_normal(name, replay(bundle, samples, threshold), interval))
    for directory in chaos_dirs:
        name, samples, phases = samples_from_chaos(directory, settle)
        report["chaos"].append(summarize_faults(name, replay(bundle, samples, threshold), phases, settle))
    faults = [row for run in report["chaos"] for row in run["faults"]]
    normal_samples = sum(r["samples"] for r in report["normal"]) + sum(r["normal_phase_samples"] for r in report["chaos"])
    normal_alerts = sum(r["alert_samples"] for r in report["normal"]) + sum(r["normal_phase_alert_samples"] for r in report["chaos"])
    report["overall"] = {
        "normal_samples": normal_samples,
        "false_positive_rate": round(normal_alerts / max(1, normal_samples), 5),
        "faults": len(faults),
        "faults_detected": sum(r["detected"] for r in faults),
        "faults_localized": sum(r["localized"] for r in faults),
        "median_detection_seconds": (float(np.median([r["detection_seconds"] for r in faults if r["detected"]]))
                                     if any(r["detected"] for r in faults) else None),
    }
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml")
    parser.add_argument("--models-dir", default=None)
    parser.add_argument("--normal", nargs="*", default=[], help="Collector CSVs of fault-free runs")
    parser.add_argument("--chaos", nargs="*", default=[], help="Chaos runner output directories")
    parser.add_argument("--settle", type=int, default=30)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--threshold", type=float, default=None, help="Override the trained MSE threshold")
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    torch.set_num_threads(max(1, min(8, os.cpu_count() or 1)))
    report = evaluate(ModelBundle(args.config, args.models_dir), args.normal, args.chaos,
                      args.settle, args.interval, args.threshold)
    text = json.dumps(report, indent=2)
    if args.output:
        os.makedirs(os.path.dirname(os.path.abspath(args.output)), exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    print(text)


if __name__ == "__main__":
    main()
