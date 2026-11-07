# Kết quả kiểm thử AI — 30/10/2026

Đã chạy trực tiếp trên lab 4 cụm k3d, 6 người dùng TeaStore, chu kỳ AI 6 giây.
Lần chạy cuối: **13:40–13:48 giờ Việt Nam**. Giữ nguyên trọng số GRU/TCN,
baseline và ngưỡng MSE **0.35**; không huấn luyện lại.

## Kết quả

| Nhóm | Kết quả |
| --- | --- |
| Test hành vi AI, trace decomposition và bộ đánh giá | **18/18 PASS** |
| Replay feature/trace tổng hợp qua mô hình thật | **11/11 PASS** |
| Live baseline | **PASS**, không có ALERT |
| Live WAN GCP: delay 250ms trong 90 giây | **PASS**, ALERT sau khoảng **22 giây**, RCA đúng AWS → GCP |
| Live WAN Azure: delay 180ms trong 90 giây | **PASS**, ALERT sau khoảng **8.5 giây**, RCA đúng AWS → Azure |
| Recovery sau GCP | **FAIL** tiêu chí hết ALERT sau 30 giây; trở lại HEALTHY sau **105.5 giây** |
| Recovery sau Azure | **FAIL** tiêu chí hết ALERT sau 30 giây; trở lại HEALTHY sau **92 giây** |

Live tổng cộng **3/5 pha PASS**, có **81 mẫu** và đủ 6 thực thể ở mọi mẫu.
Trong mỗi ca WAN, cả 10/10 mẫu sau thời gian settle có `model_alert=true`.
Kết quả phát hiện có đóng góp của mô hình, không chỉ từ SLO guard.
RCA đúng cloud xuất hiện ở **4/10 mẫu GCP** và **10/10 mẫu Azure** sau settle;
không mẫu nào gán WAN sang cloud còn lại. Nhãn WAN có thể không xuất hiện ở
từng chu kỳ khi trace mẫu không đủ thông tin. Baseline có 5 mẫu sau settle.

Hai ca recovery FAIL được giữ nguyên. Sau khi WAN phục hồi, HTTP probe nhanh
trở lại trước AI. Metrics dùng cửa sổ rate 1 phút, telemetry có độ trễ export,
và mô hình giữ cửa sổ 12 mẫu, nên điểm lỗi tiếp tục phản ánh dữ liệu trước đó.
Đây là hạn chế về thời gian xóa cảnh báo đã quan sát; chưa tối ưu cửa sổ hoặc
đổi tiêu chí test để làm hai ca này PASS.

## Các lỗi đã sửa trong quá trình test

- **Báo động khi dịch vụ nhanh hơn baseline:** trước sửa, độ trễ WebUI khoảng
  70–130ms vẫn có ALERT so với baseline cũ 420ms. Khi HTTP khỏe, giảm latency
  hoặc tài nguyên không còn bị tính thành lỗi saturation. Có test hồi quy và
  kịch bản `faster_than_baseline`; các kịch bản lỗi vẫn được phát hiện.
- **Gán lỗi WAN thiếu bằng chứng:** loại suy đoán chỉ dựa trên WebUI chậm và
  downstream có MSE cao. Nhãn WAN cần bằng chứng trace; có test hồi quy cho
  dịch vụ CPU chậm không được tự động gán thành lỗi mạng.
- **Khó phân biệt mô hình và guard:** JSON detector bổ sung `model_alert`,
  `guard_reasons`, `traces_inspected`.
- **Benchmark in FAIL nhưng không làm lệnh thất bại:** benchmark hiện trả exit
  code 1 khi có ca sai. Đã kiểm chứng bằng một fixture cố tình đặt kỳ vọng sai.

## Điều kiện lab và khôi phục

Lần đầu phát hiện Tempo đang `CrashLoopBackOff` vì thiếu bucket `tempo-traces`.
Đã tạo lại các bucket theo cấu hình lab và khởi động lại Tempo. Runner hiện
kiểm tra pod Tempo Ready trước khi tiêm lỗi; hai lần bị chặn ở preflight không
được tính thành kết quả kiểm thử live thành công.

Sau lần chạy cuối:

- Qdisc `eth0` của GCP và Azure đều trở lại **noqueue**, khớp trạng thái trước test.
- Không còn helper `ai-chaos-*`; không có lỗi cleanup.
- Đã dừng các tiến trình tải và detector do runner tạo.
- Tempo **1/1 Ready**, cả hai pha recovery kết thúc ở HEALTHY.

Các ca CPU, memory leak, DB chậm, 5xx và scale-out trong lần này là replay
tổng hợp; chưa tiêm các lỗi đó vào workload thật. Bộ benchmark đánh giá
ensemble GRU + TCN đang tạo điểm số trong detector, không chứng minh hiệu năng
của Isolation Forest riêng biệt. Bucket đã được phục hồi trong lab; cấu hình
lưu trữ bền vững của MinIO không được thay đổi trong công việc này.

## Bằng chứng và chạy lại

- [Kịch bản và lệnh chạy](README.md)
- [Kết quả synthetic JSON](../benchmarks/results/synthetic.json)
- [Kết quả live JSON](../benchmarks/results/live-final-20261030/report.json)
- [81 mẫu detector](../benchmarks/results/live-final-20261030/detector.json)
- [Timeline và qdisc trước/sau](../benchmarks/results/live-final-20261030/events.json)

Các JSON/log nằm trong `tests/benchmarks/results/`, được gitignore. Tài liệu
này lưu tóm tắt; dùng lệnh trong README và thư mục output mới để tái chạy.
