# Báo cáo: Huấn luyện lại và đánh giá AI Engine trên topology 4 cụm (model v1 → v2)

Ngày: 2026-11-13 · Branch `AI` · Lab: 4 cụm k3d (hub, aws, azure, gcp) trên một host 16 vCPU / 12.8 GiB,
netem nền `delay 10ms 2ms loss 0.1%` trên mỗi spoke.

Tất cả con số dưới đây lấy từ dữ liệu thô trong `experiments/raw/` và manifest tương ứng trong
`experiments/manifests/`. Đây là kết quả của **một lab mô phỏng trên một máy**, không phải cloud thật.

## 1. Tóm tắt

| Câu hỏi | Kết quả |
|---|---|
| Model cũ còn dùng được trên topology 4 cụm? | Không: replay báo động giả (false positive, FP) **10/17** mẫu trên run bình thường run01 (mẫu rất nhỏ, chỉ để định hướng). |
| Model mới có báo động giả trên dữ liệu bình thường chưa từng thấy? | v1 và v2: **0/270** chu kỳ trên run *erratic* 45 phút (tải vượt ngoài phạm vi train, không dùng để tinh chỉnh). |
| Phát hiện lỗi thật (đợt B, held-out, v2) | **8/8** lỗi được phát hiện; mô hình phát hiện **7/7** lỗi mà nó quan sát được (WebUI outage do probe HTTP phát hiện vì service bị dừng không còn telemetry). |
| Khoanh vùng (RCA) | CPU, DB lock, memory leak, HTTP 5xx: đúng entity/nguyên nhân. WAN: sau 3 bản sửa RCA (kiểm lại bằng các đợt C, D, E), đợt E đặt tên đúng cloud ở 9/11 (GCP), 10/11 (Azure), 10/11 (AWS) chu kỳ cảnh báo, **0 lần sai cloud**, cả 7 pha PASS (mục 6). |
| Còn FAIL nào? | Có, giữ nguyên trong báo cáo: xem mục 7. |

## 2. Dữ liệu (dữ liệu thô bất biến, mỗi run có manifest)

| Experiment ID | Vai trò | Nội dung chính |
|---|---|---|
| `20261112_teastore_normal-baseline_run02` | Train/validation | 4 giờ, 1440/1440 chu kỳ × 6 entity, 0 chu kỳ bị bỏ, 188 476 request (0 lỗi), 1424 probe |
| `20261112_teastore_normal-erratic_run01` | **Test bình thường (held-out)** | 45 phút, 270 chu kỳ, tải đổi chế độ mỗi 25 s; đỉnh persistence 160 QPS (run02 tối đa 123) |
| `20261112_teastore_fault-campaign_run01` | Không hợp lệ | Dừng ở preflight (selector Tempo sai), chưa tiêm lỗi nào |
| `20261112_teastore_fault-campaign_run02` | Đợt A (tinh chỉnh) | WAN × 3, cpu, db_lock hợp lệ; memory_leak không hợp lệ (container bị OOM-kill) |
| `20261112_teastore_fault-campaign_run03` | Đợt A (tinh chỉnh) | memory_leak, http_5xx, webui_outage sau khi sửa |
| `20261113_teastore_fault-campaign-b_run01` | **Đợt B: đánh giá cuối v2** | 8 kịch bản, không dùng để tinh chỉnh |
| `20261113_teastore_fault-campaign-c_run01` | Kiểm lại RCA WAN | sau bản sửa 1 (tìm trace round-trip) |
| `20261113_teastore_fault-campaign-d_run01` | Kiểm lại RCA WAN | sau bản sửa 2 (giữ bằng chứng theo link) |
| `20261113_teastore_fault-campaign-e_run01` | Kiểm lại RCA WAN | sau bản sửa 3 (cửa sổ đồng thời 15 s) |

Dữ liệu dẫn xuất: `experiments/processed/20261113_threshold-sweep_model-v1.json` (đầu vào, commit, hash model).

## 3. Thay đổi pipeline (theo thứ tự commit)

1. **Đồng nhất feature lúc thu và lúc chạy (serving parity):** collector dùng chính `PrometheusVectorClient` của detector
   (P95 từ histogram delta, chu kỳ query lỗi bị bỏ qua và ghi lại thay vì ghi số 0).
2. **Preprocessing không rò rỉ (leakage):** tập validation lấy xen kẽ (mỗi block 60 dòng thứ 5) có vùng đệm
   (embargo) 12 dòng hai phía; không ghép cửa sổ qua khoảng trống > 25 s; forward fill theo từng split
   (test phát hiện và đã sửa một rò rỉ val → train).
3. **SLO guard học từ dữ liệu:** ngưỡng probe/latency theo entity = max(hằng số cũ, p99.5 × 1.3) trên phần train.
   WebUI bình thường ≈ 450 ms nên ngưỡng cũ 480–550 ms quá sát.
4. **Công cụ đánh giá:** `replay_eval.py` (replay dữ liệu thật qua một phiên bản model), `threshold_sweep.py`,
   `run_data_collection.sh`, `run_fault_campaign.sh`; thí nghiệm luôn chạy `--disable-telegram`.
5. **Sửa lỗi lab phát hiện trong quá trình chạy:** gateway crash khi khởi động lạnh; selector Tempo của runner WAN;
   limit bộ nhớ persistence; memory leak tăng dần và kéo dài ≥ 180 s (chi tiết mục 7).
6. **RCA WAN theo cloud:** `TraceEvidence.localize()` + tìm trace round-trip + giữ bằng chứng theo link (mục 6).

## 4. Model v1 và v2

* **v1** (train trên run02): GRU best val loss 0.01218 (epoch 48), TCN 0.00002 (epoch 7), Isolation Forest 100%
  validation normal, 864 s trên CPU. Ngưỡng thống kê **2.4671** = max(p99 × 1.35, **max × 1.15**, mean + 4σ) với
  val p99 = 0.505, max = 2.145: ngưỡng bị quyết định bởi **một** cửa sổ validation xấu nhất.
* **v2** = trọng số v1, ngưỡng quyết định **1.6**, chọn bằng replay sweep trên dữ liệu tinh chỉnh
  (run02 + đợt A; run erratic và đợt B không tham gia):

| Ngưỡng | FP run02 | gcp/azure/aws WAN phát hiện sau (s) | cpu recall | db_lock (s) | memory_leak (s) |
|---|---|---|---|---|---|
| 2.4671 (v1) | 0 | 27 / 36 / 35 | 0.17 | 35 | 68 |
| 2.0 | 0 | 27 / 26 / 35 | 0.33 | 25 | 68 |
| **1.6 (v2)** | 0 | **17 / 26 / 25** | **0.33** | **25** | **58** |
| 1.4 | 0 | 17 / 26 / 25 | 0.33 | 25 | 58 |
| 1.2 | 0.35% (1.25 đợt/giờ) | 17 / 26 / 25 | 0.50 | 25 | 58 |

  Chọn 1.6 = cách điểm gãy FP (1.2) một bậc an toàn. Cảnh báo thêm ở pha bình thường trong đợt A đều là
  "đuôi cửa sổ" ≤ 55 s sau khi lỗi kết thúc (cửa sổ 120 s vẫn chứa dữ liệu lỗi). Hiệu chỉnh likelihood của v2
  **đạt kiểm định** (Brier 0.00026, ECE 0.0107, fault min 91.6%, healthy max 27.8%); v1 không đạt (fault min 47.9%).
* Trọng số `.pt` bị gitignore; `ai-engine/models/saved/model_v{1,2}_sha256.txt` ghi hash chính xác.

## 5. Kết quả phát hiện

### 5.1. Dữ liệu bình thường (chỉ mô hình, replay)

| Run | v1 | v2 |
|---|---|---|
| run02 (phần lớn là dữ liệu train; block validation là out-of-sample) | 0/1440 | 0/1440 |
| **erratic_run01 (held-out)** | **0/270** | **0/270** |

Biên an toàn của v2 mỏng hơn: p99 của MSE lớn nhất mỗi chu kỳ trên erratic là 1.71 (> 1.6), tức có đỉnh đơn lẻ
vượt ngưỡng nhưng không kéo dài đủ 2 lần liên tiếp để thành cảnh báo.

### 5.2. Đợt B: đánh giá cuối v2 trên lỗi thật (detector online, runner chấm)

| Kịch bản | Mẫu có model alert / mẫu | Cảnh báo đầu tiên | Khoanh vùng | Runner |
|---|---|---|---|---|
| GCP WAN +250 ms | 9/9 | 27.4 s | không đặt tên được cloud | FAIL (RCA) |
| Azure WAN +180 ms | 9/9 | 16.1 s | không đặt tên được cloud | FAIL (RCA) |
| AWS WAN +200 ms | 9/9 | 14.9 s | `localized_cloud=aws` 10/11 chu kỳ ALERT (chu kỳ đầu chưa có trace) | PASS |
| CPU recommender (GCP) | 2/6 | - | `gcp:teastore-recommender` CPU | PASS |
| DB lock (Azure MariaDB) | 6/6 | - | `DATABASE_BOTTLENECK` persistence | PASS |
| Memory leak persistence (180 s) | 12/15 | - | `MEMORY_LEAK_GC_STALL` | PASS |
| HTTP 5xx WebUI | 6/6 | - | `error_rate_5xx` WebUI | PASS |
| WebUI outage | 0/6 model, 5/6 guard | - | probe HTTP lỗi | PASS |
| Baseline + 7 pha phục hồi | 1 cảnh báo (recovery sau CPU) | | | 7/8 PASS |

So với đợt A (v1): cpu 1/6 → 2/6; các lỗi còn lại cùng mức phát hiện; AWS RCA từ FAIL → PASS.

## 6. Khoanh vùng lỗi WAN theo cloud

Lỗi egress trên cloud X làm trễ mọi link chạm vào X. `localize()` lấy giao các đầu mút của mọi link bị trễ
(≥ 65 ms) và loại các cloud nằm trên một **round-trip khỏe đồng thời** (span CLIENT trừ span SERVER con, ví dụ
heartbeat `recommender → registry`). Link tính từ khe hở giữa các span (Method B) không thấy trễ một chiều,
nên chỉ được dùng để buộc tội, không để minh oan; khi bằng chứng mơ hồ thì trả về rỗng thay vì đoán.

| Đợt | Mã detector | GCP | Azure | AWS | Sai cloud |
|---|---|---|---|---|---|
| B | localize (9c6e468) | 0/10 | 0/11 | 10/11 | 0 |
| C | + tìm trace round-trip (56be347) | 0/10 | 2/11 | 11/11 | 0 |
| D | + giữ bằng chứng theo link (5248324) | 0/10 | 5/11 | 10/11 | 0 |
| **E** | + cửa sổ đồng thời 15 s (37dbf52) | **9/11** | **10/11** | **10/11** | **0** |

(Số chu kỳ ALERT trong toàn pha lỗi có `localized_cloud` đúng / tổng số chu kỳ ALERT; replay offline ở dưới tính sau thời gian settle 30 s.) Nguyên nhân từng bước:
* B: Tempo chỉ được hỏi các trace > 40 ms, lấy 12 trace mới nhất → heartbeat khỏe (~20 ms) không bao giờ về.
* C: khi lỗi ở GCP, probe ≈ 560 ms vẫn dưới ngưỡng phục hồi học được (603 ms) → registry "đã phục hồi" mỗi chu
  kỳ và `forget()` xóa cả bằng chứng `gcp→aws` (260 ms). Replay offline dữ liệu đợt C với bản sửa: GCP 5/9,
  Azure 6/9, AWS 9/9, 0 sai cloud (xấp xỉ: chỉ có link "tươi" ≤ 20 s được ghi lại mỗi chu kỳ).
* D: heartbeat của recommender thưa (lấy mẫu 20% ở edge) nên `gcp→aws` trễ chỉ xuất hiện 1 lần (+97 s), mới hơn
  heartbeat khỏe `azure→aws` vài giây; quy tắc "round-trip khỏe phải mới hơn" quá chặt. Trong topology này mọi
  link round-trip đều chạm aws (registry) nên quan sát khỏe sớm hơn chỉ có thể làm kết quả rỗng, không thể chỉ
  sai cloud; nới thành cửa sổ 15 s.
* E: cả 3 lỗi WAN PASS; các chu kỳ chưa có tên cloud là 1–2 chu kỳ đầu khi trace round-trip chưa về.
  Lưu ý: bản sửa RCA được kiểm trên các đợt mới (C, D, E) nhưng mỗi bản sửa được thiết kế sau khi xem đợt trước,
  nên E là lần kiểm độc lập duy nhất của mã RCA cuối cùng (một lần chạy, 3 lỗi).

## 7. Vấn đề phát hiện, cách xử lý và giới hạn còn lại

| Vấn đề | Bằng chứng | Xử lý |
|---|---|---|
| Runner WAN luôn dừng ở preflight | selector `app.kubernetes.io/name=tempo` không khớp `app=tempo` (cũng có trong báo cáo 2026-10-30) | sửa selector (7946ccc) |
| Memory leak làm container chết | persistence `-Xmx256m` + ~250 MiB non-heap trong limit 512Mi → OOMKilled (exit 137) ngay khi leak bắt đầu; thử với 768Mi: working set đỉnh 510 MiB | limit 768Mi, leak tăng dần có trần cgroup (3d982e4) |
| Memory leak 90 s không thể nhận diện | `ram_floor_2m_pct` = min trong 120 s: heap 87% nhưng floor vẫn 35% | leak chạy ≥ 180 s |
| Tiêu chí RCA AWS không thể đạt | runner đòi chuỗi `aws->aws` | chấm theo `localized_cloud` |
| **FAIL còn lại:** recovery sau CPU (đợt B) | 1 cảnh báo 37 s sau khi dừng lỗi; feature CPU vẫn 50.6% vì `rate(...[1m])` giảm dần trong 60 s, settle của runner 30 s | giữ nguyên; là đánh đổi của ngưỡng thấp hơn (v1 không cảnh báo ở MSE 1.68) |
| **FAIL còn lại:** recovery sau AWS WAN (đợt C) | 1 export: `client_latency_p95` persistence = 0.45 s (z≈12) 54–64 s sau lỗi, có thể là lời gọi registry bị trễ | giữ nguyên; cũng vượt ngưỡng v1. Hướng cải thiện: yêu cầu số request tối thiểu cho P95 client |
| CPU phát hiện chậm | feature `rate[1m]` tăng dần 60 s; lỗi bị pha loãng khi lấy trung bình 8 feature × 12 bước | chưa xử lý (đổi feature cần thu lại dữ liệu train) |
| Mã RCA cuối chưa chạy lại trên 5 lỗi service | đợt B dùng mã 0e30d18; các bản sửa sau chỉ chạm bằng chứng link WAN (`TraceEvidence.paths`, tìm trace round-trip) | chạy lại đợt đầy đủ ở lần đánh giá kế tiếp |
| Một máy duy nhất | mọi cụm chia CPU/RAM; WAN là netem | kết quả không đại diện cho cloud thật |

## 8. Tái lập

```bash
scripts/run_data_collection.sh 20261112_teastore_normal-baseline_run02 14400 4 50
scripts/run_data_collection.sh 20261112_teastore_normal-erratic_run01 2700 4 50 --erratic
python3.12 ai-engine/data/preprocess.py && OMP_NUM_THREADS=8 python3.12 ai-engine/training/train.py      # v1
python3.12 scripts/threshold_sweep.py experiments/processed/20261113_threshold-sweep_model-v1.json \
  --thresholds 2.4671 2.2 2.0 1.8 1.6 1.4 1.2 1.0 \
  --normal experiments/raw/20261112_teastore_normal-baseline_run02/metrics/entity_features.csv \
  --chaos experiments/raw/20261112_teastore_fault-campaign_run02/{wan,service} experiments/raw/20261112_teastore_fault-campaign_run03/service \
  --exclude experiments/raw/20261112_teastore_fault-campaign_run02/service:memory_leak
python3.12 ai-engine/training/recalibrate.py --threshold 1.6 --evidence <sweep.json> --reason "<lý do>"     # v2
python3.12 ai-engine/inference/replay_eval.py --normal experiments/raw/20261112_teastore_normal-erratic_run01/metrics/entity_features.csv
scripts/run_fault_campaign.sh 20261113_teastore_fault-campaign-b_run01 12
SERVICE_SCENARIOS="" scripts/run_fault_campaign.sh 20261113_teastore_fault-campaign-e_run01 12
```

Unit test: `OMP_NUM_THREADS=1 python3.12 -m unittest tests.chaos.test_ai tests.chaos.test_streaming
tests.chaos.test_missing_data tests.chaos.test_live_evaluation tests.chaos.test_detector_runtime
tests.chaos.test_preprocess tests.chaos.test_replay_eval tests.chaos.test_guards` → 81 test OK.
