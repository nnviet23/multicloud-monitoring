#!/usr/bin/env python3.12
"""
Unified Multi-Cloud Anomaly Scoring & Probability Calibration Module (V3).

Shared by:
  - `ai-engine/training/train.py` (offline validation error distribution & threshold calibration)
  - `ai-engine/inference/detector.py` (online real-time anomaly detection)
  - `ai-engine/inference/evaluate_test.py` (synthetic & ground-truth evaluation)

Guarantees that training-time validation scoring and inference-time online scoring
use the exact same directional weights, recency horizon decay, response-health
conditions, and calibrated anomaly probability mapping.
"""

import math
import numpy as np
import torch

UPPER_BOUND_SATURATION_METRICS = {
    "server_latency_p95",
    "client_latency_p95",
    "error_rate_5xx",
    "max_pod_cpu_pct",
    "max_pod_ram_pct",
    "ram_floor_2m_pct",
    "gc_pause_rate",
}

ACTIVE_RESOURCE_METRICS = {
    "max_pod_cpu_pct",
    "max_pod_ram_pct",
}

EXOGENOUS_WORKLOAD_METRICS = {
    "qps",
}

# Canonical scoring hyperparameters shared across training and inference
LOW_SATURATION_WEIGHT_HEALTHY = 0.0
LOW_SATURATION_WEIGHT_FAULTY = 0.15
ACTIVE_RESOURCE_Z_LIMIT = 3.5
ACTIVE_RESOURCE_WEIGHT = 0.15
EXOGENOUS_Z_LIMIT = 3.0
EXOGENOUS_WEIGHT = 0.15
RECENCY_DECAY_RATE = 0.45

# Standardized-space thresholds for inferring response health when external HTTP probe is absent
HEALTHY_SRV_LATENCY_Z_MAX = 2.0
HEALTHY_CLI_LATENCY_Z_MAX = 2.0
HEALTHY_ERROR_5XX_Z_MAX = 0.5


def infer_window_response_healthy(x_window, features):
    """
    Infers whether each window in `x_window` (shape `(N, seq_len, n_features)`) represents
    a healthy service response based on the latest standardized latency and 5xx error features.
    """
    if isinstance(x_window, torch.Tensor):
        x_np = x_window.detach().cpu().numpy()
    else:
        x_np = np.asarray(x_window)

    if x_np.ndim == 2:
        x_np = x_np[np.newaxis, :, :]

    idx_map = {f: i for i, f in enumerate(features)}
    n_samples = x_np.shape[0]
    mask = np.ones(n_samples, dtype=bool)

    if "server_latency_p95" in idx_map:
        mask &= x_np[:, -1, idx_map["server_latency_p95"]] < HEALTHY_SRV_LATENCY_Z_MAX
    if "client_latency_p95" in idx_map:
        mask &= x_np[:, -1, idx_map["client_latency_p95"]] < HEALTHY_CLI_LATENCY_Z_MAX
    if "error_rate_5xx" in idx_map:
        mask &= x_np[:, -1, idx_map["error_rate_5xx"]] < HEALTHY_ERROR_5XX_Z_MAX

    return mask


def compute_directional_errors(x_input, x_rec, features, is_response_healthy=None):
    """
    Canonical directional & recency-weighted reconstruction error for a single window
    `(1, seq_len, n_features)` (or `(seq_len, n_features)`).

    Returns:
      - `sample_mse`: float
      - `feat_mse`: np.ndarray of shape `(n_features,)`
    """
    if not isinstance(x_input, torch.Tensor):
        x_input = torch.as_tensor(x_input, dtype=torch.float32)
    if not isinstance(x_rec, torch.Tensor):
        x_rec = torch.as_tensor(x_rec, dtype=torch.float32, device=x_input.device)

    if x_input.ndim == 2:
        x_input = x_input.unsqueeze(0)
    if x_rec.ndim == 2:
        x_rec = x_rec.unsqueeze(0)

    if is_response_healthy is None:
        is_response_healthy = bool(infer_window_response_healthy(x_input[:1], features)[0])
    else:
        is_response_healthy = bool(is_response_healthy)

    diff = x_input - x_rec  # (1, seq_len, n_features)
    seq_len = diff.shape[1]
    weights = torch.ones_like(diff)

    low_weight = LOW_SATURATION_WEIGHT_HEALTHY if is_response_healthy else LOW_SATURATION_WEIGHT_FAULTY

    for idx, fname in enumerate(features):
        if fname in UPPER_BOUND_SATURATION_METRICS:
            mask_low = (x_input[:, :, idx] < 0.0) & (diff[:, :, idx] < 0.0)
            weights[:, :, idx] = torch.where(
                mask_low,
                torch.tensor(low_weight, dtype=diff.dtype, device=diff.device),
                weights[:, :, idx],
            )

            if is_response_healthy and fname in ACTIVE_RESOURCE_METRICS:
                mask_active = (x_input[:, :, idx] >= 0.0) & (x_input[:, :, idx] < ACTIVE_RESOURCE_Z_LIMIT)
                weights[:, :, idx] = torch.where(
                    mask_active,
                    torch.tensor(ACTIVE_RESOURCE_WEIGHT, dtype=diff.dtype, device=diff.device),
                    weights[:, :, idx],
                )
        elif fname in EXOGENOUS_WORKLOAD_METRICS:
            mask_exo = x_input[:, :, idx] < EXOGENOUS_Z_LIMIT
            weights[:, :, idx] = torch.where(
                mask_exo,
                torch.tensor(EXOGENOUS_WEIGHT, dtype=diff.dtype, device=diff.device),
                torch.tensor(1.0, dtype=diff.dtype, device=diff.device),
            )

    t_indices = torch.arange(seq_len, dtype=diff.dtype, device=diff.device)
    t_weights = torch.exp(RECENCY_DECAY_RATE * (t_indices - (seq_len - 1)))
    t_weights = (t_weights / t_weights.sum()).view(1, seq_len, 1)

    weighted_sq_err = (diff ** 2) * weights
    feat_mse_tensor = (weighted_sq_err * t_weights).sum(dim=1).squeeze(0)
    sample_mse = float(feat_mse_tensor.mean().item())
    feat_mse = feat_mse_tensor.detach().cpu().numpy()
    return sample_mse, feat_mse


def compute_batch_directional_errors(x_true, x_pred, features, healthy_mask=None):
    """
    Evaluates `compute_directional_errors` across a batch of windows `(N, seq_len, n_features)`
    using the exact same per-window scoring function used during online inference.

    Returns:
      - `sample_errors`: np.ndarray of shape `(N,)`
      - `feat_errors`: np.ndarray of shape `(N, n_features)`
    """
    x_true_t = torch.as_tensor(x_true, dtype=torch.float32)
    x_pred_t = torch.as_tensor(x_pred, dtype=torch.float32)
    n_samples = x_true_t.shape[0]
    n_features = x_true_t.shape[2]

    if healthy_mask is None:
        healthy_mask = infer_window_response_healthy(x_true_t, features)
    elif isinstance(healthy_mask, bool):
        healthy_mask = np.full(n_samples, healthy_mask, dtype=bool)
    else:
        healthy_mask = np.asarray(healthy_mask, dtype=bool)

    sample_errors = np.zeros(n_samples, dtype=np.float64)
    feat_errors = np.zeros((n_samples, n_features), dtype=np.float64)

    for i in range(n_samples):
        s_mse, f_mse = compute_directional_errors(
            x_true_t[i : i + 1],
            x_pred_t[i : i + 1],
            features,
            is_response_healthy=bool(healthy_mask[i]),
        )
        sample_errors[i] = s_mse
        feat_errors[i] = f_mse

    return sample_errors, feat_errors


class DualSlidingWindowScorer:
    """
    Computes calibrated Anomaly Probability `likelihood` (`L_t in [0, 1]`) and
    sustained anomaly verdicts using short-term vs long-term error windows.

    Calibration properties:
      - Decision boundary alignment: at `short_mean == threshold`, `likelihood == 0.50` (50.0%).
      - Healthy baseline anchoring: at `short_mean <= base_mean`, `likelihood <= 0.01` (1.0%).
      - Strictly monotonic logistic sigmoid parameterized by validation `(base_mean, base_std, threshold)`.
    """

    def __init__(self, base_mean, base_std, threshold, short_w=2, long_w=15, min_consecutive=2, temperature=None):
        self.base_mean = float(base_mean)
        self.base_std = max(1e-4, float(base_std))
        self.threshold = float(threshold)
        self.short_w = int(short_w)
        self.long_w = int(long_w)
        self.min_consecutive = int(min_consecutive)
        # Logistic temperature scale so P(anomaly | base_mean) <= 1% and P(anomaly | threshold) == 50%
        if temperature is not None and temperature > 0:
            self.temperature = float(temperature)
        else:
            gap = max(1e-3, self.threshold - self.base_mean)
            self.temperature = max(gap / math.log(99.0), self.base_std, 1e-3)
        self.error_history = []
        self.consecutive_breaches = 0

    def compute_likelihood(self, short_mean):
        logit = (float(short_mean) - self.threshold) / self.temperature
        logit = max(-20.0, min(20.0, logit))
        return 1.0 / (1.0 + math.exp(-logit))

    def update_and_score(self, current_mse):
        current_mse = float(current_mse)
        self.error_history.append(current_mse)
        if len(self.error_history) > self.long_w:
            self.error_history.pop(0)

        short_slice = self.error_history[-self.short_w:]
        short_mean = float(np.mean(short_slice))
        likelihood = self.compute_likelihood(short_mean)

        if current_mse > self.threshold:
            self.consecutive_breaches += 1
        else:
            self.consecutive_breaches = 0

        is_sustained_anomaly = (
            self.consecutive_breaches >= self.min_consecutive and short_mean > self.threshold
        )
        is_transient_spike = (current_mse > self.threshold) and not is_sustained_anomaly

        return {
            "short_mean_mse": short_mean,
            "likelihood": likelihood,
            "likelihood_pct": round(likelihood * 100.0, 2),
            "consecutive_breaches": self.consecutive_breaches,
            "is_sustained_anomaly": is_sustained_anomaly,
            "is_transient_spike": is_transient_spike,
        }


def validate_likelihood_calibration(normal_mse_array, fault_mse_array, base_mean, base_std, threshold, dw_cfg=None):
    """
    Validates that `DualSlidingWindowScorer.compute_likelihood` produces well-calibrated
    probabilities on held-out normal validation windows (`y=0`) and fault windows (`y=1`).

    Computes:
      - Brier Score: mean((p_i - y_i)^2)
      - Expected Calibration Error (ECE, 10 bins)
      - Log-Loss (Binary Cross-Entropy)
      - Decision boundary consistency (`P(threshold) == 0.5`, `max(P_normal) < 0.5`, `min(P_fault) > 0.5`)
    """
    dw_cfg = dw_cfg or {}
    scorer = DualSlidingWindowScorer(
        base_mean=base_mean,
        base_std=base_std,
        threshold=threshold,
        short_w=dw_cfg.get("short_window", 3),
        long_w=dw_cfg.get("long_window", 18),
        min_consecutive=dw_cfg.get("min_consecutive_breaches", 2),
    )

    normal_mse = np.asarray(normal_mse_array, dtype=np.float64)
    fault_mse = np.asarray(fault_mse_array, dtype=np.float64)

    # Evaluate rolling short-window probabilities across the held-out normal validation sequence
    normal_probs = []
    for val in normal_mse:
        res = scorer.update_and_score(float(val))
        normal_probs.append(res["likelihood"])
    normal_probs = np.asarray(normal_probs, dtype=np.float64)

    # Evaluate sustained fault probabilities for each fault MSE level
    fault_probs = []
    for f_val in fault_mse:
        f_scorer = DualSlidingWindowScorer(
            base_mean=base_mean,
            base_std=base_std,
            threshold=threshold,
            short_w=dw_cfg.get("short_window", 3),
            long_w=dw_cfg.get("long_window", 18),
            min_consecutive=dw_cfg.get("min_consecutive_breaches", 2),
        )
        for _ in range(f_scorer.short_w):
            res = f_scorer.update_and_score(float(f_val))
        fault_probs.append(res["likelihood"])
    fault_probs = np.asarray(fault_probs, dtype=np.float64)

    y_true = np.concatenate([np.zeros(len(normal_probs)), np.ones(len(fault_probs))])
    y_prob = np.concatenate([normal_probs, fault_probs])
    y_prob_clipped = np.clip(y_prob, 1e-7, 1.0 - 1e-7)

    brier_score = float(np.mean((y_prob - y_true) ** 2))
    log_loss = float(-np.mean(y_true * np.log(y_prob_clipped) + (1.0 - y_true) * np.log(1.0 - y_prob_clipped)))

    # 10-bin Expected Calibration Error (ECE)
    bins = np.linspace(0.0, 1.0, 11)
    ece = 0.0
    n_total = len(y_true)
    for b_idx in range(10):
        lo, hi = bins[b_idx], bins[b_idx + 1]
        if b_idx == 9:
            mask = (y_prob >= lo) & (y_prob <= hi)
        else:
            mask = (y_prob >= lo) & (y_prob < hi)
        if np.any(mask):
            bin_acc = float(np.mean(y_true[mask]))
            bin_conf = float(np.mean(y_prob[mask]))
            ece += (np.sum(mask) / n_total) * abs(bin_acc - bin_conf)

    prob_at_threshold = scorer.compute_likelihood(threshold)
    normal_below_threshold = normal_mse <= threshold
    max_healthy_prob = float(np.max(normal_probs[normal_below_threshold])) if np.any(normal_below_threshold) else 0.0
    min_fault_prob = float(np.min(fault_probs)) if len(fault_probs) > 0 else 1.0

    calibration_verified = bool(
        brier_score <= 0.05
        and ece <= 0.10
        and abs(prob_at_threshold - 0.50) < 1e-6
        and max_healthy_prob <= 0.50
        and min_fault_prob > 0.50
    )

    return {
        "calibration_method": "logistic_boundary_anchored",
        "temperature": round(scorer.temperature, 6),
        "threshold_anchor_prob_pct": round(prob_at_threshold * 100.0, 2),
        "brier_score": round(brier_score, 6),
        "expected_calibration_error": round(float(ece), 6),
        "log_loss": round(log_loss, 6),
        "normal_val_mean_prob_pct": round(float(np.mean(normal_probs)) * 100.0, 2) if len(normal_probs) else 0.0,
        "normal_val_p95_prob_pct": round(float(np.percentile(normal_probs, 95)) * 100.0, 2) if len(normal_probs) else 0.0,
        "normal_val_max_prob_pct": round(max_healthy_prob * 100.0, 2),
        "fault_min_prob_pct": round(min_fault_prob * 100.0, 2),
        "fault_mean_prob_pct": round(float(np.mean(fault_probs)) * 100.0, 2) if len(fault_probs) else 100.0,
        "calibration_verified": calibration_verified,
    }

