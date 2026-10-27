#!/usr/bin/env python3.12
"""
Model Training Pipeline: GRU Autoencoder + TCN Autoencoder + Isolation Forest Baseline
Author: Antigravity AI Pair Programmer
Project: Multicloud Monitoring

Pipeline:
  1. Automated Data Pipeline (calls preprocess.py with physical scale floors & regime augmentation)
  2. PyTorch GRU Autoencoder Training
  3. PyTorch TCN Autoencoder Training (Dilated Causal Temporal Convolutional Network)
  4. Isolation Forest Baseline Training
  5. Dual-Sliding-Window Anomaly Likelihood & Threshold Calibration
  6. Feature-level Root Cause Analysis (RCA) Baseline Profiling
"""

import os
import sys
import json
import yaml
import time
import argparse
import joblib
import numpy as np

import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.ensemble import IsolationForest

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

# Ensure ai-engine root is in python path
current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_root = os.path.abspath(os.path.join(current_dir, ".."))
if ai_engine_root not in sys.path:
    sys.path.insert(0, ai_engine_root)

from models.gru_autoencoder import GRUAutoencoder
from models.tcn_autoencoder import TCNAutoencoder
from data.preprocess import run_preprocessing

def parse_args():
    parser = argparse.ArgumentParser(description="Train Anomaly Detection Models on Baseline Telemetry")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to config YAML")
    parser.add_argument("--epochs", type=int, default=None, help="Override epochs count")
    return parser.parse_args()

def train_deep_autoencoder(model, model_name, ckpt_path, train_loader, val_loader, cfg, device):
    t_cfg = cfg["training"]
    epochs = t_cfg.get("epochs", 50)
    lr = float(t_cfg.get("learning_rate", 0.002))
    weight_decay = float(t_cfg.get("weight_decay", 1e-5))
    patience = t_cfg.get("early_stopping_patience", 12)

    criterion = nn.MSELoss()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs, eta_min=1e-5)

    print("\n" + "=" * 70)
    print(f"  TRAINING {model_name.upper()}")
    print("=" * 70)
    print(f"  Device        : {device}")
    print(f"  Epochs        : {epochs} | Batch Size: {t_cfg.get('batch_size', 32)} | Learning Rate: {lr}")
    print(f"  Checkpoint    : {ckpt_path}")
    print("-" * 70)

    history = {"train_loss": [], "val_loss": []}
    best_val_loss = float("inf")
    patience_counter = 0

    start_time = time.time()
    for epoch in range(1, epochs + 1):
        model.train()
        train_loss = 0.0
        for (batch_x,) in train_loader:
            batch_x = batch_x.to(device)
            optimizer.zero_grad()
            reconstructed = model(batch_x)
            loss = criterion(reconstructed, batch_x)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            train_loss += loss.item() * batch_x.size(0)

        train_loss /= len(train_loader.dataset)

        model.eval()
        val_loss = 0.0
        with torch.no_grad():
            for (batch_x,) in val_loader:
                batch_x = batch_x.to(device)
                reconstructed = model(batch_x)
                loss = criterion(reconstructed, batch_x)
                val_loss += loss.item() * batch_x.size(0)

        val_loss /= len(val_loader.dataset)
        scheduler.step()

        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)

        saved_marker = ""
        if val_loss < best_val_loss:
            best_val_loss = val_loss
            patience_counter = 0
            torch.save(
                {
                    "epoch": epoch,
                    "model_state_dict": model.state_dict(),
                    "best_val_loss": best_val_loss,
                    "config": cfg
                },
                ckpt_path
            )
            saved_marker = " [★ Best Checkpoint]"
        else:
            patience_counter += 1

        if epoch % 5 == 0 or epoch == 1 or saved_marker:
            current_lr = scheduler.get_last_lr()[0]
            print(f"  Epoch [{epoch:2d}/{epochs:2d}] | Train MSE: {train_loss:.5f} | Val MSE: {val_loss:.5f} | LR: {current_lr:.6f}{saved_marker}")

        if patience_counter >= patience:
            print(f"\n[Early Stopping] No improvement in validation loss for {patience} consecutive epochs.")
            break

    total_sec = time.time() - start_time
    print("-" * 70)
    print(f"[V] {model_name} finished in {total_sec:.1f}s. Best Val MSE: {best_val_loss:.5f}")

    best_ckpt = torch.load(ckpt_path, map_location=device, weights_only=False)
    model.load_state_dict(best_ckpt["model_state_dict"])
    return model, history, best_val_loss

def calibrate_anomaly_thresholds(gru_model, tcn_model, val_loader, features, cfg, device):
    """
    Computes statistical reconstruction error distribution over clean normal validation set
    and calibrates Dual-Sliding-Window Anomaly Likelihood parameters.
    """
    gru_model.eval()
    tcn_model.eval()
    gru_errors, tcn_errors, feat_errors_list = [], [], []

    with torch.no_grad():
        for (batch_x,) in val_loader:
            batch_x = batch_x.to(device)
            rec_gru = gru_model(batch_x)
            rec_tcn = tcn_model(batch_x)

            gru_mse = gru_model.compute_sample_loss(batch_x, rec_gru)
            tcn_mse = tcn_model.compute_sample_loss(batch_x, rec_tcn)

            # Ensemble feature error (50% GRU + 50% TCN)
            f_mse = 0.5 * (
                gru_model.compute_feature_losses(batch_x, rec_gru) +
                tcn_model.compute_feature_losses(batch_x, rec_tcn)
            )

            gru_errors.append(gru_mse.cpu().numpy())
            tcn_errors.append(tcn_mse.cpu().numpy())
            feat_errors_list.append(f_mse.cpu().numpy())

    gru_err = np.concatenate(gru_errors)
    tcn_err = np.concatenate(tcn_errors)
    ensemble_err = 0.5 * (gru_err + tcn_err)
    feat_errors = np.concatenate(feat_errors_list, axis=0)

    mean_err = float(np.mean(ensemble_err))
    std_err = float(max(1e-4, np.std(ensemble_err)))
    p95 = float(np.percentile(ensemble_err, 95))
    p99 = float(np.percentile(ensemble_err, 99))
    p99_5 = float(np.percentile(ensemble_err, 99.5))
    max_normal_err = float(np.max(ensemble_err))

    # Calibrated threshold: max(p99_5, mean + 4 * std) with safety floor to prevent startup false alarms
    recommended_threshold = float(max(p99_5 * 1.25, mean_err + 4.0 * std_err, 0.35))

    feature_baselines = {}
    mean_feat = np.mean(feat_errors, axis=0)
    std_feat = np.std(feat_errors, axis=0)
    p99_feat = np.percentile(feat_errors, 99, axis=0)

    for idx, fname in enumerate(features):
        trigger = float(max(p99_feat[idx] * 1.5, mean_feat[idx] + 4.0 * std_feat[idx], 0.25))
        feature_baselines[fname] = {
            "normal_mean_error": float(mean_feat[idx]),
            "normal_std_error": float(std_feat[idx]),
            "rca_trigger_threshold": trigger
        }

    threshold_meta = {
        "recommended_threshold_p99": recommended_threshold,
        "gru_val_mse": float(np.mean(gru_err)),
        "tcn_val_mse": float(np.mean(tcn_err)),
        "error_distribution": {
            "mean": mean_err,
            "std": std_err,
            "p95": p95,
            "p99": p99,
            "p99_5": p99_5,
            "max": max_normal_err
        },
        "feature_rca_baselines": feature_baselines,
        "dual_sliding_window": {
            "short_window": 3,
            "long_window": 18,
            "likelihood_alert_threshold": 0.995,
            "min_consecutive_breaches": 2
        }
    }
    return threshold_meta

def train_isolation_forest_baseline(train_windows, val_windows, cfg):
    print("\n" + "=" * 70)
    print("  TRAINING ISOLATION FOREST BASELINE (SHALLOW BENCHMARK)")
    print("=" * 70)
    if_cfg = cfg["baseline"]["isolation_forest"]
    save_path = if_cfg["save_path"]
    os.makedirs(os.path.dirname(os.path.abspath(save_path)), exist_ok=True)

    N_train, W, F = train_windows.shape
    X_train_flat = train_windows.reshape(N_train, W * F)

    N_val = val_windows.shape[0]
    X_val_flat = val_windows.reshape(N_val, W * F)

    iso_forest = IsolationForest(
        n_estimators=if_cfg.get("n_estimators", 150),
        contamination=if_cfg.get("contamination", 0.01),
        random_state=if_cfg.get("random_state", 42),
        n_jobs=-1
    )
    iso_forest.fit(X_train_flat)

    val_preds = iso_forest.predict(X_val_flat)
    normal_ratio = np.mean(val_preds == 1) * 100.0

    joblib.dump(iso_forest, save_path)
    print(f"  Isolation Forest fitted on {N_train} windows.")
    print(f"  Validation Clean Normal Accuracy: {normal_ratio:.1f}%")
    print(f"[V] Saved Isolation Forest baseline to: {save_path}")
    return save_path

def plot_training_loss(gru_hist, tcn_hist, output_path):
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # GRU subplot
    ep_gru = range(1, len(gru_hist["train_loss"]) + 1)
    axes[0].plot(ep_gru, gru_hist["train_loss"], label="GRU Train MSE", color="#1f77b4", lw=2)
    axes[0].plot(ep_gru, gru_hist["val_loss"], label="GRU Val MSE", color="#ff7f0e", lw=2, ls="--")
    axes[0].set_title("GRU Autoencoder Convergence", fontweight="bold")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("Reconstruction Error (MSE)")
    axes[0].grid(True, linestyle=":", alpha=0.6)
    axes[0].legend()

    # TCN subplot
    ep_tcn = range(1, len(tcn_hist["train_loss"]) + 1)
    axes[1].plot(ep_tcn, tcn_hist["train_loss"], label="TCN Train MSE", color="#2ca02c", lw=2)
    axes[1].plot(ep_tcn, tcn_hist["val_loss"], label="TCN Val MSE", color="#d62728", lw=2, ls="--")
    axes[1].set_title("TCN Autoencoder Convergence", fontweight="bold")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("Reconstruction Error (MSE)")
    axes[1].grid(True, linestyle=":", alpha=0.6)
    axes[1].legend()

    plt.tight_layout()
    plt.savefig(output_path, dpi=180)
    plt.close()
    print(f"[Visualization] Training loss curves saved to: {output_path}")

def main():
    args = parse_args()
    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    if args.epochs:
        cfg["training"]["epochs"] = args.epochs

    # Always run preprocessing to ensure latest scale floors & splits are applied
    run_preprocessing(args.config)

    processed_dir = cfg["data"]["processed_dir"]
    train_win_path = os.path.join(processed_dir, "train_windows.npy")
    val_win_path = os.path.join(processed_dir, "val_windows.npy")

    train_windows = np.load(train_win_path)
    val_windows = np.load(val_win_path)

    with open(os.path.join(processed_dir, "feature_names.json"), "r", encoding="utf-8") as f:
        features = json.load(f)

    batch_size = cfg["training"].get("batch_size", 32)
    train_dataset = TensorDataset(torch.from_numpy(train_windows))
    val_dataset = TensorDataset(torch.from_numpy(val_windows))

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True, drop_last=False)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    device = torch.device("cpu")
    m_cfg = cfg["model"]
    save_dir = cfg["training"]["save_dir"]
    os.makedirs(save_dir, exist_ok=True)

    # 1. Train GRU Autoencoder
    gru_model = GRUAutoencoder(
        input_dim=m_cfg.get("input_dim", 14),
        hidden_dim=m_cfg.get("hidden_dim", 64),
        latent_dim=m_cfg.get("latent_dim", 16),
        num_layers=m_cfg.get("num_layers", 2),
        dropout=m_cfg.get("dropout", 0.1)
    ).to(device)
    gru_ckpt = os.path.join(save_dir, cfg["training"].get("checkpoint_name", "gru_autoencoder.pt"))
    gru_model, gru_hist, gru_best = train_deep_autoencoder(
        gru_model, "GRU Autoencoder", gru_ckpt, train_loader, val_loader, cfg, device
    )

    # 2. Train TCN Autoencoder
    tcn_model = TCNAutoencoder(
        input_dim=m_cfg.get("input_dim", 14),
        hidden_dim=m_cfg.get("hidden_dim", 64),
        latent_dim=m_cfg.get("latent_dim", 16),
        kernel_size=3,
        dropout=m_cfg.get("dropout", 0.1)
    ).to(device)
    tcn_ckpt = os.path.join(save_dir, "tcn_autoencoder.pt")
    tcn_model, tcn_hist, tcn_best = train_deep_autoencoder(
        tcn_model, "TCN Autoencoder", tcn_ckpt, train_loader, val_loader, cfg, device
    )

    # 3. Calibrate Dual-Sliding-Window Anomaly Thresholds
    threshold_meta = calibrate_anomaly_thresholds(gru_model, tcn_model, val_loader, features, cfg, device)
    threshold_path = os.path.join(save_dir, "threshold_config.json")
    with open(threshold_path, "w", encoding="utf-8") as f:
        json.dump(threshold_meta, f, indent=2)

    # 4. Train Isolation Forest Baseline
    train_isolation_forest_baseline(train_windows, val_windows, cfg)

    # 5. Plot loss curves
    loss_plot_path = os.path.join(processed_dir, "training_loss.png")
    plot_training_loss(gru_hist, tcn_hist, loss_plot_path)

    print("\n" + "=" * 70)
    print("  MULTI-CLOUD AI ENGINE V2 TRAINING SUMMARY")
    print("=" * 70)
    print(f"  * GRU Autoencoder Best MSE: {gru_best:.6f} ({gru_ckpt})")
    print(f"  * TCN Autoencoder Best MSE: {tcn_best:.6f} ({tcn_ckpt})")
    print(f"  * Ensemble Normal Mean MSE: {threshold_meta['error_distribution']['mean']:.6f} (std: {threshold_meta['error_distribution']['std']:.6f})")
    print(f"  * Calibrated Threshold    : {threshold_meta['recommended_threshold_p99']:.6f}")
    print(f"  * Dual-Window Config      : Short={threshold_meta['dual_sliding_window']['short_window']} | Long={threshold_meta['dual_sliding_window']['long_window']}")
    print("=" * 70)
    print("[V] All models (GRU + TCN + IsolationForest) trained and calibrated!\n")

if __name__ == "__main__":
    main()
