# Cải thiện AI và kiểm thử lại — 31/10/2026

Đã triển khai xử lý dữ liệu thiếu không nhìn tương lai, phục hồi dựa trên
request mới, giữ bằng chứng RCA có thời hạn và phân biệt thiếu telemetry với
hệ thống khỏe. Không thay trọng số GRU/TCN hoặc ngưỡng MSE `0.35` để ép test đạt.
AI chưa đủ bằng chứng để coi là hoàn thiện cho production.

## Thay đổi

- Chia train/validation trước khi forward fill theo entity. Giá trị khởi đầu
  thiếu là 0; validation chỉ kế thừa quá khứ của chính entity, không backward
  fill. Shadow preprocessing trên CSV hiện tại cho train/val windows và
  baseline giống hệt trước sửa; dữ liệu hiện tại không có NaN.
- P95 online lấy từ delta histogram counter thay vì chỉ dựa vào cửa sổ 1 phút.
  Export lặp, counter reset, mất bucket hoặc quan sát quá tuổi không phải bằng
  chứng phục hồi. Cùng một export không tăng số lần xác nhận model alert.
- Giảm lịch sử latency khi có request mới khỏe và nhiều probe khỏe; chỉ giảm
  giá trị cũ, không nhân spike mới ra cả window. Lịch sử 5xx cần hai export
  khỏe. CPU chỉ giảm khi có xác nhận mới và CPU hiện tại thấp theo cả phần trăm
  lẫn z-score; RAM/GC giữ nguyên.
- Gauge CPU/RAM/discovery lọc JVM có counter hoạt động gần đây. Đã quan sát
  WebUI RAM cũ 89% so với 42.9% khi bỏ gauge pod chết trong cùng thời điểm query.
- Trace RCA ghi ID/tuổi, TTL 90 giây, không gia hạn khi đọc; phục hồi vô hiệu
  bằng chứng cũ. Cache chỉ giải thích cảnh báo, không kích hoạt mô hình/guard.
  Lọc suy luận WAN khi CPU phía gọi hoặc đích >=85% vì phần thời gian dư giữa
  client/server span có thể bị nhiễu bởi lập luồng CPU.
- HTTP probe giữ mã 502 thật, dùng trang sản phẩm thay vì chỉ `/status`.
  Endpoint lấy từ config; endpoint tùy chỉnh bị hỏng không tự chuyển localhost.
  Prometheus lỗi, thiếu CPU/RAM hoặc thiếu entity bắt buộc cho model UNKNOWN
  và `likelihood_pct=null`; guard SLO độc lập vẫn có thể ALERT.
- `likelihood_pct` dùng `min(current_mse, short_mean_mse)`;
  `window_likelihood_pct` tách phần rủi ro còn trong lịch sử. Recalibration chỉ
  cập nhật metadata, có hash model/validation. Brier 0.000090, ECE 0.009078 là
  kết quả trên normal validation và fault tổng hợp, không phải tập sự cố thực
  tế độc lập. Ensemble online hiện dùng GRU + TCN.

## Kết quả đã xác minh

| Nhóm | Kết quả | Giới hạn |
| --- | --- | --- |
| Unit/regression | 41/41 đạt | Bao gồm NaN, counter lặp/reset, giữ RAM/GC, spike amplification, TTL, CPU gây nhiễu WAN, HTTP 502 và thiếu telemetry |
| Replay mô hình thật | 11/11 đạt | Feature/trace summary tổng hợp; không thay thế tiêm memory leak thật |
| CPU JVM thật, 12 users | Phát hiện CPU đúng GCP, 5/5 mẫu sau settle có model alert | `services-3`; trở lại HEALTHY ổn định sau 22.6 giây, không ALERT sau 30 giây |
| WebUI outage thật, 12 users | Đạt phát hiện lỗi; 4/5 mẫu sau settle ALERT, có HTTP 502 | Phần lớn do SLO guard; recovery không đạt 30 giây, HEALTHY ổn định ở 100.1 giây trong `services-3` |
| DB lock có xác minh SQL | Chưa đạt phát hiện/RCA: 0/5 ALERT sau settle | `db-verified`: reader SQL độc lập timeout 124, nhưng luồng web/probe vẫn nhanh; chưa chứng minh workload đã xuyên mọi tầng cache tới bảng khóa |
| Prometheus không truy cập được | UNKNOWN, likelihood null dù HTTP probe 200 | Lưu `unknown.json`; không báo HEALTHY bằng feature 0 giả |

## WAN cuối trên bản sửa hiện tại

`live-final`, 12 users cố định, interval 6 giây, baseline 60 giây, mỗi fault
90 giây, recovery 120 giây, settle 30 giây: **5/5 pha đạt**. Mỗi pha có ít nhất
3 mẫu sau settle và đủ 6 entity. Model và guard giữ trạng thái xuyên các pha.

| Pha | Mẫu sau settle | ALERT / model alert | RCA WAN đúng cloud | HEALTHY ổn định sau khi gỡ lỗi |
| --- | --- | --- | --- | --- |
| Baseline | 5 | 0 / 0 | — | — |
| GCP delay 250ms | 10 | 10 / 10 | 7/10 | — |
| Recovery GCP | 15 | 0 / 0 | — | 27.7 giây |
| Azure delay 180ms | 10 | 10 / 10 | 10/10 | — |
| Recovery Azure | 15 | 0 / 0 | — | 20.7 giây |

ALERT đầu trong pha fault: GCP 28.0 giây, Azure 9.0 giây. Recovery tính từ
lúc gỡ lỗi đến mẫu HEALTHY đầu tiên mà mọi mẫu tiếp theo trong cửa sổ đo vẫn
HEALTHY và probe tốt; không chỉ lấy lần HEALTHY thoáng qua. Không có ALERT
quay lại trong phần recovery còn lại của lần chạy này.

Tiêu chí PASS của pha fault yêu cầu model alert và ít nhất một RCA đúng cloud;
**5/5 pha không đồng nghĩa RCA ổn định 100% mỗi mẫu**. GCP cải thiện từ 1/10 ở
lần retest cũ lên 7/10, vẫn cần tăng độ phủ trace và kiểm tra lặp nhiều lần.
So sánh recovery khoảng 93 giây trước sửa với 27.7/20.7 giây hiện tại là kết
quả hai lần chạy lab có tải khác nhau (6 và 12 users), chưa phải benchmark
đối chứng cùng tải hoặc cam kết độ trễ production.

## Các lần thử trung gian và lỗi còn lại

Không loại các lần thử không đạt khỏi bằng chứng:

- Baseline cũ trong `RESULTS-2026-10-31.md`: WAN chỉ đạt 3/5 pha, recovery
  khoảng 93 giây; GCP chỉ có RCA đúng 1/10 mẫu sau settle.
- `live-1`: 4/5 pha; GCP recovery 28.2 giây, Azure có một ALERT muộn và recovery
  39.2 giây. GCP RCA đúng 7/10, Azure 10/10 mẫu sau settle.
- `live-2`: 4/5 pha; GCP từng HEALTHY sau 21.2 giây nhưng lại ALERT ở cuối
  recovery. Nguyên nhân làm mới lịch sử bằng phép gán đã nhân một spike mới
  ra cả window. Đã sửa thành phép giảm có giới hạn và thêm regression test;
  không dùng mốc HEALTHY đầu tiên để tuyên bố recovery thành công.
- Bước chuẩn bị CPU lần đầu chạy compiler có OTel agent gây timeout/OOM pod.
  Đã tắt `JAVA_TOOL_OPTIONS`, giới hạn heap helper và loại bước compile khỏi
  pha đo. Pod đã phục hồi; lỗi chuẩn bị được giữ trong `services/report.json`.
- Các test DB trước `db-verified` chưa có `autocommit=0`; không được dùng làm
  bằng chứng tiêm lỗi InnoDB thành công. Runner cuối kiểm tra reader độc lập.
  Điều kiện `autocommit=0` theo [tài liệu MariaDB LOCK TABLES](https://mariadb.com/docs/server/reference/sql-statements/transactions/lock-tables).
- `services-3` dùng bản trước lần bổ sung lọc WAN bị CPU gây nhiễu và xác nhận
  hai export để giảm lịch sử 5xx. Các sửa cuối có regression test; chưa dùng
  kết quả cũ để tuyên bố WebUI restart đã được sửa hoàn toàn.

Ưu tiên tiếp theo: tăng độ phủ RCA GCP, tạo workload DB không bị cache che, đối chiếu SQL span và
request bị block; kiểm thử lại thời gian khởi động WebUI; thêm memory leak
thật, tải dài và tập sự cố độc lập để đo false positive/false negative. TTL và
lọc CPU chỉ giảm suy luận WAN sai, chưa biến span residual thành phép đo mạng
chắc chắn trong mọi môi trường.

## Tái hiện và bằng chứng

Chạy từ thư mục gốc, Python 3.12; xem `README.md` cùng thư mục để biết yêu cầu.

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3.12 -m unittest discover -s tests/chaos -p 'test_*.py' -v
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3.12 ai-engine/inference/evaluate_test.py --benchmark --output /tmp/ai-synthetic.json
python3.12 tests/chaos/run_live.py --baseline 60 --fault 90 --recovery 120 --settle 30 --users 12 --output tests/benchmarks/results/live-new-run
python3.12 tests/chaos/run_service_faults.py --scenarios cpu db_lock webui_outage --users 12 --output tests/benchmarks/results/service-new-run
```

Artifact gốc tại `tests/benchmarks/results/improve-20261031/` (gitignored):
`unit-tests.log`, `synthetic-final.json`, `preprocess-audit.json`,
`dead-pod-audit.json`, `unknown.json`, các thư mục live/service có
`events.json`, `report.json`, `detector.json`, `detector.log`, `traffic.log`.
`live-final/timing-audit.json` ghi thời gian HEALTHY ổn định và tỷ lệ RCA từng
pha. `cleanup.json` xác nhận cả 8 deployment đủ replicas, qdisc GCP/Azure
`noqueue`, không còn session `SLEEP` tiêm DB, helper Docker hoặc tiến trình
detector/traffic/fault runner của lượt test; CPU các dịch vụ khoảng 0.3–1.1%.
WAN dùng qdisc có watchdog; CPU có deadline/stop; DB có timeout và KILL session;
WebUI có watchdog khôi phục replicas. Runner lưu lỗi cleanup và giữ ca FAIL.

SHA256 trọng số giữ nguyên:

```text
gru_autoencoder.pt c24beb13b45fa390338a72b029173b59982c8f1601b03c3e0a1d5fd364668461
tcn_autoencoder.pt 690d648b4a9dd3514c7772e08cba01213bd5f5c80c5f3e15470832988c6125dd
```
