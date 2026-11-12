#!/usr/bin/env python3
"""Replay a decision-threshold sweep and write it as a derived dataset with provenance.

Usage: python3.12 scripts/threshold_sweep.py <out.json> --thresholds 2.4671 2.0 1.6 \
           --normal <collector.csv>... --chaos <runner dir>... [--exclude dir:fault ...]
Model-only metrics (no SLO guards, no online recovery logic): normal-phase alerts inside
chaos runs are reported per phase offset because the 120s window tail of a fault still
scores high for the first ~60s of a recovery phase.
"""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai-engine"))
from inference import replay_eval as R  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("output")
    ap.add_argument("--thresholds", nargs="+", type=float, required=True)
    ap.add_argument("--normal", nargs="*", default=[])
    ap.add_argument("--chaos", nargs="*", default=[])
    ap.add_argument("--exclude", nargs="*", default=[], help="<chaos dir>:<fault id> pairs to leave out")
    ap.add_argument("--config", default=str(ROOT / "ai-engine/configs/model_config.yaml"))
    ap.add_argument("--models-dir", default=str(ROOT / "ai-engine/models/saved"))
    ap.add_argument("--settle", type=int, default=30)
    args = ap.parse_args()
    excluded = {tuple(item.rsplit(":", 1)) for item in args.exclude}
    bundle = R.ModelBundle(args.config, args.models_dir)
    normal = [R.samples_from_csv(p, bundle.limits) for p in args.normal]
    chaos = [(d, *R.samples_from_chaos(d, args.settle)) for d in args.chaos]
    rows = []
    for th in args.thresholds:
        row = {"threshold": th, "normal": [], "faults": [], "recovery_tail_alerts": []}
        for path, (name, samples) in zip(args.normal, normal):
            row["normal"].append(R.summarize_normal(name, R.replay(bundle, samples, th), 10))
        for directory, name, samples, phases in chaos:
            scored = R.replay(bundle, samples, th)
            starts = {p["id"]: R.epoch(p["start"]) for p in phases}
            summary = R.summarize_faults(name, scored, phases, args.settle)
            for fault in summary["faults"]:
                if (directory, fault["fault"]) not in excluded:
                    row["faults"].append({"source": directory, **fault})
            row["recovery_tail_alerts"] += [
                {"source": directory, "phase": s["phase"], "seconds_into_phase": int(s["t"] - starts[s["phase"]]),
                 "entities": s["entities"]} for s in scored if s["label"] == 0 and s["alert"]]
        rows.append(row)
    sha = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
           for p in sorted(Path(args.models_dir).glob("*")) if p.suffix in (".pt", ".joblib", ".json")}
    out = {"generated_by": "scripts/threshold_sweep.py",
           "git_commit": subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip(),
           "inputs": {"normal": args.normal, "chaos": args.chaos, "excluded": sorted(map(list, excluded))},
           "parameters": {"settle_seconds": args.settle, "metrics": "model-only replay (no SLO guards / recovery logic)"},
           "model_sha256": sha, "sweep": rows}
    Path(args.output).write_text(json.dumps(out, indent=2) + "\n")
    for row in rows:
        fp = [(n["source"], n["false_positive_rate"], n["episodes_per_hour"]) for n in row["normal"]]
        faults = {f["fault"]: (f["recall_samples"], f["detection_seconds"]) for f in row["faults"]}
        print(row["threshold"], fp, len(row["recovery_tail_alerts"]), faults)


if __name__ == "__main__":
    main()
