# Semantic Conventions: CAT-06 JVM & Process Runtime Environment

**Status**: Mixed (JVM Memory & GC Stable, CPU Experimental)  
**Namespace**: `jvm.*`, `process.*`  
**OTel SemConv Domain**: `docs/runtime/jvm-metrics.md`, `docs/runtime/`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-06` quy định chuẩn ngữ nghĩa đo lường môi trường thực thi máy ảo Java (Java Virtual Machine Runtime) và tiến trình hệ điều hành (OS Process).

Trong đồ án, toàn bộ 6 vi dịch vụ nghiệp vụ của TeaStore (`teastore-webui`, `teastore-auth`, `teastore-image`, `teastore-recommender`, `teastore-registry`, `teastore-persistence`) đều được viết bằng Java và chạy trên máy chủ ứng dụng Apache Tomcat. Telemetry được thu thập tự động thông qua **OpenTelemetry Java Instrumentation Agent v2.10.0** nhúng trong biến `CATALINA_OPTS`.

`CAT-06` là nguồn tín hiệu sống còn để phát hiện các sự cố kinh điển trong ứng dụng Java:
1. **Rò rỉ bộ nhớ Java Heap (JVM Memory Leak):** Heap Used tăng tiệm cận Heap Committed/Limit mà không thể thu hồi sau các chu kỳ GC.
2. **Hiện tượng Đình trệ do Thu gom Rác (Stop-The-World GC Stalls):** Thời gian tạm dừng tiến trình Java do Garbage Collector (`jvm.gc.duration`) kéo dài hàng trăm mili-giây, làm tăng vọt độ trễ P99 của toàn bộ hệ thống.
3. **Cạn kiệt luồng xử lý Tomcat (Thread Pool Exhaustion):** Số lượng luồng JVM (`jvm.thread.count`) chạm trần do các request bị nghẽn đợi I/O cơ sở dữ liệu.

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `jvm.memory.type` | `jvm_memory_type` / `type` | Stable | Required [1] | string | Phân loại vùng nhớ máy ảo Java. | `heap`, `non_heap` |
| `jvm.memory.pool.name` | `pool` | Stable | Recommended | string | Tên phân vùng quản lý bộ nhớ thế hệ của JVM. | `G1 Eden Space`, `G1 Old Gen`, `Metaspace` |
| `jvm.gc.action` | `action` | Stable | Required [2] | string | Loại hành động thu gom rác của Garbage Collector. | `end of major GC`, `end of minor GC` |
| `jvm.gc.name` | `gc` | Stable | Required [2] | string | Tên của thuật toán / bộ thu gom rác JVM đang kích hoạt. | `G1 Young Generation`, `G1 Old Generation` |
| `jvm.thread.daemon` | `daemon` | Stable | Recommended | boolean | Cờ đánh dấu luồng nền Daemon của JVM. | `true`, `false` |
| `process.pid` | `process_pid` | Stable | Recommended | int | Mã định danh tiến trình hệ điều hành của JVM. | `1` |
| `process.runtime.name` | `runtime_name` | Stable | Recommended | string | Tên môi trường thực thi runtime. | `OpenJDK Runtime Environment` |
| `process.runtime.version` | `runtime_version` | Stable | Recommended | string | Phiên bản chi tiết của máy ảo Java. | `17.0.12+7-Ubuntu` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc có trên mọi metric đo bộ nhớ JVM để phân biệt rõ rệt giữa vùng nhớ đối tượng (`heap`) và vùng nhớ mã bytecode/metaspace (`non_heap`).
- **[2]:** Bắt buộc có trên metric `jvm.gc.duration` để tách biệt Major GC (dừng toàn bộ ứng dụng) và Minor GC.

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

| Metric Name (OTel SemConv) | Prometheus TSDB Name | Instrument Type | Unit (UCUM) | Orientation | Description & USE/RED Role |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `jvm.memory.used` | `jvm_memory_used_bytes` | Gauge | `By` | +1 | Dung lượng bộ nhớ JVM hiện đang sử dụng theo từng vùng nhớ (`heap`/`non_heap`). Đo **JVM Memory Utilization**. |
| `jvm.memory.committed` | `jvm_memory_committed_bytes` | Gauge | `By` | 0 | Dung lượng bộ nhớ JVM đã được hệ điều hành cấp phát và sẵn sàng sử dụng. |
| `jvm.memory.limit` | `jvm_memory_limit_bytes` | Gauge | `By` | 0 | Dung lượng bộ nhớ tối đa cấu hình cho JVM (`-Xmx`). Dùng tính toán khoảng đệm tràn bộ nhớ. |
| `jvm.gc.duration` | `jvm_gc_duration_seconds_sum` / `_count` | Histogram | `s` | +1 | Tổng thời gian và số lần máy ảo Java bị dừng để thực hiện thu gom rác. Đo **Runtime Saturation / GC Stall**. |
| `jvm.thread.count` | `jvm_thread_count` | Gauge | `{thread}` | 0 | Tổng số lượng luồng thực thi đang hoạt động trong JVM. Đo **Thread Saturation**. |
| `jvm.cpu.recent_utilization`| `jvm_cpu_recent_utilization` | Gauge | `1` | 0 | Tỷ lệ phần trăm CPU tiêu thụ riêng bởi tiến trình JVM (giá trị từ 0.0 đến 1.0). Đo **Process CPU Utilization**. |

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

Đây là một trong những khu vực có sự thay đổi tên gọi lớn nhất trong lịch sử phát triển của OpenTelemetry:

1. **Cuộc đại di chuyển từ `process.runtime.jvm.*` sang `jvm.*` (`v1.22.0`):**
   - Theo schema OTel `1.22.0` (PR #241): Nhóm metric máy ảo Java ban đầu mang tiền tố `process.runtime.jvm.*` được đổi tên ngắn gọn thành `jvm.*`:
     - `process.runtime.jvm.memory.usage` $\longrightarrow$ `jvm.memory.usage`
     - `process.runtime.jvm.memory.committed` $\longrightarrow$ `jvm.memory.committed`
     - `process.runtime.jvm.gc.duration` $\longrightarrow$ `jvm.gc.duration`
     - `process.runtime.jvm.threads.count` $\longrightarrow$ `jvm.thread.count`
2. **Chuẩn hóa động từ quá khứ `used` thay cho danh từ `usage` (`v1.24.0`):**
   - Theo schema OTel `1.24.0` (PR #536): Tiếp tục đổi tên metric bộ nhớ:
     - `jvm.memory.usage` $\longrightarrow$ `jvm.memory.used`
3. **Cơ chế Dual SemConv Fallback Trong Đồ Án:**
   - Để tương thích với nhiều phiên bản OTel Java Agent khác nhau (từ agent cũ v1.x đến agent mới v2.10), trên Grafana Dashboard `03. Application & JVM (RED)` (Panel 6) và trong mã nguồn `ai-engine/data/collector.py`, đồ án triển khai **kỹ thuật PromQL Dual-Metric Fallback**:
     ```promql
     # Fallback đo JVM Heap Memory:
     sum by (service_name) (
       jvm_memory_used_bytes{jvm_memory_type="heap"} 
       or process_runtime_jvm_memory_usage_bytes{type="heap"} 
       or process_runtime_jvm_memory_usage_bytes
     ) / (1024*1024)

     # Fallback đo JVM Thread Count:
     sum by (service_name) (
       jvm_thread_count 
       or process_runtime_jvm_threads_count
     )

     # Fallback đo JVM GC Pause Rate (ms/s):
     sum by (service_name) (
       rate(jvm_gc_duration_seconds_sum[1m]) 
       or rate(process_runtime_jvm_gc_duration_seconds_sum[1m])
     ) * 1000
     ```
   - Nhờ cơ chế này, hệ thống đảm bảo thu thập thông suốt 100% telemetry JVM mà không bị phụ thuộc cứng vào bất kỳ phiên bản Java Agent đơn lẻ nào.

