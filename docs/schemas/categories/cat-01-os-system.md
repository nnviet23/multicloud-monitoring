# Semantic Conventions: CAT-01 OS & System Kernel

**Status**: Stable (Attributes) / Mixed (Metrics)  
**Namespace**: `system.*`, `host.*`  
**OTel SemConv Domain**: `docs/system/system-metrics.md`, `docs/resource/host.md`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-01` quy định từ điển ngữ nghĩa nguyên tử cho việc đo lường tài nguyên phần cứng, hệ điều hành Linux kernel, CPU scheduling, bộ nhớ RAM, swap paging và tải hệ thống (System Load Average).

Trong môi trường phân tán đa đám mây (Multi-Cloud Kubernetes Lab & Production), các thuộc tính và số đo của `CAT-01` đóng vai trò là tầng đáy của phương pháp luận **USE Method (Utilization, Saturation, Errors)**. Tầng này cung cấp các tín hiệu then chốt giúp phân biệt giữa:
- **Nghẽn phần cứng thực sự tại Node/Host:** Khi CPU load vượt quá số cores, wait I/O (%wa) tăng cao hoặc paging faults liên tục do thiếu RAM.
- **Nghẽn ở tầng ảo hóa container/cgroup:** Khi hostmetrics vẫn bình thường nhưng Pod bị CPU throttling do cấu hình limit K8s quá thấp.

Telemetry của `CAT-01` được thu thập tại biên thông qua bộ cào `hostmetrics` của OpenTelemetry Collector (tại cả Spoke Edge và Central Hub) theo chu kỳ định kỳ (15 giây).

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

Bảng dưới đây định nghĩa các thuộc tính ngữ cảnh và nhãn chiều (labels/dimensions) áp dụng cho `CAT-01`:

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `host.name` | `host_name` / `instance` | Stable | Required | string | Tên định danh của máy chủ vật lý hoặc VM host. [1] | `k3d-aws-k3d-server-0`, `k3d-azure-k3d-server-0` |
| `host.id` | `host_id` | Stable | Recommended | string | Mã định danh duy nhất của máy chủ (Machine ID / DMI UUID). [2] | `i-08a9c1d2e3f4a5b6c`, `vm-azure-01` |
| `host.arch` | `host_arch` | Stable | Recommended | string | Kiến trúc vi xử lý của hệ thống. | `amd64`, `arm64` |
| `os.type` | `os_type` | Stable | Required | string | Hệ điều hành của máy chủ. | `linux` |
| `os.description` | `os_description` | Stable | Recommended | string | Phiên bản chi tiết bản phân phối OS và Kernel. | `Ubuntu 24.04 LTS (Kernel 6.6.137)` |
| `system.cpu.state` | `state` | Stable | Conditionally Required [3] | string | Trạng thái thực thi của CPU cores theo `/proc/stat`. | `user`, `system`, `idle`, `wait`, `steal`, `interrupt` |
| `system.cpu.logical_number` | `cpu` | Stable | Conditionally Required [4] | int | Chỉ số thứ tự của lõi CPU logic (Core ID). | `0`, `1`, `2`, `3` |
| `system.memory.state` | `state` | Stable | Conditionally Required [5] | string | Phân loại trạng thái không gian bộ nhớ RAM. | `used`, `free`, `cached`, `buffered`, `slab_reclaimable` |
| `system.paging.direction` | `direction` | Stable | Conditionally Required [6] | string | Chiều truyền dữ liệu của bộ nhớ ảo (Swap / Paging). | `in`, `out` |
| `system.paging.type` | `type` | Stable | Conditionally Required [7] | string | Phân loại lỗi trang nhớ bộ nhớ ảo. | `major`, `minor` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc có trên mọi bản ghi metric để gom nhóm theo máy chủ. Trong môi trường Kubernetes k3d, `host.name` tương ứng với tên Node Kubernetes.
- **[2]:** Được làm giàu qua bộ phát hiện tài nguyên `resourcedetection` processor (detector `system` / `env`).
- **[3]:** Bắt buộc xuất hiện trên metric `system.cpu.time` để bóc tách thời gian CPU. Trạng thái `wait` phản ánh nghẽn I/O disk; `steal` phản ánh CPU bị tranh chấp bởi hypervisor.
- **[4]:** Xuất hiện khi thu thập chi tiết theo từng Core logic (`system.cpu.time`).
- **[5]:** Bắt buộc trên `system.memory.usage` để tính toán chính xác Available RAM (`free + cached + buffered`).
- **[6]:** Bắt buộc trên `system.paging.operations` để phân biệt Swap In (đọc từ đĩa vào RAM) và Swap Out (đẩy RAM xuống đĩa).
- **[7]:** Bắt buộc trên `system.paging.faults` để nhận diện `major faults` (đòi hỏi đọc đĩa, gây đình trệ tiến trình).

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

| Metric Name (OTel SemConv) | Prometheus TSDB Name | Instrument Type | Unit (UCUM) | Orientation | Description & USE/RED Role |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `system.cpu.time` | `system_cpu_time_seconds_total` | Counter | `s` | +1 | Tổng thời gian CPU đã tích lũy theo từng trạng thái (`state`). Đóng vai trò tính toán **CPU Utilization (%)** và **I/O Wait Saturation (%)**. |
| `system.cpu.load_average.1m` | `system_cpu_load_average_1m` | Gauge | `1` | 0 | Tải trung bình hệ thống trong 1 phút vừa qua (System Load Average 1m). Đóng vai trò đo **CPU Saturation**. |
| `system.cpu.load_average.5m` | `system_cpu_load_average_5m` | Gauge | `1` | 0 | Tải trung bình hệ thống trong 5 phút vừa qua. |
| `system.cpu.load_average.15m` | `system_cpu_load_average_15m` | Gauge | `1` | 0 | Tải trung bình hệ thống trong 15 phút vừa qua. |
| `system.memory.usage` | `system_memory_usage_bytes` | Sum / Gauge | `By` | +1 | Dung lượng bộ nhớ RAM vật lý tiêu thụ theo từng trạng thái (`used`, `free`, `cached`, `buffered`). Đóng vai trò đo **Memory Utilization**. |
| `system.paging.operations` | `system_paging_operations_total` | Counter | `{operation}` | +1 | Số lượng thao tác swap paging (`in` / `out`) trên đĩa nhớ ảo. Đóng vai trò đo **Memory Saturation / Thrashing**. |
| `system.paging.faults` | `system_paging_faults_total` | Counter | `{fault}` | +1 | Số lượng lỗi trang bộ nhớ ảo (`major` / `minor`). Tỷ lệ `major faults` tăng cao là bằng chứng tiến trình bị nghẽn trang. |

*Ghi chú về Orientation:* `+1` thể hiện chỉ số tăng dần (Monotonic Cumulative Counter); `0` thể hiện trạng thái biến thiên tức thời (Gauge).

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

Dựa trên lược sử chuyển đổi lược đồ của OpenTelemetry Specification:

1. **Tiến hóa cấu trúc tên gọi nhãn Direction (`v1.24.0`):**
   - Theo schema OTel `1.24.0`: Thuộc tính `system.network.io.direction` và `system.disk.io.direction` được chuẩn hóa thành `network.io.direction` và `disk.io.direction`. Tuy nhiên trong Prometheus exporter của OTel Collector Contrib, nhãn gắn vào metric vẫn là `direction="read|write|receive|transmit"` nhằm giữ tính tương thích với hệ sinh thái Prometheus node-exporter truyền thống.
2. **Tiến hóa từ `system.memory.utilization` sang `system.memory.usage`:**
   - Trong OTel SemConv sơ khai, một số instrumentation phát metric đo tỷ lệ phần trăm `system.memory.utilization`. Chuẩn OTel hiện đại và Prometheus TSDB quy định phát metric dung lượng byte thô `system.memory.usage` (`system_memory_usage_bytes`), việc tính phần trăm được thực hiện tại tầng truy vấn PromQL:
     $$\text{Memory Util \%} = \frac{\sum \text{used}}{\sum (\text{used} + \text{free} + \text{cached} + \text{buffered})} \times 100$$
3. **Cơ chế Fallback Trong Đồ Án:**
   - Khi truy vấn biến `cluster` trên Grafana Dashboards và AI Engine, hệ thống sử dụng truy vấn bám sát Counter chuẩn: `label_values(system_cpu_time_seconds_total, k8s_cluster_name)`, loại bỏ hoàn toàn các tên metric cũ không chứa hậu tố đơn vị (`system_memory_usage`).

