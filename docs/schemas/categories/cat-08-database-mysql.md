# Semantic Conventions: CAT-08 Database Client, Storage & Query Profiling (MySQL)

**Status**: Stable (Client Spans & SQL Attributes) / Experimental (Database Exporter Metrics)  
**Namespace**: `db.*`  
**OTel SemConv Domain**: `docs/db/database-spans.md`, `docs/db/`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-08` quy định chuẩn ngữ nghĩa đo lường cơ sở dữ liệu quan hệ (Relational Database) và các truy vấn dữ liệu từ phía máy khách (Database Client Profiling).

Trong kiến trúc TeaStore, dịch vụ `teastore-persistence` nằm trên cụm `azure-k3d` kết nối trực tiếp với cơ sở dữ liệu **MySQL 8.0** (`teastore-db`:3306) thông qua JDBC Driver.

Hệ thống đo lường của đồ án áp dụng **chiến lược quan sát 3 lớp (3-Layer Telemetry Strategy)** học hỏi từ SigNoz:
1. **Lớp 1: JDBC Client Spans & Metrics (Đo lường 100% Thực tế Hiện hành):**
   - Được OTel Java Agent tự động thu thập từ phía `teastore-persistence`. Ghi nhận chính xác câu lệnh SQL, bảng dữ liệu, thời gian thực thi của từng truy vấn (`$T_{\text{DB}}$`) và trạng thái thành công/lỗi của giao dịch cơ sở dữ liệu.
2. **Lớp 2: Nhật Ký Cơ Sở Dữ Liệu (MySQL Error & Connection Logs):**
   - Được thu thập tại biên bởi OTel `filelog` receiver trên `azure-k3d`. Phục vụ phân tích các lỗi kết nối TCP probe, cảnh báo `Aborted connection`, và slow query logs.
3. **Lớp 3: Chỉ Số Nội Bộ Máy Chủ Database (Extensible via mysqld-exporter):**
   - Các chỉ số nội bộ về Connection Pool (`threads_connected`, `max_connections`) và Buffer Pool (`innodb_buffer_pool_reads`). *(Lưu ý trung thực: Hiện tại đồ án đo đạc hiệu năng DB qua JDBC Client Spans và OS Disk I/O; tầng mysqld-exporter được thiết kế ở trạng thái Planned/Extensible).*

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `db.system` / `db.system.name` | `db_system` | Stable | Required [1] | string | Tên hệ quản trị cơ sở dữ liệu. | `mysql`, `mariadb` |
| `db.name` / `db.namespace` | `db_name` | Stable | Required [1] | string | Tên cơ sở dữ liệu (schema/catalog name) đang thực thi truy vấn. | `teadb` |
| `db.statement` / `db.query.text`| `db_statement` | Stable | Required [2] | string | Nội dung câu lệnh truy vấn cơ sở dữ liệu (đã được làm sạch dữ liệu nhạy cảm). | `SELECT * FROM product WHERE id = ?` |
| `db.operation` | `db_operation` | Stable | Recommended | string | Tên thao tác nghiệp vụ cơ sở dữ liệu. | `SELECT`, `INSERT`, `UPDATE`, `DELETE` |
| `db.sql.table` / `db.collection.name` | `db_table` | Stable | Recommended | string | Tên bảng dữ liệu mục tiêu của câu truy vấn. | `product`, `order`, `user` |
| `db.user` | `db_user` | Stable | Recommended | string | Tên tài khoản người dùng đăng nhập cơ sở dữ liệu. | `teastore`, `root` |
| `net.peer.name` | `server` / `peer_name` | Stable | Required [3] | string | Địa chỉ hostname của máy chủ cơ sở dữ liệu. | `teadb`, `teastore-db` |
| `net.peer.port` | `peer_port` | Stable | Required [3] | int | Cổng dịch vụ lắng nghe của cơ sở dữ liệu. | `3306` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc có trên mọi span JDBC để phân loại công nghệ cơ sở dữ liệu và kích hoạt quy tắc phân tích RCA cơ sở dữ liệu.
- **[2]:** Bắt buộc có trên các trace span truy vấn SQL để AI Engine và SRE phân tích chi tiết câu lệnh chậm.
- **[3]:** Bắt buộc để bộ xử lý Service Graph vẽ chính xác cạnh kết nối từ ứng dụng sang cơ sở dữ liệu.

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

| Metric Name (OTel SemConv) | Prometheus TSDB Name | Instrument Type | Unit (UCUM) | Orientation | Description & USE/RED Role |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `db.client.operation.duration` | `traces_service_graph_request_server_seconds_bucket{server=~"teadb\|teastore-db"}` | Histogram | `s` | +1 | Phân phối thời gian thực thi truy vấn cơ sở dữ liệu phía client. Đo **Database Latency ($T_{\text{DB}}$)**. |
| `db.client.operation.total` | `traces_service_graph_request_total{server=~"teadb\|teastore-db"}` | Counter | `{operation}` | +1 | Tổng số lượng truy vấn cơ sở dữ liệu đã thực hiện. Đo **Database QPS / Rate**. |
| `db.client.operation.errors`| `traces_service_graph_request_total{server=~"teadb\|teastore-db", status_code="STATUS_CODE_ERROR"}` | Counter | `{error}` | +1 | Số lượng truy vấn cơ sở dữ liệu bị lỗi (SQL syntax error, deadlock, timeout). Đo **Database Error Rate**. |
| `mysql.threads.connected` | `mysql_global_status_threads_connected` | Gauge | `{thread}` | 0 | Số lượng kết nối đang mở tới MySQL (*Planned / Extensible via mysqld-exporter*). |
| `mysql.buffer_pool.reads` | `mysql_global_status_innodb_buffer_pool_reads` | Counter | `{read}` | +1 | Số lần đọc đĩa vật lý do không trúng cache Buffer Pool (*Planned / Extensible*). |

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

1. **Chuẩn hóa `db.statement` sang `db.query.text` (`v1.26.0`):**
   - Theo schema OTel `1.26.0` (PR #897): Thuộc tính câu lệnh truy vấn `db.statement` được đổi tên thành `db.query.text` nhằm bao quát cả cơ sở dữ liệu phi quan hệ (NoSQL / Vector DB).
2. **Tiến hóa từ `db.name` sang `db.namespace` (`v1.27.0`):**
   - Tên cơ sở dữ liệu được mở rộng thành `db.namespace` để hỗ trợ đa môi trường catalog/schema.
3. **Cơ chế Fallback Trong Đồ Án:**
   - Trong `ai-engine/inference/detector.py` (hàm phân tích vết thực thi `TempoTraceAnalyzer`), bộ trích xuất span tags kiểm tra linh hoạt cả 2 thế hệ thuộc tính:
     ```python
     sql_statement = span.get("db.query.text") or span.get("db.statement") or "N/A"
     db_name = span.get("db.namespace") or span.get("db.name") or "teadb"
     ```
   - Nhờ vậy, AI Engine trích xuất thông tin truy vấn thành công 100% dù vết thực thi được phát sinh từ OTel SDK thế hệ cũ hay mới.

