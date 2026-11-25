# ADR-0002: Kyverno Policy-as-Code & Supply Chain Security Governance

## Status
Implemented (Đã triển khai)

## Context
Trong môi trường Kubernetes đa cụm phân tán (`hub-k3d`, `aws-k3d`, `azure-k3d`), việc duy trì tuân thủ kiến trúc, kiểm soát bảo mật và ngăn chặn cấu hình sai (misconfigurations) đòi hỏi cơ chế kiểm soát tự động và mang tính khai báo (declarative policy governance).

Các thách thức vận hành và bảo mật bao gồm:
1. **Rủi ro chuỗi cung ứng phần mềm (Software Supply Chain Risks):** Việc sử dụng image trôi nổi (`latest` hoặc floating tags) dẫn đến các phiên bản không xác định lọt vào cụm, gây khó khăn cho việc tái hiện kết quả đo lường khoa học và mở rộng bề mặt tấn công.
2. **Quyền hạn container quá mức (Privilege Escalation & Container Escape):** Các container chạy dưới quyền `root`, có quyền ghi vào hệ thống tệp gốc (`readOnlyRootFilesystem: false`), hoặc gắn kết đường dẫn máy chủ cục bộ (`hostPath`) tiềm ẩn nguy cơ kiểm soát node máy chủ.
3. **Thiếu kiểm tra sớm (Shift-Left Deficit):** Nếu chỉ phát hiện vi phạm bảo mật khi manifest đã nạp vào cụm (runtime admission webhook), quy trình triển khai GitOps sẽ bị nghẽn (Argo CD sync loop fail) mà không có phản hồi sớm trong pipeline CI.

## Decision
Chúng tôi quyết định áp dụng **Kyverno** làm động cơ Quản trị Chính sách bằng Mã (Policy-as-Code) tiêu chuẩn cho toàn bộ các cụm trong hệ thống, kết hợp phương pháp xác thực chữ ký số không khóa (Keyless Signing) và kiểm thử chính sách Shift-Left:

### 1. Kiến trúc Chính sách Khai báo (Declarative ClusterPolicy)
Bộ chính sách Kyverno `ClusterPolicy` được định nghĩa chuẩn hóa tại `deploy/policies/` (và liên kết vào cluster overlays) phục vụ kiểm tra tĩnh (static CI/CD validation) ở giai đoạn k3d cục bộ, và kích hoạt cưỡng chế (runtime admission enforcement, `validationFailureAction: Enforce`) trong **Phase 5 (Real-Cloud)**. Nhằm phù hợp với ngân sách **20 GB RAM** của phòng lab k3d cục bộ, live Kyverno admission controller và chữ ký Cosign được hoãn sang **Phase 5 (Real-Cloud)** (`deploy/policies/` vẫn được kiểm thử tĩnh liên tục):
- **`disallow-latest-tag`:** Bắt buộc toàn bộ container image phải sử dụng phiên bản ghim cố định (pinned version tag hoặc SHA256 immutable digest), tuyệt đối cấm tag `:latest` hoặc không chỉ định tag.
- **`require-ro-rootfs`:** Bắt buộc container trong các workload kiểm thử và viễn trắc phải kích hoạt `readOnlyRootFilesystem: true`. Mọi thư mục tạm thời phải sử dụng volume `emptyDir`.
- **`disallow-root-user`:** Bắt buộc cấu hình `runAsNonRoot: true` và `runAsUser > 0` trong `securityContext` của Pod và Container.
- **`drop-all-capabilities`:** Yêu cầu loại bỏ toàn bộ Linux capabilities (`drop: ["ALL"]`), chỉ cấp phép bổ sung có chọn lọc (ví dụ: `NET_ADMIN` cho việc mô phỏng mạng khi được phê duyệt rõ ràng).
- **`restrict-host-path`:** Nghiêm cấm việc gắn kết `hostPath` volumes ngoại trừ các daemon hệ thống được phân quyền đặc thù.

### 2. Kiểm thử Chính sách Shift-Left (Shift-Left Testing via Kyverno CLI)
- Tích hợp kiểm tra chính sách trực tiếp vào quy trình phát triển và CI/CD:
  - Sử dụng lệnh `kyverno test deploy/policies/` để đánh giá manifest trước khi hợp nhất mã nguồn vào nhánh `main`.
  - Tích hợp vào `Makefile` (`make validate-k8s` / `make test`) nhằm ngăn chặn lập trình viên đẩy các manifest vi phạm quy chuẩn lên Git.

### 3. Ký số Không khóa (Keyless Signing) và Nguồn gốc Phần mềm SLSA
- Áp dụng chuẩn **Sigstore Cosign** kết hợp **GitHub Actions OIDC** để thực hiện ký số không khóa (keyless signing) cho các container image tự build nội bộ (ví dụ: `fault-agent`, custom locust images, AI engine components).
- Kiểm tra tính toàn vẹn và xuất xứ phần mềm theo chuẩn **SLSA Build L2 Provenance**, xác thực rằng hình ảnh container được sinh ra từ chính pipeline CI đáng tin cậy của kho lưu trữ.

## Consequences
### Tích cực (Positive)
- **Bảo mật phòng ngừa chủ động (Shift-Left Security):** Phát hiện 100% vi phạm cấu hình ngay tại máy trạm hoặc trong pull request trước khi manifest được áp dụng vào cụm.
- **Tính lặp lại khoa học tuyệt đối:** Việc ghim cố định digest hoặc phiên bản image loại bỏ tình trạng sai lệch môi trường (configuration drift) giữa các lần chạy benchmark.
- **Dễ bảo trì và làm quen:** Cú pháp chính sách của Kyverno là tài nguyên Kubernetes nguyên bản (native K8s YAML), không đòi hỏi học các ngôn ngữ chuyên biệt phức tạp như Rego trong OPA.

### Tiêu cực & Thách thức (Trade-offs)
- Các cấu hình bảo mật nghiêm ngặt (như `readOnlyRootFilesystem`) yêu cầu cấu hình thêm các ổ đĩa tạm `emptyDir` cho một số dịch vụ bên thứ ba ghi logs/tmp.
- Kyverno Admission Webhook yêu cầu tài nguyên nhất định trên cụm control plane (~100–150 MB RAM per cluster).

## Alternatives considered
1. **Open Policy Agent (OPA) / Gatekeeper:** Giải pháp mạnh mẽ nhưng sử dụng ngôn ngữ Rego phức tạp, khó tích hợp và bảo trì hơn đối với đội ngũ phát triển hạ tầng so với YAML-native của Kyverno.
2. **Kubernetes Pod Security Standards (PSS/PSA) tích hợp sẵn:** Chỉ hỗ trợ kiểm soát cấp độ namespace cơ bản, không có khả năng tùy biến điều kiện chi tiết hoặc xác thực chữ ký số container như Kyverno.
3. **Quản lý khóa ký thủ công (KMS / Private GPG Keys):** Tiềm ẩn rủi ro rò rỉ khóa bí mật dài hạn (long-lived secrets); giải pháp Keyless signing qua Sigstore OIDC an toàn và tinh gọn hơn.

## References
- Kyverno Official Documentation — Kubernetes Native Policy Management
- Sigstore Cosign: Container Signing and Verification
- OpenSSF SLSA (Supply-chain Levels for Software Artifacts) Specification
- Kubernetes Security Best Practices: Pod Security Standards
