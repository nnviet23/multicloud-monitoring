# GIT INTEGRATION & MERGE PLAN: HỢP NHẤT NHÁNH HẠ TẦNG (`feat/infra-ansible-k3d`) VỚI NHÁNH AI ANOMALY DETECTION

Bạn hãy đóng vai trò là một **Senior DevOps/SRE Release Engineer và Git Workflow Specialist**.

## 1. BỐI CẢNH & MỤC TIÊU

Hiện tại, tôi đang đứng ở nhánh `feat/infra-ansible-k3d`. Nhánh này đã hoàn thiện toàn bộ:
- Hạ tầng 3 cụm k3d (`hub-k3d`, `aws-k3d`, `azure-k3d`), mạng WAN mô phỏng `tc netem` và PKI mTLS 1.3.
- Bộ 7 Grafana Dashboards chuẩn SRE (đã nâng cấp USE Method, 4 Golden Signals và Hotfix Schema v39).
- Hệ thống cảnh báo thông minh **Robusta** và bộ đặc tả **Unified Resource Monitoring Schemas** (`docs/schemas/`).

Bây giờ, tôi muốn tích hợp và kiểm tra chức năng **AI Anomaly Detection** đang được phát triển ở nhánh AI (cùng tồn tại hoặc phối hợp với Robusta). Để đảm bảo an toàn tuyệt đối cho nhánh `feat/infra-ansible-k3d`, tôi yêu cầu bạn tạo một **nhánh local mới** từ nhánh hiện tại, sau đó mới thực hiện merge với nhánh AI và kiểm tra hệ thống.

---

## 2. QUY TRÌNH THỰC HIỆN TỪNG BƯỚC (STEP-BY-STEP EXECUTION)

### BƯỚC 1: Kiểm tra trạng thái Git hiện tại & Lưu giữ thay đổi (Pre-flight Check)
1. Chạy `git status` và `git branch -a` (cùng `git fetch --all`) để:
   - Xác nhận nhánh hiện tại đúng là `feat/infra-ansible-k3d`.
   - Kiểm tra xem có file nào đang sửa dở (uncommitted changes) hoặc untracked files từ Phase 3.5/3.6 chưa được commit không. Nếu có, hãy thực hiện `git add` và `git commit` sạch sẽ trên nhánh `feat/infra-ansible-k3d` (tuyệt đối không commit các file nhạy cảm trong `security/pki/**/*.key` hay `.env`).
   - Xác định tên chính xác của nhánh AI trong repository (ví dụ: `feat/ai-anomaly-detection`, `origin/feat/ai...`, hoặc nhánh có từ khóa `ai` / `anomaly`).

### BƯỚC 2: Tạo nhánh tích hợp mới (Integration Branch) từ `feat/infra-ansible-k3d`
1. Từ nhánh `feat/infra-ansible-k3d` đã sạch sẽ, tạo và chuyển sang một nhánh local mới có tên:
   ```bash
   git checkout -b feat/integrate-infra-ai-anomaly
   ```
   *(Nhánh `feat/infra-ansible-k3d` gốc sẽ được giữ nguyên vẹn 100% làm điểm quay lui an toàn).*

### BƯỚC 3: Thực hiện Merge với nhánh AI (`--no-ff`)
1. Chạy lệnh merge nhánh AI vào nhánh `feat/integrate-infra-ai-anomaly` (sử dụng `--no-ff` để giữ rõ lịch sử commit hoặc `--no-commit` nếu cần kiểm tra xung đột trước):
   ```bash
   git merge <tên-nhánh-AI> --no-ff
   ```
2. **Nguyên tắc giải quyết xung đột (Conflict Resolution Rules) — CỰC KỲ QUAN TRỌNG:**
   Nếu xảy ra Merge Conflict, hãy giải quyết theo nguyên tắc **Bảo tồn cả hai (Additive Merge - Không làm mất tính năng của bất kỳ nhánh nào)**:
   - **`k8s/` (Kustomize Overlays, OTel Collector, Grafana Dashboards):**
     - Giữ nguyên toàn bộ cấu hình 7 scrapers `hostmetrics`, OTTL Cloud Dependencies, exporter `awss3` (`raw-telemetry`), **Robusta** và **7 Grafana Dashboards v2/v4** của nhánh `feat/infra-ansible-k3d`.
     - Tích hợp thêm các manifests/deployments/configs của module **AI Anomaly Detection** từ nhánh AI vào Kustomize overlay tương ứng mà không xóa bỏ Robusta (để Robusta và AI Anomaly Detection cùng hoạt động song song hoặc bổ trợ nhau).
   - **`Makefile` / `infra/`:** Giữ nguyên cấu trúc 5 lệnh chuẩn (`make setup`, `make infra`, `make deploy`, `make verify`, `make teardown`) của nhánh `feat/infra-ansible-k3d`, và bổ sung thêm các target/image của nhánh AI (nếu có) vào `pull_images.sh`, `import_k3d_images.sh` và `Makefile`.
   - **`docs/` & `PLAN.md`:** Hợp nhất tài liệu của cả 2 nhánh, giữ nguyên toàn bộ `docs/progress/*` và `docs/schemas/*` mới nhất.

### BƯỚC 4: Kiểm tra tính hợp lệ và đánh giá kiến trúc tích hợp (Post-Merge Verification)
Sau khi merge thành công:
1. Kiểm tra cú pháp Kustomize cho tất cả các cụm:
   ```bash
   kubectl kustomize k8s/overlays/local-k3d/hub > /dev/null
   kubectl kustomize k8s/overlays/local-k3d/spoke-aws > /dev/null
   kubectl kustomize k8s/overlays/local-k3d/spoke-azure > /dev/null
   ```
2. Kiểm tra toàn bộ các tệp JSON trong `k8s/base/visualization-grafana/dashboards/` đảm bảo không còn ký tự conflict (`<<<<<<<`, `=======`, `>>>>>>>`).
3. Phân tích cách module **AI Anomaly Detection** (từ nhánh AI) kết nối với luồng dữ liệu hiện tại (nó đọc dữ liệu từ Prometheus/Thanos, từ OTel Collector hay từ MinIO `raw-telemetry`? Và nó xuất kết quả cảnh báo/metrics đi đâu?).

---

## 3. BÁO CÁO KẾT QUẢ SAU KHI HOÀN THÀNH

Hãy báo cáo rõ ràng cho tôi:
1. Tên chính xác của nhánh AI đã tìm thấy và tên nhánh tích hợp mới đã tạo (`feat/integrate-infra-ai-anomaly`).
2. Danh sách các file mới hoặc file thay đổi được đưa vào từ nhánh AI (`git diff --stat feat/infra-ansible-k3d..feat/integrate-infra-ai-anomaly`).
3. Các xung đột (conflicts) đã phát sinh trong quá trình merge và cách bạn đã xử lý từng file.
4. Phân tích kỹ thuật về kiến trúc của module AI Anomaly Detection vừa gộp vào: Nó hoạt động thế nào, cần bổ sung container image hay biến môi trường gì không, và làm sao để kết hợp nó với Robusta + Grafana Dashboards hiện tại?