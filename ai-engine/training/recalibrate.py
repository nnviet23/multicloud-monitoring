#!/usr/bin/env python3
"""Recheck likelihood calibration with existing weights; never retrain models.

With --threshold the decision threshold (operating point) is moved first, e.g. after a
replay sweep on tuning data; the reason and evidence file are stored in
threshold_config.json["threshold_selection"] and the likelihood is re-anchored to it.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

import numpy as np
import torch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("MPLCONFIGDIR", "/tmp/multicloud-monitoring-matplotlib")
from models.gru_autoencoder import GRUAutoencoder
from models.tcn_autoencoder import TCNAutoencoder
from models.scoring import compute_batch_directional_errors, validate_likelihood_calibration
from training.train import compute_reference_fault_mse


def recalibrate(config_path, output=None, threshold=None, evidence=None, reason=None):
    cfg = yaml.safe_load(Path(config_path).read_text())
    directory = Path(cfg["training"]["save_dir"])
    threshold_path = directory / "threshold_config.json"
    metadata = json.loads(threshold_path.read_text())
    processed = Path(cfg["data"]["processed_dir"])
    audit = json.loads((processed / "preprocess_summary.json").read_text())
    if audit.get("baseline_fit_scope") != "train_only" or audit.get("window_overlap_between_train_and_val") != 0:
        raise ValueError("Recalibration requires disjoint validation windows and train-only baselines")
    if threshold is not None:
        if not 0.35 <= threshold <= 10.0:
            raise ValueError("threshold must be within [0.35, 10]")
        previous = metadata.get("threshold_selection", {}).get("statistical_threshold",
                                                              metadata["recommended_threshold_p99"])
        metadata["threshold_selection"] = {
            "method": "operating point chosen by replay sweep (ai-engine/inference/replay_eval.py)",
            "statistical_threshold": previous,
            "selected_threshold": round(float(threshold), 4),
            "evidence": evidence,
            "reason": reason,
        }
        metadata["recommended_threshold_p99"] = round(float(threshold), 4)
    windows_path = processed / "val_windows.npy"
    windows = np.load(windows_path)
    features = cfg["data"]["features"]
    common = dict(input_dim=len(features), hidden_dim=cfg["model"].get("hidden_dim", 64),
                  latent_dim=cfg["model"].get("latent_dim", 16))
    gru = GRUAutoencoder(**common, num_layers=cfg["model"].get("num_layers", 2))
    tcn = TCNAutoencoder(**common)
    scores = []
    hashes = {}
    for model, name in [(gru, cfg["training"].get("checkpoint_name", "gru_autoencoder.pt")),
                        (tcn, "tcn_autoencoder.pt")]:
        path = directory / name
        model.load_state_dict(torch.load(path, map_location="cpu", weights_only=True)["model_state_dict"])
        model.eval()
        with torch.no_grad():
            reconstruction = model(torch.from_numpy(windows).float())
        sample_scores, _ = compute_batch_directional_errors(windows, reconstruction.numpy(), features)
        scores.append(sample_scores)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    calibration = validate_likelihood_calibration(
        (scores[0] + scores[1]) / 2,
        compute_reference_fault_mse(gru, tcn, features, windows.shape[1], torch.device("cpu")),
        metadata["error_distribution"]["mean"], metadata["error_distribution"]["std"],
        metadata["recommended_threshold_p99"], metadata.get("dual_sliding_window", {}))
    if not calibration["calibration_verified"]:
        raise ValueError(f"Likelihood calibration failed: {calibration}")
    calibration.update(scope="normal_validation_and_synthetic_reference_faults",
                       validation_sha256=hashlib.sha256(windows_path.read_bytes()).hexdigest(),
                       model_sha256=hashes)
    metadata["likelihood_calibration"] = calibration
    Path(output or threshold_path).write_text(json.dumps(metadata, indent=2) + "\n")
    return calibration


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml")
    parser.add_argument("--output", default=None, help="Alternate metadata path (default: existing threshold file)")
    parser.add_argument("--threshold", type=float, default=None, help="New decision threshold (operating point)")
    parser.add_argument("--evidence", default=None, help="Sweep result file justifying --threshold")
    parser.add_argument("--reason", default=None, help="One-line justification stored with the threshold")
    args = parser.parse_args()
    if args.threshold is not None and not (args.evidence and args.reason):
        parser.error("--threshold requires --evidence and --reason")
    torch.set_num_threads(1)
    print(json.dumps(recalibrate(args.config, args.output, args.threshold, args.evidence, args.reason), indent=2))
