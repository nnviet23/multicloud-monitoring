# Báo Cáo Tinh Chỉnh Kiến Trúc, Chuẩn Hóa Telemetry & Khắc Phục Sự Cố Kỹ Thuật
## (Architecture Refactoring, Telemetry Standardization & Issue Resolution Report)

> **Mã tài liệu:** `docs/progress/02_Refactoring_and_Issue_Resolution.md`  
> **Dự án:** Multi-Cloud Observability & Closed-Loop AIOps Platform  
> **Trạng thái:** Đã hoàn thành 100% & Toàn bộ hệ thống ổn định (100% Fixed & Verified)  
> **Phiên bản:** `v4.0.0` (Unified Master Guide)  
> **Tài liệu hợp nhất từ:** `01_implemetation_issue.md`, `02_solution_plan.md`, `05_SigNoz_strategy.md`, `06_Datadog_strategy.md`, `07_codebase_and_architecture_audit.md`, `08_codebase_fix_v1.md`, `09_codebase_audit_v2.md`, `11_dashboard_nodata_resolution.md`, `12_cleanArchitecture.md`

---

## 1. Tổng Quan Quá Trình Kiểm Định & Tinh Chỉnh Hệ Thống (Audit Overview)

Trong quá trình đưa hệ thống từ giai đoạn thử nghiệm lý thuyết lên môi trường chạy thực tế trên máy trạm đa cụm k3d, nhóm phát triển đã tiến hành 2 đợt rà soát mã nguồn quy mô lớn (**Codebase & Architecture Audits v1 & v2**), đối chiếu các thông lệ tốt nhất từ các giải pháp quan sát hàng đầu thế giới (**SigNoz** và **Datadog**), và giải quyết triệt để các rào cản kỹ thuật.

### 1.1. Các vấn đề kiến trúc then chốt đã được chuẩn hóa:
1. **Loại bỏ hoàn toàn thông tin nhạy cảm mã cứng (Zero Plaintext Secrets):**
   - Thay thế toàn bộ mật khẩu, access keys và private keys được nhúng thô trong các tệp manifest bằng các tệp biến môi trường `.env` và Kubernetes Secrets được tạo động qua script tự động.
2. **Phân tách rạch ròi tài khoản lưu trữ đối tượng (Object Storage Credential Segregation):**
   - Phân chia tài khoản truy cập MinIO S3 thành 2 nhóm độc lập: `thanos-s3-creds` (dành riêng cho Thanos) và `otel-s3-creds` (dành riêng cho Tempo và Loki), bảo đảm nguyên tắc đặc quyền tối thiểu.
   - Bổ sung cấu hình `aws_sdk_auth: true` và `insecure: true` để tránh lỗi chứng thực SSL giả lập trên mạng nội bộ MinIO.
3. **Tuân thủ nguyên tắc trách nhiệm đơn lẻ (Single Responsibility Principle - SRP):**
   - Tái cấu trúc lại thư mục manifests: mỗi tệp chỉ định nghĩa đúng một tài nguyên Kubernetes, có tiền tố thứ tự triển khai rõ ràng (`00-namespace.yaml`, `01-secret.yaml`, `02-configmap.yaml`, `03-pvc.yaml`, `04-statefulset.yaml`, `05-service.yaml`).

---

## 2. Chiến Lược Chuẩn Hóa Telemetry Học Hỏi Từ SigNoz & Datadog

### 2.1. Tiếp thu mô hình chuẩn hóa ngữ nghĩa từ SigNoz
Nghiên cứu kiến trúc của SigNoz (nền tảng quan sát mã nguồn mở xây dựng thuần túy trên OpenTelemetry) đã giúp hệ thống giải quyết bài toán định danh đa vùng đám mây:
- **Cơ chế liên kết Pod theo kết nối IP (`pod_association` via `connection`):**
  - Thay vì cố gắng đọc tên Pod qua đường dẫn tệp nhật ký phức tạp, SigNoz sử dụng IP của kết nối socket mạng (`k8sattributes` processor) để tự động đối chiếu với Kubernetes API Server, từ đó gán đúng nhãn `k8s.pod.name`, `k8s.namespace.name`, `k8s.node.name`.
- **Chuẩn hóa nhãn OpenTelemetry Semantic Conventions (Chấm thay vì Gạch dưới):**
  - Loại bỏ hoàn toàn việc gán nhãn thủ công dạng snake_case (`k8s_cluster_name`, `cloud_provider`) trong các câu lệnh biến đổi OTTL.
  - Toàn bộ dữ liệu tại Collector đều sử dụng ký hiệu dấu chấm chuẩn: `k8s.cluster.name`, `cloud.provider`, `cloud.region`, `deployment.environment.name`. Việc chuyển đổi sang dấu gạch dưới snake_case được giao phó hoàn toàn cho bộ xuất `prometheusexporter` xử lý tự động khi tiếp xúc với Prometheus/Thanos.

### 2.2. Tiếp thu mô hình kiểm soát chi phí & thẻ định danh từ Datadog
- **Thẻ định danh thống nhất (Unified Service Tagging):** Áp dụng 3 thẻ cốt lõi xuyên suốt mọi tín hiệu (Metrics, Logs, Traces): `env` (môi trường), `service` (tên dịch vụ) và `version` (phiên bản ứng dụng).
- **Lọc tiếng ồn tại biên (Edge Noise Filtering):** Hủy bỏ các yêu cầu thăm dò sức khỏe (`/actuator/health`, `/healthz`, `/readyz`) ngay tại Collector Spoke để bảo vệ đường truyền WAN khỏi các mẩu tin vô ích.

---

## 3. Phân Tích Chi Tiết Các Lỗi Kỹ Thuật Lớn & Giải Pháp Khắc Phục Triệt Để

### 3.1. Sự cố 1: Xung đột nhãn trùng lặp (Duplicate Label Collision) làm biến mất Metrics
- **Hiện tượng:** Tại OTel Collector Edge và Hub Gateway, `prometheusexporter` liên tục ném lỗi:
  ```text
  failed to convert metric system.cpu.time: duplicate label names in constant and variable labels for metric "system_cpu_time_seconds_total"
  ```
  Hệ quả: Toàn bộ chỉ số tài nguyên máy chủ (`system_*`) và máy ảo Java (`jvm_*`) bị hủy bỏ 100%, dẫn tới việc Dashboard 4 bị trắng hoàn toàn và Dashboard 3 không có dữ liệu Java.
- **Nguyên nhân gốc rễ:**
  - Bộ xuất `prometheusexporter` khi bật `resource_to_telemetry_conversion.enabled: true` sẽ tự động chuyển đổi các Resource Attributes có dấu chấm (`cloud.provider`, `k8s.cluster.name`) thành nhãn Prometheus dạng snake_case.
  - Đồng thời, các câu lệnh OTTL trong Collector lại gán thêm nhãn tĩnh snake_case trùng tên (`attributes["cloud_provider"] = "aws"`). Thư viện Go Client của Prometheus cấm trùng lặp nhãn và chủ động drop metric.
- **Giải pháp xử lý:**
  - Loại bỏ hoàn toàn các dòng gán nhãn snake_case thủ công trong tệp cấu hình OTel Collector.
  - Chỉ giữ lại thuộc tính chuẩn ngữ nghĩa OpenTelemetry dot-notation. Cấu hình lại `prometheusexporter` để tự động chuyển đổi duy nhất một lần.

### 3.2. Sự cố 2: Lỗi cú pháp so sánh chuỗi trong PromQL
- **Hiện tượng:** Dashboard 1 và Dashboard 5 báo lỗi dữ liệu xấu:
  ```text
  bad data, "server_cloud_provider" unexpected string, expected identifier
  ```
- **Nguyên nhân gốc rễ:**
  - Trong PromQL, biểu thức so sánh nhãn chỉ chấp nhận so sánh giữa một nhãn và một chuỗi ký tự cố định nằm trong dấu ngoặc kép (ví dụ: `label = "value"`).
  - Biểu thức cũ trong dashboard viết: `{client_cloud_provider != server_cloud_provider}`. Trình phân tích cú pháp của Prometheus/Thanos không hiểu `server_cloud_provider` ở vế phải và ném lỗi HTTP 400 Bad Request.
- **Giải pháp xử lý:**
  - Chuyển đổi sang phép lọc tường minh giữa các cặp đám mây:
    ```promql
    {client_cloud_provider="aws", server_cloud_provider="azure"} or {client_cloud_provider="azure", server_cloud_provider="aws"}
    ```

### 3.3. Sự cố 3: Lỗi phép tính chia với Empty Vector trong chỉ số SLI Availability
- **Hiện tượng:** Panel `Global System Availability` (Dashboard 1) và `Current Availability SLI` (Dashboard 7) báo lỗi "No Data" khi hệ thống hoạt động hoàn toàn bình thường không có lỗi.
- **Nguyên nhân gốc rễ:**
  - Khi hệ thống vận hành trơn tru với 0 lỗi HTTP 5xx, bộ kết nối OTel Service Graph hoàn toàn không sinh ra chỉ số `traces_service_graph_request_failed_total` (trả về vector rỗng `[]`).
  - Trong đại số PromQL: biểu thức `100 - (traces_failed / traces_total * 100)` khi gặp vector rỗng ở tử số sẽ biến toàn bộ kết quả thành vector rỗng `[]`, khiến Grafana hiểu là không có dữ liệu (No Data).
- **Giải pháp xử lý:**
  - Bổ sung cơ chế bù trừ đường cơ sở số 0 (Zero-Fallback Baseline):
    ```promql
    100 - (
      (
        sum(rate(traces_service_graph_request_failed_total[5m])) 
        or (sum(rate(traces_service_graph_request_total[5m])) * 0)
      ) / sum(rate(traces_service_graph_request_total[5m])) * 100
    )
    ```
  - Khi không có lỗi, tử số tự động lấy giá trị `0.00` và tỷ lệ sẵn sàng hiển thị chính xác là `100%`.

### 3.4. Sự cố 4: Giới hạn của Grafana Tempo Plugin với truy vấn TraceQL
- **Hiện tượng:** Panel `Tempo Distributed TraceQL Explorer (Cross-Cloud Slow & Error Traces)` trên Dashboard 6 báo lỗi:
  ```text
  HTTP 500: backend TraceQL search queries are not supported
  ```
- **Nguyên nhân gốc rễ:**
  - Plugin Grafana Tempo phiên bản Core hiện tại chỉ hỗ trợ cú pháp tìm kiếm `queryType: "traceql"` trên giao diện dòng lệnh Explore (Frontend), chưa hỗ trợ cơ chế chạy truy vấn TraceQL tìm kiếm vết hàng loạt từ tầng máy chủ backend trong các panel bảng điều khiển định kỳ.
- **Giải pháp xử lý:**
  - Xóa bỏ hoàn toàn panel không được hỗ trợ này khỏi file JSON của Dashboard 6 (`logs-traces-deepdive.json`).
  - Điều chỉnh lại tọa độ lưới (`gridPos.y`) của panel kế tiếp từ `y = 32` lên `y = 22`.
  - Kiểm định lại tính hợp lệ của file JSON bằng lệnh `python3 -m json.tool` (xác nhận 100% hợp lệ).

### 3.5. Sự cố 5: Minh bạch hóa và sửa lỗi hiển thị tài nguyên Host trên Dashboard 4
- **Hiện tượng:** Các biểu đồ hiển thị CPU Usage (400%), Memory Usage (9.59 GB) và Disk Space Usage bị lệch hoặc báo No Data.
- **Nguyên nhân gốc rễ & Sự thật kỹ thuật:**
  1. **CPU 400%:** Máy tính vật lý thử nghiệm sở hữu 4 nhân xử lý (`nproc = 4`). Linux node_exporter tính mỗi nhân là 100%, do đó tổng tải cực đại đạt $4 \times 100\% = 400\%$. Đây là số đo thực tế nhưng gây bối rối cho người xem thông thường.
  2. **RAM 9.59 GB:** Đây là giới hạn RAM thực tế được cấu hình cấp phát cho môi trường máy ảo WSL2 (`Mem: 9.6 GiB` theo lệnh `free -h`).
  3. **Ổ cứng No Data:** Biểu thức PromQL bị gắn cứng tên thiết bị `device="/dev/sde"`, trong khi trên môi trường k3d/WSL2, phân vùng đĩa ảo VHDX dung lượng 1007 GB thực tế được gắn kết dưới tên `/dev/sdd` (khoảng 939.72 GiB khả dụng).
- **Giải pháp xử lý:**
  1. **CPU:** Chuẩn hóa công thức về thang đo tỷ lệ phần trăm $0\% - 100\%$ chia đều trên tổng số nhân máy tính:
     ```promql
     sum(rate(node_cpu_seconds_total{mode!="idle"}[1m])) / sum(count by (cpu) (node_cpu_seconds_total{mode="idle"})) * 100
     ```
  2. **RAM:** Chuyển đổi sang hiển thị tỷ lệ phần trăm RAM đang dùng so với tổng RAM khả dụng của máy ảo:
     ```promql
     (sum(node_memory_MemTotal_bytes) - sum(node_memory_MemAvailable_bytes)) / sum(node_memory_MemTotal_bytes) * 100
     ```
  3. **Ổ cứng:** Thay thế bộ lọc tên thiết bị cố định bằng biểu thức chính quy nhận diện động `device=~"/dev/sd.*"`. Đồ thị lập tức nhận diện đúng phân vùng `/dev/sdd` và hiển thị chính xác mức sử dụng là $1.71\%$.

---

## 4. Bảng Tổng Hợp Trạng Thái Khắc Phục Lỗi (Resolution Matrix)

| STT | Vấn đề / Sự cố kỹ thuật | Nguyên nhân gốc rễ | Giải pháp đã áp dụng | Trạng thái |
| :---: | :--- | :--- | :--- | :---: |
| 1 | Mật khẩu mã cứng trong manifests | Không dùng biến môi trường tập trung | Chuyển toàn bộ sang `.env` và k8s secrets | **ĐÃ XỬ LÝ** |
| 2 | Lỗi xác thực MinIO S3 của Thanos | Cấu hình SSL giả lập không đúng | Bổ sung `insecure: true` & `aws_sdk_auth` | **ĐÃ XỬ LÝ** |
| 3 | Mất toàn bộ metrics `system_*` & `jvm_*` | Xung đột nhãn snake_case và dot-notation | Chuẩn hóa thuần OpenTelemetry Semantic | **ĐÃ XỬ LÝ** |
| 4 | Lỗi cú pháp PromQL so sánh chuỗi | Cú pháp sai `{label1 != label2}` | Chuyển sang so sánh tường minh theo cặp | **ĐÃ XỬ LÝ** |
| 5 | Lỗi No Data chỉ số Availability | Phép chia tử số rỗng (Empty vector) | Thêm đường cơ sở bù trừ `or (... * 0)` | **ĐÃ XỬ LÝ** |
| 6 | Lỗi HTTP 500 TraceQL trên Dashboard 6 | Plugin Grafana Tempo chưa hỗ trợ backend | Xóa bỏ panel lỗi và căn chỉnh tọa độ lưới | **ĐÃ XỬ LÝ** |
| 7 | Dashboard 4 Disk Space Usage No Data | Gắn cứng tên thiết bị đĩa `/dev/sde` | Dùng biểu thức chính quy động `device=~"/dev/sd.*"`| **ĐÃ XỬ LÝ** |
| 8 | Dashboard 4 CPU/RAM số liệu khó hiểu | CPU tính theo 4 nhân (400%), RAM cố định | Chuẩn hóa về thang đo chuẩn $0\% - 100\%$ | **ĐÃ XỬ LÝ** |

---

## 5. Kết Luận
Sau quá trình tinh chỉnh và xử lý triệt để, toàn bộ mã nguồn manifests, cấu hình OTel Collector và mô hình hiển thị Grafana Dashboards đã đạt mức độ hoàn thiện cao, tuân thủ nghiêm ngặt các tiêu chuẩn kỹ thuật quốc tế và bảo đảm hệ thống vận hành ổn định lâu dài.
