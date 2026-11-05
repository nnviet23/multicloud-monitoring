# REFACTORING ACTION CHECKLIST

> **Dự án:** Multi-Cloud Monitoring Platform  
> **Tài liệu tham chiếu:** `docs/refactoring/REPOSITORY_AUDIT.md`  
> **Trạng thái quy ước:**  
> - `[ ]` Not Started (Chưa thực hiện - Chờ phê duyệt)  
> - `[-]` In Progress (Đang thực hiện)  
> - `[x]` Verified (Đã hoàn thành & Đã kiểm chứng)  

---

## 1. DỌN DẸP MÃ CHẾT & TỆP THỪA (DEAD CODE CLEANUP)

- [x] **CLEAN-01:** Xóa bỏ hoàn toàn thư mục mã mẫu cũ không còn sử dụng: `src/` (bao gồm `src/infra-sample/ansible-sample/playbooks_sample/` và `src/README.md`). *(Đã xác nhận thư mục src không còn tồn tại)*
- [x] **CLEAN-02:** Xóa tệp vết trace mẫu tĩnh `Benchmark-app/sample_jaeger_traces.json` (hệ thống đã có Tempo live). *(Đã xác nhận)*
- [x] **CLEAN-03:** Dọn dẹp các tệp tạm / cache phát sinh trong quá trình audit dưới thư mục scratch nếu có.

---

## 2. KHẮC PHỤC CÁC LỖI KỊCH BẢN & HẠ TẦNG (INFRASTRUCTURE & SCRIPT FIXES)

- [x] **INFRA-01:** Bổ sung container image `descartesresearch/teastore-webui:1.4.1` vào mảng tải của `infra/scripts/pull_images.sh`. *(Đã xác nhận)*
- [x] **INFRA-02:** Bổ sung các image quan sát cốt lõi (Prometheus, Thanos, Loki, Tempo, MinIO, Grafana, Pyrra, Robusta, MySQL) vào `pull_images.sh` để hỗ trợ môi trường offline/air-gapped. *(Đã xác nhận)*
- [x] **INFRA-03:** Di chuyển 2 kịch bản `pull_images.sh` và `import_k3d_images.sh` từ `infra/ansible/playbooks/` sang thư mục chuẩn `infra/scripts/`. *(Đã xác nhận)*
- [x] **INFRA-04:** Hiệu chỉnh playbook tổng `infra/ansible/playbooks/site.yml`: Bổ sung `import_playbook: 04_sync_cluster_hosts.yml` và `import_playbook: 06_distribute_mtls_secrets.yml`. *(Đã xác nhận)*
- [x] **INFRA-05:** Khắc phục xung đột tiền tố đánh số `04_`: Đổi tên `04_reset_wan_emulation.yml` thành `99_reset_wan_emulation.yml`. *(Đã xác nhận)*
- [x] **INFRA-06:** Sửa lỗi sai lệch đường dẫn certs trong `infra/ansible/playbooks/00_cleanup_all.yml` (chuyển từ `security/certs` sang `security/pki`). *(Đã xác nhận)*
- [x] **INFRA-07:** Thay thế lệnh cài đặt động `apk add iproute2` mỗi lần chạy trong `03_emulate_wan_latency.yml` bằng việc sử dụng một pinned image có sẵn `tc`.
- [x] **INFRA-08:** Tham số hóa địa chỉ IP gateway `192.168.65.254` trong `04_sync_cluster_hosts.yml` qua biến `DOCKER_HOST_GATEWAY_IP` với fallback mặc định. *(Đã xác nhận)*

---

## 3. CHUẨN HÓA QUY ƯỚC ĐẶT TÊN & TÀI LIỆU (NAMING & DOCS HYGIENE)

- [x] **DOCS-01:** Xóa bỏ tham chiếu ma `docs/process/03_resource_monitor.md` tại dòng 4 của `docs/progress/03_resource_monitor.md` và dòng 361 của `docs/progress/01_implemetation_issue.md`. *(Đã xác nhận)*
- [x] **DOCS-02:** Gộp nội dung tổng quan đề tài từ `overview.md` vào `README.md` chính tại thư mục gốc, sau đó xóa tệp `overview.md` để tập trung thông tin. *(Đã xác nhận)*
- [x] **DOCS-03:** Chuẩn hóa lại tên các tệp có tiền tố `docs__schemas__` trong `docs/schemas/`:
  - `docs__schemas__experiment-manifest.example.yaml` ➔ `experiment-manifest.example.yaml`
  - `docs__schemas__telemetry-field-inventory.example.csv` ➔ `telemetry-field-inventory.example.csv`
- [x] **DOCS-04:** Chuẩn hóa tên tệp mẫu quyết định kiến trúc: `docs/decisions/docs__decisions__ADR-template.md` ➔ `docs/decisions/ADR-000-template.md`. *(Đã xác nhận)*
- [x] **DOCS-05:** Chuẩn hóa tên các tệp quy tắc trong `.agent/rules/` (loại bỏ tiền tố `agents__rules__`). *(Đã xác nhận)*
- [x] **DOCS-06:** Khởi tạo thư mục chuẩn bị thực nghiệm cho Phase 4: `experiments/manifests/`, `experiments/results/` và đổi tên `experiments__README.md` ➔ `README.md`. *(Đã xác nhận)*

---

## 4. BẢO MẬT & AN TOÀN THÔNG TIN (SECURITY & SECRETS)

- [x] **SEC-01:** Cập nhật `.gitignore` để bao phủ toàn diện các chứng chỉ và khóa riêng tư phát sinh trong `security/pki/` (`security/pki/**/*.key`, `security/pki/**/*.crt`, `security/pki/**/*.csr`, `security/pki/**/*.srl`). *(Đã xác nhận)*
- [ ] **SEC-02:** Loại bỏ hardcoded IP SANs (`172.28.0.2`, `172.28.0.3`) trong `security/pki/certs-hub/server_ext.cnf`, chuyển hướng toàn bộ giao tiếp client sang tên miền định danh DNS (`k3d-hub-k3d-serverlb`).
- [x] **SEC-03:** Tách toàn bộ Secrets Kubernetes sang nạp động qua Kustomize `secretGenerator` từ file `.env` ngoài (`.env.example` và `.env` cục bộ cho MinIO, Grafana, Loki, Tempo, Thanos, Robusta), loại bỏ hoàn toàn mật khẩu plaintext trong Git YAML manifests. *(Đã xác nhận)*

---

## 5. TỐI ƯU HÓA MÃ NGUỒN CẤU HÌNH (CONFIG OPTIMIZATION)

- [x] **CONF-01:** Khử trùng lặp và tách biệt secret trong `k8s/base/otel-collector/gateway/04-deployment.yaml` qua `envFrom: secretRef: loki-s3-creds`. *(Đã xác nhận)*
- [ ] **CONF-02:** Tối ưu hóa câu truy vấn PromQL dài 1,700 ký tự với 14 tầng `label_replace` trong Grafana dashboard `k8s/base/visualization-grafana/dashboards/system-topology.json`.
- [ ] **CONF-03:** Bổ sung `livenessProbe` và `readinessProbe` (sử dụng extension `health_check` cổng 13133) vào Deployment của OTel Collector Hub và Spoke.
- [ ] **CONF-04:** Bổ sung định mức tài nguyên tối thiểu (`requests: cpu: 10m, memory: 16Mi`) cho các initContainer trong TeaStore và MinIO.

---

## 6. ĐƠN GIẢN HÓA QUY TRÌNH TRIỂN KHAI (DEPLOYMENT SIMPLIFICATION)

- [x] **DEP-01:** Xây dựng tệp điều phối trung tâm `Makefile` tại thư mục gốc hỗ trợ các mục tiêu chuẩn hóa:
  - `make setup`: Chuẩn bị môi trường .env, kéo images.
  - `make infra`: Khởi tạo 3 cụm k3d, mạng WAN bridge, sinh và phân phối certs mTLS, cấu hình CoreDNS, nạp images.
  - `make deploy`: Triển khai toàn bộ Kustomize manifests cho Hub, Spoke AWS và Spoke Azure.
  - `make verify`: Chạy kiểm tra tự động trạng thái nodes, pods, mạng WAN.
  - `make teardown`: Xóa sạch cụm, docker bridge và volumes trả lại trạng thái ban đầu.
- [x] **DEP-02:** Cấu hình Kustomize Overlays Hub (`k8s/overlays/local-k3d/hub`) gom toàn bộ 8 base manifests phục vụ việc deploy một lệnh duy nhất. *(Đã xác nhận)*

---

## 7. KIỂM THỬ HỒI QUY (REGRESSION TESTING VERIFICATION)

- [x] **TEST-01:** Cả 3 cụm k3d (`hub-k3d`, `aws-k3d`, `azure-k3d`) build overlays thành công với Kustomize (Hub: 58 resources, Spoke AWS: 19 resources, Spoke Azure: 13 resources).
- [ ] **TEST-02:** Mạng WAN mô phỏng bằng `tc netem` đạt độ trễ RTT 10ms ±2ms và tỷ lệ mất gói 0.1%.
- [ ] **TEST-03:** Toàn bộ 7 microservices của TeaStore hoạt động bình thường, WebUI truy cập được qua `http://localhost:8080/tools.descartes.teastore.webui/`.
- [ ] **TEST-04:** Kết nối cơ sở dữ liệu MySQL giữa Spoke AWS và Spoke Azure ổn định, không bị lỗi kết nối.
- [ ] **TEST-05:** Bắt tay mTLS 1.3 giữa Spoke OTel Collector và Hub OTel Gateway hoạt động thông suốt trên cổng 4317.
- [ ] **TEST-06:** Thanos Query thu thập đầy đủ chỉ số metrics từ cả 3 cụm (filter theo `k8s_cluster_name`).
- [ ] **TEST-07:** Loki nhận logs ổn định từ các Pods TeaStore.
- [ ] **TEST-08:** Tempo nhận traces ổn định và hiển thị cây span liên kết xuyên suốt các dịch vụ.
- [ ] **TEST-09:** MinIO lưu trữ khối TSDB từ Thanos và tệp OTLP JSON thô trong bucket `raw-telemetry`.
- [ ] **TEST-10:** Trọn bộ 7 Dashboards SRE trên Grafana (`http://localhost:3000`) hiển thị trực quan không lỗi panel.
- [ ] **TEST-11:** Pyrra UI (`http://localhost:9099`) theo dõi đúng SLI/SLO 99.5% của TeaStore WebUI.
- [ ] **TEST-12:** Robusta gửi cảnh báo thử nghiệm về Telegram thành công.
- [ ] **TEST-13:** Chạy thử nghiệm sinh tải bằng Locust và ghi nhận kết quả không phát sinh lỗi nghẽn đường ống.
