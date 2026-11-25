# ADR-0004: Centralized Multi-Cluster GitOps Delivery with Argo CD & Canary Rollouts

## Status
Implemented (Đã triển khai)

## Context
Quản lý đồng thời ba cụm Kubernetes (`hub-k3d`, `aws-k3d`, `azure-k3d`) với hàng chục manifest dịch vụ đòi hỏi một giải pháp điều phối triển khai thống nhất, tự động và mang tính khai báo (Declarative GitOps Delivery).

Những thách thức vận hành cần giải quyết:
1. **Lệch pha cấu hình (Configuration Drift):** Khi áp dụng cấu hình thủ công qua `kubectl apply`, trạng thái thực tế của các cụm sẽ dần phân nhánh và mất đồng bộ so với mã nguồn trong Git.
2. **Quản lý đa cụm phân tán:** Việc cài đặt riêng rẽ các công cụ triển khai trên từng Spoke làm tăng chi phí quản trị, nhân đôi tiêu tốn tài nguyên và thiếu một góc nhìn tập trung (Single Pane of Glass).
3. **Rủi ro triển khai gián đoạn dịch vụ:** Việc cập nhật phiên bản microservices bằng chiến lược RollingUpdate truyền thống không có cơ chế đo lường tự động chất lượng dịch vụ (telemetry-driven health verification), dẫn đến nguy cơ triển khai phiên bản lỗi gây sập diện rộng trước khi được phát hiện.

## Decision
Chúng tôi quyết định chọn **Argo CD** làm động cơ GitOps điều phối tập trung trên cụm `hub-k3d`, kết hợp **Argo CD ApplicationSets** cho việc đồng bộ đa cụm và **Argo Rollouts** cho chiến lược phát hành luân phiên (Progressive Canary Delivery):

### 1. Kiến trúc GitOps Trung tâm (Centralized Hub-Spoke GitOps)
- Triển khai máy chủ **Argo CD `v2.12.3`** duy nhất trên cụm điều khiển `hub-k3d` (`deploy/argocd/kustomization.yaml`).
- Đăng ký hai cụm Spoke (`aws-k3d` và `azure-k3d`) vào Argo CD thông qua Kubernetes Secret chứa kubeconfig và ServiceAccount Token có quyền hạn giới hạn theo chuẩn RBAC.
- Tận dụng cơ chế **Sync Waves** (`argocd.argoproj.io/sync-wave`) và **Prune Propagation** để đảm bảo trình tự triển khai chính xác:
  - Wave 0: Namespaces, CRDs, RBAC
  - Wave 1: ConfigMaps, SealedSecrets, Storage
  - Wave 2: Platform Operators (cert-manager, Kyverno, OTel Operator — các operator nặng được giới hạn hoặc hoãn sang Phase 5 trên lab cục bộ)
  - Wave 3: Workload Applications (TeaStore, Locust, Collectors)

### 2. Tự động hóa Đa cụm với Argo CD ApplicationSets
- Sử dụng **ApplicationSets** (`deploy/argocd/`) với bộ sinh danh sách (List Generator) và bộ sinh ma trận (Matrix Generator) để tự động hóa việc tạo các đối tượng `Application` cho từng cụm:
  - Khai báo mẫu ứng dụng chung một lần duy nhất, tham chiếu đường dẫn thư mục overlay tương ứng (`deploy/clusters/{{name}}`).
  - Tự động áp dụng các biến nhãn môi trường (`env: aws`, `env: azure`, `env: hub`) mà không cần nhân bản cấu hình lặp lại.

### 3. Phát hành Luân phiên (Progressive Delivery) với Argo Rollouts *(Phase 5 Real-Cloud)*
- Trên môi trường **k3d cục bộ**, các microservice TeaStore sử dụng tài nguyên `Deployment` tiêu chuẩn để tiết kiệm bộ nhớ trong ngân sách 20 GB RAM.
- Ở **Phase 5 (Real-Cloud)**, triển khai **Argo Rollouts** controller trên cụm `aws-k3d` cho các microservice tính toán của TeaStore (đặc biệt là `webui` và `recommender`):
  - Thay thế tài nguyên `Deployment` tiêu chuẩn bằng `Rollout` CRD.
  - Cấu hình phân chia lưu lượng truy cập (Canary Step Weight): 10% -> 25% -> 50% -> 100%.
  - **Phân tích Metric Tự động (AnalysisTemplate):** Tự động truy vấn Prometheus/Thanos trên `hub-k3d` trong suốt quá trình triển khai canary:
    - Ngưỡng tỷ lệ lỗi HTTP 5xx: `sum(rate(http_requests_total{status=~"5.."}[2m])) / sum(rate(http_requests_total[2m])) < 0.01` (dưới 1%).
    - Ngưỡng độ trễ P99: `histogram_quantile(0.99, sum(rate(http_request_duration_seconds_bucket[2m])) by (le)) < 0.5` (dưới 500ms).
  - Tự động dừng và quay lui (automated rollback) nếu phát hiện bất kỳ chỉ số nào vượt ngưỡng cảnh báo.

## Consequences
### Tích cực (Positive)
- **Điểm kiểm soát duy nhất (Single Pane of Glass):** Quản trị viên theo dõi toàn bộ trạng thái đồng bộ của cả 3 cụm qua giao diện Web và CLI của Argo CD tại `hub-k3d`.
- **Triển khai an toàn không downtime:** Argo Rollouts kết hợp tự động phân tích viễn trắc giúp loại bỏ 100% rủi ro đưa phiên bản lỗi ra toàn bộ người dùng.
- **Tiết kiệm tài nguyên:** Không cần cài đặt Argo CD Server và Web UI trên các cụm Spoke, tiết kiệm ~500MB RAM cho mỗi Spoke.

### Tiêu cực & Thách thức (Trade-offs)
- Phụ thuộc vào kết nối mạng giữa Hub và Spoke: nếu kết nối WAN gián đoạn, Argo CD tạm thời không thể đồng bộ trạng thái mới ra Spoke (nhưng các workload đang chạy trên Spoke vẫn duy trì hoạt động bình thường).
- Đòi hỏi viết các định nghĩa `AnalysisTemplate` chuẩn xác để tránh trường hợp false-positive gây rollback nhầm.

## Alternatives considered
1. **Flux v2:** Là công cụ GitOps mạnh mẽ và nhẹ, nhưng mô hình hướng phân tán (thường cài đặt Flux instance riêng rẽ trên từng cụm) làm tăng độ phức tạp khi cần quản trị tập trung từ một điểm so với mô hình Hub-Spoke của Argo CD.
2. **Jenkins / GitHub Actions triển khai trực tiếp bằng CLI:** Tiếp cận kiểu "Push-based CI" truyền thống; yêu cầu mở cổng Kubernetes API ra ngoài Internet cho CI runner, tiềm ẩn rủi ro bảo mật lớn hơn so với "Pull-based GitOps".
3. **Triển khai Blue/Green thủ công:** Đòi hỏi nhân đôi tài nguyên pod trong suốt quá trình chuyển giao, vi phạm giới hạn ngân sách phần cứng 8–10 GB RAM.

## References
- Argo CD Architectural Overview: Multi-Cluster Management
- Argo ApplicationSets Specification & Generators Guide
- Argo Rollouts: Progressive Delivery for Kubernetes
- OpenTelemetry & Prometheus Analysis Templates for Canary Deployments
