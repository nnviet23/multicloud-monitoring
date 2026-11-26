# Runbook 02: Cross Cluster Trace Broken (Đứt Gãy Vết Viễn Trắc Phân Tán)

## Summary
- **Trigger Alert:** `CrossClusterTraceBroken`, `CrossClusterCallFailureRateHigh`, `mTLSHandshakeFailed`
- **Severity:** Page (Critical / P1)
- **Owner / On-Call:** Observability Platform & SRE Team
- **Linked SLO:** Distributed Trace Ingestion Completeness (>99.5%)

---

## What this means
Các vết phân tán (Distributed Traces) xuyên cụm giữa `aws-k3d` và `azure-k3d` không còn được liên kết liền mạch (xuất hiện hiện tượng orphan traces hoặc cụt trace sau khi gọi qua mạng WAN). Nguyên nhân có thể do hỏng context injection/extraction của W3C `traceparent`, bộ lọc tại Spoke Collector bị lỗi, hoặc chứng chỉ mTLS 1.3 giữa Spoke Collector và Hub Gateway bị từ chối.

---

## How to confirm

### 1. Truy vấn PromQL & TraceQL
- Kiểm tra tỷ lệ lỗi gRPC exporter trên OTel Collector Spoke:
  ```promql
  sum(rate(otelcol_exporter_enqueue_failed_spans[5m])) by (service_name)
  ```
- Truy vấn TraceQL trên Grafana Tempo:
  ```traceql
  { status = error && span.cross_cluster = true }
  ```

### 2. Xác minh câu lệnh CLI
- Kiểm tra log bắt tay TLS trên Hub OTel Gateway:
  ```bash
  kubectl --context k3d-hub-k3d logs -l app=otel-gateway -n monitoring --tail=100 | grep -iE "tls|handshake|bad certificate"
  ```
- Kiểm tra tính hợp lệ của chứng chỉ trong `security/pki/`:
  ```bash
  openssl x509 -in security/pki/hub-gateway.crt -text -noout | grep -A 2 "Validity"
  ```

---

## First mitigations
1. **Tái tạo hoặc đồng bộ chứng chỉ mTLS nếu có lỗi TLS:**
   ```bash
   python -m infra.cli certs
   make update-certs
   ```
2. **Khởi động lại Pod OTel Spoke Collector:**
   ```bash
   kubectl --context k3d-aws-k3d rollout restart daemonset/otel-collector -n monitoring
   kubectl --context k3d-azure-k3d rollout restart daemonset/otel-collector -n monitoring
   ```
3. **Kiểm tra cấu hình Javaagent auto-instrumentation:** Xác nhận cờ `-javaagent:/opt/opentelemetry-javaagent.jar` vẫn đang được nạp trong Pods của TeaStore.

### What NOT to do (known footguns)
- **KHÔNG** sửa cấu hình exporter tại Spoke sang chế độ `insecure: true` để tránh bypass mTLS qua WAN, vi phạm nguyên tắc Zero-Trust ([ADR-0003](../architecture/decisions/ADR-0003-why-mtls-zero-trust-pki.md)).
- **KHÔNG** gửi vết trực tiếp từ Spoke vào Grafana Tempo mà không qua Hub OTel Gateway, vì sẽ làm mất bước chuẩn hóa Semantic Conventions (OTTL).

---

## Escalation
- Điều động **Observability Lead** nếu các vết vẫn bị phân mảnh sau khi khởi động lại Collector.
- Điều động **TeaStore Application Team** nếu nghi ngờ mã nguồn Java thả rơi header `traceparent` qua các lời gọi REST/RMI.

---

## Related dashboards and queries
- **Grafana Dashboard 06:** `Logs, Traces & Database Deepdive` (`logs-traces-deepdive.json`).
- **Grafana Dashboard 08:** `Telemetry & Cost Governance` — panel Trace Volume Reduction Waterfall.

---

## After the incident
1. Kiểm tra tỷ lệ trace span được ghi nhận thành công trong Tempo trong 30 phút tiếp theo.
2. Xác minh tính toàn vẹn của đồ thị phân tán liên cụm trên Grafana Node Graph.
3. Cập nhật ngày hết hạn chứng chỉ vào lịch trực để gia hạn định kỳ trước 30 ngày.
