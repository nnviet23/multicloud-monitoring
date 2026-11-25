# Runbook 01: Spoke WAN Latency High (Độ Trễ Mạng WAN Liên Cụm Cao)

## Summary
- **Trigger Alert:** `CrossCloudWANLatencyDegraded`, `WANLatencyHigh`
- **Severity:** Page (Critical / P1)
- **Owner / On-Call:** SRE Platform & Network Engineering Team
- **Linked SLO:** TeaStore Cross-Cloud P99 Latency (<1500ms) & Availability SLO (99.5%)

---

## What this means
Độ trễ P99 của các cuộc gọi liên đám mây giữa `aws-k3d` (Compute Services) và `azure-k3d` (Persistence Service / MySQL) vượt ngưỡng **1500ms** trong hơn 2 phút liên tiếp. Tình trạng này làm suy giảm nghiêm trọng trải nghiệm người dùng trên TeaStore WebUI, có nguy cơ làm cạn kiệt ngân sách lỗi (Error Budget) và kích hoạt cảnh báo Burn Rate khẩn cấp.

---

## How to confirm

### 1. Truy vấn PromQL
Kiểm tra độ trễ P99 của đồ thị Service Graph liên cụm trên Thanos Query (:9090):
```promql
histogram_quantile(0.99, sum(rate(traces_service_graph_request_server_seconds_bucket{client=~"teastore-.*", server="teastore-persistence"}[5m])) by (le))
```

### 2. Xác minh câu lệnh CLI
Kiểm tra quy tắc suy hao `tc netem` trên container Spoke:
```bash
docker exec -it k3d-aws-k3d-server-0 tc qdisc show dev eth0
```
Kiểm tra xem có kịch bản tiêm lỗi Chaos đang thực thi trên host hay không:
```bash
ps aux | grep -i "run_service_faults.py"
```

---

## First mitigations
1. **Kiểm tra tiến trình thử nghiệm Chaos:** Nếu sự cố xảy ra trong phiên thử nghiệm hỗn loạn có kế hoạch, dừng kịch bản tiêm lỗi:
   ```bash
   pkill -f "run_service_faults.py" || true
   python tests/chaos/revert_chaos.py
   ```
2. **Khôi phục cấu hình WAN chuẩn:** Sử dụng Python CLI để thiết lập lại thông số mạng chuẩn (10ms ± 2ms, 0.1% loss):
   ```bash
   python -m infra.cli wan --delay 10ms --jitter 2ms --loss 0.1%
   ```
3. **Kiểm tra nghẽn đường truyền Docker Bridge:**
   ```bash
   docker network inspect mc-monitoring-net
   ```

### What NOT to do (known footguns)
- **KHÔNG** xóa mạng Docker `mc-monitoring-net` trong khi các container k3d đang hoạt động; việc này sẽ làm đứt toàn bộ kết nối gRPC mTLS giữa Spoke và Hub.
- **KHÔNG** tăng timeout của client HTTP trong WebUI lên mức vô lý mà không kiểm tra tầng Persistence, vì sẽ dẫn đến tích tụ connection pool và cạn kiệt bộ nhớ JVM.

---

## Escalation
- Nếu sau 5 phút độ trễ vẫn không giảm về mức danh định (<30ms RTT), điều động **Platform Lead** và **Network Specialist** qua kênh Telegram On-Call khẩn cấp.
- Nếu nghi ngờ lỗi do Docker daemon trên host máy trạm, chuẩn bị quy trình khởi động lại Docker Engine.

---

## Related dashboards and queries
- **Grafana Dashboard 05:** `Network & WAN Transport` (`wan-telemetry.json`) — xem panel P95/P99 WAN Latency.
- **Grafana Dashboard 01:** `Executive Overview` (`mc-executive-overview.json`) — xem Cloud Fleet Health Matrix.
- **Grafana Dashboard 07:** `SLO & Error Budget` — theo dõi tốc độ đốt Error Budget.

---

## After the incident
1. Ghi nhận thời điểm bắt đầu và kết thúc sự cố vào nhật ký vận hành (`docs/planning/activity.md`).
2. Xác minh lại phân phối RTT bằng `ping -c 50 172.28.0.3` từ container Spoke.
3. Đánh giá phần trăm Error Budget bị tiêu thụ trong phiên để quyết định có cần freeze release hay không.
