# Multi-Cloud Observability AI Engine V3: Per-Entity Anomaly Detection & Cross-Cloud Trace RCA

Module AI thế hệ V3 phục vụ giám sát độ tin cậy đa đám mây (Multi-Cloud Reliability & Observability), phát hiện bất thường bất biến theo quy mô thực thể (**Per-Entity Z-Score Standardized Universal Autoencoders**) và tự động khoanh vùng nguyên nhân gốc rễ xuyên đám mây (**Tempo Distributed Trace Span Decomposition RCA**) trên hệ thống phân tán microservices TeaStore trải rộng trên 4 cụm Kubernetes (`hub-k3d`, `aws-k3d`, `azure-k3d`, `gcp-k3d`).

---

## 1. Kiến trúc Tổng thể (AI Engine V3 Architecture)

```mermaid
flowchart TD
    subgraph MultiCloudClusters["4 Kubernetes Clusters (k3d)"]
        AWS["AWS-k3d (Edge Gateway, WebUI, Image, Registry)"]
        AZURE["Azure-k3d (IAM Auth, Persistence, MariaDB)"]
        GCP["GCP-k3d (AI/ML Recommender)"]
        HUB["Hub-k3d (OTel Gateway, Prometheus, Tempo, Loki)"]
        AWS -->|mTLS OTLP Metrics/Traces/Logs| HUB
        AZURE -->|mTLS OTLP Metrics/Traces/Logs| HUB
        GCP -->|mTLS OTLP Metrics/Traces/Logs| HUB
    end

    subgraph DynamicIngestion["Vectorized Entity Discovery & Trace Decomposition"]
        PROM["Prometheus Server (Port 9090)"]
        TEMPO["Grafana Tempo TracZe API (Port 3200)"]
        HUB --> PROM
        HUB --> TEMPO
        DISC["Dynamic Entity Discovery\n(cloud_provider, service_name)"]
        PROM -->|8 Universal Entity Features| DISC
        TEMPO -->|Sequential Span Decomposition\nT_WAN, T_self, T_DB| DISC
        CAL["EntityCalibrator\n(Per-Entity Z-Score + 30-Sample Online Auto-Calibration)"]
        DISC --> CAL
    end

    subgraph UniversalDeepEnsemble["Universal Entity Deep Ensemble (Input: 12 x 8 Z-Score)"]
        GRU["Universal GRU Autoencoder\n(Val Loss = 0.03567)"]
        TCN["Universal TCN Autoencoder\n(Val Loss = 0.000048)"]
        ISO["Universal Isolation Forest\n(96-dim, 100% Val Normal Acc)"]
        CAL --> GRU
        CAL --> TCN
        CAL --> ISO
    end

    subgraph ScoringAndRCA["Unified Scoring, Calibrated Likelihood & Trace-Guided RCA"]
        SCORE["models/scoring.py: compute_directional_errors\n+ Calibrated DualSlidingWindowScorer"]
        GRU --> SCORE
        TCN --> SCORE
        HEALTHY["✓ HEALTHY\n(Đa đám mây hoạt động bình thường)"]
        TRANSIENT["~ TRANSIENT SPIKE SUPPRESSED\n(Dao động tức thời - Không báo động)"]
        ALERT["⚠ MULTI-CLOUD ALERT\n(Phát hiện bất thường xuyên đám mây)"]
        RCA["Multi-Cloud Trace + Metric RCA\n(CROSS_CLOUD_WAN_DELAY / CPU / MEMORY_LEAK / DB)"]
        SCORE -->|Short MSE < 0.3500 & P(fault) < 50%| HEALTHY
        SCORE -->|Single-step spike| TRANSIENT
        SCORE -->|Sustained MSE > 0.3500 & P(fault) > 50%| ALERT
        ALERT --> RCA
    end
```

---

## 2. Vector 8 Đặc trưng Thực thể Phổ quát (8 Universal Entity Features)

Thay vì đóng cứng số cột theo từng tên dịch vụ, AI Engine V3 tự động phát hiện mọi cặp thực thể $e = (\text{cloud\_provider}, \text{service\_name})$ đang hoạt động trên Prometheus và trích xuất vector chuẩn $\mathbf{x}_e^{(t)} \in \mathbb{R}^8$:

| STT | Tên đặc trưng (`feature`) | Biểu thức PromQL Vectorized (`by (cloud_provider, service_name)`) | Tính bất biến khi Scale Pods / Thêm Cloud |
| :-: | :--- | :--- | :--- |
| **1** | `qps` | `sum by (cloud_provider, service_name) (rate(http_server_request_duration_seconds_count[1m]))` | Chuẩn hóa theo `EntityCalibrator` của từng dịch vụ |
| **2** | `server_latency_p95` | `histogram_quantile(0.95, sum by (le, cloud_provider, service_name) (rate(http_server_request_duration_seconds_bucket[1m])))` | Bất biến với số lượng pod (`1 -> N` replicas) |
| **3** | `client_latency_p95` | `histogram_quantile(0.95, sum by (le, cloud_provider, service_name) (rate(http_client_request_duration_seconds_bucket[1m])))` + `Tempo T_WAN` | Đo trực tiếp độ trễ gọi liên dịch vụ / xuyên cloud |
| **4** | `error_rate_5xx` | `sum by (cloud_provider, service_name) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5.."}[1m]))` | Phát hiện lỗi HTTP 5xx cục bộ tại từng dịch vụ |
| **5** | `max_pod_cpu_pct` | `clamp_max(max by (cloud_provider, service_name) (jvm_cpu_recent_utilization_ratio * jvm_cpu_count) * 100, 100)` | Dùng `max by` nên không bị pha loãng khi scale-out thêm pod |
| **6** | `max_pod_ram_pct` | `max by (cloud_provider, service_name) (sum by (..., host_name) (jvm_memory_used_bytes{heap}) / sum by (..., host_name) (jvm_memory_limit_bytes{heap})) * 100` | Bắt đỉnh RAM của pod cao nhất trong dịch vụ |
| **7** | `ram_floor_2m_pct` | $\min_{\tau \in [t-19, t]} \text{max\_pod\_ram\_pct}_e^{(\tau)}$ | Phân biệt Memory Leak thật (sàn RAM dâng cao) với răng cưa JVM GC bình thường |
| **8** | `gc_pause_rate` | `sum by (cloud_provider, service_name) (rate(jvm_gc_duration_seconds_sum[1m]))` | Tốc độ dừng JVM để dọn rác bộ nhớ |

---

## 3. Khả năng Mở rộng Động & Bóc tách Distributed Trace Xuyên Đám Mây

### 3.1. Chuẩn hóa Z-Score Theo Từng Thực thể & Online Auto-Calibration
* Mỗi thực thể $e = (\text{cloud}, \text{service})$ có đường cơ sở riêng $(\boldsymbol{\mu}_e, \boldsymbol{\sigma}_e)$ lưu trong [`models/saved/entity_baselines.json`](models/saved/entity_baselines.json):
  $$z_{e, k}^{(t)} = \text{clip}\left(\frac{x_{e, k}^{(t)} - \mu_{e, k}}{\max(\sigma_{e, k}, s_{\min, k})}, -10.0, +10.0\right)$$
* **Khi thêm Pod mới (Horizontal Pod Autoscaling)**: Cùng thực thể $(\text{cloud}, \text{service})$, các chỉ số `max_pod_cpu_pct`, `max_pod_ram_pct`, `server_latency_p95` giữ nguyên ý nghĩa vật lý — không cần huấn luyện lại mô hình.
* **Khi thêm Cloud Provider mới hoặc Microservice mới**: `EntityCalibrator` tự động thu thập 30 mẫu đầu tiên (Online Auto-Calibration) để tính $(\boldsymbol{\mu}_{e_{\text{new}}}, \boldsymbol{\sigma}_{e_{\text{new}}})$ và đưa ngay vào `GRUAutoencoder` + `TCNAutoencoder` mà không cần sửa code hay train lại trọng số mạng.

### 3.2. Toán học Bóc tách Span Xuyên Đám Mây (`TempoTraceAnalyzer`)
Khi một request `/product` đi qua chuỗi gọi đồng bộ xuyên đám mây (`AWS:teastore-webui` $\to$ `Azure:teastore-persistence` / `Azure:teastore-auth` $\to$ `GCP:teastore-recommender`), `TempoTraceAnalyzer` truy vấn trực tiếp Tempo API (`/api/search` & `/api/traces/<traceID>`) và phân rã từng span con $S_i$:
1. **Độ trễ truyền dẫn mạng WAN một chiều cô lập cho từng thực thể đích ($T_{\text{WAN}}$)**:
   $$T_{\text{WAN}}(\text{Cloud}_{\text{root}} \to S_i) = \min\left(\Delta_{\text{pre}}(S_i),\; \Delta_{\text{post}}(S_i)\right)$$
   trong đó $\Delta_{\text{pre}}(S_i) = t_{\text{start}}(S_i) - t_{\text{end}}(S_{i-1})$ và $\Delta_{\text{post}}(S_i) = t_{\text{start}}(S_{i+1}) - t_{\text{end}}(S_i)$. Công thức $\min(\Delta_{\text{pre}}, \Delta_{\text{post}})$ cô lập chính xác độ trễ mạng WAN của nhánh gọi $S_i$ mà không làm nhiễm sang span kế cận.
2. **Thời gian tự xử lý nội tại của từng dịch vụ ($T_{\text{self}}$)**:
   $$T_{\text{self}}(S) = \max\left(0,\; T_{\text{server\_span}}(S) - \sum_{c \in \text{children}(S)} T(c) - T_{\text{remote\_WAN\_wait}}(S)\right)$$
3. **Thời gian truy vấn SQL tại tầng dữ liệu ($T_{\text{DB}}$)**:
   Trích xuất trực tiếp từ các span `db.system = "mysql"` (`SELECT teadb.*`) trên `Azure:teastore-persistence`.

---

## 4. Kết quả Huấn luyện & Kiểm thử Thực nghiệm 4 Kịch bản Đa Đám Mây

### 4.1. Hiệu năng Hội tụ & Kiểm định Không Rò rỉ Dữ liệu (Zero-Leakage Validation & Calibration)
* **Chia dữ liệu theo thời gian chống rò rỉ (`split_entities_chronologically`)**: `666` dòng thực thể sạch (`111 chu kỳ × 6 thực thể`) được tách theo trục thời gian cho từng thực thể **trước khi** tính baseline và **trước khi** tạo cửa sổ trượt:
  * Tập huấn luyện (`train_df`): `534` dòng (`89` chu kỳ đầu $\times$ `6` thực thể), dùng **độc quyền** để ước lượng `entity_baselines.json` (`fit_scope = "train_only"`) và sinh `468` cửa sổ gốc $\to$ `2,808` cửa sổ huấn luyện tăng cường (`12 × 8`).
  * Tập kiểm định (`val_df`): `132` dòng tương lai độc lập (`22` chu kỳ cuối $\times$ `6` thực thể), sinh `66` cửa sổ kiểm định (`12 × 8`) với **0 mẫu thời gian chồng lấn** (`train_timestamps ∩ val_timestamps = ∅`).
* **Thống nhất chấm điểm Training & Inference (`models/scoring.py`)**: Cả bước hiệu chỉnh ngưỡng (`train.py`) và bước giám sát thời gian thực (`detector.py`, `evaluate_test.py`) dùng chung hàm `compute_directional_errors` và `DualSlidingWindowScorer`.
* **Universal GRU Autoencoder**: Best Disjoint Validation SmoothL1 Loss = **`0.035668`** (Epoch 13).
* **Universal TCN Autoencoder**: Best Disjoint Validation SmoothL1 Loss = **`0.000048`** (Epoch 40).
* **Universal Isolation Forest**: Disjoint Validation Normal Accuracy = **`100.00%`**.
* **Ngưỡng quyết định bất thường (`recommended_threshold_p99`)**: **`0.3500`** (Disjoint Validation P99 = `0.020693`, Max = `0.021904`).
* **Kiểm định xác suất lỗi (`likelihood_pct`)**: Hiệu chỉnh bằng hàm logistic neo tại ngưỡng quyết định $P(\text{fault} \mid \bar{e}_{\text{short}} = \tau) = 50.0\%$ và mức cơ sở $P(\text{fault} \mid \mu_{\text{val}}) = 1.0\%$, đạt **Brier Score = `0.000092`**, **ECE = `0.009182`**, **Log-Loss = `0.009228`** (`calibration_verified = true`).

### 4.2. Kết quả Kiểm thử Thực tế trên 4 Cụm `k3d` (`AWS`, `Azure`, `GCP`, `Hub`)

| Kịch bản Kiểm thử | Mô tả Thao tác Thực tế | Kết quả Phát hiện (`Verdict`) | Điểm MSE Thực tế | Kết quả Khoanh vùng Nguyên nhân Gốc rễ (`RCA`) |
| :--- | :--- | :---: | :---: | :--- |
| **Test 1: Normal Erratic Traffic** | Traffic hỗn loạn 10–50 users (`Flash-Crowd`, `Burst-Spike`), WAN `10ms` bình thường | **100% HEALTHY** (`0.0%` False Alarm, `8/8 TN`) | `0.20 -> 0.045` (`< 0.3500`) | Không báo động giả |
| **Test 2: GCP WAN Latency (`250ms`)** | Tiêm `tc netem delay 250ms 20ms` vào `k3d-gcp-k3d-server-0` | **ALERT** (Phát hiện 100%) | `4.58 -> 6.49` (`> 0.3500`) | `[CROSS_CLOUD_WAN_DELAY] aws->gcp (gcp:teastore-recommender) (T_WAN=117ms, client_latency_p95 lệch x102.5)` |
| **Test 3: Azure WAN Latency (`180ms`)** | Tiêm `tc netem delay 180ms 15ms` vào `k3d-azure-k3d-server-0` | **ALERT** (Phát hiện 100%) | `5.07 -> 5.25` (`> 0.3500`) | `[CROSS_CLOUD_WAN_DELAY] aws->azure (azure:teastore-persistence) (T_WAN=202ms), aws->azure (azure:teastore-auth) (T_WAN=194ms)` |
| **Test 4: Pod Scale-Out (`1 -> 2` Pods)** | `kubectl scale deploy/teastore-recommender --replicas=2` trên `gcp-k3d` | **100% HEALTHY** (`0.0%` False Alarm) | `< 0.3500` | Bất biến hoàn toàn khi tăng gấp đôi số Pod mà không cần train lại |

---

## 5. Hướng dẫn Thực thi & Vận hành (Runbook)

```bash
# 1. Thu thập dữ liệu thực thể đa đám mây từ Prometheus
python3.12 ai-engine/data/collector.py --duration 1200 --interval 6 --output ai-engine/data/raw/multicloud_entity_baseline.csv

# 2. Phân tích khám phá dữ liệu (EDA) & Tiền xử lý Z-Score theo từng thực thể
python3.12 ai-engine/data/analyze_data.py
python3.12 ai-engine/data/preprocess.py

# 3. Huấn luyện Universal GRU + TCN Autoencoders + Isolation Forest
python3.12 ai-engine/training/train.py

# 4. Chạy bộ kiểm thử 11 kịch bản chuẩn hóa và RCA (--benchmark)
python3.12 ai-engine/inference/evaluate_test.py --benchmark

# 5. Khởi chạy Giám sát & Khoanh vùng Nguyên nhân Gốc rễ Xuyên Cloud Thời gian thực
python3.12 ai-engine/inference/detector.py --interval 6
```

---

Xem [tests/chaos/README.md](../tests/chaos/README.md) để chạy test hành vi AI,
replay có kiểm tra kết quả kỳ vọng và tiêm lỗi WAN thật với khôi phục tự động.

## 6. Cấu trúc Thư mục Module AI V3

```
ai-engine/
├── configs/
│   └── model_config.yaml                  # Cấu hình 8 đặc trưng thực thể, scale floors, ngưỡng cửa sổ kép
├── data/
│   ├── raw/
│   │   └── multicloud_entity_baseline.csv # Dữ liệu thực thể thu thập thực tế trên 3 cloud (AWS, Azure, GCP)
│   ├── processed/
│   │   ├── entity_baselines.json          # Tham số chuẩn hóa (Median, IQR, Scale) fit_scope="train_only"
│   │   ├── train_windows.npy              # 2,808 cửa sổ huấn luyện (12 x 8)
│   │   ├── val_windows.npy                # 66 cửa sổ kiểm định tương lai không chồng lấn (12 x 8)
│   │   ├── feature_names.json             # Danh sách 8 đặc trưng thực thể chuẩn
│   │   ├── eda_summary.png                # Biểu đồ phân tích dữ liệu đa đám mây
│   │   ├── eda_report.md                  # Báo cáo thống kê khám phá dữ liệu
│   │   └── training_loss.png              # Đường cong hội tụ GRU & TCN Autoencoders
│   ├── collector.py                       # Bộ thu thập dữ liệu PromQL Vectorized tự động phát hiện thực thể
│   ├── analyze_data.py                    # Phân tích thống kê theo từng thực thể
│   └── preprocess.py                      # Chia thời gian trước, chuẩn hóa train-only & tạo cửa sổ tách biệt
├── models/
│   ├── scoring.py                         # Module chấm điểm định hướng & hiệu chỉnh xác suất lỗi dùng chung
│   ├── gru_autoencoder.py                 # Universal GRU Autoencoder (input_dim=8)
│   ├── tcn_autoencoder.py                 # Universal TCN Autoencoder (input_dim=8)
│   └── saved/
│       ├── entity_baselines.json          # Baseline phục vụ chuẩn hóa online & auto-calibration
│       ├── gru_autoencoder.pt             # Trọng số GRU Autoencoder
│       ├── tcn_autoencoder.pt             # Trọng số TCN Autoencoder
│       ├── isolation_forest.joblib        # Mô hình Isolation Forest (96 chiều)
│       └── threshold_config.json          # Ngưỡng cảnh báo P99 (0.3500) & RCA baselines
├── inference/
│   ├── detector.py                        # Engine phát hiện bất thường + TempoTraceAnalyzer RCA
│   ├── evaluate_test.py                   # Công cụ thẩm định Ground-Truth & Benchmark
│   └── test_runs/                         # Log và JSON kết quả kiểm thử thực tế 4 kịch bản
└── training/
    ├── train.py                           # Pipeline huấn luyện mô hình V3
    └── training_report.md                 # Báo cáo kết quả huấn luyện
```
