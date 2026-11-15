# Báo Cáo Kỹ Thuật: Rà Soát & Chuẩn Hóa Toàn Diện Codebase Hạ Tầng, Chaos Scripts & 8 Grafana Dashboards (V1)

**Nhánh làm việc:** `feat/integrate-infra-ai-anomaly`  
**Ngày thực hiện:** 15/11/2026  
**Trạng thái:** HOÀN THÀNH (100% Verification Tests PASSED)  
**Phạm vi:** Hạ tầng quan sát (`k8s/`), Chaos testing (`tests/chaos/`), Dashboards Grafana (`k8s/base/visualization-grafana/dashboards/`), Tài liệu (`README.md`).  
**Tuân thủ ranh giới kỹ thuật:** TUYỆT ĐỐI KHÔNG can thiệp vào bất kỳ file code nào thuộc module AI (`ai-engine/`).

---

## 1. TỔNG QUAN VÀ MỤC TIÊU ĐỢT RÀ SOÁT

Đợt rà soát và chuẩn hóa kỹ thuật lần này nhằm mục đích:
1. **Loại bỏ tham chiếu GCP lỗi thời** trong toàn bộ các công cụ tiêm lỗi hỗn loạn (`tests/chaos/`), đưa hệ thống về đúng topo 3 cụm chuẩn:
   - Hub: `hub-k3d` (context: `k3d-hub-k3d`)
   - Spoke AWS: `aws-k3d` (context: `k3d-aws-k3d`)
   - Spoke Azure: `azure-k3d` (context: `k3d-azure-k3d`)
2. **Cơ chế tự động phát hiện context Kubernetes:** Chống lỗi ngắt đột ngột (`context not found`) khi chạy scripts tiêm lỗi trên các môi trường máy trạm hoặc CI/CD khác nhau.
3. **Đồng bộ hóa 2 nhãn định danh chuẩn** (`k8s_cluster_name` và `cloud_provider`) xuyên suốt từ OTel Collector Edge/Gateway đến Prometheus/Thanos.
4. **Vá lỗi hiển thị trên toàn bộ 8 file JSON Grafana Dashboards:**
   - Sửa dứt điểm hiện tượng Tách Dòng (Split Rows) ở các bảng đa cụm thông qua gom nhóm đồng nhất và `merge transformation`.
   - Bổ sung cấu hình trục tung kép (Dual Y-Axis) cho các panel đo lường nhiều đại lượng có thang đo/đơn vị khác biệt.
   - Chuẩn hóa tên metric `system_paging_faults_total` và biến động `$cluster`.
5. **Cập nhật toàn diện `README.md`** để đồng bộ danh mục 8 Dashboards SRE phục vụ nghiệm thu.

---

## 2. CHI TIẾT THỰC THI TỪNG TASK

### TASK 1: Chuẩn hóa các script và manifest trong thư mục `tests/chaos/`

1. **`tests/chaos/run_live.py`:**
   - **Xóa bỏ GCP Delay:** Loại bỏ kịch bản `"gcp_wan_delay": ("gcp", 250)` khỏi cấu trúc `FAULTS`, chỉ giữ lại `azure_wan_delay` (180ms) và `aws_wan_delay` (200ms).
   - **Thêm cơ chế tự động phân giải context (`resolve_context`):**
     - Cho phép nhận tham số dòng lệnh `--hub-context`, `--aws-context`, `--azure-context`.
     - Cho phép đọc biến môi trường `<CLOUD>_CONTEXT` (`HUB_CONTEXT`, `AWS_CONTEXT`, `AZURE_CONTEXT`) hoặc `KUBE_CONTEXT`.
     - Tự động gọi `kubectl config get-contexts -o name` để so khớp danh sách context khả dụng (`k3d-<cluster>-k3d`, `k3d-<cluster>`, `<cluster>-k3d`, `<cluster>`).
     - Tránh hoàn toàn việc hardcode gây dừng chương trình khi context cục bộ có tiền tố khác nhau.
   - **Cập nhật tiền kiểm tra (Preflight check):** Gọi qua context đã được phân giải an toàn thay vì gán cứng `"k3d-hub-k3d"`.

2. **`tests/chaos/run_service_faults.py`:**
   - **Tích hợp `resolve_context` và bộ đệm context (`_CONTEXT_CACHE`):**
     - Cho phép truyền context qua `--aws-context`, `--azure-context`, hoặc `--context`.
     - Hàm `kubectl(cloud, *args)` tự động sử dụng context đã kiểm tra an toàn.
   - **Loại bỏ tham chiếu `gcp:teastore-recommender`:**
     - Tại dòng 286-287, loại bỏ logic `"gcp:teastore-recommender" in cause`, chỉ đánh giá nguyên nhân gốc rễ trên `aws:teastore-recommender` phù hợp với mô hình triển khai thực tế.

3. **`tests/chaos/test_live_evaluation.py`:**
   - Cập nhật kịch bản unit test đánh giá từ `gcp_wan_delay` sang `azure_wan_delay` và cause `[CROSS_CLOUD_WAN_DELAY] aws->azure`.
   - Kết quả kiểm thử: Toàn bộ 4/4 test cases chạy PASS tuyệt đối trong 0.001 giây.

4. **`tests/chaos/README.md`:**
   - Cập nhật số lượng cụm yêu cầu từ 4 cụm về 3 cụm chuẩn (`hub-k3d`, `aws-k3d`, `azure-k3d`).
   - Sửa luồng chạy thực nghiệm loại bỏ GCP, thay bằng Azure delay 180ms / AWS delay 200ms.
   - Chuẩn hóa mô tả mục tiêu CPU JVM tại AWS (`aws:teastore-recommender`).

---

### TASK 2: Đồng bộ cấu hình OpenTelemetry Collector & Prometheus Rules

1. **`k8s/base/otel-collector/edge/02-configmap.yaml` (Spoke Edge Collector):**
   - Trong processor `transform/cluster_id` tại khối `metric_statements`:
     Bổ sung gán tường minh 2 nhãn định danh chuẩn cho mọi metric:
     ```yaml
     - set(attributes["k8s_cluster_name"], "${CLUSTER_NAME}")
     - set(attributes["cloud_provider"], "${CLOUD_PROVIDER}")
     ```
   - Đảm bảo dữ liệu viễn trắc đo được từ Node Spoke (hostmetrics) luôn mang đủ 2 nhãn định danh trước khi đẩy về Hub Gateway.

2. **`k8s/base/otel-collector/gateway/03-configmap.yaml` (Central Hub Gateway):**
   - Trong processor `transform/normalize_cloud` tại khối `metric_statements`:
     Bổ sung gán tường minh:
     ```yaml
     - set(attributes["k8s_cluster_name"], attributes["k8s.cluster.name"])
     - set(attributes["cloud_provider"], attributes["cloud.provider"])
     ```
   - Cùng với tính năng `resource_to_telemetry_conversion: enabled: true` trên Prometheus exporter, mọi số liệu telemetry đẩy vào Thanos TSDB đều mang đủ 2 nhãn chuẩn `k8s_cluster_name` và `cloud_provider`.

3. **`k8s/base/metrics-thanos/01-configmap-prometheus-rules.yaml`:**
   - Cập nhật quy tắc cảnh báo `SpokeClusterHeartbeatAbsent`:
     Thay thế nhãn cũ `cluster="aws-k3d"` sang nhãn chuẩn `k8s_cluster_name="aws-k3d"` và `k8s_cluster_name="azure-k3d"`:
     ```yaml
     - alert: SpokeClusterHeartbeatAbsent
       expr: absent(up{k8s_cluster_name="aws-k3d"} == 1) or absent(up{k8s_cluster_name="azure-k3d"} == 1)
       for: 2m
     ```

4. **Chuẩn hóa metric Paging Faults:**
   - Xác nhận tất cả các dashboard và cấu hình chỉ sử dụng metric chuẩn `system_paging_faults_total` (có hậu tố bộ đếm `_total`), không còn tồn tại dạng viết thiếu cũ.

---

### TASK 3: Rà soát và vá lỗi trên TOÀN BỘ 8 file Grafana Dashboards (`.json`)

#### 3.1. Khắc phục triệt để lỗi Tách Dòng (Split Rows) ở các Bảng Table đa cụm
- **`k8s-infrastructure.json` (`04. Compute & OS Kernel (USE)`) - Panel 8 (`Filesystem Usage (%) & Inode Saturation (%)`):**
  - Đồng nhất gom nhóm ở cả Target A và Target B sang: `by (k8s_cluster_name, cloud_provider, mountpoint)`.
  - Cả 2 target đều thiết lập `"format": "table"`, `"instant": true`.
  - Bổ sung cấu hình override hiển thị cột `cloud_provider` (`displayName: "Cloud Provider"`).
  - Giữ nguyên transformation `merge` ở đầu mảng để gộp dòng chính xác theo cụm và mountpoint.
- **`system-topology.json` (`02. Topology & Cloud Context`) - Panel 6 (`Cluster Node Resource & Network Health Summary Table`):**
  - Đồng nhất gom nhóm ở cả 4 targets A, B, C, D sang: `by (k8s_cluster_name, cloud_provider)`.
  - Cả 4 target đều có `"format": "table"`, `"instant": true`.
  - Bổ sung cấu hình override hiển thị cột `cloud_provider` (`displayName: "Cloud Provider"`).
  - Kết hợp với transformation `merge` sẵn có, bảng hiển thị một dòng duy nhất cho mỗi cụm đám mây với đầy đủ 4 chỉ số CPU, RAM, Network Drops, TCP Sockets.
- **`mc-executive-overview.json` (`01. Executive Overview`) - Panel 7 (`Cloud Cluster Fleet Health Matrix`):**
  - Đã được chuẩn hóa đồng nhất: 4 targets A, B, C, D đều dùng `by (k8s_cluster_name, cloud_provider)`, `"format": "table"`, `"instant": true`, và `transformations: [ { "id": "merge", "options": {} } ]`.

#### 3.2. Cấu hình Trục Tung Kép (Dual Y-Axis) cho các biểu đồ Timeseries
- **`wan-telemetry.json` (`05. Network & WAN Transport`):**
  - **Panel 8 (`Cross-Cluster Packet Rates & TCP Socket Saturation`):**
    - Trục Y trái: Target A đo tốc độ gói tin `rate(system_network_packets_total)` với đơn vị `pps`.
    - Trục Y phải: Cấu hình override cho Target B (`byFrameRefID: "B"`) đo số lượng kết nối TCP (`system_network_connections`) với `custom.axisPlacement: "right"` và đơn vị `short`.
  - **Panel 7 (`Actual Network Packet Drops & Transmission Errors`):**
    - Trục Y trái: Target A đo tỷ lệ rớt gói tin (`rate(system_network_dropped_total)`).
    - Trục Y phải: Cấu hình override cho Target B (`byFrameRefID: "B"`) đo tỷ lệ lỗi truyền tải (`rate(system_network_errors_total)`) với `custom.axisPlacement: "right"`, đơn vị `pps`, màu cố định `red`.
- **`mc-cost-telemetry.json` (`08. Telemetry & Cost Governance`):**
  - **Panel 4 (`Telemetry Ingestion Rate by Multi-Cloud Cluster`):**
    - Trục Y trái: Target A đo tốc độ nạp metric `rate(otelcol_receiver_accepted_metric_points)` đơn vị `pps`.
    - Trục Y phải: Cấu hình override cho Target B (`byFrameRefID: "B"`) đo tốc độ nạp log records `rate(otelcol_receiver_accepted_log_records)` với `custom.axisPlacement: "right"`, đơn vị `logs/s`, màu cố định `green`.
- **`k8s-infrastructure.json` (`04. Compute & OS Kernel (USE)`):**
  - **Panel 5 (`Memory Swap & Paging Activity`):**
    - Trục Y trái: Target A đo tần suất thao tác paging `system_paging_operations_total` đơn vị `ops`.
    - Trục Y phải: Cấu hình override cho Target B (`byFrameRefID: "B"`) đo tỷ lệ lỗi trang `system_paging_faults_total` với `custom.axisPlacement: "right"`, đơn vị `faults/s`, màu cố định `orange`.
- **Bảo toàn các Panels đã có Dual Y-Axis hoàn chỉnh:**
  - `red-metrics.json`: Panel 4 (CPU wait % vs Active sockets), Panel 5 (DB Latency ms vs Errors req/s), Panel 6 (Heap MB vs Threads & GC pause ms), Panel 7 (AIOps Likelihood % vs Latency RCA ms).
  - `k8s-infrastructure.json`: Panel 6 (Throughput Bps vs IOPS), Panel 7 (Latency ms vs Queue), Panel 9 (Traffic Bps vs Packet rate).
  - `mc-cost-telemetry.json`: Panel 8 (Memory RSS bytes vs Dropped Points/s).

#### 3.3. Kiểm tra biến động Dashboard (Variables)
- Toàn bộ 8 dashboards đều truy vấn biến `$cluster` bằng câu truy vấn Prometheus chuẩn:
  `label_values(system_cpu_time_seconds_total, k8s_cluster_name)`
- Không có bất kỳ biến hay query nào dùng cú pháp lỗi thời `{cluster=...}`.

---

### TASK 4: Cập nhật tài liệu `README.md`

1. Cập nhật bảng tổng hợp công nghệ tại Mục 2: Cập nhật mô tả Grafana lên **8 bộ Dashboard SRE chuyên biệt**.
2. Cập nhật bảng ma trận truy cập Web GUI tại Mục 5: Bổ sung mô tả chi tiết cho **8 Dashboard SRE chuẩn hóa**.
3. Bổ sung Mục chi tiết mới **5.1. Danh Mục 8 Grafana Dashboards SRE**:
   - `01. Executive Overview` (`mc-executive-overview.json`): Tổng quan hạm đội đa đám mây, độ trễ liên vùng WAN, ma trận sức khỏe cụm (Merge transformation).
   - `02. Topology & Cloud Context` (`system-topology.json`): Định tuyến L3/L4 subnet liên đám mây, kiểm kê 6 trục phụ thuộc đám mây sâu 360°, bảng tổng hợp Node & Kernel theo cụm.
   - `03. Application & JVM (RED)` (`red-metrics.json`): RED metrics (Rate, Errors, Duration), Call latency & errors tầng DB/RMI, bão hòa JVM runtime, phân rã RCA dấu vết AIOps ($T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$).
   - `04. Compute & OS Kernel (USE)` (`k8s-infrastructure.json`): 3 Gauge cấp phát tài nguyên (CPU 400%, RAM 9.59 GB, Disk 1007 GB), USE Method cho CPU, RAM, Paging (Dual Y-axis), Disk (Dual Y-axis), Filesystem & Inode Table, TCP State.
   - `05. Network & WAN Transport` (`wan-telemetry.json`): Độ trễ WAN (P50/P95), băng thông mạng cầu `mc-monitoring-net`, Packet Drops vs Errors (Dual Y-axis), Packet Rates vs Active Sockets (Dual Y-axis).
   - `06. Logs, Traces & Database` (`logs-traces-deepdive.json`): Khối lượng log stream theo dịch vụ, Warning/Error log rate, Anomaly logs, Trace Spans Latency distribution (P99/P90/P50), liên kết Trace-to-Loki LogQL.
   - `07. SLO & Error Budget` (`slo-governance.json`): Tỷ lệ sẵn sàng SLI vs SLO 99.5%, Remaining Error Budget %, Multi-Window Burn Rate Trend (5m vs 30m), phân bổ tiêu thụ ngân sách lỗi.
   - `08. Telemetry & Cost Governance` (`mc-cost-telemetry.json`): FinOps viễn trắc, tốc độ nạp Metrics vs Logs (Dual Y-axis), Thác nước lọc nhiễu Edge Spoke & Tail-sampling Hub Gateway, Top 10 High-Cardinality Metrics, Collector buffer health.
4. Cập nhật Mục 6: Bổ sung ghi chú về cơ chế tự động phân giải context an toàn (`kubectl config get-contexts -o name`) trong kịch bản tiêm lỗi hỗn loạn.

---

## 3. DANH SÁCH CÁC FILE ĐÃ CHỈNH SỬA

| STT | Đường dẫn File | Loại thay đổi | Nội dung chính |
|---|---|---|---|
| 1 | `tests/chaos/run_live.py` | Python Script | Bỏ `gcp_wan_delay`, thêm `resolve_context()` tự động phát hiện kube-context, nhận CLI `--hub-context/--aws-context/--azure-context`. |
| 2 | `tests/chaos/run_service_faults.py` | Python Script | Tích hợp `resolve_context()`, bỏ logic RCA tham chiếu cứng `gcp:teastore-recommender`. |
| 3 | `tests/chaos/test_live_evaluation.py` | Unit Test | Thay `gcp_wan_delay` bằng `azure_wan_delay`, cập nhật cause kỳ vọng `aws->azure`. |
| 4 | `tests/chaos/README.md` | Tài liệu | Cập nhật 3 cụm k3d, bỏ các kịch bản và thông số liên quan đến GCP. |
| 5 | `k8s/base/otel-collector/edge/02-configmap.yaml` | K8s Manifest | Gán tường minh `k8s_cluster_name` và `cloud_provider` trong processor `transform/cluster_id` cho metric. |
| 6 | `k8s/base/otel-collector/gateway/03-configmap.yaml` | K8s Manifest | Gán tường minh `k8s_cluster_name` và `cloud_provider` trong processor `transform/normalize_cloud` cho metric. |
| 7 | `k8s/base/metrics-thanos/01-configmap-prometheus-rules.yaml` | K8s Manifest | Thay `cluster="aws-k3d"` sang `k8s_cluster_name="aws-k3d"` trong rule `SpokeClusterHeartbeatAbsent`. |
| 8 | `k8s/base/visualization-grafana/dashboards/k8s-infrastructure.json` | Grafana JSON | Panel 8 Table gom nhóm `by (k8s_cluster_name, cloud_provider, mountpoint)`, Panel 5 Timeseries thêm Dual Y-Axis (`faults/s`). |
| 9 | `k8s/base/visualization-grafana/dashboards/system-topology.json` | Grafana JSON | Panel 6 Table gom nhóm `by (k8s_cluster_name, cloud_provider)` + override hiển thị cột Cloud Provider. |
| 10 | `k8s/base/visualization-grafana/dashboards/wan-telemetry.json` | Grafana JSON | Panel 8 Timeseries thêm Dual Y-Axis (`short` Sockets vs `pps` Packets), Panel 7 thêm Dual Y-Axis (`pps` Errors vs Drops). |
| 11 | `k8s/base/visualization-grafana/dashboards/mc-cost-telemetry.json` | Grafana JSON | Panel 4 Timeseries thêm Dual Y-Axis (`logs/s` Logs vs `pps` Metrics). |
| 12 | `README.md` | Tài liệu chính | Bổ sung đầy đủ thông tin chi tiết về 8 Dashboards SRE SRE và chuẩn hóa context tiêm lỗi. |

---

## 4. BẰNG CHỨNG KIỂM ĐỊNH (VERIFICATION EVIDENCE)

Toàn bộ các lệnh kiểm định tự động đã được thực thi và xác nhận thành công 100%:

### 4.1. Kiểm thử Unit Test bộ đánh giá Chaos Testing (`make test-ai`)
```bash
--> Running AI Anomaly Detection Engine test suite...
python3 -m unittest tests/chaos/test_live_evaluation.py
....
----------------------------------------------------------------------
Ran 4 tests in 0.001s

OK
```

### 4.2. Kiểm thử tính hợp lệ cú pháp của 8 file Dashboards JSON (`make validate-dashboards`)
```bash
--> Validating all 8 Grafana Dashboards JSON syntax...
All 8 Grafana Dashboards are 100% valid JSON!
```
Chi tiết kiểm tra cả 8 file:
- `k8s/base/visualization-grafana/dashboards/mc-executive-overview.json`: VALID JSON
- `k8s/base/visualization-grafana/dashboards/system-topology.json`: VALID JSON
- `k8s/base/visualization-grafana/dashboards/red-metrics.json`: VALID JSON
- `k8s/base/visualization-grafana/dashboards/k8s-infrastructure.json`: VALID JSON
- `k8s/base/visualization-grafana/dashboards/wan-telemetry.json`: VALID JSON
- `k8s/base/visualization-grafana/dashboards/logs-traces-deepdive.json`: VALID JSON
- `k8s/base/visualization-grafana/dashboards/slo-governance.json`: VALID JSON
- `k8s/base/visualization-grafana/dashboards/mc-cost-telemetry.json`: VALID JSON

### 4.3. Kiểm thử Dry-run Kustomize Build 3 cụm (`make validate-kustomize`)
```bash
--> Dry-run validating Kustomize manifests for all 3 clusters...
All Kustomize manifests build successfully!
```

### 4.4. Kiểm thử tổng hợp toàn hệ thống (`make test`)
```bash
--> Running AI Anomaly Detection Engine test suite...
python3 -m unittest tests/chaos/test_live_evaluation.py
....
----------------------------------------------------------------------
Ran 4 tests in 0.001s

OK
--> Validating all 8 Grafana Dashboards JSON syntax...
All 8 Grafana Dashboards are 100% valid JSON!
--> Dry-run validating Kustomize manifests for all 3 clusters...
All Kustomize manifests build successfully!
All automated system verification tests PASSED!
```

### 4.5. Xác nhận tính nguyên vẹn của module AI (`ai-engine/`)
```bash
$ git status -s ai-engine
# Kết quả rỗng: 0 file bị thay đổi trong ai-engine/
```

---

## 5. KẾT LUẬN

Hệ thống đã được chuẩn hóa đồng bộ, nhất quán và sạch sẽ trên toàn bộ 4 khu vực yêu cầu. Mọi lỗi tách dòng trên bảng thống kê đa cụm và các biểu đồ đa đơn vị đo lường đều đã được xử lý triệt để mà không phá vỡ hay ảnh hưởng đến bất kỳ thành phần nào của module AI Anomaly Detection. Hệ thống sẵn sàng cho các bài kiểm chuẩn tải và nghiệm thu đề tài.
