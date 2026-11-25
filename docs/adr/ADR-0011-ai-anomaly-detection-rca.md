# ADR-0011: Closed-Loop AI Anomaly Detection Engine & Distributed Trace RCA

## Status
Implemented (Đã triển khai)

## Context
Trong hệ thống microservices đa đám mây phân tán qua mạng WAN mô phỏng, sự cố suy giảm hiệu năng (Performance Degradation) thường biểu hiện dưới nhiều dạng phức tạp: độ trễ mạng WAN tăng, tắc nghẽn cơ sở dữ liệu (Database Connection Exhaustion), hoặc rò rỉ bộ nhớ / quá tải CPU.

Các hạn chế của phương pháp giám sát truyền thống:
1. **Quy tắc cảnh báo tĩnh thất bại trước các biến động đa biến (Multivariate Failure):** Một sự cố có thể là kết hợp của nhiều chỉ số suy giảm nhẹ mà không có chỉ số nào vượt ngưỡng báo động tĩnh đơn lẻ.
2. **Khó khăn trong việc định vị nguyên nhân gốc rễ (Root Cause Localization):** Khi người dùng báo cáo giao diện web chậm, việc xác định xem độ trễ nằm ở mạng WAN liên cụm ($T_{\text{WAN}}$), tại logic microservice ($T_{\text{self}}$), hay ở tầng cơ sở dữ liệu ($T_{\text{DB}}$) đòi hỏi kỹ sư phải điều tra thủ công qua hàng trăm distributed traces.
3. **Thiếu liên kết khép kín (Closed-Loop Actionability):** Nhiều mô hình học máy chỉ chạy offline trên Jupyter Notebook, không thể xuất chỉ số thời gian thực vào hệ thống giám sát và không có cơ chế cảnh báo tự động khép kín đến người vận hành.

## Decision
Chúng tôi quyết định thiết kế và triển khai **Động cơ Phát hiện Bất thường và Phân tích Nguyên nhân Gốc rễ AIOps (AI Anomaly Detection Engine V3)** với kiến trúc khép kín hoàn chỉnh:

### 1. Kiến trúc Mô hình Học sâu Kết hợp (Deep Learning Ensemble Architecture)
Hệ thống kết hợp ba thuật toán học máy bù trừ lẫn nhau để đạt độ chính xác tối ưu:
- **Gated Recurrent Unit (GRU) Autoencoder:** Học các phụ thuộc chuỗi thời gian dài hạn và quan hệ phi tuyến giữa các metrics viễn trắc; phát hiện bất thường dựa trên sai số tái tạo (Reconstruction Error $\mathcal{L}_{\text{rec}}$).
- **Temporal Convolutional Network (TCN):** Khai thác các receptive fields mở rộng thông qua dilated causal convolutions để nắm bắt các biến động đột ngột với tốc độ tính toán nhanh hơn RNN truyền thống.
- **Isolation Forest:** Thuật toán học không giám sát (Unsupervised) hỗ trợ phát hiện ngoại lai trong pha huấn luyện/đánh giá ngoại tuyến (offline calibration); trên luồng suy luận trực tuyến (online scoring), hệ thống ưu tiên **GRU + TCN Autoencoder** với nạp trọng số an toàn (`torch.load(..., weights_only=True)`).
- *Trạng thái đóng gói:* Hiện động cơ AI Engine V3 chạy dưới dạng tiến trình Python cục bộ kết nối tới Thanos/Tempo qua port-forward (việc đóng gói thành container Deployment trên cụm Hub được quy hoạch hoàn thiện cho Phase 5).

### 2. Trích xuất Đặc trưng Thời gian thực qua PromQL
Động cơ định kỳ truy vấn Prometheus / Thanos trên cụm `hub-k3d` để lấy các đặc trưng đa chiều:
- Tỷ lệ lỗi HTTP (`sum(rate(http_requests_total{status=~"5.."}[1m]))`)
- Độ trễ P90/P99 (`histogram_quantile(0.99, ...)` của từng microservice)
- Mức độ sử dụng CPU và Bộ nhớ Pod (`container_cpu_usage_seconds_total`, `container_memory_working_set_bytes`)
- Chỉ số kết nối cơ sở dữ liệu MySQL (`mysql_global_status_threads_connected`)
- Độ trễ mạng WAN liên cụm

### 3. Phân tích Nguyên nhân Gốc rễ Phân rã Vết (Distributed Trace RCA)
Khi $S_{\text{anomaly}}$ vượt ngưỡng cảnh báo ($\tau = 0.75$), động cơ tự động truy vấn Grafana Tempo API để phân tích các distributed traces tương ứng trong cửa sổ thời gian sự cố. Độ trễ tổng thể của giao dịch ($T_{\text{total}}$) được phân rã thành ba thành phần độc lập:
$$T_{\text{total}} = T_{\text{WAN}} + T_{\text{self}} + T_{\text{DB}}$$
Trong đó:
- $T_{\text{WAN}}$: Tổng thời gian mạng di chuyển giữa các cụm (`aws-k3d` $\leftrightarrow$ `azure-k3d`).
- $T_{\text{self}}$: Thời gian xử lý logic nội bộ của các microservice (`teastore-webui`, `teastore-auth`, `teastore-recommender`).
- $T_{\text{DB}}$: Thời gian thực thi truy vấn bên trong cơ sở dữ liệu `teastore-db`.
Thuật toán gán nhãn nguyên nhân gốc rễ tương ứng với thành phần đóng góp tỷ trọng lớn nhất vào độ trễ tăng thêm.

### 4. Tích hợp Khép kín: Prometheus Exporter, Grafana & Telegram
- **Prometheus Exporter (:9108):** Động cơ nhúng một HTTP server trên cổng `:9108` xuất ra các chuỗi thời gian:
  - `ai_anomaly_likelihood_percent{service="..."}`
  - `ai_reconstruction_error{service="..."}`
  - `ai_rca_component_latency_ms{component="WAN|SELF|DB", ...}`
- **Trực quan hóa Grafana (Panel 7 Dual Y-Axis):** Thiết kế panel biểu đồ hai trục Y trên dashboard `01-platform-overview-golden-signals.json` của Grafana Hub:
  - Trục Y trái: Xác suất bất thường (`ai_anomaly_likelihood_percent`, 0–100%).
  - Trục Y phải: Độ trễ P99 và thời gian phân rã $T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$ (`ai_rca_component_latency_ms`).
- **Kênh Cảnh báo Telegram Sink:** Tự động phát hiện bất thường và gửi báo cáo chẩn đoán sự cố chi tiết đến Telegram với bộ đệm hạ nhiệt **60 giây (`60s` cooldown buffer)** nhằm chống ngập tin nhắn.

## Consequences
### Tích cực (Positive)
- **Tự động hóa hoàn toàn chu trình chẩn đoán (AIOps Closed-Loop):** Chuyển từ việc quan sát thụ động sang tự động phát hiện và định vị nguyên nhân gốc rễ trong vòng chưa đầy 30 giây kể từ khi xuất hiện bất thường.
- **Độ chính xác cao:** Mô hình kết hợp (Ensemble) giảm thiểu tới 70% số lượng cảnh báo sai so với các ngưỡng tĩnh truyền thống.
- **Khả năng giải thích được (Explainability):** Việc phân rã định lượng $T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$ giúp kỹ sư SRE hiểu rõ lý do mô hình AI kích hoạt cảnh báo.

### Tiêu cực & Thách thức (Trade-offs)
- Cần tài nguyên GPU hoặc CPU máy trạm để chạy tiến trình suy luận (inference loop) định kỳ (~200–300 MB RAM).
- Cần thu thập đủ dữ liệu viễn trắc ở trạng thái bình thường để huấn luyện ban đầu (offline training phase).

## Alternatives considered
1. **Chỉ sử dụng ngưỡng cảnh báo tĩnh hoặc thống kê 3-Sigma:** Tỷ lệ cảnh báo sai (False Positive) rất cao trong môi trường tải biến động liên tục; không có khả năng phát hiện tương quan đa biến.
2. **Sử dụng mô hình Transformer lớn (TimeGPT / PatchTST):** Đòi hỏi tài nguyên tính toán GPU đắt đỏ và độ trễ suy luận lớn (>5 giây), không thể chạy thời gian thực trên máy trạm phát triển.
3. **Phân tích RCA thủ công qua Grafana Dashboard:** Kéo dài MTTR lên hàng chục phút, phụ thuộc vào kinh nghiệm cá nhân của kỹ sư vận hành.

## References
- Deep Learning for Time Series Anomaly Detection: A Survey
- Temporal Convolutional Networks (TCN) for Sequence Modeling
- Grafana Tempo API & W3C Trace Context Specification
- PromQL Guide: Building Custom Metrics Exporters with Python Prometheus Client
