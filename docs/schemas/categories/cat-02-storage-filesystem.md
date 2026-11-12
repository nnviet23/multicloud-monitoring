# Semantic Conventions: CAT-02 Storage & Filesystem

**Status**: Stable (Disk Metrics) / Mixed (Filesystem & Object Storage)  
**Namespace**: `system.disk.*`, `system.filesystem.*`, `s3.*`  
**OTel SemConv Domain**: `docs/system/system-metrics.md`, `docs/object-stores/`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-02` quy định chuẩn ngữ nghĩa đo lường hai tầng lưu trữ trong hệ thống giám sát phân tán:
1. **Khối lưu trữ cục bộ & Hệ thống tệp (Block Storage & POSIX Filesystem):** Đo lường thông lượng đọc/ghi khối I/O, thời gian thực hiện thao tác (I/O service latency), hàng đợi tác vụ I/O đang chờ (I/O queue length), dung lượng tệp tin tiêu thụ và số lượng Inodes khả dụng.
2. **Lưu trữ Đối tượng Đám mây (Cloud Object Storage - MinIO S3):** Giám sát tình trạng các bucket lưu trữ TSDB blocks (`thanos-metrics`), log chunks (`loki-data`), trace blocks (`tempo-traces`), và kho dữ liệu thô (`raw-telemetry`).

Trong kiến trúc đồ án, `CAT-02` đóng vai trò quan trọng đối với **Cụm Lưu trữ Cơ sở Dữ liệu MySQL (`azure-k3d`)** và **Trung tâm Lưu trữ Tập trung MinIO (`hub-k3d`)**. Bất kỳ sự suy giảm hiệu năng I/O nào (I/O latency > 50ms hoặc disk queue > 5) đều lập tức gây hiệu ứng thắt cổ chai dây chuyền lan truyền ngược về phía WebUI.

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `system.disk.device` | `device` | Stable | Required | string | Tên thiết bị ổ đĩa khối hoặc phân vùng (block device name). [1] | `sda`, `vda`, `nvme0n1` |
| `disk.io.direction` | `direction` | Stable | Required | string | Chiều truyền dữ liệu của thao tác ổ đĩa. [2] | `read`, `write` |
| `system.filesystem.mountpoint` | `mountpoint` | Stable | Required | string | Đường dẫn gắn kết của phân vùng tệp (Mount point). [3] | `/`, `/var/lib/mysql`, `/data` |
| `system.filesystem.type` | `type` | Stable | Recommended | string | Định dạng hệ thống tệp POSIX. | `ext4`, `xfs`, `overlay` |
| `system.filesystem.state` | `state` | Stable | Conditionally Required [4] | string | Trạng thái phân bổ dung lượng đĩa. | `used`, `free`, `reserved` |
| `s3.bucket.name` | `bucket` / `s3_bucket` | Experimental | Required | string | Tên thùng lưu trữ đối tượng S3 trong MinIO. | `thanos-metrics`, `raw-telemetry` |
| `s3.endpoint` | `endpoint` | Experimental | Recommended | string | Địa chỉ API truy cập dịch vụ lưu trữ đối tượng. | `minio.storage.svc.cluster.local:9000` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc có trên mọi bản ghi metric ổ đĩa để bóc tách I/O theo từng ổ đĩa vật lý hoặc ảo.
- **[2]:** Bắt buộc trên các metric lưu lượng byte và IOPS để phân biệt lưu lượng đọc (`read`) và lưu lượng ghi (`write`).
- **[3]:** Bắt buộc trên metric hệ thống tệp để theo dõi độc lập các điểm gắn kết quan trọng (đặc biệt là volume dữ liệu DB và volume MinIO).
- **[4]:** Bắt buộc trên `system.filesystem.usage` để tính toán tỷ lệ lấp đầy phân vùng đĩa.

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

| Metric Name (OTel SemConv) | Prometheus TSDB Name | Instrument Type | Unit (UCUM) | Orientation | Description & USE/RED Role |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `system.disk.io` | `system_disk_io_bytes_total` | Counter | `By` | +1 | Tổng dung lượng byte đọc/ghi qua ổ đĩa khối. Đo **Disk Throughput (Bps)** (USE Utilization). |
| `system.disk.operations` | `system_disk_operations_total` | Counter | `{operation}` | +1 | Tổng số lượng thao tác đọc/ghi hoàn tất trên ổ đĩa. Đo **IOPS** (USE Utilization). |
| `system.disk.operation_time` | `system_disk_operation_time_seconds_total` | Counter | `s` | +1 | Tổng thời gian các thao tác I/O tiêu tốn trên đĩa. Kết hợp với `operations` để tính **I/O Latency (ms)**. |
| `system.disk.pending_operations` | `system_disk_pending_operations` | Gauge | `{operation}` | 0 | Số lượng thao tác I/O đang chờ trong hàng đợi lập lịch của kernel. Đo **Disk Saturation**. |
| `system.filesystem.usage` | `system_filesystem_usage_bytes` | Sum / Gauge | `By` | +1 | Dung lượng không gian lưu trữ đã dùng và còn trống theo điểm gắn kết (`mountpoint`). Đo **Storage Capacity**. |
| `system.filesystem.inodes.usage` | `system_filesystem_inodes_usage` | Sum / Gauge | `{inode}` | +1 | Số lượng chỉ mục tệp (Inodes) đã dùng theo điểm gắn kết. Đo **Inode Saturation**. |
| `s3.objects.size` | `minio_bucket_usage_total_bytes` | Gauge | `By` | 0 | Dung lượng lưu trữ thực tế tiêu thụ của từng bucket trong MinIO S3. Đo **Data Lake Volume**. |

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

1. **Chuẩn hóa nhãn `system.disk.io.direction` (`v1.24.0`):**
   - Tài liệu OTel SemConv đổi thuộc tính định hướng sang `disk.io.direction`. Trong Prometheus exporter của OTel Collector Contrib, nhãn xuất ra TSDB được duy trì là `direction="read"` hoặc `direction="write"`.
2. **Phân tách `system.disk.io_time` vs `system.disk.operation_time`:**
   - Phiên bản OTel cũ dùng `io_time` để đo thời gian bận rộn của đĩa (%util trong iostat). Chuẩn hiện đại khuyến nghị `operation_time` (đo tổng tích lũy thời gian của mọi I/O request), cho phép tính toán chính xác độ trễ trung bình của từng request bất kể hàng đợi xử lý song song (Queue Depth > 1):
     $$\text{Avg I/O Latency (ms)} = \frac{\Delta \text{operation\_time\_seconds}}{\Delta \text{operations\_total}} \times 1000$$
3. **Cơ chế Fallback Trong Đồ Án:**
   - Trên Grafana Dashboard `04. Compute & OS Kernel (USE)`, Panel 7 sử dụng công thức phòng vệ mẫu số triệt tiêu chia cho 0:
     `(rate(system_disk_operation_time_seconds_total[1m]) / (rate(system_disk_operations_total[1m]) + 0.0001)) * 1000`

