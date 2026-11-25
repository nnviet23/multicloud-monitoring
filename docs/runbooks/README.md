# Sổ Tay Vận Hành SRE — Danh Mục Runbooks (SRE Incident Runbooks)

> Thư mục này chứa danh mục các sổ tay vận hành (Runbooks) độc lập theo tiêu chuẩn upstream Google SRE, phục vụ quy trình trực nhật On-Call và phản ứng sự cố khẩn cấp cho nền tảng **Multi-Cloud Observability & Closed-Loop AIOps Platform**.

---

## 1. Cấu Trúc Chuẩn Tắc Của Mỗi Runbook (Standard Runbook Structure)

Mỗi tài liệu trong thư mục này tuân thủ cấu trúc 7 phần nghiêm ngặt:
1. **Summary:** Cảnh báo kích hoạt, mức độ nghiêm trọng (Severity: page/ticket), kỹ sư phụ trách (Owner/on-call), và chỉ tiêu SLO liên đới.
2. **What this means:** Bản chất kỹ thuật của sự cố và tác động hệ thống.
3. **How to confirm:** Câu lệnh CLI và truy vấn PromQL/LogQL để xác định chính xác sự cố.
4. **First mitigations:** Các bước can thiệp nhanh tức thời để dập tắt ảnh hưởng, bao gồm mục đặc biệt **What NOT to do (known footguns)** nhằm tránh sai sót gây trầm trọng hóa sự cố.
5. **Escalation:** Quy trình điều động chuyên gia và các kênh liên lạc khẩn cấp.
6. **Related dashboards and queries:** Bảng điều khiển Grafana và truy vấn liên quan.
7. **After the incident:** Quy trình hậu kiểm, khắc phục triệt để và tổng kết Postmortem.

---

## 2. Bảng Danh Mục Runbooks (Runbook Index)

| Mã Runbook | Tên Runbook & Tệp Nguồn                                                                        | Cảnh Báo Kích Hoạt                                          | Mức Độ          | Trọng Tâm Xử Lý                                                  |
| :--------- | :--------------------------------------------------------------------------------------------- | :---------------------------------------------------------- | :-------------- | :--------------------------------------------------------------- |
| **RB-01**  | [runbook-01-spoke-wan-latency-high.md](./runbook-01-spoke-wan-latency-high.md)                 | `CrossCloudWANLatencyDegraded` / `WANLatencyHigh`           | Page (Critical) | Suy hao mạng diện rộng liên cụm `aws-k3d` ↔ `azure-k3d`          |
| **RB-02**  | [runbook-02-cross-cluster-trace-broken.md](./runbook-02-cross-cluster-trace-broken.md)         | `CrossClusterTraceBroken` / `mTLSHandshakeFailed`           | Page (Critical) | Đứt gãy luồng Trace OTLP, hỏng mTLS 1.3 hoặc mất W3C context     |
| **RB-03**  | [runbook-03-thanos-compact-halted.md](./runbook-03-thanos-compact-halted.md)                   | `ThanosCompactHalted` / `ThanosStorageFailure`              | Page (Critical) | Tiến trình nén Thanos bị treo, lỗi ghi MinIO S3 bucket           |
| **RB-04**  | [runbook-04-prometheus-scrape-failed.md](./runbook-04-prometheus-scrape-failed.md)             | `PrometheusScrapeFailed` / `SpokeClusterHeartbeatAbsent`    | Page (Critical) | Mất tín hiệu nhịp tim cụm Spoke hoặc lỗi thu thập metrics        |
| **RB-05**  | [runbook-05-otel-collector-memory-pressure.md](./runbook-05-otel-collector-memory-pressure.md) | `OtelCollectorMemoryHigh` / `MemoryLimiterTriggered`        | Page / Ticket   | Tràn bộ nhớ OTel Gateway/Edge Collector vượt ngưỡng 400MB        |
| **RB-06**  | [runbook-06-ai-anomaly-inference-down.md](./runbook-06-ai-anomaly-inference-down.md)           | `AIAnomalyInferenceDown` / `AIOpsAnomalyDetected`           | Ticket / Page   | Dịch vụ suy luận PyTorch Deep Ensemble (:9108) dừng hoạt động    |
| **RB-07**  | [runbook-07-teastore-database-latency.md](./runbook-07-teastore-database-latency.md)           | `TeaStoreDatabaseLatencyHigh` / `MicroserviceHighErrorRate` | Page (High)     | Nghẽn kết nối và độ trễ cao cơ sở dữ liệu MySQL trên `azure-k3d` |
