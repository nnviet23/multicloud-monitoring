# ADR-0010: Multi-Cloud Telemetry FinOps Governance & WAN Egress Cost Optimization

## Status
Implemented (Levers Deployed) / Phase 5 Real-Cloud (FinOps Exporter)

*Lưu ý phạm vi:* Các cơ chế kỹ thuật cắt giảm chi phí (`filter/drop_noise`, `tail_sampling` 20% normal + 100% error/high-latency, nén `gzip`, và phân tầng lưu trữ MinIO S3) đã được triển khai hoàn chỉnh. Công cụ định lượng chi phí xuất dữ liệu theo thời gian thực ($C_{\text{egress}}$ FinOps exporter / OpenCost) được quy hoạch cho **Phase 5 (Real-Cloud)** khi chạy trên hạ tầng AWS/Azure thực tế.

## Context
Trong các hệ thống phân tán đa đám mây (Multi-Cloud Architectures), dữ liệu viễn trắc (metrics, logs, traces) được sinh ra liên tục từ hàng trăm pod và dịch vụ. Mặc dù việc thu thập viễn trắc là bắt buộc cho tính ổn định, nó lại tạo ra một gánh nặng tài chính khổng lồ:
1. **Chi phí truyền tải mạng xuyên đám mây (Inter-Cloud Egress Costs):** Các nhà cung cấp dịch vụ đám mây lớn (AWS, Azure, GCP) tính phí truyền dữ liệu ra ngoài Internet (Data Egress) rất cao, thường dao động từ **$0.08 đến $0.12 trên mỗi Gigabyte (GB)** dữ liệu. Nếu một hệ thống microservice truyền tải 1 TB dữ liệu viễn trắc thô mỗi ngày qua WAN, chi phí egress hàng tháng có thể lên tới $2,400 – $3,600 chỉ riêng cho việc giám sát.
2. **Chi phí lưu trữ đĩa cứng thể rắn (SSD Storage Costs):** Lưu trữ toàn bộ chuỗi thời gian metrics và logs thô trên đĩa SSD có chi phí cao gấp 5–8 lần so với lưu trữ đối tượng (Object Storage).
3. **Thiếu khung quản trị tài chính (FinOps Governance Gap):** Các kỹ sư thường bật chế độ debug hoặc thu thập 100% traces mà không nhận thức được tác động chi phí trực tiếp lên ngân sách hạ tầng.

## Decision
Chúng tôi quyết định áp dụng mô hình quản trị tài chính viễn trắc **Multi-Cloud Telemetry FinOps** với các biện pháp kỹ thuật nhằm tối ưu hóa chi phí đường truyền WAN và lưu trữ:

### 1. Mô hình Định lượng Chi phí Truyền tải WAN Egress
Xây dựng công thức ước tính chi phí truyền tải viễn trắc hàng tháng ($C_{\text{egress}}$):
$$C_{\text{egress}} = \sum_{c \in \{\text{spokes}\}} \left( V_{\text{metrics}}^{(c)} + V_{\text{logs}}^{(c)} + V_{\text{traces}}^{(c)} \right) \times P_{\text{egress}}$$
Trong đó:
- $V_{\text{metrics}}^{(c)}, V_{\text{logs}}^{(c)}, V_{\text{traces}}^{(c)}$ là dung lượng dữ liệu viễn trắc truyền qua WAN từ cụm Spoke $c$ (GB/tháng).
- $P_{\text{egress}}$ là đơn giá truyền dữ liệu liên vùng (chuẩn $0.09/GB).

### 2. Chiến lược Tối ưu hóa Chi phí Đa tầng (Multi-Tier Cost Reduction)
Hệ thống triển khai 4 chốt chặn kỹ thuật để tối thiểu hóa $C_{\text{egress}}$:
1. **Lọc nhiễu tại Biên (Edge Noise Elimination):**
   - Bộ xử lý `filter/drop_noise` tại Spoke OTel Collector loại bỏ 100% các yêu cầu kiểm tra sức khỏe Kubernetes (`/health`, `/ready`, `/actuator/health`).
   - *Hiệu quả FinOps:* Giảm trực tiếp từ **60% đến 80%** tổng khối lượng span và log thô trước khi chạm vào giao diện mạng WAN.
2. **Lấy mẫu Thông minh tại Biên (`tail_sampling` 20% Normal & Error-Preserving):**
   - Chỉ chuyển tiếp 20% các trace bình thường qua WAN, nhưng giữ lại 100% các trace có mã trạng thái lỗi (`status.code == ERROR`) hoặc có độ trễ bất thường (`> 1500ms`).
   - *Hiệu quả FinOps:* Giảm thêm 80% dung lượng trace bình thường qua mạng liên cụm.
3. **Nén dữ liệu OTLP gRPC (Gzip / Zstd Compression):**
   - Kích hoạt thuật toán nén `gzip` trên toàn bộ OTLP exporters.
   - *Hiệu quả FinOps:* Giảm thêm 70–85% kích thước payload truyền qua mạng diện rộng.
4. **Phân tầng Lưu trữ và Giảm độ phân giải (Tiered Storage & Downsampling):**
   - Chuyển toàn bộ dữ liệu metrics, logs, traces sang tầng lưu trữ đối tượng MinIO S3 (tiết kiệm ~70% chi phí so với SSD).
   - Thanos Compactor áp dụng chính sách giảm độ phân giải tự động (5m sau 40h, 1h sau 10d), giúp nén dung lượng lưu trữ dài hạn hơn 90% trong khi vẫn giữ khả năng hiển thị xu hướng trong 365 ngày.

## Consequences
### Tích cực (Positive)
- **Cắt giảm tới 75–85% tổng chi phí viễn trắc:** Sự kết hợp giữa lọc tại biên, lấy mẫu thông minh và nén dữ liệu giúp giảm chi phí truyền tải WAN từ mức hàng nghìn USD xuống còn vài trăm USD/tháng trong môi trường quy mô lớn.
- **Không làm giảm chất lượng giám sát SRE:** 100% các lỗi nghiêm trọng, ngoại lệ hệ thống và các điểm nghẽn độ trễ cao đều được bảo toàn trọn vẹn tại trung tâm Hub.
- **Bảo vệ môi trường máy trạm:** Giảm thiểu lượng ghi đĩa I/O và dung lượng ổ cứng bị chiếm dụng trên máy trạm của sinh viên/kỹ sư.

### Tiêu cực & Thách thức (Trade-offs)
- Quá trình nén và giải nén OTLP tiêu tốn một lượng nhỏ chu kỳ CPU trên cả Spoke và Hub.
- Dữ liệu giảm độ phân giải (downsampled metrics) không còn thể hiện các đột biến ngắn hạn (sub-minute spikes) khi xem lại dữ liệu cũ hơn 40 giờ.

## Alternatives considered
1. **Không lọc tại biên mà truyền 100% dữ liệu thô về Hub:** Dễ triển khai ban đầu nhưng chi phí băng thông WAN bùng nổ theo cấp số nhân khi hệ thống mở rộng, vi phạm nguyên tắc thiết kế FinOps.
2. **Lọc toàn bộ trace và chỉ giữ lại metrics:** Tiết kiệm tối đa chi phí nhưng làm mất hoàn toàn khả năng điều tra nguyên nhân gốc rễ và trace RCA khi có sự cố giao dịch.
3. **Sử dụng Kafka làm bộ đệm trung gian liên cụm:** Tăng độ tin cậy nhưng chi phí vận hành cụm Kafka đa vùng làm tăng gấp đôi ngân sách hạ tầng so với kết nối OTLP mTLS trực tiếp.

## References
- FinOps Foundation: Cloud Cost Management & Data Transfer Optimization
- AWS / Azure Data Transfer Pricing Guides (Inter-Region & Internet Egress)
- OpenTelemetry Collector: Performance Tuning & Data Compression Benchmarks
- Thanos Storage Cost Economics: SSD vs Object Storage
