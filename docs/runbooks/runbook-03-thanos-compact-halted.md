# Runbook 03: Thanos Compact Halted (Tiến Trình Nén Thanos Bị Dừng)

## Summary
- **Trigger Alert:** `ThanosCompactHalted`, `ThanosStorageFailure`
- **Severity:** Page (Critical / P1)
- **Owner / On-Call:** SRE Storage & Core Infrastructure Team
- **Linked SLO:** Long-term Metrics Retention & Query Availability (>99.9%)

---

## What this means
Tiến trình nén và giảm độ phân giải TSDB (`thanos-compact`) trên cụm `hub-k3d` đã dừng hoạt động. Nguyên nhân phổ biến gồm: phát hiện các khối TSDB bị chồng lấn (overlapping blocks), tệp chỉ mục TSDB bị lỗi hỏng, hoặc mất kết nối xác thực đến MinIO S3 object storage (lỗi `403 AccessDenied`). Nếu không khắc phục kịp thời, việc truy vấn metrics lịch sử dài hạn sẽ bị chậm và chi phí dung lượng đĩa sẽ tăng cao.

---

## How to confirm

### 1. Truy vấn PromQL
Kiểm tra cờ trạng thái `thanos_compact_halted` trên Thanos Query (:9090):
```promql
thanos_compact_halted{} == 1
```
Kiểm tra số thao tác lưu trữ thất bại với MinIO S3:
```promql
sum(rate(thanos_objstore_bucket_operations_failed_total{bucket="thanos-data"}[5m]))
```

### 2. Xác minh câu lệnh CLI
Kiểm tra log của Thanos Compact:
```bash
kubectl --context k3d-hub-k3d logs -l app.kubernetes.io/component=compact -n monitoring --tail=100
```
Kiểm tra kết nối và quyền hạn của tài khoản S3 đối với MinIO bucket:
```bash
kubectl --context k3d-hub-k3d get secret thanos-s3-creds -n monitoring -o yaml
```

---

## First mitigations
1. **Kiểm tra trạng thái MinIO Server:**
   ```bash
   kubectl --context k3d-hub-k3d get pods -l app=minio -n monitoring
   ```
2. **Nếu lỗi `403 AccessDenied`:** Đồng bộ lại Secret MinIO từ tệp cấu hình `.env`:
   ```bash
   make sync-secrets
   kubectl --context k3d-hub-k3d rollout restart deployment/thanos-compact -n monitoring
   ```
3. **Nếu có khối TSDB chồng lấn (Overlapping Blocks):**
   - Xác định ID của khối bị lỗi từ thông điệp log (`halted because of overlapping blocks: ...`).
   - Khởi động lại Thanos Compact với cờ giải quyết chồng lấn an toàn hoặc kiểm tra bằng công cụ `thanos tools bucket inspect`.

### What NOT to do (known footguns)
- **KHÔNG** tự ý xóa các thư mục TSDB block trực tiếp trên MinIO S3 bucket mà chưa sao lưu snapshot metadata.
- **KHÔNG** nâng số lượng `replicas` của Thanos Compact lớn hơn 1 (Thanos Compact là Singleton; chạy song song sẽ gây xung đột dữ liệu dẫn đến hỏng vĩnh viễn TSDB index).

---

## Escalation
- Điều động **Storage Infrastructure Lead** nếu cần can thiệp xử lý khối TSDB hỏng bằng công cụ offline.
- Thông báo cho **Platform Lead** nếu thời gian nén bị trễ quá 24 giờ.

---

## Related dashboards and queries
- **Grafana Dashboard 08:** `Telemetry & Cost Governance` — panel High-Cardinality Metrics & S3 Storage.
- **MinIO Console UI:** `http://localhost:9001` (xem bucket `thanos-data`).

---

## After the incident
1. Kiểm tra lại cờ `thanos_compact_halted == 0`.
2. Xác minh các khoảng nén 5m và 1h downsampled blocks đã được sinh thành công trong MinIO bucket.
3. Đảm bảo quy tắc lưu trữ 30d raw / 90d 5m / 365d 1h được thi hành đúng theo [ADR-0007](../adr/ADR-0007-tiered-storage-thanos-loki-tempo.md).
