# Runbook 05: OTel Collector Memory Pressure (Áp Lực Bộ Nhớ OTel Collector)

## Summary
- **Trigger Alert:** `OtelCollectorMemoryHigh`, `MemoryLimiterTriggered`
- **Severity:** Page / Ticket (Warning chuyển sang Critical nếu chạm 450MB)
- **Owner / On-Call:** Observability Platform Team
- **Linked SLO:** Telemetry Pipeline Data Loss (<0.01%)

---

## What this means
Bộ nhớ Resident Set Size (RSS) của OpenTelemetry Collector (tại Spoke Edge hoặc Hub Gateway) vượt ngưỡng cảnh báo **400MB**. Nếu mức tiêu thụ chạm ngưỡng giới hạn 500MB, bộ xử lý `memory_limiter` sẽ bắt đầu cưỡng chế hủy dữ liệu (drop metrics/spans) để tự vệ, hoặc Pod sẽ bị nhân Linux ép dừng vì tràn bộ nhớ (`OOMKilled`).

---

## How to confirm

### 1. Truy vấn PromQL
Kiểm tra dung lượng bộ nhớ thực tế và số lượng phần tử bị drop:
```promql
otelcol_process_resident_memory_bytes{service_name=~"otel-.*"}
```
```promql
sum(rate(otelcol_processor_dropped_spans_total[5m])) by (processor)
```

### 2. Xác minh câu lệnh CLI
Kiểm tra tài nguyên Pod và cảnh báo memory limiter trong logs:
```bash
kubectl --context k3d-hub-k3d top pod -l app=otel-gateway -n monitoring
kubectl --context k3d-hub-k3d logs -l app=otel-gateway -n monitoring | grep -i "memory_limiter"
```

---

## First mitigations
1. **Kiểm tra và siết chặt bộ lọc nhiễu biên (Edge Filter):**
   Xác nhận bộ xử lý `filter/drop_noise` tại Spoke Collector vẫn đang loại bỏ 100% các yêu cầu thăm dò sức khỏe (`/healthz`, `/readyz`, `/metrics`) trước khi truyền qua WAN.
2. **Tạm thời hạ tỷ lệ lấy mẫu vết (Head-based Trace Sampling):**
   Nếu tải hệ thống đang tăng đột biến, điều chỉnh tỷ lệ lấy mẫu từ `20%` xuống `10%` trong ConfigMap của Spoke Collector và nạp lại cấu hình:
   ```bash
   kubectl --context k3d-aws-k3d rollout restart daemonset/otel-collector -n monitoring
   ```
3. **Nâng giới hạn tài nguyên RAM:** Nếu lưu lượng tải hợp lệ tăng cao, điều chỉnh `limits.memory` từ 512Mi lên 768Mi trong manifest Kustomize overlay tương ứng.

### What NOT to do (known footguns)
- **KHÔNG** loại bỏ bộ xử lý `memory_limiter` khỏi đường ống thu thập; bộ xử lý này phải luôn là mắt xích đầu tiên theo đúng thứ tự chuẩn: Memory Limiter $\rightarrow$ Filter $\rightarrow$ Transform $\rightarrow$ Batch $\rightarrow$ Exporter.
- **KHÔNG** tắt bộ xử lý `batch`, vì việc gửi từng gói nhỏ lẻ sẽ làm tăng vọt chi phí CPU và bộ nhớ đệm gRPC.

---

## Escalation
- Điều động **Observability Engineer** nếu số lượng spans/metrics bị drop tiếp tục tăng.
- Báo cáo **FinOps / Platform Lead** nếu phát sinh bùng nổ nhãn metric (high-cardinality label explosion).

---

## Related dashboards and queries
- **Grafana Dashboard 08:** `Telemetry & Cost Governance` — panel Collector Buffer Health & High-Cardinality Metrics.
- **Grafana Dashboard 04:** `Compute & OS Kernel (USE)` — mức sử dụng RAM node.

---

## After the incident
1. Kiểm tra lại mức tiêu thụ RAM ổn định dưới 350MB.
2. Rà soát lại cấu hình batch size và timeout trong `deploy/platform/otel-collector/`.
3. Kiểm tra xem có microservice nào mới triển khai sinh nhãn động vô hạn hay không.
