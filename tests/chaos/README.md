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

Cách chạy chuẩn là cả đợt (campaign) qua `scripts/run_fault_campaign.sh`; xem mục 6.

```bash
python3.12 tests/chaos/run_live.py \
  --scenarios gcp_wan_delay azure_wan_delay aws_wan_delay \
  --baseline 120 --fault 120 --recovery 150 --settle 30 --interval 10 --users 12 \
  --output experiments/raw/<experiment_id>/wan
```

Yêu cầu 4 cụm k3d đang chạy, TeaStore ở `localhost:8080`, Docker và kubectl có
quyền truy cập lab. Helper image cục bộ mặc định `network-infra-check:ubuntu24.04`
phải có `tc`, `sh`, `sleep`; có thể chọn image khác bằng `--tc-image`.
Runner không tải image hay cài gói khi chạy.

Luồng chạy: baseline → GCP delay 250ms → phục hồi → Azure delay 180ms → phục hồi
→ AWS delay 200ms → phục hồi. Giữ cùng một detector (`--interval 10`, khớp chu kỳ
train) xuyên các pha; detector luôn chạy với `--disable-telegram` nên thí nghiệm
không gửi cảnh báo thật.
Mỗi pha phải dài ít nhất `settle + 3 × interval` giây. Lần chạy mới cần thư mục
output mới để giữ lại bằng chứng lần trước.

Runner chỉ thay qdisc của `eth0` trên node spoke được chỉ định. Lab có netem nền
`delay 10ms 2ms loss 0.1%` (`--baseline-netem`); runner dừng nếu qdisc hiện tại
khác nền này, khi tiêm lỗi chỉ nâng delay và giữ jitter/loss, rồi khôi phục và
kiểm tra qdisc trở về đúng netem nền. Helper chỉ được cấp `NET_ADMIN`; watchdog
tự khôi phục sau thời gian giới hạn ngay cả khi runner bị kill. Preflight kiểm
tra pod Tempo bằng nhãn `app=tempo`. Lệnh không thay đổi replicas hoặc dữ liệu TeaStore.

Kết quả trong thư mục output:

- `events.json`: thời gian các pha, helper đang hoạt động, qdisc trước/sau, lỗi cleanup.
- `detector.log`, `detector.json`: log AI và điểm số từng chu kỳ.
- `traffic.log`: kết quả tải HTTP.
- `report.json`: PASS/FAIL riêng từng pha; số cảnh báo, model alerts, RCA, độ phủ telemetry.

Ca lỗi phải có **model alert và RCA đúng cloud** sau thời gian settle để PASS.
"Đúng cloud" nghĩa là detector phát `[CROSS_CLOUD_WAN_DELAY] localized_cloud=<cloud bị lỗi>`:
`TraceEvidence.localize()` lấy giao các đầu mút của mọi link bị trễ (≥ 65 ms) và
loại các cloud nằm trên link round-trip khỏe cùng lúc (span CLIENT trừ span SERVER
con). Link tính bằng khe hở giữa các span (Method B) không thấy trễ một chiều nên
chỉ được dùng để buộc tội, không để minh oan. Lỗi egress AWS không có link `aws->aws`
nên tiêu chí cũ dạng `aws->{cloud}` không bao giờ đạt được cho AWS.
Baseline và recovery phải không có ALERT và có probe HTTP khỏe. Mỗi pha cần ít
nhất 3 mẫu, mỗi mẫu đủ 6 thực thể. Báo cáo tách `model_alert` khỏi `guard_reasons`
để thấy mô hình hay ngưỡng SLO tạo cảnh báo. `detection_seconds` tính từ lúc tiêm
lỗi tới ALERT đầu tiên trong pha; xem baseline trước khi diễn giải con số này.
Baseline có ALERT được ghi FAIL, không được tính là phát hiện lỗi thành công.

Kết quả live chỉ phản ánh lab và thời điểm chạy; baseline cũ, warm-up và
độ trễ export telemetry có thể làm baseline hoặc recovery FAIL. Báo cáo giữ
nguyên các ca FAIL để xác định vấn đề thay vì tự đổi threshold cho test PASS.

## 4. CPU JVM, database lock, memory leak, HTTP 5xx và WebUI outage thật

```bash
python3.12 tests/chaos/run_service_faults.py \
  --scenarios cpu db_lock memory_leak http_5xx webui_outage \
  --fault 90 --recovery 150 --users 12 --interval 10 \
  --output experiments/raw/<experiment_id>/service
```

Runner chạy tuần tự, giữ một detector xuyên các pha và lưu log/JSON:

- `cpu`: biên dịch agent Java bằng JDK có sẵn trong pod, attach vào đúng JVM
  recommender và chạy một thread CPU có thời hạn. Agent có lệnh stop và tự dừng
  sau tối đa 180 giây; không cần tải thư viện hoặc khởi động lại JVM.
  Compiler/helper tắt `JAVA_TOOL_OPTIONS` và giới hạn heap 32–64 MiB để tránh
  tự chạy OTel agent hoặc làm pod thiếu bộ nhớ trong bước chuẩn bị.
- `db_lock`: giữ write lock trên hai bảng catalog TeaStore trong một session
  MariaDB với `autocommit=0`, có `SLEEP` giới hạn, sau đó unlock. Một kết nối
  SQL độc lập phải bị timeout khi đọc bảng để xác nhận lock có tác dụng.
  Cleanup đóng session; remote
  `timeout` giới hạn cả thời gian đợi lấy lock. Không sửa dữ liệu bảng.
  Runner evict cache JPA và reset EntityManagerFactory qua endpoint quản trị
  TeaStore. Cache ở các tầng khác vẫn có thể che lỗi khỏi luồng duyệt web;
  SQL lock được xác nhận chưa đủ chứng minh request người dùng bị chặn.
- `memory_leak`: cùng agent Java, giữ heap tăng dần (≤ 6 MiB mỗi 0,9 s) trong JVM
  persistence (Azure), dừng tăng ở 86% max heap hoặc khi working set của container
  (cgroup v2: `memory.current − inactive_file`) chạm 88% limit, rồi giải phóng.
  Luôn chạy ít nhất 180 giây (`MIN_FAULT_SECONDS`) vì `ram_floor_2m_pct` là giá
  trị nhỏ nhất trong 120 giây: leak ngắn hơn không thể nâng floor.
  Limit persistence là 768Mi: với `-Xmx256m` và ~250 MiB non-heap (OTel + Kieker
  agent) thì 512Mi cũ khiến kernel OOM-kill container ngay khi leak bắt đầu.
- `http_5xx`: POST `cartAction` với productid sai mỗi 0,35 s (xác minh HTTP 500 trước).
- `webui_outage`: tạm đưa replicas WebUI về 0 rồi trả về số replicas ban đầu.
  Watchdog độc lập tự khôi phục nếu runner bị dừng bất thường.

CPU cần model alert và RCA CPU tại `gcp:teastore-recommender`; DB cần ALERT và
bằng chứng SQL bottleneck (có thể tới sau khi lock được nhả vì span chỉ kết thúc
lúc đó); memory leak cần model alert và `MEMORY_LEAK_GC_STALL` tại persistence;
5xx cần model alert và `error_rate_5xx` tại WebUI. Outage kiểm tra ALERT và probe
HTTP lỗi (WebUI bị dừng nên không có telemetry JVM cho mô hình).

## 5. Dữ liệu mới, thời gian phục hồi và ý nghĩa điểm số

- Preprocessing chia train/validation trước khi điền dữ liệu thiếu. Forward fill
  theo từng entity và từng thời điểm; validation được phép mang giá trị cuối
  train sang. Khi chưa có quan sát quá khứ, fallback ban đầu là 0; không bfill.
- Detector dùng chênh lệch histogram counter giữa các export để đo P95 của các
  request mới. Counter reset, bucket thay đổi, dữ liệu lặp hoặc quá tuổi không
  được coi là bằng chứng phục hồi.
- Chỉ làm mới lịch sử hai feature latency khi có hai export khỏe độc lập, hoặc
  batch ít nhất 5 request mới khỏe cùng nhiều HTTP probe khỏe. Lịch sử 5xx cần
  đủ hai export khỏe; CPU chỉ giảm khi có xác nhận mới và CPU hiện tại thấp cả
  theo phần trăm lẫn z-score. Memory và GC được giữ lại.
  Chỉ giảm các giá trị latency lịch sử, không nhân một spike mới ra cả window.
  Poll đọc lại cùng export không tự tăng số bằng chứng xác nhận model alert.
- RCA có thể sử dụng trace của cùng sự cố trong tối đa 90 giây. `rca_evidence`
  ghi trace ID và tuổi; đọc cache không gia hạn TTL, xác nhận phục hồi vô hiệu
  bằng chứng cũ. Cache không dùng để kích hoạt model hay SLO guard.
  Không gán WAN theo phần thời gian dư của span khi CPU bên gọi/đích đang
  saturation: lịch lập luồng tại client cũng có thể làm phần dư tăng.
- `likelihood_pct` là risk score của model dựa trên điểm hiện tại và short
  window; `window_likelihood_pct` cho biết rủi ro còn trong lịch sử. SLO guard
  có thể ALERT dù risk score của model thấp; xem `model_alert`/`guard_reasons`.
- Khi truy vấn Prometheus lỗi, thiếu CPU/RAM hoặc thiếu entity đã huấn luyện,
  trạng thái mô hình là UNKNOWN; SLO guard độc lập vẫn có thể phát ALERT.
  Detector không cập nhật buffer bằng các số 0 giả. Endpoint lấy từ config; endpoint tùy
  chỉnh không tự chuyển sang dữ liệu localhost.
  Có thể khai báo `inference.required_entities` để thay đổi danh sách bắt buộc
  khi chủ đích gỡ một dịch vụ. Gauge discovery/CPU/RAM lọc các JVM có counter
  hoạt động gần đây để tránh gauge pod đã chết còn lưu trong exporter.

Sau khi thay đổi cách ánh xạ likelihood, kiểm định lại với trọng số hiện có:

```bash
OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 python3.12 ai-engine/training/recalibrate.py
```

Lệnh giữ nguyên weights và ngưỡng MSE, cập nhật metadata likelihood trên normal
validation và reference fault tổng hợp. Kết quả này không thay thế đánh giá xác
suất trên các sự cố thực tế độc lập. Thêm `--threshold <giá trị> --evidence <file
sweep> --reason "<lý do>"` để đổi điểm vận hành (operating point); ngưỡng thống kê
cũ, ngưỡng chọn, file bằng chứng và lý do được lưu trong
`threshold_config.json["threshold_selection"]`.

## 6. Đợt tiêm lỗi (campaign) và đánh giá offline

```bash
# Cả 8 kịch bản, kết quả vào experiments/raw/<experiment_id>/{wan,service,system}
scripts/run_fault_campaign.sh 20261113_teastore_fault-campaign-b_run01 12
# Chỉ một phần (giá trị rỗng bỏ qua stage)
WAN_SCENARIOS="" SERVICE_SCENARIOS="memory_leak http_5xx" scripts/run_fault_campaign.sh <id> 12

# Chạy lại dữ liệu thật đã ghi qua một phiên bản mô hình (chỉ mô hình, không SLO guard)
python3.12 ai-engine/inference/replay_eval.py \
  --normal experiments/raw/<normal_run>/metrics/entity_features.csv \
  --chaos experiments/raw/<campaign>/wan experiments/raw/<campaign>/service
# Quét ngưỡng quyết định, ghi thành dữ liệu dẫn xuất có provenance
python3.12 scripts/threshold_sweep.py experiments/processed/<date>_threshold-sweep_<model>.json \
  --thresholds 2.4 2.0 1.6 1.2 --normal ... --chaos ...
```

Trong replay, cảnh báo ở pha recovery trong ~60 giây đầu là đuôi cửa sổ 120 giây
còn chứa dữ liệu lỗi; detector online xóa chúng bằng logic phục hồi mà replay
không mô phỏng. Đánh giá false positive dựa trên run bình thường riêng.
