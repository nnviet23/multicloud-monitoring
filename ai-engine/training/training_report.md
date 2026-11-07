# Báo cáo Huấn luyện Hệ thống AI Đa Đám Mây V3 (Zero-Leakage & Unified Scoring)

## 1. Kiến trúc, Phân tách Dữ liệu & Chống Rò rỉ (Zero Data Leakage)
- **Chiến lược chia tập dữ liệu**: Chia theo thứ tự thời gian (`strict_chronological_per_entity_pre_windowing`) cho từng thực thể trước khi tính baseline và trước khi cắt cửa sổ trượt.
- **Phạm vi tính `entity_baselines.json`**: Chỉ tính trên tập `Train` (`fit_scope = train_only`), tuyệt đối không dùng mẫu của tập `Validation`.
- **Chồng lấn cửa sổ (`Window Overlap`)**: `0` mẫu thời gian dùng chung giữa `train_windows` và `val_windows`.
- **Số cửa sổ Train (đã tăng cường)**: `2808`
- **Số cửa sổ Validation độc lập**: `66`
- **8 Đặc trưng Thực thể Chuẩn**: `qps`, `server_latency_p95`, `client_latency_p95`, `error_rate_5xx`, `max_pod_cpu_pct`, `max_pod_ram_pct`, `ram_floor_2m_pct`, `gc_pause_rate`

## 2. Kết quả Hội tụ & Hiệu chỉnh Ngưỡng (Unified Scoring)
- **Hàm chấm điểm dùng chung**: [`models/scoring.py`](../models/scoring.py) (`compute_directional_errors` & `DualSlidingWindowScorer`) dùng thống nhất giữa huấn luyện và suy luận.
- **Universal GRU Autoencoder**: Best Disjoint Val Loss = `0.035668` (Epoch `13`)
- **Universal TCN Autoencoder**: Best Disjoint Val Loss = `0.000048` (Epoch `40`)
- **Universal Isolation Forest**: Disjoint Validation Normal Accuracy = `100.00%`
- **Ngưỡng quyết định bất thường (`recommended_threshold_p99`)**: `0.3500` (Disjoint Val Mean = `0.00481`, P99 = `0.02069`, Max = `0.02190`)

## 3. Kiểm định Xác suất Lỗi (`likelihood_pct` Calibration Verification)
- **Phương pháp hiệu chuẩn**: `logistic_boundary_anchored` (neo $P(\text{anomaly} \mid \text{MSE} = \tau) = 50.0\%$ và $P(\text{anomaly} \mid \mu_{\text{val}}) \le 1.0\%$, Temperature = `0.075121`)
- **Brier Score**: `0.000092` (Mục tiêu $\le 0.05$)
- **Expected Calibration Error (ECE)**: `0.009182` (Mục tiêu $\le 0.10$)
- **Log-Loss**: `0.009228`
- **Xác suất trên tập Validation khỏe mạnh**: Trung bình `1.0%` | P95 `1.11%` | Max `1.19%` ($< 50\%$)
- **Xác suất trên các kịch bản lỗi chuẩn**: Min `100.0%` | Trung bình `100.0%` ($> 50\%$)
- **Trạng thái kiểm định (`calibration_verified`)**: `True`

## 4. Biểu đồ Hội tụ
![Training Loss Curve](../data/processed/training_loss.png)
