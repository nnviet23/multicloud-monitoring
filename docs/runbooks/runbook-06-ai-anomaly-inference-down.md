# Runbook 06: AI Anomaly Inference Down (Động Cơ Suy Luận AI Dừng Hoạt Động)

## Summary
- **Trigger Alert:** `AIAnomalyInferenceDown`, `AIOpsAnomalyDetected`
- **Severity:** Ticket / Page
- **Owner / On-Call:** AIOps & Machine Learning Engineering Team
- **Linked SLO:** AI Closed-Loop Inference Pipeline Availability (>99.0%)

---

## What this means
Động cơ học máy phát hiện bất thường Deep Learning Ensemble (kết hợp GRU Autoencoder, TCN và Isolation Forest) phục vụ suy luận thời gian thực trên cổng `:9108` đã dừng hoạt động, mất kết nối hoặc ngừng cập nhật điểm số bất thường `ai_anomaly_score` trong hơn 60 giây. Khả năng phát hiện tự động các điểm suy giảm hiệu năng liên đám mây bị gián đoạn.

---

## How to confirm

### 1. Truy vấn PromQL
Kiểm tra nhịp tim của tiến trình AI Engine trên Thanos Query:
```promql
up{job="ai-engine"} == 0
```
Kiểm tra thời gian cập nhật suy luận cuối cùng:
```promql
time() - ai_engine_last_inference_timestamp_seconds > 60
```

### 2. Xác minh câu lệnh CLI
Kiểm tra tiến trình và endpoint xuất chỉ số trên host máy trạm:
```bash
curl -s http://localhost:9108/metrics | grep -E "ai_anomaly_score|ai_engine_up"
ps aux | grep -i "detector.py"
tail -n 50 /tmp/ai_detector.log
```

---

## First mitigations
1. **Kiểm tra log lỗi của tiến trình suy luận:**
   ```bash
   tail -n 100 /tmp/ai_detector.log
   ```
2. **Khởi động lại tiến trình AI Inference Daemon:**
   ```bash
   pkill -f "detector.py" || true
   nohup python3 ai-engine/inference/detector.py > /tmp/ai_detector.log 2>&1 &
   ```
3. **Kiểm tra kết nối đến Thanos Query (:9090) và Tempo (:3200):** Đảm bảo module trích xuất 8 đặc trưng PromQL có thể truy vấn dữ liệu từ Thanos.

### What NOT to do (known footguns)
- **KHÔNG** kích hoạt huấn luyện lại mô hình (model retraining) trong thời gian đang xảy ra sự cố suy luận thời gian thực; việc này sẽ gây tranh chấp CPU/GPU trên host.
- **KHÔNG** tắt bộ đệm hạ nhiệt 60s cooldown buffer của kênh thông báo Telegram để tránh bão tin nhắn (alert storm).

---

## Escalation
- Điều động **Machine Learning Engineer** phụ trách AIOps Engine nếu tiến trình gặp lỗi hỏng trọng số mô hình PyTorch hoặc cạn kiệt tài nguyên CUDA/CPU.
- Báo cáo **SRE On-Call Lead** để chuyển sang chế độ giám sát cảnh báo tĩnh truyền thống (Prometheus Alerts & Pyrra SLOs).

---

## Related dashboards and queries
- **Grafana Dashboard 03:** `Application & JVM (RED)` — Panel 7 Dual Y-Axis so sánh Anomaly Score và ngưỡng kích hoạt.
- **Kênh Telegram Cảnh báo:** Kênh nhận tin nhắn RCA phân rã trễ $T_{\text{WAN}}, T_{\text{self}}, T_{\text{DB}}$.

---

## After the incident
1. Kiểm tra lại chỉ số `ai_engine_up == 1` và endpoint `:9108/metrics` phản hồi mã 200.
2. Kiểm tra xem có hiện tượng drift dữ liệu đặc trưng (feature drift) trong khoảng thời gian vừa qua không.
3. Lưu trữ các mẫu bất thường vừa phát hiện vào tập dữ liệu kiểm chuẩn khoa học (`experiments/datasets/`).
