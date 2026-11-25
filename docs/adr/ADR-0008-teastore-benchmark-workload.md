# ADR-0008: TeaStore Microservice Benchmark Architecture & Locust Workload Modeling

## Status
Implemented (Đã triển khai)

## Context
Để đánh giá định lượng tính hiệu quả của nền tảng giám sát đa đám mây (Multi-Cloud Observability Platform), thuật toán phân tích nguyên nhân gốc rễ (RCA) và cơ chế phát hiện bất thường AIOps, hệ thống cần một ứng dụng kiểm thử chuẩn mực (reference benchmark application) đáp ứng các tiêu chí:
1. **Tính chân thực của mô hình phân tán:** Ứng dụng phải thể hiện đầy đủ các đặc tính của hệ thống microservices hiện đại: giao tiếp RPC giữa các dịch vụ, phân tách tầng tính toán và tầng dữ liệu bền vững, gọi cơ sở dữ liệu quan hệ, và tương tác người dùng qua trình duyệt.
2. **Khả năng phân vùng đa đám mây (Multi-Cloud Partitioning):** Kiến trúc phải cho phép chia tách tự nhiên các thành phần trên nhiều cụm k3d khác nhau để mô phỏng tương tác liên đám mây qua mạng WAN.
3. **Mô hình tải có thể lặp lại và mở rộng (Repeatable Workload Generation):** Cần một công cụ sinh tải linh hoạt, có thể định nghĩa bằng mã (Workload-as-Code), mô phỏng chính xác hành vi người dùng e-commerce và hỗ trợ chạy tự động không cần giao diện đồ họa (headless mode) trong CI/CD.

## Decision
Chúng tôi quyết định chọn **SPEC RG TeaStore** làm ứng dụng kiểm thử tham chiếu chính thức và **Locust** làm bộ sinh tải tiêu chuẩn cho toàn bộ dự án:

### 1. Phân vùng Kiến trúc TeaStore Đa Cụm (Multi-Cloud Topology)
TeaStore là bộ benchmark microservice mã nguồn mở được phát triển bởi Nhóm Nghiên cứu Chuẩn mực Hiệu năng SPEC (Standard Performance Evaluation Corporation Research Group). Chúng tôi phân vùng triển khai ứng dụng trên 2 cụm Spoke như sau:
- **Cụm Tính toán `aws-k3d` (Compute Services):**
  - `teastore-webui`: Giao diện web phía người dùng (Tomcat / JSP), tiếp nhận yêu cầu từ người dùng và điều phối các lệnh gọi backend.
  - `teastore-auth`: Xử lý đăng nhập, quản lý phiên làm việc và xác thực người dùng.
  - `teastore-recommender`: Thuật toán gợi ý sản phẩm dựa trên lịch sử xem hàng (tính toán nặng).
  - `teastore-image`: Lưu trữ và phục vụ hình ảnh sản phẩm.
  - `teastore-registry`: Dịch vụ đăng ký và phát hiện dịch vụ (Service Discovery) nội bộ của TeaStore.
- **Cụm Dữ liệu `azure-k3d` (Persistence & Database Services):**
  - `teastore-persistence`: Dịch vụ truy cập dữ liệu nghiệp vụ, chuyển đổi đối tượng qua JPA/Hibernate.
  - `teastore-db`: Cơ sở dữ liệu quan hệ **MySQL 8.0**, lưu trữ thông tin sản phẩm, đơn hàng và tài khoản người dùng.

### 2. Mô hình Tải Thực tế với Locust (`locustfile.py`)
- Sử dụng **Locust** (Python-based Load Testing Tool) đóng gói chạy trong container hoặc chạy trực tiếp từ máy trạm:
  - Định nghĩa kịch bản người dùng chuẩn mực tại `locustfile.py` mô phỏng luồng hành vi mua sắm thực tế:
    1. Truy cập trang chủ (`/tools.descartes.teastore.webui/`)
    2. Đăng nhập tài khoản khách hàng (`/tools.descartes.teastore.webui/loginAction`)
    3. Duyệt danh mục sản phẩm và xem chi tiết mặt hàng
    4. Thêm sản phẩm vào giỏ hàng (`/tools.descartes.teastore.webui/cartAction`)
    5. Thực hiện thanh toán và xác nhận đơn hàng
  - **Phân phối hành vi người dùng:** Phân chia tỷ lệ các tác vụ theo trọng số: 60% duyệt hàng (browse), 25% thao tác giỏ hàng (cart), 15% đặt hàng (checkout).
  - Hỗ trợ các profile tải định lượng:
    - *Baseline Test:* Tải ổn định 20–50 người dùng đồng thời (steady-state) để thiết lập đường cơ sở hiệu năng.
    - *Stress / Spike Test:* Tải tăng đột biến lên 200–300 người dùng đồng thời để kích hoạt bão hòa tài nguyên.
  - Bổ sung bởi các kịch bản tiêm lỗi và HTTP load probes trong `tests/chaos/run_service_faults.py` nhằm kiểm thử tự động các tình huống suy giảm dịch vụ và xác minh telemetry end-to-end.

### 3. Tương quan Viễn trắc Toàn trình (End-to-End Tracing)
- Tất cả các container Java của TeaStore được tự động gắn **OTel Javaagent**:
  - Giao tiếp HTTP giữa `teastore-webui` (trên `aws-k3d`) và `teastore-persistence` (trên `azure-k3d`) tự động lan truyền ngữ cảnh vết W3C (`traceparent`).
  - Cho phép quan sát toàn bộ hành trình của một giao dịch mua hàng từ lúc người dùng nhấp chuột đến các câu lệnh SQL truy vấn vào MySQL.

## Consequences
### Tích cực (Positive)
- **Chuẩn mực khoa học quốc tế:** SPEC RG TeaStore là benchmark được công nhận rộng rãi trong các công trình nghiên cứu hệ thống phân tán và SRE, đem lại giá trị học thuật cao cho đồ án tốt nghiệp.
- **Dễ dàng tái hiện kết quả:** Kịch bản Locust bằng Python cho phép tự động hóa hoàn toàn việc sinh tải, đảm bảo các thí nghiệm đo lường luôn có điều kiện đầu vào đồng nhất.
- **Bộc lộ rõ nét đặc tính mạng WAN:** Việc chia tách WebUI và Persistence qua hai cụm riêng biệt giúp đo lường chính xác tác động của độ trễ mạng WAN lên thời gian phản hồi của người dùng cuối.

### Tiêu cực & Thách thức (Trade-offs)
- Ứng dụng TeaStore dựa trên Java Tomcat có mức chiếm dụng RAM đáng kể (~250–350 MB cho mỗi microservice container), đòi hỏi phải tinh chỉnh cẩn thận cờ JVM `-Xmx` và `-Xms`.
- Cần thời gian khởi tạo và nạp dữ liệu ban đầu (database seeding) cho MySQL khi dựng cụm mới.

## Alternatives considered
1. **Google Microservices Demo (Online Boutique):** Kiến trúc đơn giản hơn nhưng không có thành phần cơ sở dữ liệu quan hệ phong phú và không thuộc bộ chuẩn mực SPEC RG được bình duyệt khoa học.
2. **Spring PetClinic Microservices:** Hạn chế về các luồng tải mua sắm và gợi ý sản phẩm phức tạp, ít được cộng đồng nghiên cứu hiệu năng hệ thống sử dụng làm chuẩn so sánh.
3. **Bộ sinh tải JMeter / k6:** JMeter nặng về giao diện GUI và tiêu tốn nhiều RAM; k6 sử dụng Javascript tốt nhưng Locust viết bằng Python thuần túy cho phép tích hợp trực tiếp với các thư viện AIOps và telemetry verification của dự án.

## References
- SPEC Research Group: TeaStore — A Micro-Service Reference Architecture for Benchmarking
- Locust Documentation: Python-based Load Testing
- OpenTelemetry Javaagent Instrumentation for Apache Tomcat & Spring
