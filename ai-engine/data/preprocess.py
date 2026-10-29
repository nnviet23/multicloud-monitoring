#!/usr/bin/env python3.12
"""
Per-Entity Standardized Time-Series Preprocessing Pipeline (V3).
Computes Per-Entity Robust Baselines (Median & Scale-Floored IQR) for each (cloud_provider, service_name),
transforms each entity's timeline into standardized residual space Z_e(t) in R^8,
extracts per-entity sliding windows (12 x 8), performs a stratified 4-phase train/val split,
and applies domain-aware augmentation on training windows.
"""

import os
import json
import yaml
import argparse
import numpy as np
import pandas as pd


def load_config(config_path):
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def compute_entity_baselines(df, features, scale_floors):
    """
    Computes Median, IQR, P95, P99, and Scale-Floored Robust denominator per (cloud_provider, service_name).
    """
    baselines = {}
    all_medians = {f: [] for f in features}
    all_scales = {f: [] for f in features}

    for (cp, sn), grp in df.groupby(["cloud_provider", "service_name"]):
        entity_key = f"{cp}:{sn}"
        ent_meta = {
            "cloud_provider": cp,
            "service_name": sn,
            "sample_count": int(len(grp)),
            "features": {}
        }
        for f in features:
            vals = grp[f].astype(np.float64).values
            med = float(np.median(vals))
            q25, q75, p95, p99 = [float(x) for x in np.percentile(vals, [25, 75, 95, 99])]
            iqr = max(0.0, q75 - q25)
            floor = float(scale_floors.get(f, 1.0))
            scale = max(iqr, floor)

            ent_meta["features"][f] = {
                "median": round(med, 6),
                "iqr": round(iqr, 6),
                "floor": round(floor, 6),
                "scale": round(scale, 6),
                "p95": round(p95, 6),
                "p99": round(p99, 6),
            }
            all_medians[f].append(med)
            all_scales[f].append(scale)

        baselines[entity_key] = ent_meta

    # Global fallback for newly discovered services during initial warm-up
    default_features = {}
    for f in features:
        floor = float(scale_floors.get(f, 1.0))
        default_features[f] = {
            "median": round(float(np.median(all_medians[f])) if all_medians[f] else 0.0, 6),
            "iqr": round(float(np.median(all_scales[f])) if all_scales[f] else floor, 6),
            "floor": round(floor, 6),
            "scale": round(max(float(np.median(all_scales[f])) if all_scales[f] else floor, floor), 6),
        }
    baselines["__default__"] = {
        "cloud_provider": "any",
        "service_name": "default",
        "sample_count": int(len(df)),
        "features": default_features
    }
    return baselines


def transform_entity_df(grp, ent_meta, features):
    """Transforms a single entity's dataframe into standardized z-score matrix (N, 8)."""
    n = len(grp)
    k = len(features)
    z_mat = np.zeros((n, k), dtype=np.float32)
    for j, f in enumerate(features):
        f_meta = ent_meta["features"][f]
        med = f_meta["median"]
        scale = max(1e-6, f_meta["scale"])
        raw = grp[f].astype(np.float32).values
        z_mat[:, j] = np.clip((raw - med) / scale, -10.0, 10.0)
    return z_mat


def create_windows(data_2d, window_size, stride=1):
    windows = []
    n = len(data_2d)
    for start in range(0, n - window_size + 1, stride):
        windows.append(data_2d[start:start + window_size])
    if not windows:
        return np.empty((0, window_size, data_2d.shape[1]), dtype=np.float32)
    return np.array(windows, dtype=np.float32)


def augment_training_windows(train_windows, features, rng):
    """
    Generates realistic standardized training windows:
      1. Micro-jitter in z-score space
      2. Load-correlated scaling (QPS + CPU + RAM rise together while Latency/Error remain normal)
      3. Pre-GC Sawtooth RAM pattern (max_pod_ram_pct elevated while ram_floor_2m_pct stays low)
    """
    augmented = [train_windows]
    idx_map = {f: i for i, f in enumerate(features)}

    # 1. Gaussian micro-jitter
    jitter = train_windows + rng.normal(0.0, 0.05, size=train_windows.shape).astype(np.float32)
    augmented.append(jitter)

    # 2. Load-correlated active workload regimes
    for delta in [-0.35, 0.45, 0.85]:
        w = train_windows.copy()
        for fname in ["qps", "max_pod_cpu_pct", "max_pod_ram_pct"]:
            if fname in idx_map:
                j = idx_map[fname]
                w[:, :, j] = np.clip(w[:, :, j] + delta + rng.normal(0.0, 0.06, size=w[:, :, j].shape), -2.5, 2.6)
        augmented.append(w.astype(np.float32))

    # 3. Healthy JVM pre-GC sawtooth (high instant RAM before GC, but normal 2-min RAM floor)
    if "max_pod_ram_pct" in idx_map and "ram_floor_2m_pct" in idx_map:
        w_gc = train_windows.copy()
        j_ram = idx_map["max_pod_ram_pct"]
        j_flr = idx_map["ram_floor_2m_pct"]
        sawtooth = np.linspace(-0.2, 1.8, train_windows.shape[1], dtype=np.float32).reshape(1, -1)
        w_gc[:, :, j_ram] = np.clip(w_gc[:, :, j_ram] + sawtooth, -2.0, 2.5)
        w_gc[:, :, j_flr] = np.clip(w_gc[:, :, j_flr], -2.0, 0.6)
        augmented.append(w_gc.astype(np.float32))

    return np.concatenate(augmented, axis=0)


def main():
    parser = argparse.ArgumentParser(description="Preprocess Multi-Cloud Per-Entity Telemetry (V3)")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to model_config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    raw_csv = cfg["data"]["raw_csv_path"]
    processed_dir = cfg["data"]["processed_dir"]
    baselines_path = cfg["data"]["entity_baselines_path"]
    features = cfg["data"]["features"]
    scale_floors = cfg["data"]["physical_scale_floors"]
    window_size = cfg["data"]["window_size"]
    stride = cfg["data"]["stride"]
    val_split = cfg["data"]["val_split"]
    seed = cfg["data"]["random_seed"]

    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(baselines_path)), exist_ok=True)

    print("========================================================================", flush=True)
    print("  MULTI-CLOUD PER-ENTITY STANDARDIZED PREPROCESSING PIPELINE (V3)", flush=True)
    print("========================================================================", flush=True)

    df = pd.read_csv(raw_csv)
    df = df.sort_values(["cloud_provider", "service_name", "timestamp"]).reset_index(drop=True)
    df[features] = df[features].ffill().bfill().fillna(0.0)

    if "anomaly_label" in df.columns:
        df = df[df["anomaly_label"] == 0].reset_index(drop=True)

    baselines = compute_entity_baselines(df, features, scale_floors)

    with open(baselines_path, "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)
    with open(os.path.join(processed_dir, "entity_baselines.json"), "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)

    train_chunks = []
    val_chunks = []
    entity_window_counts = {}

    for (cp, sn), grp in df.groupby(["cloud_provider", "service_name"]):
        entity_key = f"{cp}:{sn}"
        z_mat = transform_entity_df(grp, baselines[entity_key], features)
        ew = create_windows(z_mat, window_size=window_size, stride=stride)
        if len(ew) == 0:
            continue
        entity_window_counts[entity_key] = int(len(ew))

        # Stratified 4-phase split across this entity's timeline
        num_phases = min(4, max(1, len(ew) // 5))
        phases = np.array_split(ew, num_phases)
        for p in phases:
            if len(p) == 0:
                continue
            v_cnt = max(1, int(len(p) * val_split))
            t_cnt = len(p) - v_cnt
            if t_cnt > 0:
                train_chunks.append(p[:t_cnt])
            val_chunks.append(p[t_cnt:])

    base_train_windows = np.concatenate(train_chunks, axis=0)
    val_windows = np.concatenate(val_chunks, axis=0)

    rng = np.random.default_rng(seed)
    train_windows = augment_training_windows(base_train_windows, features, rng)
    rng.shuffle(train_windows)

    np.save(os.path.join(processed_dir, "train_windows.npy"), train_windows)
    np.save(os.path.join(processed_dir, "val_windows.npy"), val_windows)

    with open(os.path.join(processed_dir, "feature_names.json"), "w", encoding="utf-8") as f:
        json.dump(features, f, indent=2)

    summary = {
        "architecture": "Per-Entity Z-Score Standardized Universal Autoencoder (V3)",
        "total_raw_entity_rows": int(len(df)),
        "discovered_entities": list(entity_window_counts.keys()),
        "entity_window_counts": entity_window_counts,
        "num_features": len(features),
        "features": features,
        "window_size": window_size,
        "stride": stride,
        "base_train_windows": int(len(base_train_windows)),
        "augmented_train_windows": int(len(train_windows)),
        "val_windows": int(len(val_windows)),
        "train_shape": list(train_windows.shape),
        "val_shape": list(val_windows.shape),
        "physical_scale_floors": scale_floors,
    }
    with open(os.path.join(processed_dir, "preprocess_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"  * Total Raw Entity Rows  : {len(df)}", flush=True)
    print(f"  * Discovered Entities    : {', '.join(entity_window_counts.keys())}", flush=True)
    print(f"  * Base Train Windows     : {base_train_windows.shape}", flush=True)
    print(f"  * Augmented Train Windows: {train_windows.shape}", flush=True)
    print(f"  * Validation Windows     : {val_windows.shape}", flush=True)
    print(f"  * Saved Entity Baselines : {baselines_path}", flush=True)
    print("========================================================================", flush=True)


if __name__ == "__main__":
    main()
