# PHASE 3.7: DEEP AUDIT & SYNCHRONIZATION BETWEEN `ai-engine` AND INFRASTRUCTURE TELEMETRY PIPELINE

Bạn hãy đóng vai trò là một **Principal AIOps Architect, OpenTelemetry Specialist và Python/Kubernetes Integration Engineer**.

## 1. BỐI CẢNH & VẤN ĐỀ CẦN KIỂM TRA

Chúng ta vừa merge thành công nhánh `AI` vào nhánh `feat/integrate-infra-ai-anomaly` và có báo cáo tổng quan tại `docs/progress/04_ai_engine.md`.

Tuy nhiên, vì nhánh `AI` (`ai-engine/` và `tests/chaos/`) được phát triển độc lập với nhánh hạ tầng (`feat/infra-ansible-k3d`), tôi cần bạn thực hiện một cuộc **Kiểm tra đối chiếu mã nguồn sâu (Code-Level Integration Audit & Alignment)** để đảm bảo không có sự lệch pha về tên Metrics, tên Labels, Endpoints và cơ chế phối hợp giữa `ai-engine` với hệ thống Thanos/Tempo/Loki/Robusta/Grafana hiện tại.

---

## 2. CÁC NHIỆM VỤ KIỂM TRA & ĐỒNG BỘ CỤ THỂ

### NHIỆM VỤ 1: Kiểm tra và đối chiếu toàn bộ PromQL & Trace API trong `ai-engine/`
Hãy đọc trực tiếp mã nguồn các file trong `ai-engine/` (đặc biệt là `collector.py`, `tempo_analyzer.py` / module phân rã trace, các file config `.yaml`/`.json`) và báo cáo chi tiết:
1. **Bảng đối chiếu 8 Features PromQL:**
   - Liệt kê chính xác câu lệnh PromQL thực tế trong code của `collector.py` đang dùng cho từng feature (`qps`, `server_latency_p95`, `client_latency_p95`, `error_rate_5xx`, `max_pod_cpu_pct`, `max_pod_ram_pct`, `ram_floor_2m_pct`, `gc_pause_rate`).
   - Kiểm tra xem các tên metric và tên label trong các câu PromQL đó có khớp 100% với các metrics đang được xuất ra bởi **OTel Java Agent v2.10** và **OTel Collector Gateway (Thanos)** trên nhánh hạ tầng không? (Đặc biệt lưu ý: nhánh hạ tầng đã chuẩn hóa nhãn thành `k8s_cluster_name`, `cloud_provider`, `service_name` và dùng `traces_service_graph_*` cũng như `jvm_*`).
   - Kiểm tra xem các manifest trong `k8s/base/teastore/` đã bật xuất JVM & HTTP metrics sang OTel Collector chưa. Nếu có bất kỳ câu lệnh PromQL nào trong `collector.py` bị lệch tên metric hoặc tên label so với hạ tầng hiện tại, hãy chỉ rõ và đề xuất/cập nhật cho khớp hoàn toàn.
2. **Kiểm tra kết nối Tempo Trace RCA:**
   - Kiểm tra xem module `TempoTraceAnalyzer` truy vấn Grafana Tempo qua endpoint và định dạng tag nào (`service.name`, `cloud.provider`, `k8s.cluster.name`, `net.peer.name`, `db.system`), có khớp với cấu hình OTTL hiện tại trong `k8s/base/otel-collector/gateway/03-configmap.yaml` không?

### NHIỆM VỤ 2: Kiểm tra tính tương thích của `tests/chaos/` và `tests/locust/` với hạ tầng 3 cụm k3d
Hãy đọc các script trong `tests/chaos/` (`run_live.py`, `run_service_faults.py`, `FaultAgent.java`) và `tests/locust/`:
1. Kiểm tra xem tên các Kubernetes context (`k3d-hub-k3d`, `k3d-aws-k3d`, `k3d-azure-k3d`), tên namespace (`teastore`, `monitoring`, `storage`), và tên container k3d (`k3d-aws-k3d-server-0`, `k3d-azure-k3d-server-0`) trong các script chaos có khớp 100% với cấu hình hạ tầng hiện tại không? (Lưu ý xóa bỏ mọi tham chiếu cứng tới cụm `gcp` nếu còn sót lại trong script chaos).
2. Kiểm tra cơ chế nạp `FaultAgent.java` vào pod TeaStore có xung đột với `CATALINA_OPTS` chứa `opentelemetry-javaagent.jar` hiện tại không?

### NHIỆM VỤ 3: Thiết kế cầu nối Closed-Loop AIOps (Nối `ai-engine` vào Prometheus/Grafana & Telegram/Robusta)
Hãy kiểm tra và hoàn thiện cơ chế đầu ra của `ai-engine`:
1. **Xuất Metrics AI về Prometheus/Thanos & Grafana:**
   - Kiểm tra xem `ai-engine` đã có HTTP endpoint `/metrics` (dạng Prometheus client) hoặc đẩy OTLP để xuất các chỉ số:
     - `ai_anomaly_likelihood_percent{cloud_provider, service_name, model}`
     - `ai_reconstruction_error{cloud_provider, service_name, model}`
     - `ai_rca_component_latency_ms{cloud_provider, service_name, component="wan|self|db"}`
     chưa? Nếu chưa có hoặc chưa kết nối, hãy thiết kế/bổ sung nhẹ để Prometheus trên `hub-k3d` (hoặc OTel Collector) thu thập được và hiển thị trực tiếp lên Dashboard `mc-executive-overview.json` / `red-metrics.json`.
2. **Tích hợp Cảnh báo AI với Telegram / Robusta:**
   - Kiểm tra xem khi `ai-engine` phát hiện `ALERT` kèm kết quả phân rã RCA (`CROSS_CLOUD_WAN_DELAY`, `MEMORY_LEAK_GC_STALL`, `DATABASE_BOTTLENECK`), nó đã gửi thông báo qua Telegram Bot (sử dụng cùng `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` trong file `.env`) hoặc đẩy webhook sang Alertmanager/Robusta chưa?

---

## 3. CẬP NHẬT BÁO CÁO CHI TIẾT

Sau khi kiểm tra (và đồng bộ hóa các điểm lệch nếu có), hãy cập nhật bổ sung vào `docs/progress/04_ai_engine.md`:
1. **Mục 3.4 (Mới): Ma trận ánh xạ chi tiết 8 Features PromQL & Tempo Trace Tags** (ghi rõ câu lệnh PromQL thực tế trong code và tính tương thích với OTel Collector).
2. **Mục 4.3 (Mới): Kiểm định tính tương thích của Chaos Scripts (`tests/chaos/`) trên 3 cụm k3d**.
3. **Mục 5.1 (Mới): Cơ chế tích hợp Closed-Loop AIOps (Prometheus Exporter & Telegram/Robusta Alert Sink)**.