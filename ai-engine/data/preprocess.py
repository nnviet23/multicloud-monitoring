#!/usr/bin/env python3.12
"""
Data Preprocessing & Windowing Module for Multi-Cloud Observability
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring

Performs:
  1. Feature extraction for 14 Golden Features
  2. Domain-Aware RobustScaler with physical scale floors (prevents false alarms
     when latency is faster than average or during light-load / warmup regimes)
  3. Sliding window generation: 3D Tensor [N_sequences, Window_Size, N_Features]
  4. Stratified phase-balanced Train / Validation split + Normal regime augmentation
"""

import os
import json
import yaml
import joblib
import argparse
import numpy as np
import pandas as pd
from sklearn.preprocessing import RobustScaler

# Physical minimum scale floors so narrow-IQR metrics (like latency_p95 ~ 80ms
# or jvm_threads_live ~ 26) do not blow up to ±30 during light load or startup.
PHYSICAL_SCALE_FLOORS = {
    "throughput_qps": 60.0,
    "latency_p95": 0.045,        # 45ms scale unit (5ms..95ms stays within ~2 units)
    "app_cpu_pct": 12.0,         # 12% CPU scale unit (handles warm-up & burst CPU smoothly)
    "max_pod_cpu_pct": 25.0,     # 25% hotspot CPU scale unit
    "app_ram_pct": 12.0,         # 12% RAM scale unit
    "max_pod_ram_pct": 15.0,
    "jvm_threads_live": 6.0,     # 6 threads scale unit (15..32 threads stays normal)
    "jvm_gc_pause_rate": 0.025,
    "webui_cpu_pct": 22.0,       # 22% WebUI CPU scale unit (JSP/JIT & flash-crowd bursts)
    "webui_ram_pct": 18.0,
    "persistence_cpu_pct": 8.0,
    "persistence_ram_pct": 18.0,
    "image_cpu_pct": 10.0,
    "wan_network_io_kbs": 70.0,
}

def parse_args():
    parser = argparse.ArgumentParser(description="Preprocess telemetry data for Deep Learning")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to config YAML")
    return parser.parse_args()

def create_sliding_windows(data_matrix, window_size, stride=1):
    """
    Transforms 2D matrix (T, F) into 3D windows (N, W, F)
    """
    num_samples, _ = data_matrix.shape
    windows = []
    for start in range(0, num_samples - window_size + 1, stride):
        end = start + window_size
        windows.append(data_matrix[start:end, :])
    return np.array(windows, dtype=np.float32)

def generate_normal_regime_augmentations(windows, rng):
    """
    Augments normal training windows with realistic operational regimes:
      - Light / Idle load scaling (when server just started or traffic is low)
      - Mild Gaussian sensor jitter
      - Erratic user traffic transitions (sudden bursts, drops, and rollercoaster swings)
    """
    augmented = [windows]
    # 1. Mild jitter augmentation
    noise = rng.normal(0.0, 0.08, size=windows.shape).astype(np.float32)
    augmented.append(windows + noise)

    # 2. Low-load / fresh-start regime (scaled down towards idle baseline)
    n_low = max(1, len(windows) // 4)
    idx = rng.choice(len(windows), size=n_low, replace=False)
    low_windows = windows[idx].copy()
    low_factors = rng.uniform(0.25, 0.75, size=(n_low, 1, 1)).astype(np.float32)
    low_windows = low_windows * low_factors + rng.normal(0.0, 0.05, size=low_windows.shape).astype(np.float32)
    augmented.append(low_windows)

    # 3. Erratic traffic regime (abrupt step changes & fluctuating user load within window)
    n_erratic = max(1, len(windows) // 3)
    idx_err = rng.choice(len(windows), size=n_erratic, replace=False)
    err_windows = windows[idx_err].copy()
    seq_len = windows.shape[1]
    for i in range(n_erratic):
        step_t = rng.integers(2, seq_len - 2)
        factor_before = rng.uniform(-0.8, 0.8)
        factor_after = rng.uniform(-0.8, 0.9)
        # Apply abrupt workload shift primarily to QPS (idx 0) and WAN IO (idx 13) + mild ripple
        err_windows[i, :step_t, 0] += factor_before
        err_windows[i, step_t:, 0] += factor_after
        err_windows[i, :step_t, 13] += factor_before * 0.85
        err_windows[i, step_t:, 13] += factor_after * 0.85
    err_windows += rng.normal(0.0, 0.06, size=err_windows.shape).astype(np.float32)
    augmented.append(err_windows)

    # 4. Active Burst & JVM Warm-up CPU regime (higher healthy CPU utilization while latency remains fast)
    n_burst = max(1, len(windows) // 3)
    idx_burst = rng.choice(len(windows), size=n_burst, replace=False)
    burst_windows = windows[idx_burst].copy()
    for i in range(n_burst):
        cpu_boost = rng.uniform(0.4, 2.2)
        # Indices: 2=app_cpu_pct, 3=max_pod_cpu_pct, 8=webui_cpu_pct, 10=persistence_cpu_pct, 12=image_cpu_pct
        burst_windows[i, :, 2] += cpu_boost
        burst_windows[i, :, 3] += cpu_boost * rng.uniform(0.9, 1.3)
        burst_windows[i, :, 8] += cpu_boost * rng.uniform(0.8, 1.25)
        burst_windows[i, :, 10] += cpu_boost * rng.uniform(0.3, 0.7)
        burst_windows[i, :, 12] += cpu_boost * rng.uniform(0.3, 0.7)
    burst_windows += rng.normal(0.0, 0.06, size=burst_windows.shape).astype(np.float32)
    augmented.append(burst_windows)

    return np.concatenate(augmented, axis=0)

def run_preprocessing(config_path="ai-engine/configs/model_config.yaml"):
    with open(config_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    raw_path = cfg["data"]["raw_csv_path"]
    processed_dir = cfg["data"]["processed_dir"]
    features = cfg["data"]["features"]
    window_size = cfg["data"]["window_size"]
    stride = cfg["data"].get("stride", 1)
    val_split = cfg["data"].get("val_split", 0.2)
    seed = cfg["data"].get("random_seed", 42)
    rng = np.random.default_rng(seed)

    os.makedirs(processed_dir, exist_ok=True)
    models_dir = cfg["training"]["save_dir"]
    os.makedirs(models_dir, exist_ok=True)

    print("=" * 70)
    print("  MULTI-CLOUD TELEMETRY PREPROCESSING & WINDOWING (V2 ROBUST)")
    print("=" * 70)
    print(f"  Input CSV      : {raw_path}")
    print(f"  Target Features: {len(features)} Golden Features")
    print(f"  Window Size    : {window_size} samples ({window_size * 10} seconds)")
    print(f"  Validation Ratio: {val_split * 100:.1f}% (Stratified across all 4 load phases)")
    print("-" * 70)

    # 1. Load data
    df = pd.read_csv(raw_path)
    total_raw_samples = len(df)
    print(f"[1/4] Loaded raw dataset: {total_raw_samples} samples.")

    missing_cols = [c for c in features if c not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns in CSV: {missing_cols}")

    data_subset = df[features].values.astype(np.float64)

    # 2. Fit RobustScaler with Physical Scale Floors
    scaler = RobustScaler(unit_variance=True)
    scaler.fit(data_subset)

    for idx, fname in enumerate(features):
        floor_val = PHYSICAL_SCALE_FLOORS.get(fname, 1.0)
        if scaler.scale_[idx] < floor_val:
            scaler.scale_[idx] = floor_val

    scaled_all = scaler.transform(data_subset)
    scaler_path = os.path.join(models_dir, "robust_scaler.joblib")
    joblib.dump(scaler, scaler_path)
    print(f"[2/4] Fitted Domain-Aware RobustScaler (with physical scale floors) -> {scaler_path}")

    # 3. Generate sliding windows & Stratified Phase Split (80% Train / 20% Val per hour phase)
    all_windows = create_sliding_windows(scaled_all, window_size, stride)
    n_total_win = len(all_windows)

    train_list, val_list = [], []
    n_phases = 4
    phase_len = n_total_win // n_phases
    for p in range(n_phases):
        p_start = p * phase_len
        p_end = n_total_win if p == n_phases - 1 else (p + 1) * phase_len
        phase_win = all_windows[p_start:p_end]
        split_pt = int(len(phase_win) * (1.0 - val_split))
        train_list.append(phase_win[:split_pt])
        val_list.append(phase_win[split_pt:])

    train_windows_base = np.concatenate(train_list, axis=0)
    val_windows = np.concatenate(val_list, axis=0)

    # Augment training windows with low-load / warmup transitions
    train_windows = generate_normal_regime_augmentations(train_windows_base, rng)

    print(f"[3/4] Stratified Phase Split & Augmentation:")
    print(f"      Base Train Windows     : {len(train_windows_base)}")
    print(f"      Augmented Train Windows: {len(train_windows)} (includes low-load & jitter regimes)")
    print(f"      Validation Windows     : {len(val_windows)}")

    train_out_path = os.path.join(processed_dir, "train_windows.npy")
    val_out_path = os.path.join(processed_dir, "val_windows.npy")
    np.save(train_out_path, train_windows)
    np.save(val_out_path, val_windows)

    feature_meta_path = os.path.join(processed_dir, "feature_names.json")
    with open(feature_meta_path, "w", encoding="utf-8") as f:
        json.dump(features, f, indent=2)

    summary = {
        "raw_samples": total_raw_samples,
        "features": features,
        "n_features": len(features),
        "window_size": window_size,
        "window_duration_seconds": window_size * 10,
        "train_windows_shape": list(train_windows.shape),
        "val_windows_shape": list(val_windows.shape),
        "scaler_path": scaler_path,
        "physical_scale_floors": PHYSICAL_SCALE_FLOORS
    }
    with open(os.path.join(processed_dir, "preprocess_summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print(f"[4/4] Saved processed tensors to {processed_dir}")
    print("=" * 70)
    print("[V] Preprocessing completed successfully!\n")
    return summary

if __name__ == "__main__":
    args = parse_args()
    run_preprocessing(args.config)
