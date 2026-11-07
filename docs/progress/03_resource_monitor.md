# Chiến Lược Giám Sát Toàn Diện: Hạ Tầng Hệ Điều Hành, Mạng L3/L4 & Ngữ Cảnh Đa Đám Mây (Full-Stack Infrastructure, OS/Kernel & Cloud Dependency Observability)

> **Tài liệu tham chiếu:** `docs/progress/03_resource_monitor.md`  
> **Dự án:** Multi-Cloud Monitoring Platform (TeaStore Hub-Spoke Observability)  
> **Phiên bản:** v3.0.0 (Balanced Full-Stack SRE & USE Method Edition)  
> **Cập nhật lần cuối:** 2026-11-07  
> **Mục tiêu:** Chuyển dịch từ mô hình giám sát thiên lệch về siêu dữ liệu đám mây tĩnh (Static Cloud Metadata) sang kiến trúc **Quan sát toàn diện (True Full-Stack Observability)**. Kết hợp chặt chẽ giữa **Chẩn đoán tầng Hệ điều hành, Nhân Linux, Đĩa từ, Mạng L3/L4 theo phương pháp USE (Utilization - Saturation - Errors)** với **Mô hình 6 Trục Phụ Thuộc Đám Mây Sâu (Cloud Dependency Context)** và **Tín hiệu vàng ứng dụng (RED/Golden Signals)**.

---

## 1. Triết Lý Thiết Kế: Cân Bằng Giữa "Hành Vi Hệ Thống Động" Và "Ngữ Cảnh Đám Mây Tĩnh"

Trong vận hành hệ thống phân tán đa đám mây (Multi-Cloud SRE), việc giám sát tài nguyên không thể chỉ dừng lại ở việc gắn nhãn tài nguyên đó thuộc VPC nào hay dùng IAM Role gì. Một chiến lược giám sát chuẩn mực phải trả lời được đồng thời hai câu hỏi:
1. **WHAT & WHERE (Tầng Ngữ Cảnh Đám Mây - Cloud Dependency Context):** Sự cố đang xảy ra ở đám mây nào (`aws` hay `azure`), vùng nào (`us-east-1` hay `southasia`), nhánh mạng Subnet/Security Group nào, và ảnh hưởng đến danh tính IAM/Resource ARN nào?
2. **WHY & HOW (Tầng Chẩn Đoán Hệ Điều Hành, Lưu Trữ & Mạng - OS, Kernel, Storage & Network Diagnostics):** Tại sao tài nguyên đó bị suy giảm hiệu năng? Do nghẽn CPU thực thi hay do **CPU I/O Wait (`%wa`)** chờ ổ đĩa MySQL flush dữ liệu? Do thiếu RAM dẫn đến Linux Kernel `OOMKiller` cắt tiến trình (`SIGKILL 9`), do cạn kiệt **Inode (`df -i`)**, hay do **TCP Retransmissions / Packet Drops** trên đường truyền WAN liên cụm?

```
┌──────────────────────────────────────────────────────────────────────────────────────────┐
│ TẦNG 4: APPLICATION & GOLDEN SIGNALS (L7 Workload Behavior - RED Method)                 │
│ • Rate (QPS), Errors (HTTP 4xx/5xx), Duration (Latency P50/P95/P99), Saturation (JVM/DB) │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 3: CLOUD & KUBERNETES DEPENDENCY CONTEXT (Where & Who - 6 Cloud Vectors)            │
│ • Identity (IAM Role ARN, Managed Identity), Network Perimeter (VPC/VNet, Subnet, SG)   │
│ • Storage/Crypto (EBS/Managed Disk, KMS/KeyVault), Governance (Account ID, Cost Tags)    │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 2: DISTRIBUTED L3/L4 NETWORK & SOCKET STACK (Inter-Cluster WAN & Transport)         │
│ • WAN Latency RTT (10ms ±2ms), Jitter, Packet Drops, Network Errors (rx/tx)              │
│ • TCP Socket States (ESTABLISHED, TIME_WAIT, CLOSE_WAIT), TCP Retransmissions            │
├──────────────────────────────────────────────────────────────────────────────────────────┤
│ TẦNG 1: LINUX OS, KERNEL, COMPUTE & STORAGE FUNDAMENTALS (Why & How - USE Method)        │
│ • CPU & Load: User/System Time, I/O Wait (%wa), Steal Time, System Load (1m, 5m, 15m)    │
│ • Memory & Paging: Used/Cached/Free, Swap I/O, Major/Minor Page Faults, OOM Kill Events  │
│ • Disk & Filesystem: IOPS, Throughput, Disk Queue/Latency, Capacity (df -h), Inodes (df -i)│
└──────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Giám Sát Tầng Hệ Điều Hành, Kernel, Lưu Trữ & Mạng (USE Method & Linux Diagnostics)

Áp dụng phương pháp **USE Method (Utilization, Saturation, Errors)** của Brendan Gregg cho toàn bộ các nút máy chủ ảo hóa (`hub-k3d`, `aws-k3d`, `azure-k3d`):

### 2.1. Phân Tích CPU, System Load & Hiện Tượng Nghẽn I/O Wait (`%wa`)
Một sai lầm phổ biến là đồng nhất *System Load Average* cao với việc *CPU bị quá tải*. Trong Linux, Load Average tính cả các tiến trình đang chạy trên CPU (`R` - Runnable) lẫn các tiến trình đang nằm trong hàng đợi không thể ngắt do chờ đọc/ghi đĩa hoặc mạng (`D` - Uninterruptible Sleep).

* **Chỉ số thu thập qua OTel `hostmetrics` (`cpu` & `load` scrapers):**
  * `system_cpu_time_seconds_total{state="user|system"}`: Mức sử dụng CPU thực tế cho logic ứng dụng và lời gọi hệ thống (Kernel syscalls).
  * `system_cpu_time_seconds_total{state="wait"}` (**I/O Wait - `%wa`**): Tỷ lệ thời gian CPU rảnh rỗi nhưng phải chờ thao tác I/O hoàn tất. Khi `teastore-db` (MySQL trên Azure Spoke) chịu tải ghi lớn hoặc MinIO (trên Hub) nén TSDB blocks, nếu `%wa` tăng vọt trong khi CPU `user` thấp, đó là bằng chứng xác thực của **nghẽn tầng lưu trữ (Storage Bottleneck)**.
  * `system_cpu_load_average_1m`, `5m`, `15m`: Đối chiếu với số nhân CPU để phát hiện mức độ bão hòa hàng đợi thực thi (Saturation).

### 2.2. Quản Lý Bộ Nhớ (Memory), Paging & Chẩn Đoán OOM Killer
* **Chỉ số thu thập (`memory` & `paging` scrapers):**
  * `system_memory_usage_bytes{state="used|free|buffered|cached|slab_reclaimable"}`: Phân tách rõ bộ nhớ ứng dụng thực sự chiếm dụng (`used`) và bộ nhớ đệm trang của nhân Linux (`cached`/`buffered`).
  * `system_paging_operations_total{type="major|minor", direction="page_in|page_out"}`: Tốc độ lỗi trang (Page Faults). Khi `major page faults` tăng cao, hệ thống phải đọc trang nhớ từ đĩa, làm suy giảm nghiêm trọng thời gian phản hồi của JVM Tomcat.
  * **Kiểm soát vòng đời tiến trình & OOM (`SIGTERM` vs `SIGKILL`):** Giám sát sự kiện container bị giết cưỡng bức với `Exit Code 137` (`SIGKILL - 9` từ Linux Kernel OOM Killer, như sự cố `INC-P2-01`) so với việc dừng chủ động an toàn bằng `SIGTERM - 15` (cho phép Tomcat và MySQL đóng kết nối và flush buffer xuống đĩa).

### 2.3. Chẩn Đoán Đĩa Từ (Disk I/O) & Hệ Thống Tệp Tin (Filesystem & Inodes)
* **Chỉ số thu thập (`disk` & `filesystem` scrapers):**
  * **Utilization & Throughput:** `system_disk_io_bytes_total` (Tốc độ đọc/ghi MB/s) và `system_disk_operations_total` (IOPS).
  * **Saturation & Latency:** `system_disk_operation_time_seconds_total` (Thời gian xử lý I/O tích lũy) và `system_disk_pending_operations` (Độ sâu hàng đợi I/O - tương đương cột `aqu-sz` và `await` trong lệnh `iostat -xz 1`).
  * **Filesystem Capacity (`df -h`):** `system_filesystem_usage_bytes` — cảnh báo khi phân vùng chứa `/var/lib/mysql` hoặc `/data` của MinIO vượt ngưỡng 80%.
  * **Inode Exhaustion (`df -i`):** `system_filesystem_inodes_usage` — cực kỳ quan trọng đối với Hub Collector và MinIO vì việc ghi hàng chục ngàn tệp JSON nhỏ vào bucket `raw-telemetry` có thể làm cạn kiệt Inode trước khi ổ cứng đầy dung lượng byte.

### 2.4. Chẩn Đoán Ngăn Xếp Mạng L3/L4 & Trạng Thái Socket TCP
* **Chỉ số thu thập (`network` scraper & Kernel netem):**
  * **Bandwidth:** `rate(system_network_io_bytes_total[1m])` và `rate(system_network_packets_total[1m])` theo chiều `receive` (RX) và `transmit` (TX).
  * **Packet Drops & Errors:** `rate(system_network_dropped_total[1m])` và `rate(system_network_errors_total[1m])`. Phản ánh trực tiếp tác động vật lý của bộ mô phỏng suy hao mạng WAN `tc netem` (10ms RTT ±2ms, 0.1% packet loss) lên giao diện mạng `eth0` của các cụm Spoke.
  * **TCP Connection States (`ss -tulnp` equivalent):** `system_network_connections{protocol="tcp", state="ESTABLISHED|TIME_WAIT|CLOSE_WAIT|SYN_SENT"}`.
    * Sự gia tăng đột biến của `TIME_WAIT` giữa `teastore-webui` và các dịch vụ con cho thấy việc thiếu tái sử dụng kết nối (HTTP Keep-Alive).
    * Sự tích tụ của `CLOSE_WAIT` hoặc `SYN_SENT` giữa `teastore-persistence` (Azure) và `teastore-registry` (AWS) chỉ ra hiện tượng treo kết nối qua đường truyền WAN hoặc nghẽn luồng xử lý.

---

## 3. Ma Trận Chẩn Đoán Sự Cố Hạ Tầng (Linux & SRE Troubleshooting Matrix)

Bảng dưới đây kết nối trực tiếp các công cụ dòng lệnh chẩn đoán hệ thống Linux truyền thống với các chỉ số OpenTelemetry / PromQL tự động hóa trên nền tảng giám sát tập trung:

| Triệu Chứng Sự Cố | Lệnh Linux Chẩn Đoán Thủ Công | Metric Chuẩn Hóa Trên Thanos / Prometheus | Nguồn Log & Trace Tương Quan (Loki / Tempo) |
|---|---|---|---|
| **Load cao nhưng CPU User thấp (Nghẽn I/O)** | `top`, `uptime`, `vmstat 1`, `iostat -xz 1` | `rate(system_cpu_time_seconds_total{state="wait"}[1m])` kết hợp `system_cpu_load_average_1m` | Trace Span JDBC kéo dài bất thường trên `teastore-db`; Slow query log trong Loki. |
| **Pod Restart / Cạn kiệt bộ nhớ (OOM)** | `dmesg -T \| grep -i oom`, `free -h`, `journalctl -k` | `system_memory_usage_bytes{state="used"}` chạm ngưỡng Limit; `system_paging_operations_total` tăng vọt. | Robusta bắt sự kiện `OOMKilled` (Exit 137) từ K8s API và gửi báo cáo về Telegram. |
| **Nghẽn ghi đĩa DB hoặc Object Storage** | `iostat -xz 1`, `iotop` | `rate(system_disk_operation_time_seconds_total[1m])` và `system_disk_pending_operations > 0`. | Log cảnh báo Compaction chậm từ Thanos Sidecar hoặc InnoDB flush log từ MySQL. |
| **Lỗi không tạo được file dù đĩa còn trống** | `df -h` vs `df -i`, `lsblk` | `system_filesystem_inodes_usage{state="used"} / system_filesystem_inodes_usage{state="free"}`. | Log lỗi `No space left on device` tại exporter `awss3` hoặc `minio`. |
| **Mạng WAN chập chờn, rớt gói, trễ cao** | `ping`, `tc -s qdisc show dev eth0`, `tcpdump -i any` | `rate(system_network_dropped_total[1m]) > 0` và `traces_service_graph_request_server_seconds_bucket`. | Span Waterfall trên Tempo hiển thị độ trễ chênh lệch ~10ms giữa Client Span (AWS) và Server Span (Azure). |
| **Cạn kiệt cổng kết nối hoặc rò rỉ Socket** | `ss -tan \| awk '{print $1}' \| sort \| uniq -c`, `nc -zv` | `system_network_connections{protocol="tcp", state=~"TIME_WAIT\|CLOSE_WAIT"}`. | Log `Aborted connection` trên MySQL (`INC-P3-08`) hoặc `Connection refused / timeout` trên Tomcat. |

---

## 4. Mô Hình Ngữ Cảnh 6 Trục Phụ Thuộc Đám Mây Sâu (Cloud Dependency Context Layer)

Sau khi tầng OS, Lưu trữ và Mạng (Mục 2 & 3) cung cấp tín hiệu động để trả lời câu hỏi **"Tại sao lỗi?"**, tầng Ngữ cảnh Đám mây (Cloud Dependency Layer) đóng vai trò làm giàu siêu dữ liệu (Contextual Enrichment) để định vị chính xác tài nguyên đó nằm ở đâu trong kiến trúc Multi-Cloud.

*(Lưu ý học thuật: Trong môi trường mô phỏng cục bộ bằng `k3d`, các thuộc tính hạ tầng đám mây sâu dưới đây được tiêm chuẩn hóa thông qua chính sách **Synthetic Topology Enrichment via OTTL** tại Hub Gateway nhằm mô phỏng cơ chế thu thập từ AWS IMDSv2 và Azure IMDS trên môi trường đám mây thực tế).*

### 4.1. Sáu Trục Phụ Thuộc Đám Mây Cơ Sở (6 Foundational Cloud Vectors)
1. **Identity & Access Vector (IAM / Entra ID):** `cloud.identity.arn` (IAM Role ARN / User-Assigned Managed Identity), K8s ServiceAccount IRSA.
2. **Network & Traffic Perimeter Vector:** `network.vpc.id` (`vpc-0a1b2c3d4e5f67890` / `vnet-teastore-southasia`), `network.subnet.id` (`10.0.1.0/24` vs `10.1.2.0/24`), `network.security_group.id`.
3. **Storage & Persistence Vector:** `storage.volume.id` (AWS EBS `gp3` / Azure Managed Disk `Premium_LRS`), Object Storage Buckets (`thanos-metrics`, `loki-data`, `tempo-traces`, `raw-telemetry`).
4. **Cryptography & Secrets Vector:** `security.kms.key_arn`, Azure Key Vault CMK URI, chứng chỉ đường truyền `mTLS 1.3 (ChaCha20-Poly1305)`.
5. **Compute & Platform Vector:** `cloud.provider` (`aws`, `azure`, `hub`), `cloud.platform` (`aws_eks`, `azure_aks`), `cloud.region` (`us-east-1`, `southasia`), `k8s.cluster.name`, `k8s.node.name`.
6. **Governance, Audit & Billing Vector:** `cloud.account.id`, `cloud.resource_id`, `telemetry.hub.received_time`.

### 4.2. Ma Trận Thuộc Tính Chuẩn Hóa OpenTelemetry (Unified SemConv Matrix)

| Phân Lớp Giám Sát | Nhóm Tín Hiệu | Tên Thuộc Tính / Metric Chuẩn (`SemConv / PromQL`) | Nguồn Thu Thập Thực Tế Trong Hệ Thống | Tính Xác Thực Dữ Liệu (Authenticity) |
|---|---|---|---|---|
| **Tầng 1: OS & Kernel** | CPU & I/O Wait | `system.cpu.time` (`state=user,system,wait,idle`) | OTel Spoke `hostmetrics` (cào từ `/proc/stat`) | **Đo lường Vật lý 100%** |
| | System Load | `system.cpu.load_average.1m / 5m / 15m` | OTel Spoke `hostmetrics` (cào từ `/proc/loadavg`) | **Đo lường Vật lý 100%** |
| | Memory & Paging | `system.memory.usage`, `system.paging.operations` | OTel Spoke `hostmetrics` (`/proc/meminfo`, `/proc/vmstat`) | **Đo lường Vật lý 100%** |
| **Tầng 2: Disk & FS** | Disk IOPS & Latency | `system.disk.io`, `system.disk.operation_time`, `system.disk.pending_operations` | OTel Spoke `hostmetrics` (`/proc/diskstats`) | **Đo lường Vật lý 100%** |
| | Filesystem & Inodes | `system.filesystem.usage`, `system.filesystem.inodes.usage` | OTel Spoke `hostmetrics` (`statfs` syscall) | **Đo lường Vật lý 100%** |
| **Tầng 3: Network L3/L4**| Traffic & Drops | `system.network.io`, `system.network.dropped`, `system.network.errors` | OTel Spoke `hostmetrics` (`/proc/net/dev` + `tc netem`) | **Đo lường Vật lý 100%** |
| | TCP Socket States | `system.network.connections` (`ESTABLISHED`, `TIME_WAIT`, ...) | OTel Spoke `hostmetrics` (`/proc/net/tcp`) | **Đo lường Vật lý 100%** |
| **Tầng 4: K8s & App** | K8s Runtime | `k8s.cluster.name`, `k8s.namespace.name`, `k8s.pod.name`, `service.name` | K8s Downward API & OTel Java Agent v2.10 | **Đo lường Thực tế 100%** |
| | RED Metrics | `traces_service_graph_request_total`, `..._server_seconds_bucket` | OTel Hub `servicegraphconnector` tính từ Live Traces | **Đo lường Thực tế 100%** |
| **Tầng 5: Cloud Context**| Cloud Topology | `cloud.provider`, `cloud.region`, `cloud.account.id`, `network.vpc.id`, `cloud.identity.arn` | OTTL Enrichment Processor tại Hub Collector | **Mô phỏng Ngữ cảnh (Synthetic Enrichment)** |

---

## 5. Chiến Lược Loại Bỏ `unknown_service` Và Bảo Toàn Dữ Liệu Nghiên Cứu

1. **Zero Unknown Policy (Định danh 100% nút mạng):**
   * Các cuộc gọi không mang W3C TraceContext phản hồi như Java RMI (`:1099` tới `teastore-registry`) hoặc JDBC (`:3306` tới `teastore-db`) được bộ quy tắc OTTL Peer Service Enrichment tự động ánh xạ `peer.service` dựa trên cổng đích và giao thức tầng 4.
2. **Data Integrity & Raw Telemetry Lake:**
   * Mọi bản ghi Metrics (bao gồm toàn bộ chỉ số OS/Kernel/Network), Logs và Traces sau khi chuẩn hóa đều được sao lưu bất biến (WORM) dưới định dạng OTLP JSON vào bucket `s3://raw-telemetry/` trên MinIO để phục vụ kiểm chứng độc lập và huấn luyện mô hình phát hiện bất thường ở Phase 4.