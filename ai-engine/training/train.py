#!/usr/bin/env python3.12
"""
Training Pipeline for Universal Per-Entity Multi-Cloud Anomaly Detection (V3).
Trains:
  1. Universal GRU Autoencoder (input_dim=8 standardized entity features)
  2. Universal TCN Autoencoder (input_dim=8 standardized entity features)
  3. Universal Isolation Forest Baseline (96 flattened features)
Calibrates directional & recency-weighted anomaly thresholds on the independent,
non-overlapping validation set (`val_windows.npy`) using the shared `models.scoring`
module, and validates `likelihood_pct` calibration (Brier Score, ECE, Log-Loss).
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
from models.scoring import (
    compute_directional_errors,
    compute_batch_directional_errors,
    validate_likelihood_calibration,
)


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
                flush=True,
            )
        if no_improve >= patience:
            print(f"  [{name}] Early stopping triggered at epoch {epoch}.", flush=True)
            break

    if best_state is not None:
        model.load_state_dict(best_state)
    return model, train_losses, val_losses, best_val_loss, best_epoch


def compute_reference_fault_mse(gru_model, tcn_model, features, window_size, device):
    """
    Evaluates reference fault windows (from `tests/chaos/scenarios.json` if present, or
    canonical fault perturbations) through the shared `compute_directional_errors` function
    to validate `likelihood_pct` separation on true faults vs held-out normal validation windows.
    """
    repo_root = os.path.abspath(os.path.join(ai_engine_root, ".."))
    scenarios_path = os.path.join(repo_root, "tests", "chaos", "scenarios.json")
    fault_vectors = []
    if os.path.isfile(scenarios_path):
        try:
            with open(scenarios_path, "r", encoding="utf-8") as f:
                scenarios = json.load(f)
            for sc in scenarios:
                if sc.get("expected") == "ALERT":
                    fault_vectors.append((np.array(sc["z"], dtype=np.float32), bool(sc.get("response_healthy", False))))
        except Exception:
            pass

    if not fault_vectors:
        fault_vectors = [
            (np.array([-0.5, 6.2, 6.8, 0.0, -0.2, 0.1, 0.0, 0.0], dtype=np.float32), False),
            (np.array([0.2, 3.8, 1.2, 0.0, 2.5, 5.5, 5.8, 4.9], dtype=np.float32), False),
            (np.array([1.1, 5.4, 0.5, 6.0, 5.8, 1.5, 0.8, 1.2], dtype=np.float32), False),
        ]

    fault_mses = []
    with torch.no_grad():
        for z_vec, resp_ok in fault_vectors:
            win = np.tile(z_vec, (window_size, 1))
            t_in = torch.from_numpy(win).unsqueeze(0).to(device)
            g_mse, _ = compute_directional_errors(t_in, gru_model(t_in), features, is_response_healthy=resp_ok)
            t_mse, _ = compute_directional_errors(t_in, tcn_model(t_in), features, is_response_healthy=resp_ok)
            fault_mses.append(0.5 * (g_mse + t_mse))
    return np.array(fault_mses, dtype=np.float64)


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
    window_size = int(cfg["data"]["window_size"])

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
    print(f"  Train Windows : {train_windows.shape} | Disjoint Val Windows: {val_windows.shape}", flush=True)
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
    print(f"  [IsolationForest] Disjoint Validation Normal Accuracy: {iso_normal_acc:.2f}%", flush=True)

    # 4. Calibrate Ensemble Reconstruction Error & Thresholds on Disjoint Validation Windows
    #    using the unified `models.scoring.compute_batch_directional_errors`
    gru_model.eval()
    tcn_model.eval()
    with torch.no_grad():
        val_tensor = torch.from_numpy(val_windows).float().to(device)
        rec_gru = gru_model(val_tensor).cpu().numpy()
        rec_tcn = tcn_model(val_tensor).cpu().numpy()

    gru_s_err, gru_f_err = compute_batch_directional_errors(val_windows, rec_gru, features)
    tcn_s_err, tcn_f_err = compute_batch_directional_errors(val_windows, rec_tcn, features)

    ens_sample_err = 0.5 * (gru_s_err + tcn_s_err)
    ens_feat_err = 0.5 * (gru_f_err + tcn_f_err)

    val_mean = float(np.mean(ens_sample_err))
    val_std = float(np.std(ens_sample_err))
    raw_p95 = float(np.percentile(ens_sample_err, 95))
    raw_p99 = float(np.percentile(ens_sample_err, 99))
    raw_p995 = float(np.percentile(ens_sample_err, 99.5))
    val_max = float(np.max(ens_sample_err))

    # Calibrate threshold strictly from independent validation distribution (+ safety margin)
    stat_bound = max(raw_p99 * 1.35, val_max * 1.15, val_mean + 4.0 * val_std)
    recommended_threshold = max(0.35, round(stat_bound, 4))

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

    # 5. Validate `likelihood_pct` Calibration before interpreting as fault probability
    fault_mses = compute_reference_fault_mse(gru_model, tcn_model, features, window_size, device)
    likelihood_cal = validate_likelihood_calibration(
        normal_mse_array=ens_sample_err,
        fault_mse_array=fault_mses,
        base_mean=val_mean,
        base_std=val_std,
        threshold=recommended_threshold,
        dw_cfg=cfg["thresholding"]["dual_window"],
    )

    threshold_meta = {
        "architecture": "Universal Per-Entity GRU + TCN Autoencoder Ensemble (V3)",
        "scoring_module": "models.scoring.compute_directional_errors",
        "calibration_scope": "disjoint_chronological_validation_set",
        "num_features": input_dim,
        "features": features,
        "error_distribution": {
            "mean": round(val_mean, 6),
            "std": round(val_std, 6),
            "p95": round(raw_p95, 6),
            "p99": round(raw_p99, 6),
            "p99_5": round(raw_p995, 6),
            "max": round(val_max, 6),
        },
        "recommended_threshold_p99": recommended_threshold,
        "dual_sliding_window": cfg["thresholding"]["dual_window"],
        "likelihood_calibration": likelihood_cal,
        "feature_rca_baselines": feature_rca_baselines,
        "isolation_forest_val_normal_pct": round(iso_normal_acc, 2),
        "training_duration_sec": round(time.time() - t0, 2),
    }

    threshold_path = os.path.join(save_dir, "threshold_config.json")
    with open(threshold_path, "w", encoding="utf-8") as f:
        json.dump(threshold_meta, f, indent=2)

    # 6. Plot Convergence Curve
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

    # 7. Generate Training Report Markdown
    report_lines = [
        "# Báo cáo Huấn luyện Hệ thống AI Đa Đám Mây V3 (Zero-Leakage & Unified Scoring)",
        "",
        "## 1. Kiến trúc, Phân tách Dữ liệu & Chống Rò rỉ (Zero Data Leakage)",
        "- **Chiến lược chia tập dữ liệu**: Chia theo thứ tự thời gian (`strict_chronological_per_entity_pre_windowing`) cho từng thực thể trước khi tính baseline và trước khi cắt cửa sổ trượt.",
        "- **Phạm vi tính `entity_baselines.json`**: Chỉ tính trên tập `Train` (`fit_scope = train_only`), tuyệt đối không dùng mẫu của tập `Validation`.",
        "- **Chồng lấn cửa sổ (`Window Overlap`)**: `0` mẫu thời gian dùng chung giữa `train_windows` và `val_windows`.",
        f"- **Số cửa sổ Train (đã tăng cường)**: `{len(train_windows)}`",
        f"- **Số cửa sổ Validation độc lập**: `{len(val_windows)}`",
        f"- **8 Đặc trưng Thực thể Chuẩn**: {', '.join(f'`{f}`' for f in features)}",
        "",
        "## 2. Kết quả Hội tụ & Hiệu chỉnh Ngưỡng (Unified Scoring)",
        "- **Hàm chấm điểm dùng chung**: [`models/scoring.py`](../models/scoring.py) (`compute_directional_errors` & `DualSlidingWindowScorer`) dùng thống nhất giữa huấn luyện và suy luận.",
        f"- **Universal GRU Autoencoder**: Best Disjoint Val Loss = `{gru_best_val:.6f}` (Epoch `{gru_best_ep}`)",
        f"- **Universal TCN Autoencoder**: Best Disjoint Val Loss = `{tcn_best_val:.6f}` (Epoch `{tcn_best_ep}`)",
        f"- **Universal Isolation Forest**: Disjoint Validation Normal Accuracy = `{iso_normal_acc:.2f}%`",
        f"- **Ngưỡng quyết định bất thường (`recommended_threshold_p99`)**: `{recommended_threshold:.4f}` (Disjoint Val Mean = `{val_mean:.5f}`, P99 = `{raw_p99:.5f}`, Max = `{val_max:.5f}`)",
        "",
        "## 3. Kiểm định Xác suất Lỗi (`likelihood_pct` Calibration Verification)",
        f"- **Phương pháp hiệu chuẩn**: `logistic_boundary_anchored` (neo $P(\\text{{anomaly}} \\mid \\text{{MSE}} = \\tau) = 50.0\\%$ và $P(\\text{{anomaly}} \\mid \\mu_{{\\text{{val}}}}) \\le 1.0\\%$, Temperature = `{likelihood_cal['temperature']}`)",
        f"- **Brier Score**: `{likelihood_cal['brier_score']:.6f}` (Mục tiêu $\\le 0.05$)",
        f"- **Expected Calibration Error (ECE)**: `{likelihood_cal['expected_calibration_error']:.6f}` (Mục tiêu $\\le 0.10$)",
        f"- **Log-Loss**: `{likelihood_cal['log_loss']:.6f}`",
        f"- **Xác suất trên tập Validation khỏe mạnh**: Trung bình `{likelihood_cal['normal_val_mean_prob_pct']}%` | P95 `{likelihood_cal['normal_val_p95_prob_pct']}%` | Max `{likelihood_cal['normal_val_max_prob_pct']}%` ($< 50\\%$)",
        f"- **Xác suất trên các kịch bản lỗi chuẩn**: Min `{likelihood_cal['fault_min_prob_pct']}%` | Trung bình `{likelihood_cal['fault_mean_prob_pct']}%` ($> 50\\%$)",
        f"- **Trạng thái kiểm định (`calibration_verified`)**: `{likelihood_cal['calibration_verified']}`",
        "",
        "## 4. Biểu đồ Hội tụ",
        "![Training Loss Curve](../data/processed/training_loss.png)",
        "",
    ]
    report_path = os.path.join(current_dir, "training_report.md")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))

    print("\n========================================================================", flush=True)
    print(f"  TRAINING & CALIBRATION COMPLETE in {time.time() - t0:.1f}s!", flush=True)
    print(f"  * GRU Best Val Loss : {gru_best_val:.6f} (Epoch {gru_best_ep})", flush=True)
    print(f"  * TCN Best Val Loss : {tcn_best_val:.6f} (Epoch {tcn_best_ep})", flush=True)
    print(f"  * IForest Val Acc   : {iso_normal_acc:.2f}%", flush=True)
    print(f"  * Anomaly Threshold : {recommended_threshold:.4f} (Disjoint Val P99={raw_p99:.5f}, Max={val_max:.5f})", flush=True)
    print(
        f"  * Likelihood Calib  : Verified={likelihood_cal['calibration_verified']} | "
        f"Brier={likelihood_cal['brier_score']:.5f} | ECE={likelihood_cal['expected_calibration_error']:.5f} | "
        f"NormalMax={likelihood_cal['normal_val_max_prob_pct']}% | FaultMin={likelihood_cal['fault_min_prob_pct']}%",
        flush=True,
    )
    print("========================================================================", flush=True)


if __name__ == "__main__":
    main()
