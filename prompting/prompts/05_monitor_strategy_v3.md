# PHASE 3.6: UNIFIED RESOURCE MONITORING SCHEMAS (WEB APPLICATION & COMPUTE INSTANCE) & JVM RUNTIME COMPLETENESS

Bạn hãy đóng vai trò là một **Principal Observability Architect, Site Reliability Engineer (SRE) và Systems Designer**.

## 1. BỐI CẢNH & MỤC TIÊU

Sau khi hoàn thành Phase 3.5 (nâng cấp `hostmetrics` và 7 Grafana Dashboards theo USE Method & Four Golden Signals), trước khi bước sang Phase 4 (Benchmark & Evaluation), tôi muốn chuẩn hóa **Chiến lược và Đặc tả Giám sát (Resource Monitoring Schemas)** riêng biệt cho từng loại thực thể trong hệ thống.

Mục tiêu là xây dựng một **Chuẩn Chung Thống Nhất (Unified Monitoring Schema)** kết hợp cả 3 góc độ:
1. **Monitoring Blueprint & Dependency Completeness:** Phân tách rõ ràng 3 tầng phụ thuộc (**Application Dependencies**, **System Dependencies**, **Cloud Dependencies**) và phân biệt rõ cơ chế thu thập thực tế (Runtime Telemetry vs. Cloud IMDS/K8s API vs. IaC/OTTL Enrichment).
2. **Telemetry Field Inventory (Data Dictionary):** Từ điển dữ liệu quy định chính xác tên metric, kiểu dữ liệu, đơn vị, nguồn thu thập và câu lệnh PromQL/LogQL chuẩn.
3. **SLI/SLO Contract & Cross-Layer RCA Decision Tree:** Ngưỡng đánh giá sức khỏe và sơ đồ cây chẩn đoán liên kết (Join Keys) từ tầng ứng dụng (Web App) xuống tầng máy chủ vật lý/hệ điều hành (Compute Instance).

Trong giai đoạn này, chúng ta tập trung chuẩn hóa sâu cho **2 loại tài nguyên cốt lõi**:
- **Loại 1: Web Application Resource Schema** (Đại diện: các microservices Java/Tomcat của `TeaStore`).
- **Loại 2: Compute Instance Resource Schema** (Đại diện: các Kubernetes Worker Nodes / Cloud VMs `aws-k3d`, `azure-k3d`, `hub-k3d`).

---

## 2. CÁC NHIỆM VỤ CỤ THỂ CẦN THỰC HIỆN

### NHIỆM VỤ 1: Xây dựng tài liệu đặc tả `docs/schemas/RESOURCE_MONITORING_SCHEMAS.md`
Hãy tạo tệp `docs/schemas/RESOURCE_MONITORING_SCHEMAS.md` trình bày chi tiết, bài bản và khoa học gồm các phần sau:

1. **Tổng quan Kiến trúc Schema & Cơ chế Thu thập 3 Tầng Phụ thuộc (3-Tier Dependency Acquisition Model):**
   - Giải thích rõ làm thế nào hệ thống đảm bảo tính "Đầy đủ (Completeness)" qua 3 chiều: *Identity (Định danh)*, *Health/Performance (USE/RED)*, và *Failure Signals (Tín hiệu lỗi)*.
   - Giải thích rõ cơ chế thu thập Cloud Dependencies trong thực tế so với mô phỏng:
     - *Tier 1 (Basic Host & Cloud Identity):* Thu thập qua Local IMDS (`169.254.169.254`) bằng OTel `resourcedetection` processor (không cần SDK/API key).
     - *Tier 2 (K8s & Workload IAM Identity):* Thu thập qua Kubernetes Downward API & `k8sattributes` processor (ServiceAccount IRSA / Workload Identity annotations).
     - *Tier 3 (Deep Perimeter & Crypto Dependencies - VPC, Subnet, SG, KMS):* Giải thích tại sao trên Cloud thật không gọi Cloud SDK liên tục từ Collector (để tránh Cloud API Rate Limiting/Throttling và chi phí), mà sử dụng **IaC Metadata Injection & OTTL Enrichment** — chính là kiến trúc đang áp dụng trong dự án này.

2. **Đặc tả Schema 01: Web Application Monitoring Schema (`TeaStore Microservices`)** theo cấu trúc 4 Khối (4-Block Unified Structure):
   - **Khối 1 - Dependency Breakdown:**
     - *Application Dependencies:* Upstream/Downstream services (`peer.service`, HTTP, RMI `:1099`, JDBC `:3306`), JVM Runtime (Heap/Non-Heap memory, Garbage Collection, Thread Pool).
     - *System Dependencies:* Container cgroup limits (CPU/Memory requests & limits, OOMKiller exit code 137), Ephemeral TCP sockets, Tomcat file descriptors.
     - *Cloud Dependencies:* Hosting cluster (`k8s_cluster_name`), Cloud region (`cloud.region`), Subnet routing, Cross-Cloud WAN path (`mc-monitoring-net` mTLS 1.3).
   - **Khối 2 - Telemetry Field Inventory (Four Golden Signals / RED + JVM Runtime):**
     - Lập bảng chi tiết (Metric/Signal Name, Category, PromQL/LogQL, Unit, Collector Source) cho: Rate, Errors, Duration (P50/P90/P95/P99), Saturation (JVM Memory Used, JVM GC Duration, Active Threads/Sockets), Distributed Traces và Application Logs.
   - **Khối 3 - SLI/SLO & Health Contract:**
     - Liveness/Readiness probes contract, Availability SLO (`>= 99.5%`), Latency SLO, Error Budget burn rate thresholds.
   - **Khối 4 - Cross-Layer RCA Correlation Tree (Từ Web App xuống Instance):**
     - Sơ đồ luồng quyết định chẩn đoán khi Web App bị lỗi 5xx hoặc tăng vọt Latency P99: Sử dụng khóa liên kết `service.name -> k8s_cluster_name / k8s.node.name` để phân biệt lỗi nội tại của App (JVM Full GC, Exception, Thread Exhaustion) với lỗi của Instance bên dưới (CPU I/O Wait `%wa`, Disk Latency, WAN Packet Drops).

3. **Đặc tả Schema 02: Compute Instance Monitoring Schema (`K8s Node / Cloud VM`)** theo cấu trúc 4 Khối:
   - **Khối 1 - Dependency Breakdown:**
     - *Application Dependencies (Hosted Workloads):* Pods, DaemonSets (`kubelet`, `coredns`, `otel-collector`).
     - *System Dependencies (Linux OS & Kernel Fundamentals):* CPU scheduler, Virtual Memory & Paging (`/proc/meminfo`, `/proc/vmstat`), Storage Block layer & VFS Inodes (`ext4`/`overlayfs`), Linux Network Stack & Traffic Control (`netfilter`, `tc netem`).
     - *Cloud Dependencies:* Compute Instance SKU (`host.type`), VPC/VNet (`network.vpc.id`), Subnet CIDR (`network.subnet.id`), Security Group/NSG, Block Volume (`storage.volume.id`).
   - **Khối 2 - Telemetry Field Inventory (Brendan Gregg's USE Method - Utilization, Saturation, Errors):**
     - Lập bảng chi tiết đầy đủ 3 cột U - S - E cho 4 tài nguyên cốt lõi của Instance: **CPU**, **Memory**, **Disk & Filesystem (bao gồm Inodes)**, và **Network Interface (bao gồm TCP Socket States)**.
   - **Khối 3 - Infrastructure Health Thresholds:**
     - Ngưỡng Warning / Critical cho CPU I/O Wait (`%wa > 10% / 25%`), Load Average (`> CPU cores`), Memory Used (`> 80% / 90%`), Disk/Inode Usage (`> 75% / 90%`), Packet Drops (`> 0`).
   - **Khối 4 - Bottom-Up Impact Analysis Tree (Từ Instance lên Web App):**
     - Sơ đồ phân tích phạm vi ảnh hưởng (Blast Radius) khi một Instance gặp sự cố phần cứng/hạt nhân thì những Web App microservices nào đang chạy trên đó sẽ bị ảnh hưởng.

---

### NHIỆM VỤ 2: Khởi tạo 2 tệp Schema định dạng YAML chuẩn trong `docs/schemas/`
Dựa trên nội dung của Nhiệm vụ 1, hãy tạo 2 file cấu hình Schema định dạng YAML (machine-readable) để làm chuẩn đối chiếu cho Phase 4:
1. `docs/schemas/webapp-monitoring-schema.yaml`
2. `docs/schemas/instance-monitoring-schema.yaml`

Mỗi file YAML cần khai báo rõ ràng các trường: `schema_version`, `resource_type`, `methodology` (`RED_GOLDEN_SIGNALS` / `USE_METHOD`), `identity_attributes`, `dependencies` (`application`, `system`, `cloud`), `telemetry_signals` (`metrics`, `logs`, `traces`), `slo_targets`, và `correlation_keys`.

---

### NHIỆM VỤ 3: Kiểm tra & Bổ sung mảnh ghép JVM Runtime Metrics (Application Dependency) lên `red-metrics.json`
Để đảm bảo `Web Application Schema` thực sự thu thập đầy đủ Application Runtime Dependencies trên thực tế:
1. Kiểm tra xem `opentelemetry-javaagent.jar` (v2.10.0) trên các Pods của TeaStore hiện đã xuất các metrics JVM (ví dụ: `process_runtime_jvm_memory_usage_bytes` / `jvm_memory_used_bytes`, `process_runtime_jvm_threads_count` / `jvm_thread_count`, `process_runtime_jvm_gc_duration_seconds`) sang OTel Collector và Thanos chưa.
   - Hãy kiểm tra cấu hình `CATALINA_OPTS` trong `k8s/base/teastore/` (xem có bị tắt `-Dotel.metrics.exporter=none` không; nếu đang tắt hoặc thiếu thì bật `-Dotel.metrics.exporter=otlp` hoặc kiểm tra tên metric thực tế trong Prometheus/Thanos).
2. Trong `k8s/base/visualization-grafana/dashboards/red-metrics.json`:
   - Bổ sung hoặc nâng cấp 1 Panel hiển thị **Application Runtime Saturation: JVM Memory Heap Usage & Thread Count (or Container Process Memory)** của các microservices TeaStore để hoàn thiện 100% độ phủ Application Dependencies trong thực tế.

---

### NHIỆM VỤ 4: Cập nhật tài liệu tiến độ
- Cập nhật `docs/schemas/README.md` (nếu có) hoặc `docs/progress/00_result_progress.md` và `docs/progress/01_implemetation_issue.md` (ghi nhận dưới mã **INC-P3-16**: *Thiết kế và chuẩn hóa bộ Unified Resource Monitoring Schemas cho Web Application & Compute Instance, đồng bộ hóa mô hình 3 tầng Dependencies*).

---

## 3. QUY TẮC BẮT BUỘC (STRICT RULES)
1. Giữ nguyên tính ổn định của 3 cụm k3d và không làm hỏng các panels đã sửa ở bản Hotfix Schema v39 trước đó (`merge` transformations và Dual Y-Axis).
2. Đảm bảo tất cả các file `.yaml`, `.json`, `.md` tạo mới hoặc cập nhật đều hợp lệ 100% về mặt cú pháp.
3. Không bịa đặt tên metric trong file Schema và Dashboard; phải đối chiếu với đúng tên metric đang có trong cấu hình OTel Collector và Prometheus/Thanos của dự án.