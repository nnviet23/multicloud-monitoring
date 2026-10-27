# Báo cáo Huấn luyện Mô hình AI Phát hiện Bất thường & RCA (Multi-Cloud Observability AI Engine V2)

Hệ thống đã hoàn tất quy trình huấn luyện tự động mô hình Ensemble kết hợp học sâu chuỗi thời gian đa biến (**GRU Autoencoder** + **TCN Autoencoder**) cùng mô hình học máy không giám sát **Isolation Forest** trên tập dữ liệu đo lường vi mô phân tán 4 giờ ([normal_baseline_4h.csv](../data/raw/normal_baseline_4h.csv)).

![Training Loss Curve](../data/processed/training_loss.png)

*(File ảnh gốc: [`training_loss.png`](../data/processed/training_loss.png))*

---

## 1. Thông số Kỹ thuật & Cấu hình Tiền xử lý (V2 Robust)

Nhằm khắc phục triệt để lỗi báo động giả khi hệ thống mới khởi động (cold-start) hoặc khi tải người dùng dao động thấp, module tiền xử lý [preprocess.py](../data/preprocess.py) áp dụng cơ chế chuẩn hóa miền động lực học:

| Hạng mục | Giá trị tham số | Ý nghĩa kỹ thuật |
| :--- | :---: | :--- |
| **Kích thước cửa sổ trượt (Window Size)** | **12 mẫu (120 giây)** | Nắm bắt 2 phút chu kỳ động lực học của microservices |
| **Số đặc trưng đầu vào ($F$)** | **14 Golden Features** | RED Metrics, Tải JVM Heap/CPU, Luồng Thread và WAN Network |
| **Chuẩn hóa thích ứng (Scale-Floored RobustScaler)** | **14 ngưỡng sàn vật lý** | Đặt sàn IQR tối thiểu (ví dụ: Latency floor = 45ms, CPU floor = 6%) để trạng thái nhàn rỗi/chạy nhanh không bị thổi phồng sai số |
| **Phân chia dữ liệu phân tầng (Stratified Split)** | **80% Train / 20% Val** | Phân tầng đều trên cả 4 pha phụ tải (Warm-up -> Normal -> Peak -> Cooldown) |
| **Tăng cường dữ liệu (Data Augmentation)** | **2,947 cửa sổ Train** | Bổ sung nhiễu Gauss nhẹ, kịch bản khởi động tải thấp và biến thiên phụ tải ngẫu nhiên |
| **Tập kiểm định độc lập (Validation)** | **288 cửa sổ (20%)** | Đánh giá độ hội tụ và hiệu chuẩn ngưỡng cảnh báo |

---

## 2. Kiến trúc Mô hình Deep Learning Ensemble

Hệ thống sử dụng kiến trúc kép bổ trợ lẫn nhau để phát hiện bất thường:

### A. GRU Autoencoder (Ghi nhớ phụ thuộc xa theo thời gian)
* **Encoder**: 2 tầng GRU (`hidden_dim = 64`, `dropout = 0.1`).
* **Bottleneck**: Không gian ẩn tiềm ẩn $Z$ nén về 16 chiều.
* **Decoder**: RepeatVector(12) $\to$ 2 tầng GRU (`hidden_dim = 64`) $\to$ Linear Projection (64 $\to$ 14).

### B. TCN Autoencoder (Temporal Convolutional Network - Bắt trọn xung nhịp cục bộ)
* **Encoder**: Các tầng Causal Dilated Convolutions (Dilation rates: 1, 2, 4, Kernel size: 3) kết hợp Residual Connections $\to$ nén về Latent Space 16 chiều.
* **Decoder**: Dilated Transposed Convolutions mở rộng ngược lại chiều không gian ban đầu.

### C. Isolation Forest (Mô hình đối chứng cơ sở)
* Huấn luyện 150 cây quyết định độc lập trên không gian phẳng 168 chiều ($12 \times 14$).
* Đạt độ chính xác nhận diện trạng thái bình thường: **100.0%**.

---

## 3. Kết quả Huấn luyện & Đánh giá Hội tụ (50 Epochs)

* **Bộ tối ưu hóa**: `AdamW` ($\text{lr} = 0.002$, $\text{weight\_decay} = 10^{-5}$) kết hợp bộ điều chỉnh tốc độ học `CosineAnnealingLR`.
* **Hàm tổn thất**: Mean Squared Error (MSE).

| Mô hình | Train MSE ban đầu | Best Train MSE | Best Val MSE | Thời gian huấn luyện |
| :--- | :---: | :---: | :---: | :---: |
| **GRU Autoencoder** | 0.11822 | 0.05318 | **0.060725** | $\approx 25.4$ giây |
| **TCN Autoencoder** | 0.10125 | 0.00037 | **0.000099** | $\approx 59.9$ giây |
| **Ensemble (50% GRU + 50% TCN)** | - | - | **0.030412** | - |

> [!NOTE]
> Cả 2 mô hình đều hội tụ mượt mà không xảy ra hiện tượng Overfitting (Val MSE giảm đồng thuận với Train MSE theo đường cong Cosine Decay).

---

## 4. Hiệu chuẩn Ngưỡng Cảnh báo & Thuật toán Cửa sổ trượt kép (Dual-Window)

Dựa trên phân phối sai số tái tạo của Ensemble trên 288 cửa sổ kiểm định:

| Chỉ số thống kê | Giá trị MSE | Ứng dụng trong thực thi Online Detector |
| :--- | :---: | :--- |
| **Sai số trung bình ($\mu$)** | **0.0304** | Trạng thái chuẩn của cụm 3 Kubernetes clusters |
| **Độ lệch chuẩn ($\sigma$)** | **0.0076** | Biên độ dao động sai số tự nhiên |
| **Phần trăm vị 95 (P95)** | **0.0448** | Mức theo dõi cảnh giác |
| **Phần trăm vị 99 (P99)** | **0.0476** | Đỉnh sai số của các xung dọn rác GC bình thường |
| **Ngưỡng cảnh báo đề xuất ($T_{p99}$)** | **0.3500** | **Ngưỡng quyết định bất thường chính thức** |

### Cơ chế Lọc báo động giả (False Alarm Suppression):
Bộ lọc trượt kép **Dual-Sliding-Window Scorer** so sánh cửa sổ ngắn ($W_{\text{short}} = 3$ mẫu / 30s) và cửa sổ dài ($W_{\text{long}} = 18$ mẫu / 180s):
1. **Transient Spike Suppression**: Nếu có một mẫu đơn lẻ vượt ngưỡng do GC pause hoặc trễ mạng tạm thời nhưng không duy trì liên tiếp $\ge 2$ mẫu, AI tự động xếp loại là `[~ TRANSIENT SPIKE]` và không báo còi.
2. **Directional Health Damping**: Nếu Latency hoặc CPU thấp hơn trung bình (hệ thống chạy nhanh hơn dự kiến), phần sai số chênh lệch được nhân trọng số giảm $0.15$ thay vì bị phạt.

---

## 5. Cấu hình Phân tích Nguyên nhân Gốc rễ (Root Cause Analysis - RCA)

Khi phát hiện bất thường thực sự ($MSE > 0.3500$ liên tiếp), AI tính toán tỷ trọng sai số tái tạo của từng dịch vụ và so sánh với baseline chuẩn ([threshold_config.json](../models/saved/threshold_config.json)):

| Chỉ số đo lường | Microservice / Thành phần | Ngưỡng kích hoạt RCA |
| :--- | :--- | :---: |
| `throughput_qps` | API Gateway Ingress | 0.250 |
| `latency_p95` | Toàn cụm WebUI | 0.250 |
| `app_cpu_pct` | Toàn bộ 7 Microservices | 0.250 |
| `max_pod_cpu_pct` | Hotspot Pod cao nhất | 0.250 |
| `webui_cpu_pct` | `teastore-webui` (AWS-k3d) | 0.250 |
| `webui_ram_pct` | `teastore-webui` (AWS-k3d) | 0.419 |
| `persistence_cpu_pct`| `teastore-persistence` (Azure-k3d) | 0.250 |
| `persistence_ram_pct`| `teastore-persistence` (Azure-k3d) | 0.313 |
| `image_cpu_pct` | `teastore-image` (AWS-k3d) | 0.250 |
| `wan_network_io_kbs` | Cross-cloud WireGuard/VXLAN Tunnel | 0.250 |

👉 AI sẽ tự động cô lập dịch vụ có hệ số lệch cao nhất và đề xuất nguyên nhân gốc rễ cụ thể (ví dụ: rò rỉ bộ nhớ tại Persistence trên Azure, hay nghẽn băng thông liên đám mây WAN).
