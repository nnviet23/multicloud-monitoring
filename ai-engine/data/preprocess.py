#!/usr/bin/env python3.12
"""
Per-Entity Standardized Time-Series Preprocessing Pipeline (V3 - Zero Data Leakage).

Methodological Guarantees (per scikit-learn Data Leakage Prevention Guidelines):
  1. Strict Chronological Split BEFORE Baseline Calculation & Windowing:
     Each `(cloud_provider, service_name)` entity timeline is first split chronologically
     into disjoint `train_df` (`t <= T_split`) and `val_df` (`t > T_split`).
  2. Train-Only Baseline Fitting:
     `entity_baselines.json` (Median, IQR, P95, P99, Scale-Floored Denominator) is computed
     EXCLUSIVELY on `train_df`. Validation data never influences baseline statistics.
  3. Non-Overlapping Sliding Windows:
     Sliding windows `(12 x 8)` are constructed independently inside `train_df` and
     independently inside `val_df`, guaranteeing zero shared timesteps between
     training windows and validation windows (`train_timestamps ∩ val_timestamps == ∅`).
  4. Train-Only Augmentation:
     Domain-aware augmentation is applied strictly to `train_windows`; `val_windows`
     remains 100% pure, held-out future telemetry.
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


def split_entities_chronologically(df, val_split, window_size):
    """
    Splits each `(cloud_provider, service_name)` timeline chronologically into
    strictly disjoint `train_df` (earlier timestamps) and `val_df` (later timestamps)
    BEFORE computing any baselines or sliding windows.
    """
    train_parts = []
    val_parts = []
    split_audit = {}

    for (cp, sn), grp in df.groupby(["cloud_provider", "service_name"]):
        grp = grp.sort_values("timestamp").reset_index(drop=True)
        n_total = len(grp)
        if n_total < 2 * window_size:
            raise ValueError(
                f"Entity {cp}:{sn} has only {n_total} rows; need at least {2 * window_size} "
                f"for non-overlapping train/val windows of size {window_size}."
            )

        n_val = max(window_size + 4, int(round(n_total * val_split)))
        n_train = n_total - n_val
        if n_train < window_size:
            n_train = window_size
            n_val = n_total - n_train

        train_grp = grp.iloc[:n_train].copy()
        val_grp = grp.iloc[n_train:].copy()

        train_max_ts = float(train_grp["timestamp"].max())
        val_min_ts = float(val_grp["timestamp"].min())
        if train_max_ts >= val_min_ts:
            raise AssertionError(
                f"Temporal leakage detected for {cp}:{sn}: train_max_ts ({train_max_ts}) >= val_min_ts ({val_min_ts})"
            )

        train_parts.append(train_grp)
        val_parts.append(val_grp)
        split_audit[f"{cp}:{sn}"] = {
            "total_rows": int(n_total),
            "train_rows": int(len(train_grp)),
            "val_rows": int(len(val_grp)),
            "train_start_ts": float(train_grp["timestamp"].min()),
            "train_end_ts": train_max_ts,
            "val_start_ts": val_min_ts,
            "val_end_ts": float(val_grp["timestamp"].max()),
        }

    train_df = pd.concat(train_parts, ignore_index=True)
    val_df = pd.concat(val_parts, ignore_index=True)
    return train_df, val_df, split_audit


def compute_entity_baselines(train_df, features, scale_floors):
    """
    Computes Median, IQR, P95, P99, and Scale-Floored Robust denominator per `(cloud_provider, service_name)`
    strictly on `train_df` only.
    """
    baselines = {}
    all_medians = {f: [] for f in features}
    all_scales = {f: [] for f in features}

    for (cp, sn), grp in train_df.groupby(["cloud_provider", "service_name"]):
        entity_key = f"{cp}:{sn}"
        ent_meta = {
            "cloud_provider": cp,
            "service_name": sn,
            "sample_count": int(len(grp)),
            "fit_scope": "train_only",
            "features": {},
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
        "sample_count": int(len(train_df)),
        "fit_scope": "train_only",
        "features": default_features,
    }
    return baselines


def transform_entity_df(grp, ent_meta, features):
    """Transforms a single entity's dataframe into standardized z-score matrix `(N, 8)`."""
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
        windows.append(data_2d[start : start + window_size])
    if not windows:
        return np.empty((0, window_size, data_2d.shape[1]), dtype=np.float32)
    return np.array(windows, dtype=np.float32)


def build_disjoint_entity_windows(train_df, val_df, baselines, features, window_size, stride):
    """
    Transforms `train_df` and `val_df` using train-fitted `baselines` and builds sliding
    windows separately for each split so zero raw timesteps are shared across splits.
    """
    train_chunks = []
    val_chunks = []
    entity_window_counts = {}
    train_ts_pairs = set()
    val_ts_pairs = set()

    for (cp, sn), t_grp in train_df.groupby(["cloud_provider", "service_name"]):
        t_grp = t_grp.sort_values("timestamp").reset_index(drop=True)
        entity_key = f"{cp}:{sn}"
        ent_meta = baselines.get(entity_key, baselines["__default__"])

        # 1. Train windows from strictly earlier timestamps
        z_train = transform_entity_df(t_grp, ent_meta, features)
        tw = create_windows(z_train, window_size=window_size, stride=stride)
        if len(tw) > 0:
            train_chunks.append(tw)
        for ts in t_grp["timestamp"].values:
            train_ts_pairs.add((entity_key, float(ts)))

        # 2. Validation windows from strictly later timestamps (using train-only baselines)
        v_grp = val_df[(val_df["cloud_provider"] == cp) & (val_df["service_name"] == sn)].sort_values("timestamp").reset_index(drop=True)
        z_val = transform_entity_df(v_grp, ent_meta, features)
        vw = create_windows(z_val, window_size=window_size, stride=stride)
        if len(vw) > 0:
            val_chunks.append(vw)
        for ts in v_grp["timestamp"].values:
            val_ts_pairs.add((entity_key, float(ts)))

        entity_window_counts[entity_key] = {
            "train_windows": int(len(tw)),
            "val_windows": int(len(vw)),
            "total_windows": int(len(tw) + len(vw)),
        }

    shared_ts = train_ts_pairs.intersection(val_ts_pairs)
    if shared_ts:
        raise AssertionError(f"Window overlap leakage detected: {len(shared_ts)} shared (entity, timestamp) pairs!")

    base_train_windows = np.concatenate(train_chunks, axis=0)
    val_windows = np.concatenate(val_chunks, axis=0)
    return base_train_windows, val_windows, entity_window_counts


def augment_training_windows(train_windows, features, rng):
    """
    Generates realistic standardized training windows strictly from `train_windows`:
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
                w[:, :, j] = np.clip(
                    w[:, :, j] + delta + rng.normal(0.0, 0.06, size=w[:, :, j].shape), -2.5, 2.6
                )
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
    parser = argparse.ArgumentParser(description="Preprocess Multi-Cloud Per-Entity Telemetry (V3 Leak-Free)")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to model_config.yaml")
    args = parser.parse_args()

    cfg = load_config(args.config)
    raw_csv = cfg["data"]["raw_csv_path"]
    processed_dir = cfg["data"]["processed_dir"]
    baselines_path = cfg["data"]["entity_baselines_path"]
    features = cfg["data"]["features"]
    scale_floors = cfg["data"]["physical_scale_floors"]
    window_size = int(cfg["data"]["window_size"])
    stride = int(cfg["data"]["stride"])
    val_split = float(cfg["data"]["val_split"])
    seed = int(cfg["data"]["random_seed"])

    os.makedirs(processed_dir, exist_ok=True)
    os.makedirs(os.path.dirname(os.path.abspath(baselines_path)), exist_ok=True)

    print("========================================================================", flush=True)
    print("  MULTI-CLOUD PER-ENTITY PREPROCESSING PIPELINE (V3 ZERO-LEAKAGE)", flush=True)
    print("========================================================================", flush=True)

    df = pd.read_csv(raw_csv)
    df = df.sort_values(["cloud_provider", "service_name", "timestamp"]).reset_index(drop=True)

    # Forward/backward fill strictly within each entity to avoid cross-entity contamination
    df[features] = (
        df.groupby(["cloud_provider", "service_name"])[features]
        .transform(lambda g: g.ffill().bfill())
        .fillna(0.0)
    )

    if "anomaly_label" in df.columns:
        df = df[df["anomaly_label"] == 0].reset_index(drop=True)

    # Step 1: Chronological train/val split per entity BEFORE computing baselines or windows
    train_df, val_df, split_audit = split_entities_chronologically(df, val_split=val_split, window_size=window_size)

    # Step 2: Fit per-entity baselines strictly on train_df
    baselines = compute_entity_baselines(train_df, features, scale_floors)

    with open(baselines_path, "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)
    with open(os.path.join(processed_dir, "entity_baselines.json"), "w", encoding="utf-8") as f:
        json.dump(baselines, f, indent=2)

    # Step 3: Build non-overlapping windows separately on train_df and val_df
    base_train_windows, val_windows, entity_window_counts = build_disjoint_entity_windows(
        train_df, val_df, baselines, features, window_size=window_size, stride=stride
    )

    # Step 4: Augment ONLY training windows
    rng = np.random.default_rng(seed)
    train_windows = augment_training_windows(base_train_windows, features, rng)
    rng.shuffle(train_windows)

    np.save(os.path.join(processed_dir, "train_windows.npy"), train_windows)
    np.save(os.path.join(processed_dir, "val_windows.npy"), val_windows)

    with open(os.path.join(processed_dir, "feature_names.json"), "w", encoding="utf-8") as f:
        json.dump(features, f, indent=2)

    summary = {
        "architecture": "Per-Entity Z-Score Standardized Universal Autoencoder (V3)",
        "split_strategy": "strict_chronological_per_entity_pre_windowing",
        "baseline_fit_scope": "train_only",
        "window_overlap_between_train_and_val": 0,
        "total_raw_entity_rows": int(len(df)),
        "train_raw_entity_rows": int(len(train_df)),
        "val_raw_entity_rows": int(len(val_df)),
        "discovered_entities": list(entity_window_counts.keys()),
        "entity_window_counts": entity_window_counts,
        "per_entity_temporal_split": split_audit,
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

    print(f"  * Total Raw Entity Rows  : {len(df)} (Train: {len(train_df)}, Val: {len(val_df)})", flush=True)
    print(f"  * Baseline Fit Scope     : TRAIN ONLY ({len(train_df)} rows; 0 val rows leaked)", flush=True)
    print(f"  * Train/Val Overlap      : 0 shared timesteps", flush=True)
    print(f"  * Discovered Entities    : {', '.join(entity_window_counts.keys())}", flush=True)
    print(f"  * Base Train Windows     : {base_train_windows.shape}", flush=True)
    print(f"  * Augmented Train Windows: {train_windows.shape}", flush=True)
    print(f"  * Validation Windows     : {val_windows.shape} (100% disjoint future horizon)", flush=True)
    print(f"  * Saved Entity Baselines : {baselines_path}", flush=True)
    print("========================================================================", flush=True)


if __name__ == "__main__":
    main()
