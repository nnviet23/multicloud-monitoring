# Runbook 07: TeaStore Database Latency (Độ Trễ Cơ Sở Dữ Liệu TeaStore Cao)

## Summary
- **Trigger Alert:** `TeaStoreDatabaseLatencyHigh`, `MicroserviceHighErrorRate`
- **Severity:** Page (Critical / P1)
- **Owner / On-Call:** Application SRE & Database Administration Team
- **Linked SLO:** Database Query Duration P99 (<200ms) & TeaStore Checkout Availability (>99.5%)

---

## What this means
Cơ sở dữ liệu MySQL 8.0 hoặc dịch vụ `teastore-persistence` trên cụm `azure-k3d` đang phản hồi rất chậm, nghẽn hàng đợi kết nối hoặc phát sinh nhiều truy vấn bị khóa (table/row lock contention). Vì dịch vụ Persistence phụ thuộc vào cơ sở dữ liệu để phục vụ danh mục sản phẩm, đơn hàng và giỏ hàng, độ trễ này lan truyền ngược lên toàn bộ các vi dịch vụ phía trước trên `aws-k3d`, dẫn đến lỗi timeout HTTP 504 và suy kiệt ngân sách lỗi.

---

## How to confirm

### 1. Truy vấn PromQL
Kiểm tra độ trễ P99 truy vấn cơ sở dữ liệu:
```promql
histogram_quantile(0.99, sum(rate(teastore_db_query_duration_seconds_bucket[5m])) by (le))
```
Kiểm tra số luồng MySQL đang thực thi đồng thời:
```promql
mysql_global_status_threads_running{}
```

### 2. Xác minh câu lệnh CLI
Kiểm tra danh sách tiến trình đang khóa trong MySQL:
```bash
kubectl --context k3d-azure-k3d exec -it deploy/teastore-db -n teastore -- mysqladmin -uroot -p$MYSQL_ROOT_PASSWORD processlist
```
Kiểm tra logs của `teastore-persistence`:
```bash
kubectl --context k3d-azure-k3d logs -l app=teastore-persistence -n teastore --tail=50
```

---

## First mitigations
1. **Kiểm tra kịch bản thử nghiệm Chaos:** Nếu đang thực thi kịch bản `CHAOS-03` (tiêm khóa DB hoặc trễ MySQL), hủy tiến trình tiêm lỗi ngay:
   ```bash
   python tests/chaos/revert_chaos.py
   ```
2. **Giải phóng kết nối bị treo (Hung Sessions):** Nếu có truy vấn giữ khóa bảng quá lâu, xác định Thread ID và hủy:
   ```bash
   kubectl --context k3d-azure-k3d exec -it deploy/teastore-db -n teastore -- mysql -uroot -p$MYSQL_ROOT_PASSWORD -e "KILL <thread_id>;"
   ```
3. **Khởi động lại Pod Persistence nếu kết nối HikariCP bị cạn:**
   ```bash
   kubectl --context k3d-azure-k3d rollout restart deployment/teastore-persistence -n teastore
   ```

### What NOT to do (known footguns)
- **KHÔNG** xóa hoặc khởi động lại Pod MySQL khi chưa xác nhận cơ chế đồng bộ buffer pool xuống đĩa, tránh nguy cơ làm hỏng bảng InnoDB.
- **KHÔNG** chạy lệnh sửa đổi lược đồ bảng (`ALTER TABLE`) trực tiếp trong khi hệ thống đang chịu tải cao.

---

## Escalation
- Điều động **Database Administrator (DBA)** nếu phát hiện deadlock hoặc lỗi hỏng tệp dữ liệu MySQL.
- Thông báo cho **Application Team** nếu nghi ngờ có truy vấn Hibernate N+1 không tối ưu.

---

## Related dashboards and queries
- **Grafana Dashboard 03:** `Application & JVM (RED)` — panel Database & RMI Latency / Errors (Right Y-Axis).
- **Grafana Dashboard 06:** `Logs, Traces & Database Deepdive` — phân tích slow queries.

---

## After the incident
1. Kiểm tra lại độ trễ P99 của cơ sở dữ liệu đã trở về mức chuẩn (<50ms).
2. Phân tích nhật ký MySQL Slow Query Log (`/var/log/mysql/slow.log`).
3. Xác minh tính toàn vẹn dữ liệu đơn hàng và trạng thái đồng bộ persistence.
