# ADR-0006: OpenTelemetry End-to-End Pipeline, Edge Filtering & Semantic Normalization

## Status
Implemented (Đã triển khai)

## Context
Thu thập và xử lý dữ liệu viễn trắc (metrics, logs, traces) từ các microservice phân tán trên nhiều cụm đám mây đòi hỏi một kiến trúc mở, không xâm lấn (non-intrusive), có khả năng tối ưu hóa băng thông WAN và chuẩn hóa dữ liệu tập trung.

Những thách thức kỹ thuật lớn:
1. **Chi phí thay đổi mã nguồn (Instrumentation Friction):** Việc can thiệp trực tiếp vào mã nguồn Java của TeaStore để gắn các thư viện SDK thủ công gây tốn kém thời gian, khó bảo trì và dễ gây lỗi trong quá trình nâng cấp phiên bản.
2. **Nhiễu dữ liệu và lãng phí băng thông WAN (WAN Egress Waste):** Các cuộc thăm dò sức khỏe định kỳ (Kubernetes liveness/readiness probes như `/health`, `/ready`) sinh ra lượng trace và log khổng lồ chiếm tới 60–80% khối lượng viễn trắc. Nếu truyền toàn bộ lượng dữ liệu này qua mạng liên đám mây WAN, chi phí băng thông (egress cost) sẽ tăng vọt.
3. **Độ phân tán của dữ liệu và không đồng nhất định danh (Semantic Collision):** Dữ liệu thu thập từ các nhà cung cấp đám mây khác nhau có thể sử dụng các nhãn không thống nhất (ví dụ: `cluster`, `cluster_name`, `k8s-cluster`), dẫn đến xung đột hoặc đứt gãy sơ đồ tô-pô dịch vụ (Service Graph Topology).

## Decision
Chúng tôi quyết định chuẩn hóa toàn bộ luồng thu thập và xử lý viễn trắc theo **Kiến trúc Phương án A** (Edge-Filtered Ingestion with Centralized Processing & Batch Ingestion) dựa trên OpenTelemetry:

### 1. Thu thập Không Xâm lấn (Zero-Code Instrumentation)
- Trên cụm **k3d cục bộ**, sử dụng **`initContainer`** gắn **OTel Javaagent bytecode** vào các pod TeaStore (`webui`, `auth`, `recommender`, `image`, `registry`, `persistence`) thông qua biến môi trường `JAVA_TOOL_OPTIONS` (tích hợp **OpenTelemetry Operator** + `Instrumentation` CR được hoãn sang **Phase 5 Real-Cloud** để tiết kiệm RAM).
- Thu thập đầy đủ distributed traces (W3C Trace Context propagation), JVM metrics, và tự động thu thập log tương quan (Trace-Log Correlation).
- Thu thập chỉ số cơ sở dữ liệu qua **`mysql` receiver** trên cụm `azure-k3d`.

### 2. Trình tự Bộ xử lý Bắt buộc (Strict Processor Pipeline Ordering)
Mọi cấu hình OTel Collector (cả tại Spoke và Hub) đều phải tuân thủ nghiêm ngặt thứ tự sắp xếp processor:
$$\text{Memory Limiter} \longrightarrow \text{Filter} \longrightarrow \text{Transform} \longrightarrow \text{Batch} \longrightarrow \text{Exporter}$$
- **`memory_limiter`:** Đảm bảo collector không bị `OOMKilled` bằng cách chủ động ngắt nhận dữ liệu khi bộ nhớ chạm ngưỡng giới hạn.
- **`filter`:** Loại bỏ dữ liệu rác trước khi tốn tài nguyên xử lý logic.
- **`transform`:** Thực hiện biến đổi OTTL trên tập dữ liệu đã được làm sạch.
- **`batch`:** Gom cụm dữ liệu để tối ưu hóa nén và truyền mạng.

### 3. Lọc Nhiễu tại Biên (Edge Pre-Filtering) & Lấy Mẫu 20%
- Tại các Spoke Collector (`aws-k3d`, `azure-k3d`):
  - Kích hoạt `filter/drop_noise`: Loại bỏ 100% các traces và logs phát sinh từ Kubernetes probes (`/health`, `/ready`, `/actuator/health`).
  - Áp dụng bộ lấy mẫu **`tail_sampling`** ngay tại biên kết hợp bảo tồn lỗi: giữ **100%** các trace có trạng thái `ERROR` hoặc độ trễ cao (`> 1500ms`), và lấy mẫu **20%** các trace bình thường trước khi gửi qua WAN.

### 4. Xử lý Tập trung tại Hub: Lấy mẫu Đuôi (Tail-Based Sampling) & OTTL
- Tại Hub Central Gateway:
  - **`tail_sampling`:** Đánh giá toàn bộ vòng đời của trace sau khi đã thu thập đủ các spans; bảo tồn 100% trace có lỗi HTTP 5xx hoặc độ trễ giao dịch vượt quá 1500ms (`duration > 1500ms`).
  - **OTTL Normalization:** Sử dụng OpenTelemetry Transformation Language để chuẩn hóa toàn bộ siêu dữ liệu theo đúng chuẩn **OpenTelemetry Semantic Conventions v1.45.0**:
    - `deployment.environment.name`
    - `cloud.provider` (ví dụ: `aws`, `azure`, `local`)
    - `cloud.region`
    - `k8s.cluster.name`
    - `k8s.pod.uid`
  - **Che giấu thông tin nhạy cảm (PII Masking — Future Hardening):** Sử dụng regex OTTL để ẩn thông tin thẻ tín dụng, mật khẩu, và email trong query parameters và log bodies (được lên kế hoạch tăng cường cho Phase 5).

### 5. Tiền Tổng hợp Tô-pô Dịch vụ (Service Graph Topology Connector)
- Tích hợp **`servicegraphconnector`** tại Hub OTel Gateway:
  - **Quy tắc cốt lõi:** Pipeline `traces/servicegraph` phải nhận **100% luồng trace tô-pô** trước khi bộ xử lý `tail_sampling` cắt tỉa traces, nhằm đảm bảo đồ thị quan hệ giữa các dịch vụ không bị đứt gãy.
  - Tự động sinh ra chuỗi thời gian metric liên kết dịch vụ `traces_service_graph_request_total` và xuất trực tiếp vào Thanos Receive.

## Consequences
### Tích cực (Positive)
- **Tiết kiệm 60–80% chi phí băng thông WAN:** Nhờ loại bỏ dữ liệu probe rác và lấy mẫu thông minh ngay tại biên Spoke.
- **Dữ liệu chuẩn hóa nhất quán:** Khắc phục hoàn toàn tình trạng xung đột nhãn; hỗ trợ truy vấn tương quan chéo (cross-linking) giữa Prometheus, Loki và Tempo dễ dàng.
- **Không xâm phạm mã nguồn:** Đội ngũ phát triển không cần chỉnh sửa code hay build lại artifact của TeaStore.

### Tiêu cực & Thách thức (Trade-offs)
- Javaagent bytecode injection làm tăng nhẹ thời gian khởi động (startup time) của container (~3–5 giây) và tiêu tốn thêm ~50MB RAM trên mỗi pod microservice.
- Bộ xử lý `tail_sampling` tại Hub đòi hỏi cấu hình dung lượng bộ nhớ đệm (buffer) đủ lớn để lưu giữ các spans chờ trace hoàn tất.

## Alternatives considered
1. **Lấy mẫu 100% toàn bộ dữ liệu (Full Ingestion):** Quá tải dung lượng lưu trữ đĩa cứng và làm vọt chi phí truyền tải WAN, không thực tế trong các hệ thống quy mô lớn.
2. **Viết mã viễn trắc thủ công (Manual SDK Instrumentation):** Tốn hàng tuần công sức tái cấu trúc mã nguồn TeaStore, làm mất đi tính chuẩn hóa nguyên bản của ứng dụng mẫu SPEC RG.
3. **Sử dụng Fluentbit/Promtail riêng biệt cho logs và Jaeger cho traces:** Dẫn đến sự phân mảnh công cụ, tiêu tốn nhiều tài nguyên hơn so với kiến trúc hội tụ hoàn toàn vào OpenTelemetry Collector.

## References
- OpenTelemetry Specification: Semantic Conventions for Telemetry Data (v1.45.0)
- OpenTelemetry Collector Contrib: Processors (Filter, Transform OTTL, Tail Sampling)
- OpenTelemetry Service Graph Connector Documentation
- SPEC RG DevOps Working Group: Microservice Monitoring Best Practices
