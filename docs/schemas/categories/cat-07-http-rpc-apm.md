# Semantic Conventions: CAT-07 Application Performance Monitoring (HTTP & RPC APM)

**Status**: Stable (HTTP Server/Client Spans & RED Metrics)  
**Namespace**: `http.*`, `rpc.*`, `service.*`  
**OTel SemConv Domain**: `docs/http/`, `docs/rpc/`, `docs/general/`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-07` quy định chuẩn ngữ nghĩa đo lường hiệu năng ứng dụng (Application Performance Monitoring - APM) ở tầng giao thức ứng dụng HTTP (REST API) và RPC (Remote Procedure Call - Java RMI :1099).

Trong hệ thống TeaStore, các microservices giao tiếp với nhau bằng hai phương thức:
1. **HTTP/REST:** Khách hàng duyệt WebUI, WebUI gọi các microservices (`teastore-auth`, `teastore-image`, `teastore-recommender`, `teastore-persistence`) qua giao thức HTTP/1.1 JSON.
2. **Java RMI / Registry:** Các microservices đăng ký vị trí và khám phá dịch vụ thông qua RMI Registry (`teastore-registry`:1099).

`CAT-07` là nền tảng của phương pháp luận **RED Method (Rate, Errors, Duration)**:
- **Rate (Tốc độ Yêu cầu):** Đo lường số lượng yêu cầu đến hệ thống theo đơn vị Requests Per Second (RPS / QPS).
- **Errors (Tỷ lệ Lỗi):** Tỷ lệ các cuộc gọi trả về mã lỗi HTTP 5xx hoặc RPC exceptions.
- **Duration (Thời gian Thực thi):** Phân phối độ trễ (P50, P90, P99) của các cuộc gọi máy chủ và máy khách.

Ngoài ra, `CAT-07` cung cấp các nhãn ngữ cảnh liên kết Service-to-Service (`service.name`, `service.peer.name` / `peer.service`) giúp bộ kết nối `servicegraphconnector` tại OTel Gateway tổng hợp biểu đồ cấu trúc liên kết mạng lưới dịch vụ (Service Graph Topology).

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `service.name` | `service_name` / `service` | Stable | Required [1] | string | Tên định danh logic của microservice. | `teastore-webui`, `teastore-persistence` |
| `service.version` | `service_version` | Stable | Recommended | string | Phiên bản ứng dụng microservice. | `1.4.1` |
| `http.request.method` | `http_method` / `method` | Stable | Required [2] | string | Phương thức yêu cầu HTTP chuẩn. | `GET`, `POST` |
| `http.response.status_code` | `http_status_code` / `status_code` | Stable | Required [2] | int | Mã trạng thái phản hồi HTTP. | `200`, `404`, `500`, `503` |
| `url.path` | `url_path` / `path` | Stable | Required [2] | string | Đường dẫn URI của endpoint yêu cầu (không kèm query parameters). | `/tools.descartes.teastore.webui/login` |
| `rpc.system` | `rpc_system` | Stable | Conditionally Required [3] | string | Hệ thống công nghệ Remote Procedure Call. | `java_rmi` |
| `rpc.service` | `rpc_service` | Stable | Conditionally Required [3] | string | Tên interface dịch vụ RPC được triệu gọi. | `tools.descartes.teastore.registry.IRegistry` |
| `rpc.method` | `rpc_method` | Stable | Conditionally Required [3] | string | Tên phương thức RPC được gọi từ xa. | `getService` |
| `service.peer.name` | `peer.service` / `server` | Stable | Required [4] | string | Tên định danh logic của dịch vụ đối tác phía bên kia cuộc gọi. | `teastore-persistence`, `teadb` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc có trên 100% tín hiệu traces, metrics và logs để nhận diện ứng dụng phát sinh.
- **[2]:** Bắt buộc có trên các span HTTP và metric thời gian thực thi HTTP.
- **[3]:** Bắt buộc đối với các cuộc gọi đăng ký và tìm kiếm vi dịch vụ qua Java RMI :1099.
- **[4]:** Cực kỳ quan trọng để liên kết các cạnh (Edges) trong sơ đồ Topology. Được làm giàu qua OTTL Peer Service Enrichment tại Hub Gateway.

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

| Metric Name (OTel SemConv) | Prometheus TSDB Name | Instrument Type | Unit (UCUM) | Orientation | Description & USE/RED Role |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `http.server.request.duration` | `http_server_duration_seconds_bucket` | Histogram | `s` | +1 | Phân phối thời gian xử lý yêu cầu phía máy chủ (Server Latency). Đo **Duration (P50/P90/P99)**. |
| `http.client.request.duration` | `http_client_duration_seconds_bucket` | Histogram | `s` | +1 | Phân phối thời gian thực hiện cuộc gọi phía máy khách (Client Latency). Dùng để tính toán độ trễ WAN ($T_{\text{WAN}}$). |
| `servicegraph.request.total` | `traces_service_graph_request_total` | Counter | `{request}` | +1 | Tổng số lượng yêu cầu giao tiếp giữa 2 dịch vụ (`client` $\rightarrow$ `server`). Đo **Rate (QPS)** và **Error Rate (%)**. |
| `servicegraph.request.duration` | `traces_service_graph_request_server_seconds_bucket` | Histogram | `s` | +1 | Phân phối độ trễ xử lý liên dịch vụ tổng hợp từ spans. Đo **Service-to-Service Duration**. |

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

1. **Chuẩn hóa `http.status_code` sang `http.response.status_code` (`v1.21.0`):**
   - Theo schema OTel `1.21.0` (PR #43): Đổi tên thuộc tính mã trạng thái phản hồi HTTP để phân biệt rõ rệt với status code của tầng giao vận hoặc proxy.
2. **Chuẩn hóa `http.server.duration` sang `http.server.request.duration` (`v1.22.0`):**
   - Theo schema OTel `1.22.0` (PR #224): Đổi tên metric để đồng nhất cấu trúc phân cấp `{protocol}.{role}.request.{metric}`.
3. **Tiến hóa từ `peer.service` sang `service.peer.name` (`v1.39.0`):**
   - Theo schema OTel `1.39.0`: Thuộc tính định danh dịch vụ đối tác `peer.service` được tái cấu trúc thành `service.peer.name`.
4. **Cơ chế Fallback Trong Đồ Án:**
   - Tại OTel Hub Gateway (`k8s/base/otel-collector/gateway/03-configmap.yaml`), bộ xử lý OTTL gán đồng thời cả hai thuộc tính để tương thích hoàn toàn với cả `servicegraphconnector` và các panel Grafana:
     ```yaml
     - set(span.attributes["peer.service"], "teadb") where span.attributes["db.system"] == "mysql"
     - set(span.attributes["service.peer.name"], "teadb") where span.attributes["db.system"] == "mysql"
     ```
   - Nhờ đó, sơ đồ Topology Node Graph luôn hiển thị chính xác cạnh kết nối tới cơ sở dữ liệu `teadb` mà không bị lỗi `unknown_service`.

