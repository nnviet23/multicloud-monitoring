# DEEP TECHNICAL AUDIT & REPOSITORY REFACTORING PLAN

Bạn hãy đóng vai trò là một Senior Software Architect, DevOps Engineer, Kubernetes Specialist và Site Reliability Engineer (SRE).

Tôi đang phát triển một dự án Multi-Cloud Monitoring Platform theo kiến trúc Hub-Spoke, sử dụng TeaStore làm benchmark workload, k3d để mô phỏng nhiều Kubernetes cluster, OpenTelemetry để thu thập telemetry và các hệ thống observability để lưu trữ, truy vấn và trực quan hóa dữ liệu.

Dự án hiện đã có nhiều chức năng được triển khai. Tuy nhiên, repository đang trở nên phức tạp, có nhiều thư mục và file cấu hình, khiến việc đọc hiểu, bảo trì, sửa đổi và triển khai lại chưa thực sự thuận tiện.

Tôi muốn bạn thực hiện một cuộc kiểm tra kỹ thuật toàn diện (Deep Technical Audit) và đề xuất phương án tái cấu trúc (Repository Refactoring) nhằm:

1. Giảm độ phức tạp của repository.
2. Loại bỏ file và cấu hình trùng lặp hoặc không còn cần thiết.
3. Chuẩn hóa cấu trúc thư mục.
4. Tối ưu mã nguồn và cấu hình.
5. Đơn giản hóa quy trình triển khai.
6. Giữ nguyên tất cả chức năng quan trọng đang hoạt động.
7. Đảm bảo hệ thống dễ tái lập, kiểm thử và bảo trì.
8. Không làm mất các đặc tính phục vụ nghiên cứu và benchmark.

## PHASE 1 – UNDERSTAND THE PROJECT

Trước tiên, hãy đọc kỹ các tài liệu:

- `PLAN.md`
- `docs/progress/IMPLEMENTATION.md`
- `docs/progress/01_implemetation_issue.md`
- `docs/progress/02_solution_plan.md`
- `docs/progress/03_resource_monitor.md`
- Các tài liệu kiến trúc trong `docs/architecture/`
- Các tài liệu research liên quan nếu cần thiết.

Sau đó, kiểm tra toàn bộ repository thực tế.

Không chỉ đọc README. Hãy kiểm tra các thư mục, file cấu hình, manifest, playbook, scripts và các dependency giữa chúng.

Xác định rõ:

- Những gì đã được triển khai.
- Những gì đã được kiểm chứng.
- Những gì chỉ mới được mô tả trong tài liệu.
- Những gì chưa triển khai.
- Những gì đã lỗi thời.
- Những gì đang bị trùng lặp.

Nếu tài liệu và code không khớp nhau, hãy ưu tiên bằng chứng từ repository và kết quả kiểm tra thực tế, đồng thời ghi nhận sự khác biệt.

## PHASE 2 – REPOSITORY STRUCTURE AUDIT

Hãy kiểm tra toàn bộ cấu trúc thư mục và phân tích từng nhóm:

### Infrastructure
- Docker và k3d.
- Ansible inventory, playbooks, roles, templates và variables.
- WAN emulation.
- PKI và mTLS.
- Các script quản lý host và cluster.

### Kubernetes
- Kustomize Base và Overlays.
- ConfigMaps và Secrets.
- Deployments, StatefulSets, Services.
- Persistent Volumes và Storage.
- Các manifest của Hub và Spoke.

### Observability
- OpenTelemetry Collector.
- Prometheus và Thanos.
- Loki.
- Tempo.
- MinIO.
- Grafana và dashboards.
- Pyrra và Robusta.

### Workload và Benchmark
- TeaStore.
- MySQL.
- Locust.
- Các benchmark scripts và kết quả thực nghiệm.

### Documentation và Utilities
- README.
- Architecture.
- Progress logs.
- Research documents.
- Scripts hỗ trợ triển khai và kiểm thử.

Với từng thư mục hoặc file, hãy phân loại:

- KEEP: Cần giữ.
- MERGE: Có thể gộp với file hoặc thư mục khác.
- MOVE: Nên chuyển sang vị trí hợp lý hơn.
- REFACTOR: Cần cải thiện nội dung nhưng vẫn giữ chức năng.
- REMOVE: Có thể loại bỏ nếu chứng minh không còn được sử dụng.
- INVESTIGATE: Chưa đủ thông tin để quyết định.

Không được xóa hoặc di chuyển file trong giai đoạn audit.

## PHASE 3 – DEPENDENCY & DUPLICATION ANALYSIS

Đây là một phần đặc biệt quan trọng.

Hãy kiểm tra quan hệ phụ thuộc giữa các file và thư mục:

- File nào được gọi bởi Ansible playbook?
- Playbook nào sử dụng inventory, variable và template nào?
- Kustomization nào tham chiếu đến manifest nào?
- ConfigMap nào được mount vào Pod nào?
- Secret nào được sử dụng bởi thành phần nào?
- Script nào được gọi từ README hoặc workflow?
- Các cấu hình nào đang được định nghĩa nhiều lần?
- Các giá trị cấu hình nào nên được quản lý tập trung?
- Có file nào không còn được tham chiếu nhưng vẫn có thể được sử dụng thủ công không?

Kiểm tra các vấn đề:

1. Duplicate YAML configurations.
2. Duplicate Ansible tasks.
3. Duplicate environment variables.
4. Hardcoded configuration values.
5. Unnecessary configuration files.
6. Unused manifests.
7. Circular or fragile dependencies.
8. Inconsistent naming conventions.
9. Repeated deployment commands.
10. Conflicting documentation.

Không kết luận một file là dư thừa chỉ dựa trên việc không tìm thấy tham chiếu trực tiếp.

## PHASE 4 – CODE QUALITY & TECHNICAL DEBT AUDIT

Kiểm tra các đoạn code và cấu hình có thể cải thiện:

- OTel Collector pipelines và processors.
- OTTL transformations.
- Ansible playbooks và roles.
- Kustomize Base/Overlays.
- Docker và Kubernetes configurations.
- Shell/Python scripts.
- Grafana dashboard JSON.
- Resource requests và limits.
- Readiness và liveness probes.
- Error handling và retry policies.
- Security configurations.
- Logging và observability của chính hệ thống monitoring.

Tập trung vào:

- Loại bỏ logic trùng lặp.
- Tách biệt configuration và implementation.
- Giảm hardcoding.
- Tăng tính idempotent của automation.
- Chuẩn hóa naming convention.
- Cải thiện khả năng đọc và bảo trì.
- Hạn chế số lượng thành phần không cần thiết.

Không thay đổi các phiên bản công nghệ trong lần audit này.

## PHASE 5 – RESEARCH DATA INTEGRITY & SIMULATION VALIDATION

Đây là dự án nghiên cứu, do đó việc đơn giản hóa code không được làm sai lệch kết quả thực nghiệm.

Hãy đặc biệt kiểm tra:

1. Phân biệt rõ AWS/Azure thật và AWS/Azure mô phỏng bằng k3d.
2. Phân biệt metadata thu thập thực tế với metadata giả lập hoặc được suy diễn.
3. Kiểm tra các giá trị `cloud.account.id`, `cloud.resource_id`, `cloud.identity.arn`, VPC, VNet và Subnet.
4. Kiểm tra tính nhất quán của `service.name`, `cloud.provider`, `k8s.cluster.name`, `spoke_id` và `trace_id`.
5. Kiểm tra timestamp semantics và event correlation.
6. Kiểm tra pipeline lưu raw telemetry vào MinIO.
7. Đảm bảo các phép đo benchmark không bị thay đổi bởi refactoring.
8. Kiểm tra sampling, data loss và telemetry coverage.

Không được đánh dấu một metadata là dữ liệu thực tế nếu nó được tạo ra bằng OTTL hoặc cấu hình tĩnh.

## PHASE 6 – DESIGN A CLEANER REPOSITORY

Dựa trên kết quả audit, hãy đề xuất cấu trúc thư mục mới.

Mục tiêu:

- Ít tầng thư mục hơn nếu có thể.
- Tên thư mục dễ hiểu.
- Trách nhiệm mỗi thư mục rõ ràng.
- Không tạo quá nhiều thư mục chỉ chứa một hoặc hai file.
- Tránh lặp lại cấu hình.
- Dễ tìm kiếm và mở rộng.
- Hỗ trợ triển khai bằng một entrypoint thống nhất.

Đề xuất ít nhất hai phương án:

**Option A – Minimal Refactoring:**
Chỉ dọn dẹp, đổi tên và gộp các thành phần thực sự trùng lặp, giữ phần lớn cấu trúc hiện tại.

**Option B – Simplified Architecture:**
Tổ chức lại repository theo các nhóm chức năng rõ ràng hơn, giảm độ sâu và số lượng thư mục.

Với từng phương án, trình bày:

- Cây thư mục trước và sau.
- Các file cần di chuyển.
- Các file cần gộp.
- Các file cần viết lại.
- Các file có thể loại bỏ.
- Các dependency bị ảnh hưởng.
- Lợi ích.
- Nhược điểm.
- Rủi ro.
- Mức độ phức tạp.
- Ảnh hưởng đến triển khai và nghiên cứu.

Không chọn phương án thay tôi.

## PHASE 7 – DEPLOYMENT SIMPLIFICATION

Hãy đề xuất một quy trình triển khai thống nhất.

Mục tiêu cuối cùng là người dùng có thể thực hiện theo một quy trình dễ hiểu, ví dụ:

1. Kiểm tra prerequisites.
2. Chuẩn bị host.
3. Provision clusters.
4. Thiết lập simulated WAN.
5. Thiết lập PKI/mTLS.
6. Deploy Hub.
7. Deploy Spokes.
8. Verify telemetry.
9. Verify dashboards và storage.
10. Run benchmark.

Đánh giá khả năng xây dựng một entrypoint như `make deploy`, `make verify`, `make destroy` hoặc một script CLI đơn giản.

Không tạo thêm framework hoặc công cụ mới nếu shell script và Ansible hiện tại đã đủ đáp ứng.

Đặc biệt, các lệnh triển khai phải có khả năng chạy lại an toàn và phải kiểm tra trạng thái trước khi thay đổi.

## PHASE 8 – REGRESSION TEST STRATEGY

Đề xuất cách kiểm chứng rằng refactoring không làm mất chức năng.

Cần có checklist cho:

- Cluster provisioning.
- TeaStore availability.
- MySQL connectivity.
- WAN latency/loss.
- mTLS connectivity.
- OTel metrics ingestion.
- OTel logs ingestion.
- OTel traces ingestion.
- Prometheus/Thanos queries.
- Loki log queries.
- Tempo trace queries.
- MinIO bucket integrity.
- Grafana dashboards.
- SLO evaluation.
- Alerting.
- Raw telemetry export.
- Benchmark reproducibility.

Phân biệt rõ kiểm tra cú pháp, kiểm tra cấu hình, integration test và end-to-end deployment test.

## PHASE 9 – AUDIT REPORT

Tạo tài liệu:

`docs/refactoring/REPOSITORY_AUDIT.md`

Nội dung gồm:

1. Executive Summary.
2. Current Repository Structure.
3. Current Architecture Assessment.
4. Directory and File Audit.
5. Dependency Analysis.
6. Duplicate Configuration Analysis.
7. Code Quality and Technical Debt.
8. Research Data Integrity Assessment.
9. Deployment Complexity Assessment.
10. Proposed Repository Structures.
11. Refactoring Options Comparison.
12. Regression Test Strategy.
13. Risks and Migration Considerations.
14. Recommended Next Steps.
15. Open Questions.

Tạo thêm:

`docs/refactoring/REFACTORING_CHECKLIST.md`

File này liệt kê các công việc cần làm, có trạng thái:

- [ ] Not Started
- [ ] In Progress
- [x] Verified

## STRICT RULES

Trong giai đoạn này:

- CHỈ ĐƯỢC đọc, phân tích và tạo hai tài liệu audit nêu trên.
- KHÔNG sửa code.
- KHÔNG di chuyển file.
- KHÔNG xóa file.
- KHÔNG đổi tên thư mục.
- KHÔNG thay đổi cấu hình Kubernetes.
- KHÔNG thay đổi Ansible.
- KHÔNG thay đổi OTel Collector.
- KHÔNG nâng cấp hoặc hạ cấp phiên bản công nghệ.
- KHÔNG triển khai lại cluster.
- KHÔNG tự ý cài package.
- KHÔNG tạo thêm các thành phần kiến trúc mới.

Mọi đề xuất phải có căn cứ từ code hoặc cấu hình thực tế. Khi không có đủ bằng chứng, hãy ghi rõ là chưa xác định.

## FINAL RESPONSE

Sau khi hoàn thành, hãy báo cáo:

1. Tổng số thư mục và file đã kiểm tra.
2. Những vấn đề kiến trúc và technical debt nghiêm trọng nhất.
3. Những thư mục hoặc file có khả năng trùng lặp.
4. Những thành phần có thể đơn giản hóa mà không mất chức năng.
5. Hai phương án cấu trúc repository mới.
6. Phương án triển khai bạn đánh giá hợp lý nhất và lý do.
7. Các rủi ro nếu tiến hành refactoring.
8. Những quyết định cần tôi phê duyệt trước khi triển khai.

Hãy ưu tiên tính chính xác, an toàn và khả năng tái lập hệ thống hơn số lượng thay đổi.

**Đây là một cuộc audit, không phải yêu cầu tự động refactor. Hãy dừng lại sau khi hoàn thành báo cáo và chờ tôi phê duyệt.**