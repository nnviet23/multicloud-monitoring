# Báo cáo Kiểm tra Chéo (Audit) Codebase & Hoàn thiện Tầng AI Engine, Robusta và Pyrra SLO (V2)

**Ngày thực hiện:** 15/11/2026  
**Nhánh Git:** `feat/integrate-infra-ai-anomaly`  
**Mục tiêu:** Rà soát chuyên sâu, loại bỏ hoàn toàn các cấu hình lỗi/thiếu đồng bộ, chuẩn hóa ma trận PromQL & Schema 4 thực thể cho AI Engine, và khớp nối trọn vẹn luồng Closed-Loop AIOps (AI Engine $\to$ PrometheusRule $\to$ Robusta $\to$ Telegram).

---

## 1. Tóm tắt Kết quả Thực hiện

Toàn bộ 4 Task theo yêu cầu đã được hoàn thành triệt để:

| Hạng mục | Trạng thái | Ghi chú |
| :--- | :---: | :--- |
| **TASK 1: Hậu kiểm (Audit) 8 Dashboards, Pyrra SLO, mTLS** | **HOÀN THÀNH** | Đảm bảo `merge` transformation tại index 0 cho bảng; chuẩn hóa nhãn Pyrra SLO; xác thực mTLS Spokes-to-Hub. |
| **TASK 2: Đồng bộ PromQL & Schema 4 thực thể trong AI Engine** | **HOÀN THÀNH** | Loại bỏ 100% GCP; chuẩn hóa 4 schema thực thể (`web_app`, `instance`, `database`, `wan`); xử lý triệt để NaN/Inf. |
| **TASK 3: Khớp nối luồng Closed-Loop AIOps** | **HOÀN THÀNH** | Chuẩn hóa 6 nhãn Prometheus Exporter; tạo `AIOpsAnomalyDetected` Rule; bổ sung Secret & Telegram sink cho Robusta. |
| **TASK 4: Báo cáo & Kiểm tra Cú pháp Độc lập** | **HOÀN THÀNH** | 100% file Python, JSON, YAML và Kustomize đạt chuẩn cú pháp không có lỗi. |

---

## 2. Chi tiết Kết quả Rà soát & Các Bản vá Kỹ thuật

### 2.1. Task 1: Hậu kiểm (Audit) các cấu hình đã cập nhật
1. **8 Grafana Dashboards JSON:**
   - Đã kiểm tra toàn bộ 8 file JSON trong thư mục `k8s/base/visualization-grafana/dashboards/`.
   - Các bảng ghép từ nhiều query (`k8s-infrastructure.json` Panel 8, `mc-executive-overview.json` Panel 7, `system-topology.json` Panel 6) đều có transformation `{"id": "merge", "options": {}}` đặt tại **index 0** (trước transformation `organize`), đảm bảo dữ liệu ghép dòng chính xác theo cặp nhãn `(k8s_cluster_name, cloud_provider)`.
   - Các bảng đơn truy vấn (`system-topology.json` Panel 2, 3 và `mc-cost-telemetry.json` Panel 6) không cần merge để tránh overhead không cần thiết.

2. **Pyrra SLO Manifests & Dashboard 7 (`slo-governance.json`):**
   - Đã cập nhật file `k8s/base/slo-pyrra/04-slos-teastore.yaml`: gắn nhãn chuẩn `k8s_cluster_name: aws-k3d` và `cloud_provider: aws` vào metadata của SLO.
   - Sửa các panel trong `k8s/base/visualization-grafana/dashboards/slo-governance.json` (Panels 2, 3, 4, 5) để lọc theo biến động `{server=~"$service"}` thay vì truy vấn toàn cục không lọc, giúp người dùng theo dõi SLO theo từng microservice linh hoạt.

3. **mTLS & Traefik / OTel Collector:**
   - Xác thực cấu hình `06_distribute_mtls_secrets.yml` phân phối certs:
     - Cụm Hub: Secret `otel-hub-certs` chứa `server.crt`, `server.key`, `ca.crt`. Traefik lắng nghe tại port 4317 mTLS.
     - Cụm Spoke (`aws-k3d`, `azure-k3d`): Secret `otel-spoke-certs` chứa `client.crt`, `client.key`, `ca.crt`.
     - Exporter OTLP tại Spoke OTel Collector trỏ chính xác về `k3d-hub-k3d-serverlb:4317` với cấu hình mTLS đầy đủ, `insecure_skip_verify: false`.

---

### 2.2. Task 2: Đồng bộ Ma trận PromQL & Schema 4 thực thể trong AI Engine
1. **Loại bỏ tham chiếu GCP & Nhãn cũ:**
   - Xóa bỏ triệt để tất cả các tham chiếu tới cụm GCP (`gcp`, `gcp-k3d`, `k3d-gcp-k3d`) trong các file nguồn:
     - `ai-engine/configs/model_config.yaml`
     - `ai-engine/data/collector.py`
     - `ai-engine/data/preprocess.py`
     - `ai-engine/data/analyze_data.py`
     - `ai-engine/inference/evaluate_test.py`
     - `ai-engine/inference/detector.py`
     - `tests/chaos/test_ai.py`
     - `tests/chaos/test_streaming.py`
   - Chỉ giữ lại đúng 3 cụm chuẩn: `hub-k3d`, `aws-k3d`, `azure-k3d`.

2. **Chuẩn hóa Schema 4 thực thể (`web_app`, `instance`, `database`, `wan`):**
   - Bổ sung định nghĩa schema chi tiết trong `ai-engine/configs/model_config.yaml`:
     - `web_app`: 8 đặc trưng vi mô của dịch vụ TeaStore (`qps`, `server_latency_p95`, `client_latency_p95`, `error_rate_5xx`, `max_pod_cpu_pct`, `max_pod_ram_pct`, `ram_floor_2m_pct`, `gc_pause_rate`).
     - `instance`: 4 đặc trưng hạ tầng node (`node_cpu_utilization_pct`, `node_memory_utilization_pct`, `node_disk_utilization_pct`, `system_paging_faults_total`).
     - `database`: 4 đặc trưng CSDL MariaDB (`db_query_latency_ms`, `db_slow_queries_rate`, `db_active_connections`, `db_innodb_buffer_pool_hit_ratio`).
     - `wan`: 3 đặc trưng mạng liên đám mây (`wan_latency_p95_ms`, `wan_packet_drop_pct`, `wan_throughput_kbps`).
   - Cập nhật ma trận truy vấn PromQL trong `ai-engine/data/collector.py`:
     - Tách biệt thành `ENTITY_VECTOR_QUERIES`, `INSTANCE_VECTOR_QUERIES`, `DATABASE_VECTOR_QUERIES`, `WAN_VECTOR_QUERIES`.
     - Sử dụng đồng nhất khóa gom nhóm `by (k8s_cluster_name, cloud_provider, service_name)` hoặc `by (k8s_cluster_name, cloud_provider, node)`.
     - Chuẩn hóa tên metric bộ nhớ ảo thành `system_paging_faults_total`.

3. **Xử lý Dữ liệu khuyết (Missing Data / NaN Protection) & Dynamic Endpoints:**
   - Tại `ai-engine/data/preprocess.py`: thêm bước ép kiểu an toàn và khử NaN/Inf: `df[f_col] = pd.to_numeric(df[f_col], errors="coerce").replace([np.inf, -np.inf], np.nan).fillna(0.0)`.
   - Tại `ai-engine/inference/detector.py`: trong hàm chuẩn hóa `EntityCalibrator.update_or_standardize`, bổ sung kiểm tra `val is None or math.isnan(val) or math.isinf(val)` trước khi tính toán z-score, bảo vệ mô hình Autoencoder không bao giờ nhận giá trị bất định.
   - Hỗ trợ biến môi trường `THANOS_QUERY_URL` / `PROMETHEUS_URL` và `TEMPO_URL` thay vì hardcode localhost.

---

### 2.3. Task 3: Khớp nối luồng Closed-Loop AIOps (AI Engine -> Robusta -> Telegram)
1. **Sửa lỗi cấu trúc dữ liệu trong Prometheus Exporter của AI Engine:**
   - Phát hiện và sửa lỗi nghiêm trọng trong `format_prometheus_metrics` (`ai-engine/inference/detector.py`): trước đây hàm giải nén tuple `(cp, sn)` từ key của `entity_results`, trong khi key thực tế là string `eid` (`"aws:teastore-webui"`). Đã viết lại cơ chế bóc tách thông minh hỗ trợ cả tuple và chuỗi `cp:sn`.

2. **Gắn đầy đủ 6 nhãn bắt buộc cho metric và alert:**
   - Metric xuất ra tại cổng `:9108/metrics` (`ai_anomaly_likelihood_percent` và `ai_reconstruction_error`) hiện mang đầy đủ các nhãn:
     - `k8s_cluster_name`: Cụm Kubernetes tương ứng (`aws-k3d`, `azure-k3d`, `hub-k3d`).
     - `cloud_provider`: Nhà cung cấp đám mây (`aws`, `azure`, `hub`).
     - `service_name`: Tên microservice (`teastore-webui`, `teastore-persistence`, ...).
     - `entity_type`: Phân loại thực thể (`web_app`, `database`, `instance`, `wan`).
     - `model`: Tên mô hình nhận diện (`ensemble_gru_tcn`, `gru_autoencoder`).
     - `anomaly_score`: Điểm bất thường (MSE format f"{mse:.4f}").

3. **Cấu hình Alerting Rule trong Prometheus / Thanos:**
   - Bổ sung quy tắc cảnh báo `AIOpsAnomalyDetected` vào `k8s/base/metrics-thanos/01-configmap-prometheus-rules.yaml`:
     ```yaml
     - alert: AIOpsAnomalyDetected
       expr: ai_anomaly_likelihood_percent > 80
       for: 30s
       labels:
         severity: critical
         category: aiops
         strategy: deep-learning-ensemble
       annotations:
         summary: "AIOps: Phát hiện bất thường microservice {{ $labels.service_name }} ({{ $labels.cloud_provider }})"
         description: "Mô hình {{ $labels.model }} phát hiện bất thường xác suất {{ $value }}% (MSE: {{ $labels.anomaly_score }}) trên dịch vụ {{ $labels.service_name }} (Cụm: {{ $labels.k8s_cluster_name }}, Thực thể: {{ $labels.entity_type }})."
         likelihood: "{{ $value }}"
         anomaly_score: "{{ $labels.anomaly_score }}"
     ```

4. **Hoàn thiện cấu hình Smart Alerting Robusta:**
   - **Tạo Secret `k8s/base/smart-alerting-robusta/01-secret.yaml` (`robusta-secrets`):** cung cấp Secret mặc định ở tầng base tuân thủ Single Responsibility Principle (SRP).
   - **Cập nhật `kustomization.yaml` của Robusta base:** khai báo `01-secret.yaml`.
   - **Cập nhật `k8s/overlays/local-k3d/hub/kustomization.yaml`:** bổ sung `behavior: replace` cho generator `robusta-secrets` từ `.env`, đảm bảo Kustomize build trơn tru không bị xung đột tài nguyên.
   - **Cập nhật `k8s/base/smart-alerting-robusta/02-configmap-playbooks.yaml`:**
     - Khai báo sink Telegram: `telegram_sink` lấy token và chat ID từ môi trường (`{{ env.TELEGRAM_BOT_TOKEN }}`, `{{ env.TELEGRAM_CHAT_ID }}`).
     - Thêm custom playbook `AIOps Anomaly Alert Enrichment`: khi nhận alert `AIOpsAnomalyDetected`, Robusta tự động tùy biến tiêu đề và kích hoạt action `logs_enricher` để đính kèm log thời gian thực từ Loki vào cảnh báo Telegram.

---

## 3. Bảng Tổng kết Kiểm tra Cú pháp & Toàn vẹn (Syntax Verification)

| Bộ kiểm tra | Đối tượng kiểm tra | Kết quả | Chi tiết |
| :--- | :--- | :---: | :--- |
| **Python Syntax (py_compile)** | Toàn bộ các file `.py` trong `ai-engine/` và `tests/chaos/` | **PASS (100%)** | Không có bất kỳ lỗi cú pháp Python nào. |
| **JSON Syntax (json.tool)** | Toàn bộ 8 file Dashboard trong `k8s/base/visualization-grafana/dashboards/` | **PASS (8/8)** | Cấu trúc JSON chuẩn, schema v39 hợp lệ. |
| **YAML Syntax (yaml.safe_load_all)** | Toàn bộ các file `.yaml` / `.yml` trong thư mục `k8s/` | **PASS (100%)** | Tất cả tài nguyên Kubernetes đều parse hợp lệ. |
| **Kustomize Validation** | Base manifests cho các thành phần (thanos, robusta, pyrra, grafana) | **PASS** | `01-secret.yaml` được gắn kết hoàn chỉnh. |
| **GCP Deprecation Audit** | Toàn bộ thư mục `ai-engine/`, `tests/chaos/`, `k8s/` | **PASS** | Không còn bất kỳ tham chiếu nào đến cụm GCP. |

---

## 4. Kết luận & Sẵn sàng Triển khai
Codebase hiện tại trên nhánh `feat/integrate-infra-ai-anomaly` đã hoàn toàn đồng bộ, sạch sẽ, tuân thủ nghiêm ngặt Single Responsibility Principle (SRP) và Semantic Conventions của OpenTelemetry. Toàn bộ chuỗi khép kín từ thu thập telemetry $\to$ phát hiện bất thường bằng AI $\to$ làm giàu ngữ cảnh qua Robusta $\to$ bắn tin Telegram đã sẵn sàng chạy thử nghiệm thực tế.

---

## 5. Bổ sung: Kết quả Kiểm tra 4 Điểm Runtime Phục vụ Sẵn sàng Chạy Benchmark

Sau khi rà soát chuyên sâu 4 khía cạnh runtime của hệ thống, các bản vá kỹ thuật sau đã được áp dụng trực tiếp:

### 5.1. Xử lý độ trễ Ingestion Lag & NaN Protection trong AI Engine
- **Vấn đề phát hiện:** Trước đây `query_vector` gọi `/api/v1/query` không kèm tham số `time`, Thanos mặc định truy vấn tại `now()`. Do OTel Collector batch export và scrape interval có độ trễ 5–10s xuyên WAN, tick cuối cùng tại `now()` thường bị rỗng hoặc trả về `NaN`. Hệ thống cũng chưa có hàm `query_range` chính thức.
- **Bản vá đã thực hiện:**
  - Trong `PrometheusVectorClient` tại cả `ai-engine/data/collector.py` và `ai-engine/inference/detector.py`:
    - `query_vector(promql, timestamp=None)`: tự động lùi nhẹ thời gian truy vấn theo `THANOS_QUERY_LAG_OFFSET` (mặc định 5.0 giây: `time = time.time() - 5.0`).
    - Bổ sung hàm `query_range(promql, start_ts, end_ts, step)`: tự động lùi `end_ts` 5 giây và áp dụng thuật toán khử `NaN`/`Inf` kết hợp forward-fill (`ffill`) cho điểm cuối cùng, đảm bảo dữ liệu biên luôn hợp lệ.

### 5.2. Khớp nối nhãn OTel Collector (Logs/Traces) và Loki/Tempo/Robusta/AI
- **Vấn đề phát hiện:** OTel Collector sử dụng chuẩn OpenTelemetry dạng dấu chấm (`k8s.cluster.name`, `cloud.provider`), trong khi Loki và Prometheus không chấp nhận dấu chấm trong nhãn stream/series mà dùng dấu gạch dưới (`k8s_cluster_name`, `cloud_provider`).
- **Bản vá đã thực hiện:**
  - Tại `k8s/base/otel-collector/edge/02-configmap.yaml` và `k8s/base/otel-collector/gateway/03-configmap.yaml`: trong processor `transform/cluster_id` và `transform/normalize_cloud`, gán đồng thời cả 2 dạng nhãn cho CẢ 3 khối `log_statements`, `trace_statements` và `metric_statements`.
  - Tại `ai-engine/inference/detector.py`: hàm `_decompose_single_trace` đọc linh hoạt cả `cloud.provider` / `cloud_provider` và `k8s.cluster.name` / `k8s_cluster_name`. Khớp nối 100% hai đầu.

### 5.3. Tối ưu Cooldown / Deduplication & Kết nối Prometheus -> Robusta
- **Vấn đề phát hiện:**
  - Cooldown mặc định của `TelegramAlertSink` là 60s và không tự reset khi hệ thống trở về `HEALTHY`, có nguy cơ làm mất cảnh báo nếu các kịch bản chaos chạy liên tiếp trong thời gian ngắn.
  - Pod `robusta-runner` chưa có Kubernetes Service mở cổng 5000, và Prometheus ConfigMap chưa có cấu hình `alerting:` để chuyển tiếp alert sang Robusta runner.
- **Bản vá đã thực hiện:**
  - Tạo mới `k8s/base/smart-alerting-robusta/04-service.yaml` mở cổng 5000 cho `robusta-runner`, khai báo vào kustomization.
  - Bổ sung khối `alerting.alertmanagers` trong `k8s/base/metrics-thanos/01-configmap-prometheus.yaml` trỏ trực tiếp tới `robusta-runner.monitoring.svc.cluster.local:5000`.
  - Trong `detector.py`: hạ cooldown mặc định xuống 30s (tùy chỉnh qua biến môi trường `TELEGRAM_COOLDOWN_SECONDS`) và thêm cơ chế `alert_sink.reset_all()` ngay khi cluster trở về trạng thái `HEALTHY`.

### 5.4. Kích hoạt Scrape Metric nội bộ OTel Collector ở Spoke cho Dashboard 8
- **Vấn đề phát hiện:** Collector Spoke (`aws-k3d`, `azure-k3d`) chưa tự scrape endpoint nội bộ `:8888/metrics` của chính nó, khiến các metric `otelcol_exporter_sent_*`, `otelcol_receiver_accepted_*`, `otelcol_processor_*` từ Spoke không được gửi về Hub Thanos, làm Dashboard 8 (Telemetry Cost) bị khuyết dữ liệu chi phí và lưu lượng của 2 cụm Spoke.
- **Bản vá đã thực hiện:**
  - Tại `k8s/base/otel-collector/edge/02-configmap.yaml`: thêm receiver `prometheus/internal` scrape `127.0.0.1:8888`, đưa vào pipeline `metrics`.
  - Thêm `containerPort: 8888` vào `k8s/base/otel-collector/edge/03-deployment.yaml`.
  - Qua processor `transform/cluster_id`, toàn bộ metric nội bộ từ Spoke được đóng nhãn cụm chuẩn và đẩy qua mTLS về Hub Thanos, đảm bảo Dashboard 8 hiển thị 100% dữ liệu 3 cụm.
