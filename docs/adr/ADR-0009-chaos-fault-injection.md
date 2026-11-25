# ADR-0009: Chaos Engineering Framework, Fault Injection Matrix & Quantitative Validation

## Status
Implemented (Đã triển khai)

## Context
Để chứng minh độ tin cậy của nền tảng quan sát, tính hiệu quả của các cảnh báo SLO và khả năng tự động chẩn đoán nguyên nhân gốc rễ (RCA) của động cơ AIOps, hệ thống không thể chỉ được kiểm thử trong điều kiện hoạt động lý tưởng.

Các yêu cầu kiểm thử hỗn loạn (Chaos Engineering Requirements):
1. **Mô phỏng sự cố đa tầng có kiểm soát:** Cần khả năng tiêm các loại lỗi đa dạng tương ứng với các tình huống sự cố thực tế trong môi trường sản xuất đa đám mây (mạng WAN gián đoạn, dịch vụ quá tải, lỗi cơ sở dữ liệu, rò rỉ bộ nhớ).
2. **Khả năng lặp lại và định lượng (Reproducibility & Quantitative SRE Metrics):** Mỗi thử nghiệm hỗn loạn phải có thể kích hoạt tự động theo kịch bản xác định, có thời gian bắt đầu và kết thúc rõ ràng, và đo lường được bằng các chỉ số định lượng SRE như Thời gian Phát hiện Sự cố (MTTD), Thời gian Khôi phục (MTTR) và Tốc độ Tiêu hao Ngân sách Lỗi (Error Budget Burn Rate).
3. **An toàn khi thử nghiệm (Blast Radius Containment):** Quá trình tiêm lỗi không được làm hỏng toàn bộ môi trường máy trạm hoặc gây treo các cụm Kubernetes vĩnh viễn; phải có cơ chế phục hồi tức thì sau khi kết thúc kịch bản.

## Decision
Chúng tôi quyết định xây dựng khung thử nghiệm hỗn loạn (Chaos Engineering Framework) với **Ma trận Tiêm Lỗi Đa Tầng (Multi-Tier Fault Injection Matrix)** kết hợp phương pháp xác minh định lượng SRE:

### 1. Ma trận Tiêm Lỗi (Fault Injection Matrix)
Hệ thống hỗ trợ 4 nhóm kịch bản tiêm lỗi chuẩn hóa:

| Mã Kịch bản | Tên Kịch bản | Lớp Kiến trúc | Cơ chế Thực thi | Hành vi Mô phỏng |
| :--- | :--- | :--- | :--- | :--- |
| **CHAOS-01** | WAN Degradation (Latency & Loss) | Network Layer (Giữa Hub và Spoke) | Linux `tc netem` trên giao diện `eth0` container | Tăng độ trễ liên cụm lên 200–500ms, tỷ lệ mất gói tin 5–10% |
| **CHAOS-02** | Microservice Crash & Churn | Application Layer (`aws-k3d`) | Kubernetes Pod Deletion / Process Signal (`SIGKILL`) | Đột ngột xóa Pod `teastore-webui` hoặc `teastore-auth`, gây gián đoạn dịch vụ tạm thời |
| **CHAOS-03** | Database Lock & Latency | Data Layer (`azure-k3d`) | MySQL Queries (`SLEEP()`, Lock Contention) | Chạy câu lệnh SQL giữ khóa bảng hoặc trì hoãn phản hồi trên `teastore-db` |
| **CHAOS-04** | Resource Throttling (CPU/Memory Stress) | Infrastructure Layer | Linux `stress-ng` hoặc giới hạn cgroups | Bão hòa 100% CPU hoặc làm cạn kiệt bộ nhớ container gây `OOMKilled` |

### 2. Chu trình Thực nghiệm Hỗn loạn Khoa học (Scientific Chaos Loop)
Mỗi thử nghiệm tiêm lỗi đều tuân thủ nghiêm ngặt quy trình 5 bước:
1. **Trạng thái Ổn định (Steady-State Baseline):** Chạy tải Locust trong 5–10 phút để thiết lập đường cơ sở viễn trắc ổn định (SLO burn rate = 0, P99 latency < 200ms).
2. **Hình thành Giả thuyết (Hypothesis Formulation):** Đưa ra giả thuyết kiểm định (ví dụ: *Khi tiêm lỗi mạng WAN 200ms vào kết nối Hub-Spoke, SLO burn rate của TeaStore sẽ vượt ngưỡng cảnh báo 14.4x trong vòng 2 phút và Robusta sẽ bắn thông báo về Telegram trong 60 giây*).
3. **Kích hoạt Tiêm Lỗi (Fault Injection Execution):** Thực thi lệnh tiêm lỗi có thời hạn cố định (thường từ 3–5 phút).
4. **Thu thập và Đánh giá Chỉ số SRE:**
   - **MTTD (Mean Time to Detect):** Khoảng thời gian từ lúc tiêm lỗi đến khi cảnh báo đầu tiên kích hoạt trên Alertmanager / Robusta.
   - **MTTR (Mean Time to Recover):** Khoảng thời gian từ lúc ngừng tiêm lỗi đến khi SLI trở lại ngưỡng an toàn.
   - **Độ chính xác của AIOps RCA:** Kiểm tra xem thuật toán phân rã trace $T_{\text{WAN}}$ có xác định chính xác nguyên nhân nằm ở tầng mạng hay không.
5. **Dọn dẹp và Khôi phục (Rollback & Teardown):** Tự động khôi phục giao diện mạng (`tc qdisc del dev eth0 root`), xóa các tiến trình tải phụ và đưa cụm về trạng thái ban đầu.

## Consequences
### Tích cực (Positive)
- **Kiểm chứng độ tin cậy thực tế:** Xác thực rằng toàn bộ chuỗi quan sát (OTel -> Thanos -> Pyrra -> Robusta -> Telegram -> AIOps) hoạt động chính xác khi có sự cố.
- **Dữ liệu huấn luyện phong phú cho AIOps:** Cung cấp tập dữ liệu viễn trắc gán nhãn thực tế (labeled anomaly dataset) để huấn luyện và đánh giá mô hình học sâu phát hiện bất thường.
- **Tự động hóa an toàn:** Có script reset mạng WAN (`make reset-wan`) và phục hồi cụm nhanh chóng.

### Tiêu cực & Thách thức (Trade-offs)
- Việc tiêm lỗi trực tiếp qua `tc netem` đòi hỏi quyền truy cập sâu vào Docker daemon và container k3d.
- Nếu không quản lý tốt thời gian thử nghiệm, sự cố cơ sở dữ liệu có thể để lại dữ liệu không nhất quán trong MySQL, đòi hỏi phải re-seed database.

## Alternatives considered
1. **Sử dụng Chaos Mesh hoặc LitmusChaos Operator:** Cung cấp CRDs quản lý chaos chuyên nghiệp nhưng yêu cầu cài đặt controller và daemonsets chiếm dụng thêm 400–600 MB RAM trên mỗi cụm, vượt quá ngân sách tài nguyên máy trạm.
2. **Tiêm lỗi thủ công không theo kịch bản:** Thiếu tính lặp lại (non-reproducible), dễ dẫn đến sai lệch trong kết luận khoa học và đánh giá mô hình AIOps.
3. **Chỉ thử nghiệm mô phỏng trên môi trường phần mềm giả lập (Simulated Mocks):** Không phản ánh được độ trễ thực tế của kernel Linux và tương tác giao thức mạng thật giữa các container.

## References
- Principles of Chaos Engineering (principlesofchaos.org)
- Chaos Mesh & LitmusChaos: Cloud-Native Chaos Engineering in Kubernetes
- SRE Metrics: Mean Time to Detect (MTTD) and Mean Time to Recover (MTTR)
