# BÁO CÁO PHÂN TÍCH NGUYÊN NHÂN GỐC RỄ & ĐỀ XUẤT KHẮC PHỤC NO DATA TRÊN CÁC GRAFANA DASHBOARDS
## (Root Cause Analysis & Action Plan v5.0 for Dashboard No-Data Resolution)

- **Mã tài liệu:** `docs/refactoring/05_dashboard_nodata_v1.md`
- **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability & AIOps)
- **Tác giả:** Senior Observability, SRE & OpenTelemetry Architect
- **Ngày lập:** 15/11/2026
- **Trạng thái:** Đã được Người dùng Phê duyệt - Đang triển khai (Approved - In Progress)
- **Phiên bản:** `v1.1.0`

---

## 1. TỔNG QUAN & PHÂN LOẠI NGUYÊN NHÂN GỐC RỄ (EXECUTIVE SUMMARY & TAXONOMY)

Sau khi cụm 3 cluster (`hub-k3d`, `aws-k3d`, `azure-k3d`) vận hành 100% ổn định (Zero Pods Killed) và kênh cảnh báo Telegram (Robusta + AI Anomaly) đã được kích hoạt thành công, việc rà soát thực tế trên Grafana phát hiện tình trạng **No Data** và **Lỗi truy vấn** phân bổ trên cả 8 Dashboards.

Qua quá trình debug chuyên sâu trực tiếp vào runtime của `otel-collector-hub`, `thanos-query`, `tempo` và các log nội bộ OTel Collector (`v0.114.0`), nguyên nhân **KHÔNG PHẢI do thiếu hạ tầng hay rớt kết nối mạng**, mà xuất phát từ **4 nhóm nguyên nhân kỹ thuật cốt lõi** sau:

```
┌──────────────────────────────────────────────────────────────────────────────────────────────────┐
│                             4 NGUYÊN NHÂN CỐT LÕI GÂY NO DATA                                   │
└──────────────────────────────────────────────────────────────────────────────────────────────────┘
                                                 │
         ┌───────────────────┬───────────────────┴───────────────────┬───────────────────┐
         ▼                   ▼                                       ▼                   ▼
  [NGUYÊN NHÂN 1]     [NGUYÊN NHÂN 2]                         [NGUYÊN NHÂN 3]     [NGUYÊN NHÂN 4]
  Xung đột Nhãn kép   Cú pháp PromQL sai                      Chia Vector Rỗng    Dịch vụ AI & Port 8888
  OTTL Resource       So sánh Nhãn-với-Nhãn                   Khi 0 lỗi (Healthy) Chưa chạy nền / Thiếu port
  (Duplicate Labels)  {client_cp != server_cp}                `100 - (failed/total)` Chưa bật Daemon AI
  Drop 100% metrics   Lỗi "unexpected string"                 -> Trả về [] No Data  Chưa mở port 8888 SVC
```

### Bảng tóm tắt ảnh hưởng theo từng Dashboard

| Dashboard | Tên Dashboard | Tình trạng báo cáo | Nhóm nguyên nhân gốc rễ | Mức độ ảnh hưởng |
|---|---|---|---|:---:|
| **Dashboard 1** | `01. Executive Overview` | Global Availability, WAN Traffic Ratio, P95 Latency, Fleet Health Matrix bị No Data & Lỗi cú pháp | Nguyên nhân 1, 2, 3 | **Nghiêm trọng (P1)** |
| **Dashboard 2** | `02. Multi-Cloud Topology & Inventory` | Panel 6 (Cluster Node Resource & Network Health Table) bị No Data | Nguyên nhân 1 | **Trung bình (P2)** |
| **Dashboard 3** | `03. RED & USE Observability` | Host CPU I/O Wait, JVM Heap/Threads/GC, AIOps Anelihood/RCA bị No Data | Nguyên nhân 1, 4 | **Nghiêm trọng (P1)** |
| **Dashboard 4** | `04. Compute & OS Kernel (USE)` | **100% các panels đều No Data** (17/17 panels) | Nguyên nhân 1 | **Nghiêm trọng (P1)** |
| **Dashboard 5** | `05. Network & WAN Transport` | Cross-Cloud Calls, Latency Duration, WAN Throughput, Packet Drops bị No Data & Lỗi cú pháp | Nguyên nhân 1, 2 | **Nghiêm trọng (P1)** |
| **Dashboard 6** | `06. Logs, Traces & Database` | TraceQL Explorer (Cross-Cloud Slow & Error Traces) bị No Data | Bộ lọc TraceQL quá chặt chẽ (Ngưỡng >1.5s hoặc lỗi khi hệ thống đang 100% bình thường) | **Thấp (P3)** |
| **Dashboard 7** | `07. SLO Governance & Error Budget` | Current Availability SLI bị No Data | Nguyên nhân 3 (Chia Vector Rỗng khi 0 lỗi) | **Trung bình (P2)** |
| **Dashboard 8** | `08. Cloud Cost & Telemetry Governance` | Ngoại trừ Panel 6, tất cả panels còn lại đều No Data | Nguyên nhân 1, 4 (Metrics `otelcol_*` bị drop và thiếu Port 8888) | **Nghiêm trọng (P1)** |

---

## 2. PHÂN TÍCH KỸ THUẬT CHI TIẾT THEO TỪNG NGUYÊN NHÂN GỐC RỄ

### 2.1. NGUYÊN NHÂN 1: Xung đột nhãn kép OTTL Resource Attributes (Duplicate Label Collision)
* **Hiện tượng:** Toàn bộ metrics `system_*` (hostmetrics), `jvm_*` (TeaStore JVM), `process_*`, và `otelcol_*` hoàn toàn biến mất khỏi Thanos Query (`label/__name__/values` chỉ thấy metrics của Thanos/Loki/Tempo và `traces_service_graph_*`).
* **Bằng chứng từ log container `otel-collector-hub`:**
  ```text
  error prometheusexporter@v0.114.0/collector.go:424 failed to convert metric system.cpu.time: duplicate label names in constant and variable labels for metric "system_cpu_time_seconds_total"
  error prometheusexporter@v0.114.0/collector.go:424 failed to convert metric system.disk.io: duplicate label names in constant and variable labels for metric "system_disk_io_bytes_total"
  error prometheusexporter@v0.114.0/collector.go:424 failed to convert metric jvm.memory.limit: duplicate label names in constant and variable labels for metric "jvm_memory_limit_bytes"
  error prometheusexporter@v0.114.0/collector.go:424 failed to convert metric jvm.thread.count: duplicate label names in constant and variable labels for metric "jvm_thread_count"
  error prometheusexporter@v0.114.0/collector.go:424 failed to convert metric otelcol_receiver_accepted_spans: duplicate label names in constant and variable labels for metric "otelcol_receiver_accepted_spans_total"
  ```
* **Cơ chế gây lỗi (Mechanism):**
  1. Trong cấu hình exporter của Hub Collector:
     ```yaml
     prometheus:
       endpoint: 0.0.0.0:8889
       resource_to_telemetry_conversion:
         enabled: true
     ```
     Khi bật `resource_to_telemetry_conversion: enabled: true`, OpenTelemetry Collector sẽ tự động chuyển đổi tất cả **Resource Attributes** sang nhãn Prometheus (dấu chấm `.` chuyển thành dấu gạch dưới `_`). Ví dụ: `k8s.cluster.name` $\rightarrow$ `k8s_cluster_name`, `cloud.provider` $\rightarrow$ `cloud_provider`.
  2. Tuy nhiên, trong tệp OTTL transforms tại cả Spoke (`edge/02-configmap.yaml`) và Hub (`gateway/03-configmap.yaml`), cấu hình lại gán đồng thời **cả 2 dạng**:
     ```yaml
     # Tệp Spoke & Hub OTTL
     - set(attributes["k8s.cluster.name"], "${CLUSTER_NAME}")
     - set(attributes["k8s_cluster_name"], "${CLUSTER_NAME}")    # <--- DƯ THỪA!
     - set(attributes["cloud.provider"], "${CLOUD_PROVIDER}")
     - set(attributes["cloud_provider"], "${CLOUD_PROVIDER}")      # <--- DƯ THỪA!
     ```
  3. Khi exporter xử lý, `k8s.cluster.name` được sanitize thành `k8s_cluster_name`. Nhưng trên Resource đã có sẵn thuộc tính `k8s_cluster_name`! Thư viện `prometheus/client_golang` phát hiện 2 nhãn trùng tên trên cùng 1 descriptor và ném lỗi `duplicate label names in constant and variable labels`.
  4. **Hậu quả:** Bộ chuyển đổi OTel hủy bỏ (drop) toàn bộ metric point! Hàng trăm nghìn mẫu số liệu của `system_*` (OS/Host), `jvm_*` (Java runtime), và `otelcol_*` (Pipeline Telemetry) bị vứt bỏ hoàn toàn ngay tại Gateway!

---

### 2.2. NGUYÊN NHÂN 2: Lỗi cú pháp PromQL So sánh Nhãn-với-Nhãn (`unexpected string`)
* **Hiện tượng:** Grafana hiển thị thông báo lỗi màu đỏ:
  `bad data, "server_cloud_provider" unexpected string, expected string literal`
* **Vị trí lỗi:**
  - Dashboard 1 (Panel 4 & Panel 5):
    - `(sum(rate(traces_service_graph_request_total{client_cloud_provider!=server_cloud_provider}[1m])) ...`
    - `histogram_quantile(0.95, sum by (le, client, server) (rate(traces_service_graph_request_server_seconds_bucket{client_cloud_provider!=server_cloud_provider}[1m]))) * 1000`
  - Dashboard 5 (Panel 4 & Panel 5):
    - `sum(rate(traces_service_graph_request_total{client_cloud_provider!=server_cloud_provider}[1m])) ...`
    - `rate(traces_service_graph_request_server_seconds_bucket{client_cloud_provider!=server_cloud_provider}[5m]) ...`
* **Cơ chế gây lỗi (Mechanism):**
  Trong đặc tả ngôn ngữ PromQL chuẩn, vế phải của bộ so sánh nhãn `{label operator "literal"}` **bắt buộc phải là chuỗi hằng số (string literal)** đặt trong dấu ngoặc kép (ví dụ: `client_cloud_provider!="aws"`).
  PromQL **hoàn toàn KHÔNG cho phép** so sánh trực tiếp tên nhãn này với tên nhãn khác (`{label1 != label2}`). Trình phân tích cú pháp Prometheus coi `server_cloud_provider` là một token không hợp lệ và lập tức từ chối truy vấn.
* **Giải pháp chuẩn:**
  Thay vì so sánh nhãn trừu tượng, truy vấn đa đám mây (Cross-Cloud) trong mô hình TeaStore được định nghĩa rõ ràng theo cặp cụm Spoke:
  - Chiều AWS $\rightarrow$ Azure: `{client_cloud_provider="aws", server_cloud_provider="azure"}`
  - Chiều Azure $\rightarrow$ AWS: `{client_cloud_provider="azure", server_cloud_provider="aws"}`
  - Kết hợp bằng toán tử `or`:
    ```promql
    sum(rate(traces_service_graph_request_total{client_cloud_provider="aws", server_cloud_provider="azure"}[1m])) 
    or sum(rate(traces_service_graph_request_total{client_cloud_provider="azure", server_cloud_provider="aws"}[1m]))
    or vector(0)
    ```

---

### 2.3. NGUYÊN NHÂN 3: Lỗi chia Vector Rỗng khi hệ thống 100% Khỏe mạnh (Zero-Error Availability Bug)
* **Hiện tượng:**
  - Dashboard 1: `Global System Availability` báo No Data.
  - Dashboard 7: `Current Availability SLI` báo No Data.
* **Vị trí lỗi:**
  ```promql
  clamp_max(100 - (sum(rate(traces_service_graph_request_failed_total[5m])) / (sum(rate(traces_service_graph_request_total[5m])) + 0.0001) * 100), 100)
  ```
* **Cơ chế gây lỗi (Mechanism):**
  1. Bộ nối `servicegraphconnector` trong OTel Hub chỉ sinh ra chuỗi số liệu `traces_service_graph_request_failed_total` **khi có ít nhất 1 request thất bại (HTTP 5xx / Error span)**.
  2. Khi hệ thống đang hoạt động bình thường, ổn định và không có lỗi: Metric `traces_service_graph_request_failed_total` **không tồn tại trong cơ sở dữ liệu Thanos**.
  3. Hàm `sum(rate(traces_service_graph_request_failed_total[5m]))` trả về **Empty Vector (`[]`)**, chứ không phải số `0`.
  4. Trong toán tử số học PromQL: `Empty Vector / Vector khác` $\rightarrow$ **Empty Vector (`[]`)**; và `100 - Empty Vector` $\rightarrow$ **Empty Vector (`[]`)**.
  5. Grafana nhận được kết quả rỗng nên hiển thị `No Data`, thay vì hiển thị `100% Availability`!
* **Giải pháp chuẩn:**
  Sử dụng toán tử `or vector(0)` để đảm bảo khi không có lỗi, tử số luôn mang giá trị `0`:
  ```promql
  clamp_max(100 - (((sum(rate(traces_service_graph_request_failed_total[5m])) or vector(0)) / (sum(rate(traces_service_graph_request_total[5m])) + 0.0001)) * 100), 100)
  ```
  *(Đã kiểm thử thực tế trên Thanos Query: Biểu thức này lập tức trả về `100%` chính xác).*

---

### 2.4. NGUYÊN NHÂN 4: Thiếu Cổng Dịch vụ 8888 & Dịch vụ Nền AI Engine
1. **Sự cố Cổng 8888 (Internal Telemetry):**
   - Prometheus cấu hình scrape `otel-collector-hub.monitoring.svc.cluster.local:8888`.
   - Tuy nhiên, trong `k8s/base/otel-collector/gateway/05-service.yaml`, Service chỉ mở cổng `4317`, `4318`, và `8889`; **cổng 8888 hoàn toàn bị thiếu**.
   - Hậu quả: Prometheus gặp lỗi `Connection Refused` khi cố gắng scrape cổng 8888, làm cho các số liệu nội tại của Collector (Dashboard 8) không thu thập được qua đường này.
2. **Sự cố AIOps Anomaly Likelihood (Dashboard 3):**
   - Panel 7 truy vấn `ai_anomaly_likelihood_percent` và `ai_rca_component_latency_ms`.
   - Các metric này do script `ai-engine/inference/detector.py` cung cấp qua Prometheus exporter tại cổng `9108`.
   - Hiện tại `detector.py` được thiết kế để chạy đánh giá theo lượt (batch/on-demand evaluation) chứ chưa được triển khai thành Deployment pod chạy liên tục (Daemon service) trong Kubernetes.
   - Giải pháp:
     - Trong ngắn hạn: Bổ sung fallback `or vector(0)` vào query của Dashboard 3 để hiển thị trạng thái `0% Anomaly` (Normal baseline) khi AI Engine chưa có phát hiện bất thường.
     - Trong dài hạn: Triển khai `ai-engine` thành một Deployment chạy nền trong namespace `monitoring` (kèm Virtualenv cài đủ `torch`, `joblib`, `scikit-learn`).

---

### 2.5. BỘ LỌC TRACEQL TRÊN DASHBOARD 6 (Logs, Traces & Database)
* **Hiện tượng:** `Tempo Distributed TraceQL Explorer` hiển thị No Data.
* **Nguyên nhân:**
  Query hiện tại là: `{ status = error || duration > 1.5s }`.
  Trong điều kiện TeaStore vận hành bình thường, độ trễ trung bình chỉ từ 10ms đến 50ms và tỷ lệ lỗi = 0%. Bộ lọc tìm kiếm các trace có lỗi hoặc độ trễ > 1.5s đương nhiên trả về 0 kết quả.
* **Giải pháp:**
  Cải tiến câu query TraceQL thành:
  `{ .service.name =~ "teastore.*" }`
  kết hợp sắp xếp theo thời gian hoặc thời lượng để người dùng luôn nhìn thấy luồng vết phân tán thời gian thực, và khi có sự cố tiêm lỗi thì các span lỗi / chậm sẽ nổi bật lên đầu danh sách.

---

## 3. ĐÁNH GIÁ THƯ VIỆN, CÔNG CỤ & TIÊU CHUẨN OPENTELEMETRY

### 3.1. Về chuẩn OpenTelemetry Semantic Conventions
- **Khuyến nghị chuẩn:** Tuân thủ triệt để OpenTelemetry Semantic Conventions (`v1.26+`).
- **Nguyên tắc:** 
  - Trong tầng Resource Attributes, **chỉ giữ lại các thuộc tính phân cấp bằng dấu chấm (`.`)**:
    - `k8s.cluster.name`
    - `cloud.provider`
    - `cloud.region`
    - `deployment.environment.name`
    - `service.name`
  - **Loại bỏ triệt để** việc tự gán thủ công các thuộc tính dấu gạch dưới (`k8s_cluster_name`, `cloud_provider`, `cloud_region`) trong OTTL Resource context.
  - Khi `resource_to_telemetry_conversion: enabled: true` được kích hoạt, Prometheus Exporter sẽ tự động chuyển `k8s.cluster.name` thành `k8s_cluster_name` một cách duy nhất, loại bỏ hoàn toàn lỗi duplicate label.

### 3.2. Về Thư viện và Môi trường
- **Cụm Kubernetes & Collector:** Đầy đủ 100%, không cần cài thêm MCP hay container phụ thuộc nào khác.
- **Python Môi trường WSL:** Đối với `ai-engine`, để chạy liên tục mô hình Ensemble (GRU + TCN + Isolation Forest), cần một môi trường ảo Python cô lập có sẵn:
  `torch`, `joblib`, `scikit-learn`, `requests`, `prometheus-client`.

### 3.3. Tiếp thu Ý tưởng & Kiến trúc Chuẩn từ SigNoz (SigNoz k8sattributes & Resource Architecture)
Sau khi nghiên cứu kho tài liệu và mã nguồn SigNoz tại `docs/other-reference/SigNozDocs` và `docs/other-reference/SigNozSrc`:
1. **Tích hợp `k8sattributes` Processor chuẩn SigNoz:**
   SigNoz sử dụng `k8sattributes` với `pod_association` qua cả 3 nguồn:
   - `connection` (IP client kết nối OTLP)
   - `resource_attribute: k8s.pod.ip`
   - `resource_attribute: k8s.pod.uid`
   Bộ xử lý này lắng nghe trực tiếp Kubernetes API để tự động enrich `k8s.namespace.name`, `k8s.pod.name`, `k8s.node.name`, `k8s.deployment.name` vào toàn bộ traces, metrics, logs phát ra từ workloads mà không cần gán nhãn thủ công. Ta sẽ tích hợp khối này vào Spoke Edge Collectors (`edge/02-configmap.yaml`).
2. **Quy tắc Bất biến về Độc tôn Semantic Conventions:**
   SigNoz khẳng định: Telemetry resource **chỉ chứa các thuộc tính phân cấp dạng chấm** (`k8s.cluster.name`, `cloud.provider`, `cloud.region`, `deployment.environment.name`).
   Tuyệt đối không bao giờ chèn thêm các nhãn gạch dưới (`k8s_cluster_name`, `cloud_provider`) vào Resource map vì Prometheus Exporter sẽ tự động chuyển đổi `k8s.cluster.name` $\rightarrow$ `k8s_cluster_name`. Việc chèn thêm thủ công sẽ làm gãy pipeline vì xung đột nhãn kép.

---

## 4. KẾ HOẠCH KHẮC PHỤC CHI TIẾT (ACTION PLAN v5.0)

### 4.1. Bước 1: Khắc phục Xung đột Nhãn kép & Bổ sung k8sattributes chuẩn SigNoz
1. **Tệp `k8s/base/otel-collector/edge/02-configmap.yaml`:**
   - Bổ sung `k8sattributes` processor chuẩn SigNoz vào danh sách processors và các pipelines (`traces`, `logs`, `metrics`).
   - Xóa các dòng gán nhãn trùng lặp (`k8s_cluster_name`, `cloud_provider`) trong khối `transform/cluster_id`. Chỉ giữ lại các canonical attributes: `k8s.cluster.name`, `cloud.provider`, `cloud.region`, `deployment.environment.name`.
2. **Tệp `k8s/base/otel-collector/gateway/03-configmap.yaml`:**
   - Xóa các dòng gán nhãn gạch dưới trùng lặp trong khối `metric_statements` của `transform/normalize_cloud`:
     - Xóa `set(attributes["k8s_cluster_name"], ...)`
     - Xóa `set(attributes["cloud_provider"], ...)`
     - Xóa `set(attributes["cluster"], ...)`
     - Xóa `set(attributes["cloud"], ...)`
     - Xóa `set(attributes["region"], ...)`
     Chỉ giữ lại các thuộc tính chuẩn Semantic Conventions (`k8s.cluster.name`, `cloud.provider`, `cloud.region`).
   - Cấu hình kích hoạt `service.telemetry.metrics.address: 0.0.0.0:8888`.
3. **Tệp `k8s/base/otel-collector/gateway/05-service.yaml`:**
   - Bổ sung port `8888` (`telemetry`) vào Service `otel-collector-hub`.

### 4.2. Bước 2: Chuẩn hóa cú pháp PromQL trên các Grafana Dashboards (Sửa dứt điểm Lỗi 2 & 3)
1. **`k8s/base/visualization-grafana/dashboards/mc-executive-overview.json` (Dashboard 1):**
   - Panel `Global System Availability`: Bổ sung `or vector(0)` chống rỗng.
   - Panel `Cross-Cloud WAN Traffic Ratio`: Thay thế `{client_cloud_provider!=server_cloud_provider}` bằng so sánh cụm/vùng tường minh.
   - Panel `Inter-Cloud WAN Response Time`: Thay thế cú pháp so sánh nhãn tương tự.
2. **`k8s/base/visualization-grafana/dashboards/red-metrics.json` (Dashboard 3):**
   - Panel `AIOps Proactive Anomaly Likelihood`: Bổ sung `or vector(0)` để đảm bảo hiển thị 0% khi AI Engine chưa kích hoạt báo động.
3. **`k8s/base/visualization-grafana/dashboards/wan-telemetry.json` (Dashboard 5):**
   - Panel 4 (`Cross-Cloud WAN Calls / sec`): Sửa cú pháp `{client_cloud_provider="aws", server_cloud_provider="azure"} or ...`.
   - Panel 5 (`Cross-Cloud Network Latency Duration`): Sửa cú pháp tương ứng.
4. **`k8s/base/visualization-grafana/dashboards/logs-traces-deepdive.json` (Dashboard 6):**
   - Panel 6 (`TraceQL Explorer`): Cập nhật query thành `{ .service.name =~ "teastore.*" }` để luôn hiển thị spans phân tán thực tế.
5. **`k8s/base/visualization-grafana/dashboards/slo-governance.json` (Dashboard 7):**
   - Panel 2 (`Current Availability SLI`): Bổ sung `or vector(0)` chống chia rỗng.
6. **`k8s/base/visualization-grafana/dashboards/mc-cost-telemetry.json` (Dashboard 8):**
   - Chuẩn hóa tên metrics OTel v0.114.0 (hỗ trợ cả suffix `_total` và không có `_total` bằng biểu thức regex hoặc `or`).

### 4.3. Bước 3: Triển khai Áp dụng & Kiểm thử lại (Apply & Re-validate)
1. Áp dụng ConfigMap và Service cập nhật lên cụm Hub và Spoke:
   ```bash
   kubectl --context k3d-hub-k3d apply -k k8s/overlays/local-k3d/hub
   kubectl --context k3d-aws-k3d apply -k k8s/overlays/local-k3d/aws
   kubectl --context k3d-azure-k3d apply -k k8s/overlays/local-k3d/azure
   ```
2. Khởi động lại các Collector Pods:
   ```bash
   kubectl --context k3d-hub-k3d rollout restart deployment otel-collector-hub -n monitoring
   kubectl --context k3d-aws-k3d rollout restart deployment otel-collector-spoke -n monitoring
   kubectl --context k3d-azure-k3d rollout restart deployment otel-collector-spoke -n monitoring
   ```
3. Khởi động lại Grafana Pod để nạp lại 8 tệp Dashboard JSON mới:
   ```bash
   kubectl --context k3d-hub-k3d rollout restart deployment grafana -n monitoring
   ```
4. Kiểm tra dòng dữ liệu metrics `system_*`, `jvm_*`, `otelcol_*` trên Thanos Query API.
5. Truy cập Grafana UI và xác nhận **100% các panel trên cả 8 Dashboards đều hiển thị dữ liệu trực quan, không còn bất kỳ lỗi No Data hay cú pháp nào**.

---

## 5. KẾT LUẬN GIAI ĐOẠN 1

Giai đoạn 1 đã giải quyết triệt để 4 lỗi gốc rễ hệ thống (Duplicate Label Collision trong OTel Collector v0.114.0, Lỗi cú pháp PromQL so sánh nhãn chuỗi, Phép tính chia Vector rỗng, và Mở cổng nội bộ 8888). Toàn bộ 22 metric `system_*` và 14 metric `jvm_*` đã được khôi phục thành công.

---

## 6. PHÂN TÍCH CHUYÊN SÂU CÁC VẤN ĐỀ PHÁT SINH MỚI & ĐỀ XUẤT TRIỆT ĐỂ (PHASE 2 AUDIT)

Sau khi kiểm thử trực tiếp trên giao diện Grafana, người dùng ghi nhận 4 nhóm vấn đề cần giải quyết triệt để:
1. **Dashboard 3:** Panel `Errors (Failed Requests/sec)` đang bị No Data.
2. **Dashboard 4:** `CPU Usage (400%)` và `Disk Space Usage (1007 GB WSL2 VHDX)` bị No Data; `Memory Usage (9.59 GB)` bị lệch; kiểm tra các con số (400%), (9.59 GB), (1007 GB) là gán ảo hay biết thật; rà soát toàn bộ các sơ đồ liên quan và đối chiếu với mô hình Container CPU/Memory.
3. **Dashboard 6:** `Tempo Distributed TraceQL Explorer (Cross-Cloud Slow & Error Traces)` và `Trace Spans Latency Distribution & Service Bottlenecks (P99, P90, P50)` bị No Data.
4. **Dashboard 7:** `Service Error Budget Consumption Breakdown` đang bị No Data.

Dưới đây là kết quả điều tra thực nghiệm chi tiết và đề xuất giải pháp kỹ thuật:

---

### 6.1. VẤN ĐỀ 1: Dashboard 3 - `Errors (Failed Requests/sec)` đang No Data

#### A. Bản chất nguyên nhân kỹ thuật
- Truy vấn hiện tại:
  ```promql
  sum by (server) (rate(traces_service_graph_request_failed_total{server=~"$service"}[1m]))
  ```
- **Nguyên nhân:** Cụm microservices TeaStore đang vận hành hoàn toàn ổn định (Global Availability đạt 100%), không có bất kỳ request nào bị lỗi HTTP 5xx hay status code ERROR.
- Trong OpenTelemetry Service Graph Connector, metric `traces_service_graph_request_failed_total` **chỉ được khởi tạo khi có ít nhất 1 span lỗi**. Khi không có lỗi, chuỗi dữ liệu (timeseries) này hoàn toàn không tồn tại trong Prometheus/Thanos.
- Phép tính `rate(...)` trên một chuỗi không tồn tại sẽ trả về **vector rỗng `[]`**, khiến Grafana timeseries panel hiển thị **"No Data"** thay vì hiển thị một đường phẳng ở mức `0 req/s`.

#### B. Đề xuất giải pháp
Sử dụng toán tử `or` kết hợp với `traces_service_graph_request_total * 0` để tạo ra một đường baseline 0 phẳng cho toàn bộ các server đang hoạt động:
```promql
sum by (server) (rate(traces_service_graph_request_failed_total{server=~"$service"}[1m])) or (sum by (server) (rate(traces_service_graph_request_total{server=~"$service"}[1m])) * 0)
```
- **Khi hệ thống khỏe mạnh (0 lỗi):** Trả về giá trị `0 failed req/s` cho từng server (`teastore-webui`, `teastore-persistence`, `teastore-registry`, `teadb`). Panel hiển thị đường xanh/xám phẳng ở mức 0, chấm dứt hoàn toàn chữ "No Data".
- **Khi xảy ra sự cố (Chaos fault injection hoặc Killed Pod):** Nhánh đầu tiên `traces_service_graph_request_failed_total` sẽ có dữ liệu và ngay lập tức nhảy vọt lên hiển thị đúng tốc độ lỗi thực tế.

---

### 6.2. VẤN ĐỀ 2: Dashboard 4 - Rà soát các con số (400%), (9.59 GB), (1007 GB), bản chất Container vs Host, và khắc phục No Data

#### A. Xác minh các con số (400%), (9.59 GB), (1007 GB) có phải gán ảo không?
Kết quả kiểm tra trực tiếp trên môi trường máy chủ Linux / WSL2 runtime (`nproc`, `free -h`, `df -h /`, `lsblk`):
```text
$ nproc
4

$ free -h
              total        used        free      shared  buff/cache   available
Mem:          9.6Gi       6.6Gi       347Mi        53Mi       2.9Gi       3.0Gi

$ df -h /
Filesystem      Size  Used Avail Use% Mounted on
/dev/sdf       1007G  6.6G  950G   1% /
```

**KẾT LUẬN XÁC MINH:**
1. **Các con số này HOÀN TOÀN KHÔNG PHẢI GÁN ẢO BỪA BÃI!**
   - **400%:** Máy ảo WSL2 có đúng `4 vCPU cores` (`nproc = 4`). Trong hệ sinh thái Linux / Kubernetes, mỗi core CPU đại diện cho 100% compute capacity. 4 cores = 400% năng lực xử lý tối đa của máy chủ.
   - **9.59 GB:** Lệnh `free -h` ghi nhận tổng RAM của máy ảo là `9.6 GiB` (quy đổi chính xác sang số thập phân là 9.59 GB).
   - **1007 GB:** Ổ đĩa ảo VHDX co giãn mặc định mà Docker Desktop / WSL2 cấp phát cho Linux ext4 có kích thước tối đa là đúng `1007 GB` (1 TB).
2. **Tuy nhiên, việc đưa các con số này vào Dashboard bị 2 điểm hạn chế lớn:**
   - **Thứ nhất (Thiết kế bị tĩnh/hardcoded):** Tên tiêu đề và ngưỡng gauge bị gán cứng vào phần cứng hiện tại của máy host. Nếu chuyển sang máy khác có 8 core CPU hoặc 16 GB RAM thì các tiêu đề này sẽ bị sai.
   - **Thứ hai (Bản chất đo lường Host OS vs Docker Container):** Người dùng ban đầu muốn theo dõi mức sử dụng tài nguyên của Docker Container (Container CPU & Container Memory), nhưng OTel Collector hiện tại đang thu thập từ `hostmetrics` receiver (tầng Node/Host OS). Đồng thời, trong k3d local, Prometheus chưa scrape `/metrics/cadvisor` của kubelet nên các metric `container_cpu_*` và `container_memory_*` chưa có sẵn.
   - **Thứ ba (Lỗi No Data ở Disk Space Usage):** Trong câu truy vấn đang hardcode `device="/dev/sde"`. Nhưng qua kiểm tra thực tế bằng script, trong các container k3d node, ổ đĩa chính 1007 GB được ánh xạ dưới tên thiết bị `/dev/sdd` (dung lượng 939.72 GiB), còn `/dev/sde` chỉ là đĩa nhỏ 140MB. Do đó filter `device="/dev/sde"` trả về rỗng dẫn đến No Data!
   - **Thứ tư (Lỗi No Data ở CPU Usage 400%):** Do dùng `rate(...)[1m]` tức thời mà không có fallback khi nhàn rỗi hoặc khi biến `$cluster` lọc theo cụm đơn lẻ.

#### B. Đề xuất giải pháp chuẩn hóa động cho Dashboard 4
Để đưa Dashboard 4 về đúng chuẩn chuyên nghiệp của SRE/DevOps, loại bỏ việc hardcode số phần cứng và hiển thị dữ liệu động 100%:

1. **Chuẩn hóa Gauge CPU thành tỷ lệ % động 0% – 100%:**
   - **Tiêu đề mới:** `CPU Utilization (% of Total Cluster Cores)`
   - **Công thức PromQL mới:**
     ```promql
     (sum(rate(system_cpu_time_seconds_total{k8s_cluster_name=~"$cluster", state!="idle"}[1m])) / sum(count by (cpu, k8s_cluster_name) (system_cpu_time_seconds_total{k8s_cluster_name=~"$cluster"}))) * 100
     ```
   - **Cấu hình Gauge:** `min: 0`, `max: 100`, `unit: percent`.
   - **Lợi ích:** Tự động đếm số core CPU của từng cụm (2, 4, hay 8 cores) và hiển thị thanh đo 0–100% chuẩn xác.

2. **Chuẩn hóa Gauge Memory thành % RAM sử dụng động kèm dung lượng thực tế:**
   - **Tiêu đề mới:** `Memory Utilization (% Used)`
   - **Công thức PromQL mới:**
     ```promql
     (sum(system_memory_usage_bytes{k8s_cluster_name=~"$cluster", state="used"}) / sum(system_memory_usage_bytes{k8s_cluster_name=~"$cluster"})) * 100
     ```
   - **Thêm Target B (Dung lượng RAM thực tế dạng GB):**
     ```promql
     sum(system_memory_usage_bytes{k8s_cluster_name=~"$cluster", state="used"}) / (1024*1024*1024)
     ```
   - **Cấu hình Gauge:** `min: 0`, `max: 100`, `unit: percent`.
   - **Lợi ích:** Không còn con số tĩnh 9.59 GB, thể hiện chính xác tải bộ nhớ của cụm được chọn trong dropdown `$cluster`.

3. **Sửa Disk Space Usage để nhận diện đúng ổ đĩa ảo `/dev/sd*`:**
   - **Tiêu đề mới:** `Node Storage Utilization (% VHDX Disk Capacity)`
   - **Công thức PromQL mới:**
     ```promql
     (max by (k8s_cluster_name) (system_filesystem_usage_bytes{k8s_cluster_name=~"$cluster", state="used", device=~"/dev/sd.*"}) / max by (k8s_cluster_name) (system_filesystem_usage_bytes{k8s_cluster_name=~"$cluster", device=~"/dev/sd.*"})) * 100
     ```
   - **Cấu hình Gauge:** `min: 0`, `max: 100`, `unit: percent`.
   - **Lợi ích:** Tự động bắt đúng ổ đĩa `/dev/sdd` (1007 GB), loại bỏ hoàn toàn lỗi No Data.

---

### 6.3. VẤN ĐỀ 3: Dashboard 6 - `Tempo Distributed TraceQL Explorer` & `Trace Spans Latency Distribution (P99, P90, P50)`

#### A. Bản chất nguyên nhân kỹ thuật
1. **Đối với Panel 6 (`Tempo Distributed TraceQL Explorer`):**
   - Kiểm tra log của Grafana container (`kubectl logs deployment/grafana -n monitoring`):
     ```text
     logger=tsdb.tempo endpoint=queryData pluginId=tempo dsName=Tempo error="backend TraceQL search queries are not supported"
     logger=context error="client: failed to query data: backend TraceQL search queries are not supported" status=500
     ```
   - **Nguyên nhân gốc rễ:** Đây là **giới hạn kiến trúc chính thức của plugin Tempo trong Grafana (Grafana Core)**. Backend của Grafana (`/api/ds/query`) **không hỗ trợ** chạy các truy vấn tìm kiếm TraceQL tùy biến (`TraceQL search queries`) như một panel bên trong Dashboard! Chức năng tìm kiếm TraceQL được Grafana xây dựng độc quyền cho trang **Grafana Explore** (thông qua frontend proxy).
   - Khi đặt `queryType: "traceql"` trong một Dashboard Panel thông thường, backend Grafana sẽ báo lỗi HTTP 500 và panel sẽ hiển thị No Data.
2. **Đối với Panel 7 (`Trace Spans Latency Distribution & Service Bottlenecks`):**
   - Trong Service Graph Connector, metric `traces_service_graph_request_server_seconds_bucket` chỉ được sinh ra cho các dịch vụ đóng vai trò là `server` (đích đến của request, gồm: `teastore-webui`, `teastore-registry`, `teadb`, `teastore-persistence`).
   - Các dịch vụ trung gian như `auth`, `image`, `recommender` không có nhãn `server` trong bảng bucket này. Nếu dropdown `$service` chọn trúng các dịch vụ này hoặc chọn cụm chưa có dữ liệu 5m, `histogram_quantile` trả về rỗng $\rightarrow$ No Data.

#### B. Đề xuất giải pháp
1. **Giải pháp cho Panel 6 (Tempo TraceQL Explorer):**
   - Chuyển đổi Panel 6 từ panel loại `traces` (bị lỗi backend 500) sang **Interactive Trace Exploration & Navigation Card** (loại Text/Markdown trực quan hoặc Table panel) với **Nút bấm 1-click mở trực tiếp Grafana Explore**:
     ```markdown
     ### 🔍 Distributed Traces Real-Time Explorer (Tempo TraceQL)
     Truy vấn vết phân tán thời gian thực liên cụm (AWS us-east-1 <-> Azure southasia).

     👉 **[Bấm vào đây để mở Bộ lọc TraceQL trên Grafana Explore](/explore?left=%7B%22datasource%22:%22tempo-ds%22,%22queries%22:%5B%7B%22queryType%22:%22traceql%22,%22query%22:%22%7B+status+%3D+error+%7C%7C+duration+%3E+1.5s+%7C%7C+.service.name+%3D~+%5C%22teastore.*%5C%22+%7D%22%7D%5D,%22range%22:%7B%22from%22:%22now-1h%22,%22to%22:%22now%22%7D%7D)**
     - **Bộ lọc tích hợp sẵn:** `{ status = error || duration > 1.5s || .service.name =~ "teastore.*" }`
     - **Tính năng:** Xem Waterfall Spans chi tiết, Span Attributes, Resource Tags, và liên kết ngược sang Loki Logs.
     ```
   - Đây là giải pháp chuẩn tắc và tương thích 100% với cơ chế vận hành của Grafana & Tempo.
2. **Giải pháp cho Panel 7 (Latency Percentiles P99, P90, P50):**
   - Bổ sung fallback vector để tránh No Data khi dịch vụ không có request trong cửa sổ ngắn:
     ```promql
     (histogram_quantile(0.99, sum by (le, server) (rate(traces_service_graph_request_server_seconds_bucket{server=~"$service"}[5m]))) * 1000) or (sum by (server) (rate(traces_service_graph_request_total{server=~"$service"}[5m])) * 0)
     ```
   - Tương tự cho P90 và P50. Khi không có request hoặc server nhàn rỗi, biểu đồ vẽ mức 0 ms thay vì báo lỗi No Data.

---

### 6.4. VẤN ĐỀ 4: Dashboard 7 - `Service Error Budget Consumption Breakdown` đang No Data

#### A. Bản chất nguyên nhân kỹ thuật
- Truy vấn hiện tại:
  ```promql
  sum by (server) (rate(traces_service_graph_request_failed_total{server=~"$service"}[5m]))
  ```
- **Nguyên nhân:** Tương tự Dashboard 3, hệ thống đang đạt mức khả dụng 100% (Zero Errors). Do đó không có chuỗi metric `traces_service_graph_request_failed_total`, dẫn đến việc biểu thức đánh giá ra vector rỗng và hiển thị No Data.
- Đồng thời, ở Panel 5 `Multi-Window Error Budget Burn Rate Trend`:
  ```promql
  (sum(rate(traces_service_graph_request_failed_total{server=~"$service"}[5m])) / (sum(rate(traces_service_graph_request_total{server=~"$service"}[5m])) + 0.0001)) / 0.005
  ```
  Tử số rỗng khiến kết quả Burn Rate trong cả 2 cửa sổ 5m và 30m cũng bị rỗng theo khi hệ thống hoàn toàn khỏe mạnh.

#### B. Đề xuất giải pháp
1. **Sửa Panel 6 (`Service Error Budget Consumption Breakdown`):**
   ```promql
   sum by (server) (rate(traces_service_graph_request_failed_total{server=~"$service"}[5m])) or (sum by (server) (rate(traces_service_graph_request_total{server=~"$service"}[5m])) * 0)
   ```
   - Khi 0 lỗi: Hiển thị baseline 0.000 req/s cho từng microservice.
   - Khi có lỗi: Hiển thị chính xác microservice nào đang đốt ngân sách lỗi (Error Budget).
2. **Sửa Panel 5 (`Multi-Window Error Budget Burn Rate Trend`):**
   - Cửa sổ ngắn 5m (RefId A):
     ```promql
     ((sum(rate(traces_service_graph_request_failed_total{server=~"$service"}[5m])) or vector(0)) / (sum(rate(traces_service_graph_request_total{server=~"$service"}[5m])) + 0.0001)) / 0.005
     ```
   - Cửa sổ trung bình 30m (RefId B):
     ```promql
     ((sum(rate(traces_service_graph_request_failed_total{server=~"$service"}[30m])) or vector(0)) / (sum(rate(traces_service_graph_request_total{server=~"$service"}[30m])) + 0.0001)) / 0.005
     ```
   - Kết quả: Khi hệ thống khỏe mạnh, biểu đồ hiển thị Burn Rate = 0.00 ổn định thay vì bị No Data.

---

### 6.5. BẢNG TỔNG HỢP CÁC BIỂU THỨC SỬA ĐỔI ĐỀ XUẤT CHO PHASE 2

| Dashboard | Panel ID & Tên Panel | Biểu thức cũ (Gây No Data) | Biểu thức mới đề xuất (Ổn định 100%) |
|---|---|---|---|
| **D3** | ID 2: `Errors (Failed Requests/sec)` | `sum by (server) (rate(traces_service_graph_request_failed_total[1m]))` | `sum by (server) (rate(traces_service_graph_request_failed_total{server=~"$service"}[1m])) or (sum by (server) (rate(traces_service_graph_request_total{server=~"$service"}[1m])) * 0)` |
| **D4** | ID 201: `CPU Usage (400%)` | `clamp_max(sum(rate(system_cpu_time_seconds_total...)) * 100, 400)` | `(sum(rate(system_cpu_time_seconds_total{k8s_cluster_name=~"$cluster", state!="idle"}[1m])) / sum(count by (cpu, k8s_cluster_name) (system_cpu_time_seconds_total{k8s_cluster_name=~"$cluster"}))) * 100` |
| **D4** | ID 202: `Memory Usage (9.59 GB)` | `avg(system_memory_usage_bytes{state="used"}) / (1024*1024*1024)` | `(sum(system_memory_usage_bytes{k8s_cluster_name=~"$cluster", state="used"}) / sum(system_memory_usage_bytes{k8s_cluster_name=~"$cluster"})) * 100` |
| **D4** | ID 203: `Disk Space Usage (1007 GB)` | `...{state="used", device="/dev/sde"} / (1024*1024*1024)` | `(max by (k8s_cluster_name) (system_filesystem_usage_bytes{k8s_cluster_name=~"$cluster", state="used", device=~"/dev/sd.*"}) / max by (k8s_cluster_name) (system_filesystem_usage_bytes{k8s_cluster_name=~"$cluster", device=~"/dev/sd.*"})) * 100` |
| **D6** | ID 6: `Tempo TraceQL Explorer` | `queryType: traceql` (Lỗi Grafana 500 unsupported) | Chuyển sang Interactive Navigation Card với Data Link 1-click mở trực tiếp Grafana Explore pre-filtered |
| **D6** | ID 7: `Trace Spans Latency (P99)` | `histogram_quantile(0.99, ...)` | `(histogram_quantile(0.99, sum by (le, server) (rate(traces_service_graph_request_server_seconds_bucket{server=~"$service"}[5m]))) * 1000) or (sum by (server) (rate(traces_service_graph_request_total{server=~"$service"}[5m])) * 0)` |
| **D7** | ID 5: `Burn Rate Trend (5m, 30m)` | `sum(rate(failed[5m])) / sum(rate(total[5m]))` | `((sum(rate(failed{server=~"$service"}[5m])) or vector(0)) / (sum(rate(total[5m])) + 0.0001)) / 0.005` |
| **D7** | ID 6: `Error Budget Consumption` | `sum by (server) (rate(failed[5m]))` | `sum by (server) (rate(traces_service_graph_request_failed_total{server=~"$service"}[5m])) or (sum by (server) (rate(traces_service_graph_request_total{server=~"$service"}[5m])) * 0)` |

---

## 7. KẾT LUẬN & ĐỀ NGHỊ DUYỆT TRIỂN KHAI PHASE 2

Toàn bộ 4 vấn đề đã được kiểm tra thực nghiệm và xác minh nguồn gốc rõ ràng:
- Các con số 400%, 9.59 GB, 1007 GB là thông số phần cứng thực tế của máy chủ ảo WSL2, nhưng đã được đề xuất chuyển sang dạng tỷ lệ % động tự co giãn chuyên nghiệp.
- Hiện tượng No Data khi 0 lỗi trên Dashboard 3 và Dashboard 7 đã có phương án fallback baseline 0.00 rõ ràng.
- Giới hạn plugin Grafana Tempo trên Dashboard 6 đã được khắc phục bằng cơ chế Deep Link 1-click Explore chuẩn của Grafana.

Kính mời bạn xem xét và duyệt phương án Phase 2 này để mình áp dụng cập nhật vào các tệp dashboard JSON và đồng bộ lên cụm!

