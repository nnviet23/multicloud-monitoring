# Runbook 04: Prometheus Scrape Failed (Thu Thập Metrics Thất Bại)

## Summary
- **Trigger Alert:** `PrometheusScrapeFailed`, `SpokeClusterHeartbeatAbsent`
- **Severity:** Page (Critical / P1)
- **Owner / On-Call:** Observability Platform Team
- **Linked SLO:** Telemetry Pipeline Heartbeat & Ingestion (>99.9%)

---

## What this means
Prometheus Agent hoặc Hub Thanos Receive không thể thu thập các chỉ số đo đạc từ một hoặc nhiều endpoint mục tiêu trong hệ thống. Tín hiệu nhịp tim (`up == 0`) xuất hiện tại các thành phần trọng yếu như TeaStore microservices, OTel Edge Collector trên Spoke, hoặc Node Exporter. Điều này dẫn đến khoảng mù viễn trắc (blind spots), làm sai lệch các chỉ số SLI/SLO và vô hiệu hóa các thuật toán phát hiện bất thường của AI Anomaly Engine.

---

## How to confirm

### 1. Truy vấn PromQL
Xác định danh sách các mục tiêu đang mất kết nối thu thập:
```promql
up == 0
```
Kiểm tra tỷ lệ mẫu đo đạc bị out-of-order hoặc drop:
```promql
sum(rate(prometheus_target_scrapes_sample_out_of_order_total[5m])) by (job)
```

### 2. Xác minh câu lệnh CLI
Kiểm tra trạng thái Pods trên các cụm tương ứng:
```bash
kubectl --context k3d-hub-k3d get pods -n monitoring
kubectl --context k3d-aws-k3d get pods -n monitoring
kubectl --context k3d-azure-k3d get pods -n monitoring
```
Kiểm tra khả năng phân giải DNS nội bộ giữa các cụm:
```bash
python -m infra.cli sync-hosts
```

---

## First mitigations
1. **Nếu Pod mục tiêu bị CrashLoopBackOff:** Kiểm tra lý do dừng và logs:
   ```bash
   kubectl --context k3d-<cluster> logs <pod-name> -n <namespace> --previous --tail=50
   ```
2. **Nếu lỗi phân giải mạng hoặc DNS giữa các node k3d:** Thực hiện đồng bộ lại hosts:
   ```bash
   python -m infra.cli sync-hosts
   ```
3. **Khởi động lại Pod thu thập viễn trắc:**
   ```bash
   kubectl --context k3d-<cluster> rollout restart daemonset/otel-collector -n monitoring
   ```

### What NOT to do (known footguns)
- **KHÔNG** xóa bỏ các nhãn định danh cụm (`cloud.provider`, `k8s.cluster.name`) khỏi cấu hình thu thập để tránh xung đột khóa tổng hợp (compound key collision).
- **KHÔNG** tăng `scrape_timeout` vượt quá `scrape_interval`, vì sẽ gây hiện tượng dồn ứ hàng đợi cào dữ liệu (scrape queue backlog).

---

## Escalation
- Điều động **SRE On-Call Engineer** xử lý ngay lập tức nếu cụm Spoke bị mất nhịp tim quá 2 phút.
- Báo cáo **Security Lead** nếu nguyên nhân bắt nguồn từ NetworkPolicy chặn cổng thu thập.

---

## Related dashboards and queries
- **Grafana Dashboard 01:** `Executive Overview` — bảng Cloud Cluster Fleet Health Matrix.
- **Grafana Dashboard 04:** `Compute & OS Kernel (USE)` — giám sát tải của các Node.

---

## After the incident
1. Xác nhận toàn bộ chỉ số `up` đã quay về giá trị 1.
2. Kiểm tra xem AI Anomaly Engine có ghi nhận bất thường giả (false positive) do thiếu dữ liệu hay không.
3. Xem xét cập nhật ServiceMonitor hoặc PodMonitor nếu dịch vụ thay đổi cổng hoặc đường dẫn metrics.
