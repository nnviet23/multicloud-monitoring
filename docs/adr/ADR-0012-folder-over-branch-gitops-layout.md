# ADR-0012: Folder-Over-Branch GitOps Layout & Declarative Manifest Hygiene

## Status
Implemented (Đã triển khai)

## Context
Khi quản lý hạ tầng đa cụm Kubernetes theo triết lý GitOps, việc lựa chọn chiến lược tổ chức kho lưu trữ (Repository Branching & Directory Strategy) quyết định trực tiếp đến tính ổn định của quy trình CI/CD và độ tin cậy của hệ thống:
1. **Rủi ro của mô hình Nhánh môi trường (Environment Branching Anti-Pattern):** Sử dụng các nhánh Git riêng biệt cho từng môi trường (như nhánh `aws`, nhánh `azure`, nhánh `hub` hoặc nhánh `prod`/`staging`) thường xuyên dẫn đến hiện tượng trôi lệch cấu hình (Configuration Drift). Các thay đổi cấu hình phải được cherry-pick thủ công qua lại giữa các nhánh, dễ gây ra xung đột merge (merge conflicts) và vô tình làm mất các bản vá bảo mật quan trọng.
2. **Hỗn loạn cấu trúc manifest (Manifest Clutter):** Gộp chung nhiều tài nguyên Kubernetes (Namespace, Service, Deployment, PVC) vào một tệp YAML duy nhất gây khó khăn cho việc kiểm duyệt mã nguồn (code review), theo dõi lịch sử git (git blame), và kiểm tra chính sách tự động.
3. **Xung đột giữa CI tự động và Kỹ sư vận hành:** Khi bot CI/CD hoặc Renovate tự động cập nhật phiên bản container image vào cùng tệp cấu hình mà kỹ sư đang chỉnh sửa tham số tài nguyên (CPU/RAM limit), xung đột hợp nhất (merge conflict) sẽ thường xuyên xảy ra làm tắc nghẽn quy trình phát hành.

## Decision
Chúng tôi quyết định chuẩn hóa mô hình tổ chức GitOps theo phương pháp **Thư mục thay vì Nhánh (Folder-Over-Branch GitOps Layout)** kết hợp **Nguyên tắc Đơn nhiệm (Single Responsibility Principle - SRP)** cho toàn bộ manifest:

### 1. Chiến lược Nhánh Đơn Duy nhất (Single-Trunk GitOps Strategy)
- Toàn bộ 3 cụm Kubernetes (`hub-k3d`, `aws-k3d`, `azure-k3d`) đều lấy nhánh `main` làm nguồn chân lý duy nhất (Single Source of Truth).
- Tuyệt đối không sử dụng các nhánh môi trường dài hạn. Sự khác biệt giữa các cụm được thể hiện rõ ràng và minh bạch thông qua cấu trúc thư mục Kustomize overlay.

### 2. Cấu trúc Phân vùng Thư mục Chuẩn hóa dưới `deploy/` và `workloads/`
Toàn bộ mã nguồn triển khai được tổ chức chặt chẽ theo phân cấp chức năng:
- **`deploy/platform/`:** Chứa cấu hình các nền tảng hạ tầng cốt lõi (cert-manager, sealed-secrets, metrics-thanos, loki, tempo, grafana, pyrra, robusta, otel-collector).
- **`workloads/` (tại root repository):** Chứa ứng dụng nghiệp vụ và các bộ benchmark kiểm thử (`workloads/teastore/` gồm `base/`, `aws/`, `azure/`, `release-images/`, và `workloads/_template/`).
- **`deploy/policies/`:** Chứa các chính sách kiểm soát tuân thủ Kyverno `ClusterPolicy` áp dụng chung cho toàn hệ thống.
- **`deploy/integrations/`:** Chứa các bộ monitoring mixins, exporter và cấu hình thu thập viễn trắc bổ trợ.
- **`deploy/argocd/`:** Chứa các `ApplicationSet` và root applications điều phối GitOps cho từng cụm.
- **`deploy/clusters/{aws,azure,hub}/`:** Các Kustomize overlays cụ thể cho từng cụm:
  - Mỗi cụm có tệp `kustomization.yaml` độc lập kết hợp các thành phần từ `deploy/platform/`, `workloads/`, `deploy/policies/`, `deploy/integrations/`.

### 3. Nguyên tắc Đơn nhiệm cho Manifest (Single Responsibility Principle - SRP)
Mọi tài nguyên Kubernetes phải được tách riêng thành từng tệp manifest độc lập, tuân thủ quy ước tiền tố số thứ tự triển khai:
- `00-namespace.yaml`
- `01-serviceaccount.yaml`
- `02-secret.yaml` (hoặc `02-sealedsecret.yaml`)
- `03-configmap.yaml`
- `04-pvc.yaml`
- `05-deployment.yaml` (hoặc `05-statefulset.yaml`, `05-rollout.yaml`)
- `06-service.yaml`
- `07-hpa.yaml` / `07-servicemonitor.yaml`

### 4. Tách biệt Tuyệt đối Con trỏ Release và Cấu hình Vận hành
Để ngăn chặn hoàn toàn xung đột giữa CI/CD tự động và kỹ sư:
- Con trỏ phiên bản image (`image` tag và digest) được cô lập trong thư mục `workloads/teastore/release-images/` (và khối `images:` tại các cluster overlays `deploy/clusters/{aws,azure,hub}/kustomization.yaml`). Tệp này chỉ dành riêng cho các bot CI tự động cập nhật khi có bản build mới.
- Cấu hình vận hành (CPU/RAM requests, biến môi trường, bản vá cấu hình) nằm trong các tệp `patches/*.yaml` do kỹ sư con người quản lý và kiểm duyệt.

## Consequences
### Tích cực (Positive)
- **Loại bỏ 100% trôi lệch nhánh môi trường:** Trạng thái mong muốn của toàn bộ hệ thống đa cụm luôn hiển thị rõ ràng trên nhánh `main`.
- **Zero Merge Conflicts:** Việc tách biệt `release-images.yaml` giúp CI/CD tự động commit phiên bản mới mà không bao giờ xung đột với các thay đổi cấu hình hạ tầng của kỹ sư.
- **Tương thích hoàn hảo với Kustomize & Argo CD:** Cho phép tái sử dụng tối đa các base manifests và dễ dàng kế thừa, ghi đè tham số cho từng cụm.
- **Dễ dàng kiểm duyệt và kiểm toán (Auditability):** Việc tuân thủ SRP giúp git diff cực kỳ gọn gàng, rõ ràng khi review Pull Request.

### Tiêu cực & Thách thức (Trade-offs)
- Số lượng tệp manifest trong kho mã nguồn tăng lên do mỗi tài nguyên là một tệp riêng biệt.
- Yêu cầu kỷ luật nghiêm ngặt từ đội ngũ kỹ sư trong việc tuân thủ cấu trúc thư mục và quy tắc đặt tên tiền tố.

## Alternatives considered
1. **Mô hình Nhánh theo Môi trường (Branch-per-Environment):** Nhánh riêng cho từng cụm (`aws`, `azure`, `hub`). Nhược điểm: liên tục xảy ra merge conflict, trôi lệch cấu hình và khó theo dõi lịch sử commit chung.
2. **Tách thành nhiều Repository độc lập (Polyrepo):** Một repo cho platform, một repo cho workloads, một repo cho clusters. Nhược điểm: phân mảnh mã nguồn, việc đồng bộ thay đổi giữa các repo yêu cầu quy trình phối hợp phức tạp.
3. **Gộp chung toàn bộ tài nguyên vào một tệp manifest lớn:** Khó review, vi phạm nguyên tắc SRP, tăng nguy cơ vô tình xóa nhầm tài nguyên khi chỉnh sửa.

## References
- GitOps Working Group: Principles of GitOps & Repository Patterns
- Kustomize Best Practices: Base and Overlay Structure
- Single Responsibility Principle (SRP) Applied to Kubernetes Resource Modeling
- Upstream Architecture Decision Record ADR-012: Folder-Over-Branch Multi-Cluster GitOps Layout
