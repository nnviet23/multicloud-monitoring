# GIAI ĐOẠN 1: ĐỌC, PHÂN TÍCH RESEARCH VÀ ĐỀ XUẤT PHƯƠNG ÁN TRIỂN KHAI

Bạn hãy đóng vai trò là một **Senior Cloud Infrastructure Architect, Observability Engineer và Research Assistant**, có kinh nghiệm về Kubernetes, Multi-Cloud, OpenTelemetry, Distributed Tracing, Anomaly Detection và Performance Benchmarking.

Tôi muốn bạn bắt đầu bằng việc tìm hiểu toàn bộ tài liệu hiện có của dự án trước khi đưa ra bất kỳ đề xuất triển khai hoặc thay đổi mã nguồn nào.

## 1. Đọc và tìm hiểu tài liệu dự án

Hãy đọc kỹ các tài liệu sau:

1. `PLAN.md` ở thư mục gốc dự án:
   - Hiểu mục tiêu, phạm vi, định hướng và các giai đoạn phát triển.
   - Xác định những chức năng đã có, đang thực hiện và dự kiến triển khai.
   - Ghi nhận các yêu cầu kỹ thuật và những vấn đề dự án đang muốn giải quyết.

2. `docs/architecture/systemArchitecture.html`:
   - Phân tích kiến trúc tổng thể của hệ thống.
   - Xác định các thành phần, vai trò và mối quan hệ giữa chúng.
   - Phân tích luồng dữ liệu giữa các thành phần.
   - Xác định các ranh giới giữa các cluster, các thành phần monitoring và các backend lưu trữ dữ liệu.
   - Đối chiếu kiến trúc với mục tiêu đã nêu trong `PLAN.md`.

3. Toàn bộ tài liệu PDF trong thư mục `research/`:
   - Liệt kê tất cả các file PDF hiện có.
   - Đọc nội dung từng tài liệu, bao gồm abstract, introduction, methodology, proposed architecture, experiments, results, limitations và conclusion nếu có.
   - Nếu PDF có sơ đồ, bảng biểu hoặc hình ảnh quan trọng, hãy kiểm tra cả nội dung trực quan thay vì chỉ dựa vào text extraction.
   - Không bỏ qua tài liệu chỉ vì tiêu đề có vẻ không liên quan trực tiếp. Hãy đánh giá mức độ liên quan dựa trên nội dung thực tế.

Nếu có tài liệu không thể đọc đầy đủ, hãy ghi rõ tên file, phần nội dung không truy cập được và lý do. Không được tự suy diễn nội dung chưa đọc được.

## 2. Đánh giá từng research paper

Với mỗi tài liệu nghiên cứu, hãy phân tích theo cấu trúc sau:

### 2.1. Thông tin chung
- Tên bài nghiên cứu.
- Tác giả, năm công bố và nguồn công bố nếu xác định được.
- Vấn đề nghiên cứu chính.
- Mục tiêu mà nghiên cứu muốn đạt được.

### 2.2. Nội dung và phương pháp
- Ý tưởng và phương pháp tiếp cận chính.
- Kiến trúc hoặc mô hình được đề xuất.
- Các công nghệ, thuật toán và công cụ được sử dụng.
- Cách triển khai và thiết lập thực nghiệm.
- Các chỉ số được sử dụng để đánh giá.

### 2.3. Kết quả nghiên cứu
- Những kết quả quan trọng nhất.
- Các số liệu benchmark đáng chú ý.
- Những ưu điểm và đóng góp chính.
- Những hạn chế được chính tác giả đề cập.

### 2.4. Khả năng áp dụng vào dự án hiện tại

Đây là phần quan trọng nhất.

Hãy đánh giá nghiên cứu có thể đóng góp gì cho dự án Multi-Cloud Monitoring và Anomaly Detection của chúng ta.

Cụ thể, xem xét các khía cạnh:

- Multi-Cloud Architecture và Hub-Spoke Architecture.
- Kubernetes và Container Orchestration.
- OpenTelemetry Collector và Telemetry Pipeline.
- Metrics, Logs và Distributed Traces.
- Cross-Cluster Observability.
- Data Normalization và Semantic Conventions.
- Timestamp và Event Correlation.
- Sampling và Telemetry Data Reduction.
- Anomaly Detection.
- Performance Benchmarking.
- Scalability, Reliability và Fault Tolerance.
- Network Latency và Egress Cost.

Với mỗi ý tưởng có thể áp dụng, hãy giải thích:
- Ý tưởng đó đến từ nghiên cứu nào?
- Nghiên cứu đề xuất hoặc chứng minh điều gì?
- Có thể áp dụng vào thành phần nào của kiến trúc hiện tại?
- Cần thay đổi hoặc bổ sung những gì?
- Lợi ích dự kiến là gì?
- Có khó khăn hoặc rủi ro nào khi triển khai?

Không mặc định rằng mọi giải pháp trong research đều phù hợp. Hãy phân biệt rõ giải pháp có thể áp dụng trực tiếp, cần điều chỉnh và chỉ có giá trị tham khảo.

## 3. So sánh và tổng hợp các research

Sau khi phân tích từng tài liệu, hãy tổng hợp các nghiên cứu thành một bảng so sánh.

Các cột cần có:

| Research | Research Problem | Proposed Approach | Technologies | Key Findings | Limitations | Relevance to Our Project |
|---|---|---|---|---|---|---|

Tiếp theo, phân nhóm nghiên cứu theo chủ đề:

- Architecture và Multi-Cloud Monitoring.
- Telemetry Collection và Data Pipeline.
- Distributed Tracing và Correlation.
- Anomaly Detection.
- Sampling và Cost Optimization.
- Benchmarking và Performance Evaluation.

Hãy xác định:
- Những điểm các nghiên cứu có chung quan điểm.
- Những điểm có sự khác biệt hoặc mâu thuẫn.
- Những vấn đề đã được nghiên cứu giải quyết tương đối tốt.
- Những vấn đề còn bỏ ngỏ.
- Những khoảng trống nghiên cứu (Research Gaps) mà dự án có thể tập trung khai thác.

Không được khẳng định một vấn đề là Research Gap chỉ vì không thấy nó trong các PDF hiện có. Hãy ghi rõ đó là khoảng trống quan sát được trong tập tài liệu đang phân tích, chưa phải kết luận về toàn bộ lĩnh vực nghiên cứu.

## 4. Đối chiếu với kiến trúc hiện tại

Dựa trên `PLAN.md`, `systemArchitecture.html` và các research paper, hãy đánh giá kiến trúc hiện tại.

Phân tích theo các nội dung:

1. Những thành phần kiến trúc đã hợp lý và nên giữ nguyên.
2. Những thành phần có thể cần cải thiện.
3. Những thành phần còn thiếu so với mục tiêu dự án.
4. Những quyết định thiết kế cần được nghiên cứu thêm.
5. Những rủi ro kỹ thuật có thể ảnh hưởng đến tính đúng đắn của kết quả thực nghiệm.

Đặc biệt, hãy phân biệt:
- Những gì tài liệu xác nhận đang được triển khai.
- Những gì mới chỉ được đề xuất trong kế hoạch.
- Những gì Agent suy luận từ kiến trúc.
- Những gì chưa đủ thông tin để kết luận.

Không tự ý sửa kiến trúc hoặc mã nguồn trong giai đoạn này.

## 5. Đề xuất các phương án triển khai

Dựa trên kết quả nghiên cứu, hãy đưa ra một số phương án triển khai có thể cân nhắc.

Mỗi phương án cần trình bày:

- Mục tiêu và ý tưởng chính.
- Kiến trúc hoặc luồng xử lý đề xuất.
- Các thành phần cần triển khai.
- Công nghệ và công cụ có thể sử dụng.
- Các thay đổi so với kiến trúc hiện tại.
- Ưu điểm.
- Nhược điểm và rủi ro.
- Độ phức tạp triển khai.
- Tác động đến tài nguyên, hiệu năng và chi phí.
- Cách kiểm chứng bằng thực nghiệm.
- Research paper nào hỗ trợ cho phương án đó.

Hãy đưa ra các phương án có sự khác biệt thực chất về cách tiếp cận, không chỉ thay đổi tên công nghệ.

Sau đó lập bảng so sánh các phương án theo:
- Technical Feasibility.
- Implementation Complexity.
- Performance.
- Scalability.
- Reliability.
- Research Contribution.
- Reproducibility.
- Resource Consumption.

**Chưa chọn phương án cuối cùng thay tôi.** Hãy đưa ra nhận xét và những đánh đổi để tôi có thể cùng bạn thảo luận và quyết định.

## 6. Xuất kết quả thành tài liệu Markdown

Tạo một file mới:

`docs/research/RESEARCH_ANALYSIS.md`

Nếu thư mục `docs/research/` chưa tồn tại, hãy tạo thư mục.

File Markdown cần có cấu trúc:

1. Executive Summary.
2. Project Context.
3. Current Architecture Overview.
4. Individual Research Paper Analysis.
5. Comparative Research Matrix.
6. Research Findings and Common Patterns.
7. Research Gaps and Opportunities.
8. Architecture Assessment.
9. Potential Implementation Approaches.
10. Implementation Approach Comparison.
11. Open Questions and Technical Risks.
12. References.

Yêu cầu đối với tài liệu:

- Viết bằng tiếng Việt, giữ nguyên các thuật ngữ kỹ thuật tiếng Anh khi cần thiết.
- Có cấu trúc rõ ràng, dễ đọc và dễ cập nhật.
- Sử dụng bảng Markdown khi phù hợp.
- Mỗi nhận định quan trọng cần có nguồn tham chiếu cụ thể.
- Khi trích dẫn research paper, ghi rõ tên file PDF và số trang nếu xác định được.
- Phân biệt rõ nội dung lấy từ research, nội dung lấy từ tài liệu dự án và nhận định của Agent.
- Không tạo số liệu, kết quả benchmark hoặc trích dẫn không tồn tại.
- Không sao chép nguyên văn các đoạn dài từ paper.

## 7. Quy trình làm việc và giới hạn thay đổi

Thực hiện theo thứ tự:

1. Khảo sát cấu trúc thư mục và liệt kê tài liệu đầu vào.
2. Đọc `PLAN.md`.
3. Đọc `docs/architecture/systemArchitecture.html`.
4. Đọc và phân tích từng PDF trong `research/`.
5. Tổng hợp và đối chiếu các nguồn.
6. Đề xuất các phương án triển khai.
7. Tạo `docs/research/RESEARCH_ANALYSIS.md`.
8. Kiểm tra lại tài liệu đã tạo để bảo đảm không thiếu research paper nào.

Trong giai đoạn này:

- CHỈ ĐƯỢC đọc tài liệu và tạo file `docs/research/RESEARCH_ANALYSIS.md`.
- KHÔNG sửa code hiện có.
- KHÔNG thay đổi cấu hình Kubernetes, Docker, Ansible, Terraform hoặc OpenTelemetry.
- KHÔNG cài thêm package hoặc công cụ.
- KHÔNG tự ý xóa, di chuyển hoặc đổi tên tài liệu.
- KHÔNG tự triển khai bất kỳ phương án nào.

## 8. Báo cáo sau khi hoàn thành

Sau khi hoàn thành, hãy trả lời tôi:

1. Đã tìm thấy bao nhiêu research paper và đã đọc được bao nhiêu.
2. Có tài liệu nào không thể đọc đầy đủ không?
3. Những research paper nào có giá trị tham khảo cao nhất cho dự án và tại sao?
4. Ba đến năm vấn đề kỹ thuật quan trọng nhất mà dự án cần giải quyết.
5. Các phương án triển khai đáng cân nhắc.
6. Những câu hỏi cần tôi quyết định trước khi bắt đầu triển khai.
7. Đường dẫn đến file `docs/research/RESEARCH_ANALYSIS.md`.

**Quan trọng:** Đây là giai đoạn nghiên cứu và thảo luận thiết kế. Chất lượng phân tích, tính chính xác của nguồn và khả năng liên hệ với kiến trúc thực tế quan trọng hơn việc đưa ra thật nhiều đề xuất. Không vội viết code hoặc lựa chọn công nghệ khi chưa có đủ căn cứ.