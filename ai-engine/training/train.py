#!/usr/bin/env python3.12
"""
Training Pipeline for Universal Per-Entity Multi-Cloud Anomaly Detection (V3).
Trains:
  1. Universal GRU Autoencoder (input_dim=8 standardized entity features)
  2. Universal TCN Autoencoder (input_dim=8 standardized entity features)
  3. Universal Isolation Forest Baseline (96 flattened features)
Calibrates directional & recency-weighted anomaly thresholds and generates training report.
"""

import os
import sys
import json
import time
import yaml
import joblib
import argparse
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import TensorDataset, DataLoader
from sklearn.ensemble import IsolationForest
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

current_dir = os.path.dirname(os.path.abspath(__file__))
ai_engine_root = os.path.abspath(os.path.join(current_dir, ".."))
if ai_engine_root not in sys.path:
    sys.path.insert(0, ai_engine_root)

from models.gru_autoencoder import GRUAutoencoder
from models.tcn_autoencoder import TCNAutoencoder

UPPER_BOUND_SATURATION_FEATURES = {
    "server_latency_p95",
    "client_latency_p95",
    "error_rate_5xx",
    "max_pod_cpu_pct",
    "max_pod_ram_pct",
    "ram_floor_2m_pct",
    "gc_pause_rate",
}

ACTIVE_RESOURCE_FEATURES = {
    "max_pod_cpu_pct",
    "max_pod_ram_pct",
}


def compute_directional_recency_errors(x_true, x_pred, features):
    """
    Computes directional & recency-weighted MSE across validation windows (N, seq_len, 8).
    """
    diff = x_true - x_pred
    n_samples, seq_len, n_feat = diff.shape
    weights = np.ones_like(diff, dtype=np.float32)

    idx_map = {f: i for i, f in enumerate(features)}
    srv_lat_idx = idx_map.get("server_latency_p95", 1)
    err_idx = idx_map.get("error_rate_5xx", 3)

    # Identify windows where server latency & error rate are healthy
    healthy_resp_mask = (x_true[:, -1, srv_lat_idx] < 1.8) & (x_true[:, -1, err_idx] < 0.5)

    for j, fname in enumerate(features):
        if fname in UPPER_BOUND_SATURATION_FEATURES:
            low_mask = (x_true[:, :, j] < 0.0) & (diff[:, :, j] < 0.0)
            weights[:, :, j] = np.where(low_mask, 0.15, weights[:, :, j])

            if fname in ACTIVE_RESOURCE_FEATURES:
                for i in range(n_samples):
                    if healthy_resp_mask[i]:
                        act_mask = (x_true[i, :, j] >= 0.0) & (x_true[i, :, j] < 2.8)
                        weights[i, :, j] = np.where(act_mask, 0.18, weights[i, :, j])
        elif fname == "qps":
            q_mask = x_true[:, :, j] < 2.8
            weights[:, :, j] = np.where(q_mask, 0.18, 1.0)

    t_idx = np.arange(seq_len, dtype=np.float32)
    t_weights = np.exp(0.45 * (t_idx - (seq_len - 1)))
    t_weights = (t_weights / t_weights.sum()).reshape(1, seq_len, 1)

    weighted_sq = (diff ** 2) * weights
    feat_errors = (weighted_sq * t_weights).sum(axis=1)  # (N, 8)
    sample_errors = feat_errors.mean(axis=1)             # (N,)
    return sample_errors, feat_errors


def train_deep_model(model, train_loader, val_loader, epochs, lr, weight_decay, patience, device, name="Model"):
    criterion = nn.SmoothL1Loss(beta=0.5)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=weight_decay)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, mode="min", factor=0.5, patience=4)

    best_val_loss = float("inf")
    best_state = None
    best_epoch = 0
    no_improve = 0
    train_losses, val_losses = [], []

    for epoch in range(1, epochs + 1):
        model.train()
        t_loss_sum, t_cnt = 0.0, 0
        for (batch_x,) in train_loader:
            batch_x = batch_x.to(device)
            optimizer.zero_grad()
            rec = model(batch_x)
            loss = criterion(rec, batch_x)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()
            t_loss_sum += loss.item() * len(batch_x)
            t_cnt += len(batch_x)

        avg_train = t_loss_sum / max(1, t_cnt)

        model.eval()
        v_loss_sum, v_cnt = 0.0, 0
        with torch.no_grad():
            for (batch_x,) in val_loader:
                batch_x = batch_x.to(device)
                rec = model(batch_x)
                loss = criterion(rec, batch_x)
                v_loss_sum += loss.item() * len(batch_x)
                v_cnt += len(batch_x)

        avg_val = v_loss_sum / max(1, v_cnt)
        scheduler.step(avg_val)
        train_losses.append(avg_train)
        val_losses.append(avg_val)

        if avg_val < best_val_loss - 1e-5:
            best_val_loss = avg_val
            best_epoch = epoch
            best_state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
            no_improve = 0
        else:
            no_improve += 1

        if epoch == 1 or epoch % 5 == 0 or no_improve >= patience:
            print(
                f"  [{name}] Epoch {epoch:02d}/{epochs:02d} | "
                f"Train Loss: {avg_train:.6f} | Val Loss: {avg_val:.6f} (Best: {best_val_loss:.6f} @ Ep {best_epoch})",
                flush=True
            )
        if no_improve >= patience:
            print(f"  [{name}] Early stopping triggered at epoch {epoch}.", flush=True)
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, train_losses, val_losses, best_val_loss, best_epoch


def main():
    parser = argparse.ArgumentParser(description="Train Universal Per-Entity Autoencoders (V3)")
    parser.add_argument("--config", default="ai-engine/configs/model_config.yaml", help="Path to config YAML")
    args = parser.parse_args()

    with open(args.config, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    processed_dir = cfg["data"]["processed_dir"]
    save_dir = cfg["training"]["save_dir"]
    os.makedirs(save_dir, exist_ok=True)

    train_windows = np.load(os.path.join(processed_dir, "train_windows.npy"))
    val_windows = np.load(os.path.join(processed_dir, "val_windows.npy"))
    with open(os.path.join(processed_dir, "feature_names.json"), "r", encoding="utf-8") as f:
        features = json.load(f)

    input_dim = len(features)
    hidden_dim = cfg["model"]["hidden_dim"]
    latent_dim = cfg["model"]["latent_dim"]
    num_layers = cfg["model"]["num_layers"]
    dropout = cfg["model"]["dropout"]

    batch_size = cfg["training"]["batch_size"]
    lr = cfg["training"]["learning_rate"]
    weight_decay = cfg["training"]["weight_decay"]
    epochs = cfg["training"]["epochs"]
    patience = cfg["training"]["early_stopping_patience"]

    torch.manual_seed(cfg["data"]["random_seed"])
    np.random.seed(cfg["data"]["random_seed"])
    device = torch.device("cpu")

    train_ds = TensorDataset(torch.from_numpy(train_windows).float())
    val_ds = TensorDataset(torch.from_numpy(val_windows).float())
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    print("========================================================================", flush=True)
    print("  UNIVERSAL PER-ENTITY MULTI-CLOUD AI TRAINING PIPELINE (V3)", flush=True)
    print(f"  Train Windows : {train_windows.shape} | Val Windows: {val_windows.shape}", flush=True)
    print(f"  Entity Features ({input_dim}): {', '.join(features)}", flush=True)
    print("========================================================================\n", flush=True)

    t0 = time.time()

    # 1. Train Universal GRU Autoencoder
    print(">>> [1/3] Training Universal GRU Autoencoder...", flush=True)
    gru_model = GRUAutoencoder(
        input_dim=input_dim, hidden_dim=hidden_dim, latent_dim=latent_dim, num_layers=num_layers, dropout=dropout
    ).to(device)
    gru_model, gru_t_hist, gru_v_hist, gru_best_val, gru_best_ep = train_deep_model(
        gru_model, train_loader, val_loader, epochs, lr, weight_decay, patience, device, name="GRU-AE"
    )
    gru_path = os.path.join(save_dir, cfg["training"]["checkpoint_name"])
    torch.save({
        "model_state_dict": gru_model.state_dict(),
        "input_dim": input_dim,
        "hidden_dim": hidden_dim,
        "latent_dim": latent_dim,
        "num_layers": num_layers,
        "features": features,
        "best_val_loss": gru_best_val,
        "best_epoch": gru_best_ep,
    }, gru_path)

    # 2. Train Universal TCN Autoencoder
    print("\n>>> [2/3] Training Universal TCN Autoencoder...", flush=True)
    tcn_model = TCNAutoencoder(
        input_dim=input_dim, hidden_dim=hidden_dim, latent_dim=latent_dim, dropout=dropout
    ).to(device)
    tcn_model, tcn_t_hist, tcn_v_hist, tcn_best_val, tcn_best_ep = train_deep_model(
        tcn_model, train_loader, val_loader, epochs, lr, weight_decay, patience, device, name="TCN-AE"
    )
    tcn_path = os.path.join(save_dir, "tcn_autoencoder.pt")
    torch.save({
        "model_state_dict": tcn_model.state_dict(),
        "input_dim": input_dim,
        "hidden_dim": hidden_dim,
        "latent_dim": latent_dim,
        "features": features,
        "best_val_loss": tcn_best_val,
        "best_epoch": tcn_best_ep,
    }, tcn_path)

    # 3. Train Universal Isolation Forest
    print("\n>>> [3/3] Training Universal Isolation Forest Baseline...", flush=True)
    flat_train = train_windows.reshape(len(train_windows), -1)
    flat_val = val_windows.reshape(len(val_windows), -1)
    iso_cfg = cfg["baseline"]["isolation_forest"]
    iso_model = IsolationForest(
        n_estimators=iso_cfg["n_estimators"],
        contamination=iso_cfg["contamination"],
        random_state=iso_cfg["random_state"],
        n_jobs=-1,
    )
    iso_model.fit(flat_train)
    val_preds = iso_model.predict(flat_val)
    iso_normal_acc = float(np.mean(val_preds == 1) * 100.0)
    joblib.dump(iso_model, iso_cfg["save_path"])
    print(f"  [IsolationForest] Validation Normal Accuracy: {iso_normal_acc:.2f}%", flush=True)

    # 4. Calibrate Ensemble Reconstruction Error & Thresholds
    gru_model.eval()
    tcn_model.eval()
    with torch.no_grad():
        val_tensor = torch.from_numpy(val_windows).float().to(device)
        rec_gru = gru_model(val_tensor).cpu().numpy()
        rec_tcn = tcn_model(val_tensor).cpu().numpy()

    gru_s_err, gru_f_err = compute_directional_recency_errors(val_windows, rec_gru, features)
    tcn_s_err, tcn_f_err = compute_directional_recency_errors(val_windows, rec_tcn, features)

    ens_sample_err = 0.5 * (gru_s_err + tcn_s_err)
    ens_feat_err = 0.5 * (gru_f_err + tcn_f_err)

    raw_p95 = float(np.percentile(ens_sample_err, 95))
    raw_p99 = float(np.percentile(ens_sample_err, 99))
    raw_p995 = float(np.percentile(ens_sample_err, 99.5))
    recommended_threshold = max(0.35, round(raw_p99 * 1.25, 4))

    feature_rca_baselines = {}
    for j, fname in enumerate(features):
        f_vals = ens_feat_err[:, j]
        f_p99 = float(np.percentile(f_vals, 99))
        feature_rca_baselines[fname] = {
            "mean_sq_err": round(float(np.mean(f_vals)), 6),
            "p95_sq_err": round(float(np.percentile(f_vals, 95)), 6),
            "p99_sq_err": round(f_p99, 6),
            "rca_trigger_threshold": round(max(0.40, f_p99 * 1.5), 4),
        }

    threshold_meta = {
        "architecture": "Universal Per-Entity GRU + TCN Autoencoder Ensemble (V3)",
        "num_features": input_dim,
        "features": features,
        "error_distribution": {
            "mean": round(float(np.mean(ens_sample_err)), 6),
            "std": round(float(np.std(ens_sample_err)), 6),
            "p95": round(raw_p95, 6),
            "p99": round(raw_p99, 6),
            "p99_5": round(raw_p995, 6),
            "max": round(float(np.max(ens_sample_err)), 6),
        },
        "recommended_threshold_p99": recommended_threshold,
        "dual_sliding_window": cfg["thresholding"]["dual_window"],
        "feature_rca_baselines": feature_rca_baselines,
        "isolation_forest_val_normal_pct": round(iso_normal_acc, 2),
        "training_duration_sec": round(time.time() - t0, 2),
    }

    threshold_path = os.path.join(save_dir, "threshold_config.json")
    with open(threshold_path, "w", encoding="utf-8") as f:
        json.dump(threshold_meta, f, indent=2)

    # 5. Plot Convergence Curve
    fig, axes = plt.subplots(1, 2, figsize=(13, 5))
    axes[0].plot(gru_t_hist, label="GRU Train Loss", linewidth=1.8)
    axes[0].plot(gru_v_hist, label="GRU Val Loss", linewidth=1.8)
    axes[0].set_title(f"Universal GRU Autoencoder (Best Val={gru_best_val:.5f} @ Ep {gru_best_ep})")
    axes[0].set_xlabel("Epoch")
    axes[0].set_ylabel("SmoothL1 Loss")
    axes[0].grid(True, alpha=0.3)
    axes[0].legend()

    axes[1].plot(tcn_t_hist, label="TCN Train Loss", linewidth=1.8)
    axes[1].plot(tcn_v_hist, label="TCN Val Loss", linewidth=1.8)
    axes[1].set_title(f"Universal TCN Autoencoder (Best Val={tcn_best_val:.5f} @ Ep {tcn_best_ep})")
    axes[1].set_xlabel("Epoch")
    axes[1].set_ylabel("SmoothL1 Loss")
    axes[1].grid(True, alpha=0.3)
    axes[1].legend()

    plt.tight_layout()
    loss_plot_path = os.path.join(processed_dir, "training_loss.png")
    plt.savefig(loss_plot_path, dpi=150)
    plt.close()

    # 6. Generate Training Report Markdown
    report_lines = [
        "# Báo cáo Huấn luyện Hệ thống AI Đa Đám Mây V3 (Universal Per-Entity Autoencoder)",
        "",
        "## 1. Kiến trúc & Dữ liệu Huấn luyện",
        f"- **Mô hình**: Universal Per-Entity `GRUAutoencoder` + `TCNAutoencoder` + `IsolationForest`",
        f"- **Cửa sổ Đầu vào**: `(12 bước × 8 đặc trưng chuẩn hóa Z-Score theo từng thực thể)`",
        f"- **Số cửa sổ Train (đã tăng cường)**: `{len(train_windows)}`",
        f"- **Số cửa sổ Validation**: `{len(val_windows)}`",
        f"- **8 Đặc trưng Thực thể Chuẩn**: {', '.join(f'`{f}`' for f in features)}",
        "",
        "## 2. Kết quả Hội tụ Mô hình",
        f"- **Universal GRU Autoencoder**: Best Val Loss = `{gru_best_val:.6f}` (Epoch `{gru_best_ep}`)",
        f"- **Universal TCN Autoencoder**: Best Val Loss = `{tcn_best_val:.6f}` (Epoch `{tcn_best_ep}`)",
        f"- **Universal Isolation Forest**: Validation Normal Accuracy = `{iso_normal_acc:.2f}%`",
        f"- **Ngưỡng quyết định bất thường (`recommended_threshold_p99`)**: `{recommended_threshold:.4f}` (Validation P99 = `{raw_p99:.5f}`)",
        "",
        "## 3. Biểu đồ Hội tụ",
        "![Training Loss Curve](../data/processed/training_loss.png)",
        "",
    ]
    report_path = os.path.join(current_dir, "training_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print("\n========================================================================", flush=True)
    print(f"  TRAINING COMPLETE in {time.time() - t0:.1f}s!", flush=True)
    print(f"  * GRU Best Val Loss : {gru_best_val:.6f} (Epoch {gru_best_ep})", flush=True)
    print(f"  * TCN Best Val Loss : {tcn_best_val:.6f} (Epoch {tcn_best_ep})", flush=True)
    print(f"  * IForest Val Acc   : {iso_normal_acc:.2f}%", flush=True)
    print(f"  * Anomaly Threshold : {recommended_threshold:.4f} (Val P99={raw_p99:.5f})", flush=True)
    print("========================================================================", flush=True)


if __name__ == "__main__":
    main()
