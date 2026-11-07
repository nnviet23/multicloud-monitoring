# PHASE 3.5: FULL-STACK INFRASTRUCTURE OBSERVABILITY & GRAFANA DASHBOARDS UPGRADE (OS, KERNEL, STORAGE, L3/L4 NETWORK & CLOUD CONTEXT)

Bạn hãy đóng vai trò là một **Senior Site Reliability Engineer (SRE), Linux Kernel & Systems Performance Specialist, OpenTelemetry Architect và Grafana Visualization Expert**.

## 1. BỐI CẢNH & VẤN ĐỀ HIỆN TẠI

Hiện tại, dự án **Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)** đã triển khai hoạt động ổn định 3 cụm k3d (`hub-k3d`, `aws-k3d`, `azure-k3d`) và bộ 7 Grafana Dashboards trong `k8s/base/visualization-grafana/dashboards/`.

Tuy nhiên, qua rà soát kỹ thuật (Technical Review), hệ thống giám sát tài nguyên và bộ Grafana Dashboards hiện đang mắc phải sự mất cân bằng nghiêm trọng:
1. **Quá thiên lệch về Static Cloud Dependencies:** Tập trung quá nhiều vào việc gán tĩnh các nhãn `vpc-id`, `subnet`, `iam-role-arn` qua chuỗi 14 hàm `label_replace` phức tạp trong PromQL, thậm chí một số nhãn như `"secondaryStat", "Health: 100% | P95: 12ms"` trong `system-topology.json` đang bị hardcode dạng chuỗi tĩnh thay vì phản ánh số liệu đo lường thực tế.
2. **Thiếu chiều sâu về Hệ điều hành (Linux OS/Kernel), Lưu trữ (Disk/Filesystem) và Mạng L3/L4 theo chuẩn USE Method (Utilization, Saturation, Errors):**
   - Trong `k8s-infrastructure.json` (hiện chỉ có 4 panels sơ sài): Chưa tách biệt được **CPU I/O Wait (`%wa`)** để chẩn đoán nghẽn đĩa, thiếu **System Load Average (1m, 5m, 15m)**, thiếu hoàn toàn **Disk IOPS, Disk Throughput, Disk Latency / Pending Operations**, thiếu **Filesystem Capacity (`df -h`)**, **Inode Exhaustion (`df -i`)**, và **Memory Paging / Page Faults (`vmstat`)**.
   - Trong `wan-telemetry.json`: Đang dùng `vector(10.0)`, `vector(2.0)`, `vector(0.1)` tĩnh cho 3 panel đầu mà thiếu các panel đo lường **Packet Drops thực tế (`system_network_dropped_total`)**, **Network Errors (`system_network_errors_total`)** và tương quan trạng thái **TCP Sockets (`ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`)** xuyên cụm.
   - Trong `red-metrics.json`: Mới chỉ có Rate, Errors, Duration (3 panels), thiếu tín hiệu vàng thứ 4 là **Saturation** (mức độ bão hòa tài nguyên/hàng đợi của các dịch vụ).
   - Trong `logs-traces-deepdive.json`: Thiếu panel chuyên biệt lọc các sự kiện lỗi tầng Hệ thống, Cơ sở dữ liệu và Hạ tầng (OOM, I/O errors, Aborted connections, Timeout) và bảng tra cứu nhanh Trace ID / Log tương quan.

Tôi đã cập nhật tài liệu định hướng chiến lược tại `docs/progress/03_resource_monitor.md` (phiên bản Balanced Full-Stack SRE & USE Method).

---

## 2. MỤC TIÊU NHIỆM VỤ CỦA BẠN

Hãy đọc kỹ `docs/progress/03_resource_monitor.md` cùng các file cấu hình hiện tại trong `k8s/base/otel-collector/` và `k8s/base/visualization-grafana/dashboards/`, sau đó thực hiện nâng cấp đồng bộ từ tầng thu thập (OTel Collector) lên tầng hiển thị (Grafana Dashboards) theo 4 nhiệm vụ dưới đây:

### NHIỆM VỤ 1: Kiểm tra và đảm bảo độ phủ của `hostmetrics` tại OTel Collector (Edge & Hub)
Kiểm tra `k8s/base/otel-collector/edge/02-configmap.yaml` (và cấu hình scrape tại Hub nếu có):
1. Đảm bảo receiver `hostmetrics` đã kích hoạt đầy đủ 7 scrapers cốt lõi để thu thập chỉ số Linux OS/Kernel/Network:
   - `cpu` (thu thập `system.cpu.time` với đầy đủ các state: `user`, `system`, `wait`, `idle`, `interrupt`, `steal`).
   - `load` (thu thập `system.cpu.load_average.1m`, `5m`, `15m`).
   - `memory` (thu thập `system.memory.usage` với `used`, `free`, `buffered`, `cached`, `slab_reclaimable`).
   - `paging` (thu thập `system.paging.operations` và `system.paging.usage` để giám sát page faults/swap).
   - `disk` (thu thập `system.disk.io`, `system.disk.operations`, `system.disk.operation_time`, `system.disk.pending_operations`).
   - `filesystem` (thu thập `system.filesystem.usage` và `system.filesystem.inodes.usage`).
   - `network` (thu thập `system.network.io`, `system.network.packets`, `system.network.errors`, `system.network.dropped`, `system.network.connections`).
2. Giữ nguyên các thuộc tính chuẩn hóa cụm (`k8s_cluster_name`, `cloud_provider`, `cloud_region`) để mọi metric hệ thống xuất sang Prometheus/Thanos đều lọc được theo cả 3 cụm (`aws-k3d`, `azure-k3d`, `hub-k3d`).

---

### NHIỆM VỤ 2: Nâng cấp toàn diện 7 Grafana Dashboards trong `k8s/base/visualization-grafana/dashboards/`

Hãy sửa đổi các file JSON dashboard hiện tại theo chuẩn SRE & USE Method (giữ nguyên `uid` và `datasource` `thanos-query-ds` / `loki-ds` / `tempo-ds` để không làm gãy cấu hình):

#### 1. `k8s-infrastructure.json` (`uid: mc-k8s-infrastructure`) — Nâng cấp từ 4 lên 10 Panels chuyên sâu (Linux SRE & USE Method):
- **Row 1 - Compute, Load & CPU I/O Wait:**
  - *Panel 1 (Timeseries):* **CPU Utilization by State (User vs System vs Kernel)** (`rate(system_cpu_time_seconds_total{state!="idle"}[1m])` theo cụm).
  - *Panel 2 (Timeseries - Highlighted):* **CPU I/O Wait (`%wa`) Bottleneck Detector** — Biểu diễn riêng `sum by (k8s_cluster_name) (rate(system_cpu_time_seconds_total{state="wait"}[1m]))` để phát hiện tức thì khi CPU bị nghẽn do chờ đọc/ghi đĩa (MySQL/MinIO).
  - *Panel 3 (Timeseries):* **System Load Average (1m, 5m, 15m)** (`system_cpu_load_average_1m`, `5m`, `15m` theo cụm) để đối chiếu High Load vs Low CPU.
- **Row 2 - Memory, Caching & Paging Saturation:**
  - *Panel 4 (Timeseries):* **System Memory Breakdown (Used, Cached, Buffered, Free)** (`system_memory_usage_bytes` theo `k8s_cluster_name` và `state`).
  - *Panel 5 (Timeseries):* **Memory Saturation: Paging & Page Faults Rate (`vmstat` equivalent)** (`sum by (k8s_cluster_name, type, direction) (rate(system_paging_operations_total[1m]))`).
- **Row 3 - Disk I/O Performance & Filesystem Health (`iostat`, `df -h`, `df -i`):**
  - *Panel 6 (Timeseries):* **Disk Read/Write Throughput (MB/s) & IOPS** (`rate(system_disk_io_bytes_total[1m])` và `rate(system_disk_operations_total[1m])`).
  - *Panel 7 (Timeseries):* **Disk I/O Saturation & Latency (Operation Time & Pending Queue)** (`rate(system_disk_operation_time_seconds_total[1m])` và `system_disk_pending_operations`).
  - *Panel 8 (Timeseries / Gauge):* **Filesystem Capacity (`df -h`) & Inode Utilization (`df -i`)** (`system_filesystem_usage_bytes` và `system_filesystem_inodes_usage` theo cụm).
- **Row 4 - Host Network Stack & Socket States (`ip -s`, `ss -tan`):**
  - *Panel 9 (Timeseries):* **Network Traffic Throughput (RX/TX Bps)** (`rate(system_network_io_bytes_total[1m])`).
  - *Panel 10 (Timeseries):* **TCP Socket Connection States (`ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`)** (`sum by (k8s_cluster_name, state) (system_network_connections{protocol="tcp"})`).

#### 2. `wan-telemetry.json` (`uid: mc-wan-telemetry`) — Bổ sung số liệu L3/L4 thực tế thay vì chỉ dùng hằng số:
- Giữ các chỉ số mục tiêu cấu hình `tc netem` để tham chiếu, nhưng bổ sung/nâng cấp thành **8 Panels**:
  - Bổ sung *Panel:* **Actual Network Packet Drops Rate (`tc netem` 0.1% loss impact)** (`sum by (k8s_cluster_name, direction) (rate(system_network_dropped_total[1m]))`).
  - Bổ sung *Panel:* **Network Interface Errors Rate (RX/TX Errors)** (`sum by (k8s_cluster_name, direction) (rate(system_network_errors_total[1m]))`).
  - Bổ sung *Panel:* **WAN Packet Rate (Packets/sec RX/TX across Bridge)** (`sum by (k8s_cluster_name, direction) (rate(system_network_packets_total[1m]))`).
  - Bổ sung *Panel:* **Cross-Cluster TCP Socket Saturation during WAN Transit** (`sum by (k8s_cluster_name, state) (system_network_connections{state=~"ESTABLISHED|SYN_SENT|TIME_WAIT|CLOSE_WAIT"})`).
  - Giữ và tối ưu Panel **Cross-Cloud Network Latency Duration (AWS -> Azure P50/P95/P99)** từ `traces_service_graph_request_server_seconds_bucket` và `traces_service_graph_request_client_seconds_bucket` (nếu có) để thấy rõ độ chênh lệch thời gian truyền mạng WAN.

#### 3. `system-topology.json` (`uid: mc-system-topology`) — Tối ưu hóa và kết hợp Hạ tầng + Cloud Context:
- Rút gọn và làm sạch câu truy vấn PromQL của `nodeGraph` (Panel 1) để dễ bảo trì, không hardcode thông số giả `"P95: 12ms"` tĩnh vào `secondaryStat` nếu có thể hiển thị giá trị thực hoặc nhãn trạng thái chuẩn.
- Giữ bảng **Cross-Cloud Network Routing & Subnet Matrix** (Panel 2) và **Deep Single-Resource Cloud Dependencies 360° Inventory** (Panel 3), đồng thời bổ sung thêm **1 Panel mới (Panel 6): Cluster Node Resource & Network Health Summary Table** (hiển thị CPU Usage, I/O Wait, Memory Used, Disk I/O, Packet Drops của từng cụm `aws-k3d`, `azure-k3d`, `hub-k3d` ngay bên dưới sơ đồ Topology để SRE vừa nhìn thấy Cloud Context vừa thấy ngay sức khỏe vật lý của Node).

#### 4. `red-metrics.json` (`uid: mc-red-metrics`) — Hoàn thiện đủ 4 Golden Signals (Rate, Errors, Duration, Saturation):
- Giữ 3 panels hiện tại (Rate, Errors, Duration P95) và định dạng `unit` chuẩn (`reqps`, `ms`).
- Bổ sung thêm:
  - *Panel 4:* **Latency Percentiles Comparison (P50 vs P90 vs P99 ms by Service)**.
  - *Panel 5 (Saturation):* **Service & Node Saturation (CPU I/O Wait, Active TCP Connections & Request Concurrency)** để hoàn thiện đủ 4 Golden Signals của Google SRE.
  - *Panel 6:* **Database & RMI Backend Call Duration (`teastore-persistence -> teadb` & `teastore-registry`)**.

#### 5. `logs-traces-deepdive.json` (`uid: mc-logs-traces-deepdive`) — Bổ sung chẩn đoán lỗi Hạ tầng / DB / OS:
- Giữ 3 panels hiện tại.
- Bổ sung *Panel 4 (Timeseries):* **Infrastructure, Database & Connection Anomaly Logs** (lọc các từ khóa nhạy cảm về hạ tầng như `(?i)(aborted|timeout|refused|oom|killed|io|error|fail|slow)` phân nhóm theo `service_name` và `k8s_cluster_name`).
- Bổ sung *Panel 5 (Logs):* **Database & Persistence Layer Diagnostic Log Stream (`azure-k3d`)** để theo dõi riêng biệt hành vi của MySQL và tầng JPA Persistence.

#### 6. `mc-executive-overview.json` & `slo-governance.json`:
- Trong `mc-executive-overview.json`: Nâng cấp Panel 7 (**Cloud Cluster Fleet Health Matrix**) hoặc bổ sung các cột/chỉ số thể hiện toàn diện sức khỏe cụm (Memory Used GB, CPU Load Average 1m, Network Drops/s, Disk I/O) thay vì chỉ hiển thị mỗi Memory Used như hiện tại.

---

### NHIỆM VỤ 3: Áp dụng cấu hình lên cụm Kubernetes & Kiểm thử xác thực (Live Verification)

Sau khi cập nhật các file cấu hình và JSON dashboards:
1. Áp dụng lại cấu hình OTel Collector (nếu có thay đổi ở Spoke/Hub) và rollout restart các pods collector tương ứng.
2. Áp dụng Kustomize cho Grafana (`kubectl apply -k k8s/base/visualization-grafana --context k3d-hub-k3d`) và restart pod `grafana` để nạp lại toàn bộ ConfigMap dashboards mới.
3. Chạy kiểm tra thực tế qua Prometheus/Thanos API (`http://localhost:9090`) và Grafana API (`http://localhost:3000`):
   - Xác nhận các metrics tầng OS/Kernel/Disk/Network (`system_cpu_time_seconds_total{state="wait"}`, `system_cpu_load_average_1m`, `system_disk_io_bytes_total`, `system_filesystem_inodes_usage`, `system_network_dropped_total`, `system_network_connections`, `system_paging_operations_total`) đều có dữ liệu trả về cho cả `aws-k3d` và `azure-k3d`.
   - Xác nhận cả 7 Dashboards nạp lên Grafana thành công (HTTP 200), cú pháp JSON hợp lệ 100%, không có bất kỳ lỗi cú pháp PromQL/LogQL nào.

### NHIỆM VỤ 4: Cập nhật tài liệu nhật ký dự án
- Ghi nhận bản nâng cấp này vào `docs/progress/00_result_progress.md` và `docs/progress/01_implemetation_issue.md` (dưới mã **INC-P3-15**: *Tái cân bằng hệ thống giám sát tài nguyên theo chuẩn Full-Stack SRE & USE Method: Bổ sung chẩn đoán Linux OS, Kernel I/O Wait, Disk/Inode, TCP Stack và nâng cấp toàn diện 7 Grafana Dashboards*).

---

## 3. QUY TẮC BẮT BUỘC (STRICT RULES)

1. **Không phá vỡ những gì đang chạy:** Giữ nguyên các phiên bản công nghệ đã ghim cứng (Pinned Versions), giữ nguyên cấu trúc mTLS 1.3, MinIO buckets, Pyrra SLO và Robusta Alerting.
2. **Đảm bảo tính chính xác của JSON & PromQL:** Kiểm tra kỹ dấu ngoặc, dấu phẩy và escape string trong tất cả các file `.json` trước khi apply.
3. **Không bịa đặt tên metric:** Trước khi đưa một metric của `hostmetrics` vào Grafana JSON, hãy dùng `curl` truy vấn thử trên Thanos Query (`:9090/api/v1/label/__name__/values`) để chắc chắn 100% tên metric đã được Prometheus exporter chuyển đổi chính xác (ví dụ: kiểm tra xem tên thực tế là `system_cpu_load_average_1m` hay `system_cpu_load_average_1m_ratio`, `system_filesystem_inodes_usage` hay `system_filesystem_inodes_usage_total`).

## 4. BÁO CÁO KẾT QUẢ SAU KHI HOÀN THÀNH

Khi thực hiện xong, hãy báo cáo tóm tắt:
1. Danh sách các metrics tầng OS/Kernel/Disk/Network thực tế đã xác thực trên Thanos Query.
2. Chi tiết các Panels đã được bổ sung/nâng cấp trong từng Dashboard của bộ 7 Grafana Dashboards.
3. Kết quả kiểm chứng trực tiếp qua API của Thanos và Grafana.
4. Trạng thái cập nhật của các tài liệu trong `docs/progress/`.