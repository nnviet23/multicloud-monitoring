# ADR-0013: Why Closed-Loop AI Anomaly Detection and Trace RCA

## Status
Accepted

## Context
Performance degradation in multi-cloud microservices often manifests as subtle multivariate shifts across WAN latency, service logic, and database contention before static thresholds trigger. Manual root-cause localization across hundreds of distributed traces inflates MTTR, and offline-only ML notebooks provide no real-time operational value.

## Decision
We implement **AI Anomaly Detection Engine V3** as a closed-loop AIOps pipeline:
- **Deep Learning Ensemble:** Combines a **GRU Autoencoder** (long-term temporal dependencies via reconstruction error $\mathcal{L}_{\text{rec}}$) and a **Temporal Convolutional Network (TCN)** for online scoring (`torch.load(..., weights_only=True)`), supported by **Isolation Forest** for offline calibration.
- **Real-time PromQL feature extraction:** Queries Thanos/Prometheus on `hub-k3d` for HTTP 5xx rates, P90/P99 latency, pod CPU/memory, MySQL `threads_connected`, and WAN latency.
- **Distributed Trace RCA:** When anomaly score $S_{\text{anomaly}} > 0.75$, queries Grafana Tempo to decompose total latency into $T_{\text{total}} = T_{\text{WAN}} + T_{\text{self}} + T_{\text{DB}}$ and attributes the root cause to the dominant component.
- **Closed-loop outputs:** Exposes `:9108` Prometheus metrics (`ai_anomaly_likelihood_percent`, `ai_reconstruction_error`, `ai_rca_component_latency_ms`), renders Panel 7 Dual Y-Axis in Grafana, and sends Telegram alerts with a `60s` cooldown buffer. (Containerized Hub deployment is planned for Phase 5.)

## Alternatives Considered
- **Static thresholds or 3-Sigma rules:** High false-positive rates under dynamic load and blind to multivariate correlations.
- **Large Transformer models (TimeGPT / PatchTST):** Require expensive GPU compute and >5s inference latency, unsuitable for real-time workstation execution.
- **Manual Grafana trace inspection:** Increases MTTR to tens of minutes and depends on operator experience.

## Consequences
- **Positive:** Automates detection and root-cause localization in under 30 seconds; reduces false positives by up to 70% compared to static thresholds; provides quantitative explainability ($T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$).
- **Trade-offs:** Requires ~200–300 MB RAM for the inference loop and an initial offline training phase on normal baseline telemetry.
