# Kiểm thử phát hiện bất thường và RCA

Chạy lệnh từ thư mục gốc repository với Python 3.12 có `torch`, `numpy`,
`PyYAML`, `joblib`, `scikit-learn`. Dùng trọng số đã huấn luyện trong
`ai-engine/models/saved/`; bộ test không huấn luyện lại hoặc đổi ngưỡng cảnh báo.

## 1. Test hành vi AI và bộ đánh giá

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3.12 -m unittest discover -s tests/chaos -p 'test_*.py' -v
```

Kiểm tra lọc spike đơn lẻ, lỗi kéo dài, phục hồi, hiệu chỉnh cloud mới,
chấm điểm theo độ mới của mẫu và RCA. Test hồi quy đảm bảo WebUI chậm
cùng dịch vụ phía sau bất thường không tự động bị gán thành lỗi WAN.
Bộ đánh giá live không chấp nhận chỉ có SLO guard, RCA sai cloud hoặc thiếu telemetry.

## 2. Replay kịch bản qua mô hình thật

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3.12 ai-engine/inference/evaluate_test.py \
  --benchmark \
  --output tests/benchmarks/results/synthetic.json
```

`scenarios.json` chứa 11 kịch bản, chạy qua GRU + TCN đã huấn luyện,
bộ chấm điểm nhiều chu kỳ và hàm RCA thật:

| Kịch bản | Kết quả kỳ vọng |
| --- | --- |
| Normal / flash crowd / scale-out / low traffic | HEALTHY |
| Độ trễ giảm mạnh so với baseline cũ | HEALTHY |
| WAN AWS → GCP | ALERT, CROSS_CLOUD_WAN_DELAY, đúng GCP |
| WAN AWS → Azure | ALERT, CROSS_CLOUD_WAN_DELAY, đúng Azure |
| Rò rỉ bộ nhớ và GC stall | ALERT, MEMORY_LEAK_GC_STALL |
| CPU saturation và 5xx | ALERT, SERVICE_CPU_BOTTLENECK |
| MariaDB chậm | ALERT, DATABASE_BOTTLENECK |
| HTTP 5xx kéo dài | ALERT, error_rate_5xx tại AWS WebUI |

Đây là **dữ liệu tổng hợp** ở cấp feature/trace summary, không phải tiêm lỗi CPU,
bộ nhớ hoặc database thật. Kết quả kiểm tra suppression của mẫu đầu,
ALERT sau các mẫu liên tiếp, RCA và xóa cảnh báo sau khi điểm lỗi trở về bình thường.
Lệnh trả exit code 1 nếu bất kỳ ca nào sai; JSON lưu kết quả từng ca.

## 3. Tiêm lỗi WAN trong lab k3d

```bash
python3.12 tests/chaos/run_live.py \
  --baseline 90 --fault 90 --recovery 120 --settle 30 \
  --output tests/benchmarks/results/live-new-run
```

Yêu cầu 4 cụm k3d đang chạy, TeaStore ở `localhost:8080`, Docker và kubectl có
quyền truy cập lab. Helper image cục bộ mặc định `network-infra-check:ubuntu24.04`
phải có `tc`, `sh`, `sleep`; có thể chọn image khác bằng `--tc-image`.
Runner không tải image hay cài gói khi chạy.

Luồng chạy: baseline → GCP delay 250ms → gỡ lỗi và phục hồi → Azure delay 180ms
→ gỡ lỗi và phục hồi. Tạo tải 6 users và giữ cùng một detector xuyên các pha.
Chọn một ca bằng `--scenarios gcp_wan_delay` hoặc `azure_wan_delay`.
Mỗi pha phải dài ít nhất `settle + 3 × interval` giây. Lần chạy mới cần thư mục
output mới để giữ lại bằng chứng lần trước.

Runner chỉ thay qdisc của `eth0` trên node GCP/Azure được chỉ định. Nếu đã có
WAN shaping, runner dừng trước khi thay đổi. Helper chỉ được cấp `NET_ADMIN`;
watchdog tự gỡ qdisc sau thời gian giới hạn ngay cả khi runner bị kill.
Khối `finally` gỡ lỗi khi kết thúc hoặc nhận SIGINT/SIGTERM và kiểm tra qdisc
trở về `noqueue`. Lệnh không thay đổi replicas hoặc dữ liệu TeaStore.

Kết quả trong thư mục output:

- `events.json`: thời gian các pha, helper đang hoạt động, qdisc trước/sau, lỗi cleanup.
- `detector.log`, `detector.json`: log AI và điểm số từng chu kỳ.
- `traffic.log`: kết quả tải HTTP.
- `report.json`: PASS/FAIL riêng từng pha; số cảnh báo, model alerts, RCA, độ phủ telemetry.

Ca lỗi phải có **model alert và RCA đúng cloud** sau thời gian settle để PASS.
Baseline và recovery phải không có ALERT và có probe HTTP khỏe. Mỗi pha cần ít
nhất 3 mẫu, mỗi mẫu đủ 6 thực thể. Báo cáo tách `model_alert` khỏi `guard_reasons`
để thấy mô hình hay ngưỡng SLO tạo cảnh báo. `detection_seconds` tính từ lúc tiêm
lỗi tới ALERT đầu tiên trong pha; xem baseline trước khi diễn giải con số này.
Baseline có ALERT được ghi FAIL, không được tính là phát hiện lỗi thành công.

Kết quả live chỉ phản ánh lab và thời điểm chạy; baseline cũ, warm-up và
độ trễ export telemetry có thể làm baseline hoặc recovery FAIL. Báo cáo giữ
nguyên các ca FAIL để xác định vấn đề thay vì tự đổi threshold cho test PASS.
