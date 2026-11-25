# Sổ Tay Vận Hành & Hướng Dẫn Xử Lý Sự Cố (Runbooks Overview)

> **LƯU Ý:** Hệ thống đã được nâng cấp sang mô hình sổ tay vận hành dạng mô-đun (Modular SRE Runbooks) theo chuẩn Google SRE.  
> Chi tiết từng kịch bản xử lý chuyên sâu được tổ chức độc lập trong thư mục [docs/runbooks/](./runbooks/README.md):
> - [RB-01: Spoke WAN Latency High](./runbooks/runbook-01-spoke-wan-latency-high.md)
> - [RB-02: Cross Cluster Trace Broken](./runbooks/runbook-02-cross-cluster-trace-broken.md)
> - [RB-03: Thanos Compact Halted](./runbooks/runbook-03-thanos-compact-halted.md)
> - [RB-04: Prometheus Scrape Failed](./runbooks/runbook-04-prometheus-scrape-failed.md)
> - [RB-05: OTel Collector Memory Pressure](./runbooks/runbook-05-otel-collector-memory-pressure.md)
> - [RB-06: AI Anomaly Inference Down](./runbooks/runbook-06-ai-anomaly-inference-down.md)
> - [RB-07: TeaStore Database Latency](./runbooks/runbook-07-teastore-database-latency.md)

---

## Mục Lục Tổng Quan Sự Cố (Quick Triage Reference)

- [1. SpokePodCrashLooping](#1-spokepodcrashlooping)
- [2. SpokeClusterHeartbeatAbsent](#2-spokeclusterheartbeatabsent)
- [3. CrossCloudWANLatencyDegraded](#3-crosscloudwanlatencydegraded)
- [4. MicroserviceHighErrorRate](#4-microservicehigherrorrate)
- [5. OtelCollectorMemoryHigh](#5-otelcollectormemoryhigh)
- [6. AIOpsAnomalyDetected](#6-aiopsanomalydetected)
- [7. ErrorBudgetBurn (Pyrra SLO)](#7-errorbudgetburn-pyrra-slo)
- [8. ThanosStorageFailure / MinIO AccessDenied](#8-thanosstoragefailure--minio-accessdenied)
- [9. mTLS 1.3 Handshake Failure](#9-mtls-13-handshake-failure)
- [10. Quy Trình Khởi Động & Khôi Phục Toàn Cụm (Disaster Recovery)](#10-quy-trình-khởi-động--khôi-phục-toàn-cụm-disaster-recovery)

---

## 1. SpokePodCrashLooping

* **Mức độ:** `critical` (Khẩn cấp, tác động trực tiếp đến dịch vụ TeaStore).
* **Ý nghĩa:** Container ứng dụng trên `aws-k3d` hoặc `azure-k3d` bị khởi động lại liên tục do lỗi ứng dụng (Java Exception) hoặc bị nhân Linux ép dừng do tràn bộ nhớ (`OOMKilled`).

### Kiểm tra:
1. Xác định Pod nào đang gặp sự cố:
   ```bash
   kubectl --context k3d-aws-k3d get pods -n teastore
   kubectl --context k3d-azure-k3d get pods -n teastore
   ```
2. Kiểm tra lý do dừng gần nhất (Exit Code & Terminated Reason):
   ```bash
   kubectl --context k3d-aws-k3d describe pod <pod-name> -n teastore | grep -A 5 "Last State"
   ```
3. Xem 50 dòng log cuối cùng trước khi crash (hoặc xem trong tin nhắn Robusta gửi về Telegram):
   ```bash
   kubectl --context k3d-aws-k3d logs <pod-name> -n teastore --previous --tail=50
   ```

### Làm gì:
- **Nếu `Reason: OOMKilled` (Exit Code 137):**
  - Tăng giới hạn RAM cho Pod trong Kustomize overlay tương ứng (`deploy/clusters/<spoke>/patches/`).
  - Kiểm tra xem Java Heap có bị leak bởi `FaultAgent` không:
    ```bash
    kubectl --context k3d-aws-k3d exec -it <pod-name> -n teastore -- jcmd 1 GC.heap_info
    ```
- **Nếu `Reason: Error` (CrashLoop do Database):**
  - Xem chi tiết tại [Runbook 07: TeaStore Database Latency](./runbooks/runbook-07-teastore-database-latency.md).
  - Kiểm tra cơ sở dữ liệu MySQL trên `azure-k3d`:
    ```bash
    kubectl --context k3d-azure-k3d get pods -l app=teastore-db -n teastore
    ```

---

## 2. SpokeClusterHeartbeatAbsent

* **Mức độ:** `critical` (Đứt gãy đường ống viễn trắc đa đám mây).
* **Ý nghĩa:** Central Hub không nhận được tín hiệu nhịp tim (`up == 1`) từ cụm `aws-k3d` hoặc `azure-k3d` trong hơn 120 giây. Xem thêm [Runbook 04: Prometheus Scrape Failed](./runbooks/runbook-04-prometheus-scrape-failed.md).

### Kiểm tra:
1. Kiểm tra trạng thái OTel Edge Collector trên Spoke:
   ```bash
   kubectl --context k3d-aws-k3d get pods -l app=otel-collector -n monitoring
   kubectl --context k3d-azure-k3d get pods -l app=otel-collector -n monitoring
   ```
2. Kiểm tra kết nối mạng giữa Spoke và Hub Gateway:
   ```bash
   docker exec -it k3d-aws-k3d-server-0 ping -c 3 172.28.0.2
   ```
3. Kiểm tra log của Hub Gateway xem có từ chối kết nối mTLS không:
   ```bash
   kubectl --context k3d-hub-k3d logs -l app=otel-gateway -n monitoring --tail=100 | grep -i "tls"
   ```

### Làm gì:
- Nếu OTel Edge Collector bị crash: `kubectl --context k3d-<spoke> rollout restart deployment/otel-collector-spoke -n monitoring`.
- Nếu mạng Docker bị lỗi hoặc mất DNS hosts: Chạy lệnh đồng bộ lại mạng từ Python Platform CLI:
  ```bash
  python -m infra.cli sync-hosts
  ```

---

## 3. CrossCloudWANLatencyDegraded

* **Mức độ:** `high` (Độ trễ liên vùng suy giảm nghiêm trọng).
* **Ý nghĩa:** Độ trễ P99 của các cuộc gọi liên đám mây vượt ngưỡng **1500ms** trong 2 phút liên tiếp. Chi tiết xem tại [Runbook 01: Spoke WAN Latency High](./runbooks/runbook-01-spoke-wan-latency-high.md).

### Kiểm tra:
1. Xem biểu đồ độ trễ liên cụm trên Grafana Dashboard 01 (Multi-Cloud Overview).
2. Kiểm tra cấu hình suy hao `tc netem` trên container Spoke:
   ```bash
   docker exec -it k3d-aws-k3d-server-0 tc qdisc show dev eth0
   ```
3. Kiểm tra xem có kịch bản Chaos tiêm chậm trễ WAN đang chạy không:
   ```bash
   ps aux | grep -i "run_service_faults.py"
   ```

### Làm gì:
- Nếu do tiêm lỗi thực nghiệm: Dừng kịch bản tiêm lỗi `python tests/chaos/run_service_faults.py --cleanup` (hoặc `python -m infra.cli wan --reset`).
- Khôi phục tham số suy hao WAN về trạng thái chuẩn ($10\text{ ms} \pm 2\text{ ms}$):
  ```bash
  python -m infra.cli wan --latency 10ms --jitter 2ms --loss 0.1%
  ```

---

## 4. MicroserviceHighErrorRate

* **Mức độ:** `high` (Tỷ lệ lỗi vượt chuẩn).
* **Ý nghĩa:** Tỷ lệ mã lỗi HTTP 5xx trên đồ thị liên kết dịch vụ vượt quá **5%** trong 2 phút. Xem thêm [Runbook 07: TeaStore Database Latency](./runbooks/runbook-07-teastore-database-latency.md).

### Kiểm tra:
1. Mở Grafana Dashboard 03 (Application RED Metrics) để xác định dịch vụ phát sinh lỗi.
2. Truy vấn vết lỗi (Error Traces) trên Grafana Tempo:
   - Filter: `status = error` và `duration > 1s`.
3. Kiểm tra log tập trung qua Grafana Loki:
   ```logql
   {namespace="teastore"} |= "ERROR" or |= "Exception"
   ```

### Làm gì:
- Nếu lỗi do `teastore-persistence` không kết nối được MySQL:
  ```bash
  kubectl --context k3d-azure-k3d logs -l app=teastore-persistence -n teastore --tail=50
  ```
- Khởi động lại dịch vụ lỗi:
  ```bash
  kubectl --context k3d-<cluster> rollout restart deployment/<service-name> -n teastore
  ```

---

## 5. OtelCollectorMemoryHigh

* **Mức độ:** `warning` (Nguy cơ tràn bộ nhớ Collector).
* **Ý nghĩa:** Bộ nhớ Resident Set (RSS) của OTel Collector vượt quá **400MB**. Xem chi tiết xử lý tại [Runbook 05: OTel Collector Memory Pressure](./runbooks/runbook-05-otel-collector-memory-pressure.md).

### Kiểm tra:
1. Kiểm tra mức tiêu thụ RAM của Collector:
   ```bash
   kubectl --context k3d-hub-k3d top pod -l app=otel-gateway -n monitoring
   ```
2. Kiểm tra log xem `memory_limiter` đã kích hoạt cơ chế drop dữ liệu chưa:
   ```bash
   kubectl --context k3d-hub-k3d logs -l app=otel-gateway -n monitoring | grep -i "memory_limiter"
   ```

### Làm gì:
- Tăng tỷ lệ lọc tại biên: Kiểm tra cấu hình `filter/drop_noise` tại Spoke Collector để bảo đảm loại bỏ các endpoint `/healthz`, `/readyz`.
- Giảm tỷ lệ lấy mẫu vết (Trace Sampling Rate): Tạm thời điều chỉnh head-based sampling từ `20%` xuống `10%` trong ConfigMap của Spoke Collector nếu tải đang quá cao.

---

## 6. AIOpsAnomalyDetected

* **Mức độ:** `critical` (AI phát hiện bất thường hệ thống).
* **Ý nghĩa:** Bộ học sâu kết hợp (GRU + TCN + Isolation Forest) phát hiện xác suất bất thường vượt mốc **80%** kết hợp Tempo Trace RCA phân tích suy thoái do WAN ($T_{\text{WAN}}$), Ứng dụng ($T_{\text{self}}$) hoặc Database ($T_{\text{DB}}$). Chi tiết xem tại [Runbook 06: AI Anomaly Inference Down](./runbooks/runbook-06-ai-anomaly-inference-down.md).

### Kiểm tra:
1. Đọc tin nhắn cảnh báo trên Telegram: Xác định chỉ số đóng góp lớn nhất (Top Contributing Feature) và loại sự cố (ví dụ: `[CROSS_CLOUD_WAN_DELAY]` hoặc `[DATABASE_LATENCY_SPIKE]`).
2. Mở Grafana Dashboard 03 Panel 7 Dual Y-Axis so sánh giữa Anomaly Score và ngưỡng kích hoạt.
3. Kiểm tra tiến trình AI Detector trên máy chủ:
   ```bash
   ps aux | grep -i "detector.py"
   tail -n 50 /tmp/ai_detector.log
   ```

### Làm gì:
- Đối chiếu với kịch bản kiểm thử: Kiểm tra xem có đang chạy tải đột biến Locust (`locustfile.py`) hoặc kịch bản tiêm lỗi không.
- Nếu là sự cố thật: Xem thành phần phân tích RCA ($T_{\text{DB}}$ hay $T_{\text{WAN}}$) để can thiệp đúng tầng.

---

## 7. ErrorBudgetBurn (Pyrra SLO)

* **Mức độ:** `high` (Đang bào mòn ngân sách lỗi SLO).
* **Ý nghĩa:** Pyrra tính toán tốc độ tiêu hao ngân sách lỗi (Error Budget Burn Rate) của TeaStore vượt ngưỡng cho phép (tốc độ tiêu hao cạn budget trong 1 giờ hoặc 6 giờ).

### Kiểm tra:
1. Truy cập giao diện Pyrra (`http://localhost:9099`).
2. Xem tỷ lệ lỗi thành công/thất bại và số lượng request vi phạm.

### Làm gì:
- Kích hoạt quy trình đóng băng phát hành (Freeze Release) nếu đang chạy thử nghiệm canary.
- Kiểm tra các commit cấu hình gần nhất trên Git để xác định nguyên nhân gây lỗi.

---

## 8. ThanosStorageFailure / MinIO AccessDenied

* **Mức độ:** `critical` (Tê liệt lưu trữ dài hạn).
* **Ý nghĩa:** Thanos Sidecar/Receive không thể tải nén các khối TSDB lên MinIO S3 bucket, trả về mã lỗi `403 AccessDenied`. Chi tiết xem tại [Runbook 03: Thanos Compact Halted](./runbooks/runbook-03-thanos-compact-halted.md).

### Kiểm tra:
1. Kiểm tra log của Thanos Sidecar:
   ```bash
   kubectl --context k3d-hub-k3d logs -l app.kubernetes.io/component=sidecar -n monitoring | grep -i "accessdenied"
   ```
2. Kiểm tra mật khẩu MinIO trong Secret K8s:
   ```bash
   kubectl --context k3d-hub-k3d get secret thanos-s3-creds -n monitoring -o yaml
   ```

### Làm gì:
- Đồng bộ lại mật khẩu MinIO từ `.env`:
  ```bash
  make sync-secrets
  kubectl --context k3d-hub-k3d rollout restart statefulset/prometheus-server -n monitoring
  ```

---

## 9. mTLS 1.3 Handshake Failure

* **Mức độ:** `high` (Đứt gãy liên lạc bảo mật).
* **Ý nghĩa:** OTel Collector tại Spoke bị từ chối kết nối vào Hub OTel Gateway do chứng chỉ hết hạn, sai tên định danh (SAN mismatch) hoặc không cùng Root CA. Chi tiết xem tại [Runbook 02: Cross Cluster Trace Broken](./runbooks/runbook-02-cross-cluster-trace-broken.md).

### Kiểm tra:
1. Kiểm tra trạng thái Certificate của `cert-manager` trên cụm Hub:
   ```bash
   kubectl --context k3d-hub-k3d get certificates -n monitoring
   ```
2. Kiểm tra log bắt tay TLS trên Hub Gateway:
   ```bash
   kubectl --context k3d-hub-k3d logs -l app=otel-collector-hub -n monitoring | grep -i "bad certificate"
   ```

### Làm gì:
- Sinh mới và đồng bộ lại chứng chỉ in-cluster qua `cert-manager`:
  ```bash
  python -m infra.cli certs
  ```

---

## 10. Quy Trình Khởi Động & Khôi Phục Toàn Cụm (Disaster Recovery)

Nếu môi trường máy trạm bị tắt đột ngột hoặc Docker bị restart, thực hiện quy trình khôi phục chuẩn theo 4 bước:

```bash
# Bước 1: Khởi động lại 3 cụm k3d
k3d cluster start hub-k3d
k3d cluster start aws-k3d
k3d cluster start azure-k3d

# Bước 2: Tái thiết lập suy hao mạng WAN qua Python Platform CLI
python -m infra.cli wan --latency 10ms --jitter 2ms --loss 0.1%

# Bước 3: Kiểm tra sức khỏe toàn bộ Pods trên 3 cụm
make verify

# Bước 4: Khởi động lại động cơ suy luận AI (nếu chạy dưới dạng host daemon)
nohup python3 ai-engine/inference/detector.py > /tmp/ai_detector.log 2>&1 &
```
