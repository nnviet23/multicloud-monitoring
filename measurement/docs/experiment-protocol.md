# Measurement Experiment Protocol

## 1. Mục đích

Chuẩn hóa cách chuẩn bị, chạy và xác nhận Accuracy/Performance để tránh nhầm lẫn giữa:
- cấu hình có tồn tại;
- endpoint thực sự hoạt động;
- metric thực sự được scrape/query;
- kết quả có đủ dữ liệu để diễn giải.

## 2. Pre-flight checklist

- [ ] Đang ở đúng repository và môi trường WSL dự kiến.
- [ ] Xác nhận kubeconfig và các context đang dùng.
- [ ] Xác nhận AWS spoke, Azure spoke và Hub sẵn sàng.
- [ ] Xác nhận OTLP receiver của spoke.
- [ ] Xác nhận Hub exporter `:8889` trả metrics.
- [ ] Xác nhận Prometheus scrape target Hub `UP`.
- [ ] Xác nhận API query được collector sử dụng trả dữ liệu thử.
- [ ] Xác nhận image tag khớp image đã build/import.
- [ ] Ghi lại config, thời gian, git revision và experiment ID.
- [ ] Đánh giá cardinality risk của `telemetry.hub.received_time`.

Nếu endpoint quan trọng chưa xác minh, không chạy gửi dữ liệu hoặc phải đánh dấu rõ run là không đủ điều kiện.

## 3. Accuracy protocol

1. Chọn scenario, source và seed.
2. Tạo experiment ID mới.
3. Tạo và lưu ground truth.
4. Xác nhận Job template và image.
5. Chạy generator tại spoke.
6. Lưu generator summary, gồm sent success/failure.
7. Kiểm tra Job logs/status.
8. Chờ dữ liệu xuất hiện qua Hub exporter và Prometheus.
9. Chạy collector trong timeout đã cấu hình.
10. Kiểm tra received samples và collection summary.
11. Tính Accuracy; ghi rõ đây là counter/final-value-based.
12. Lưu toàn bộ artifacts và các lỗi phát sinh.

Không dùng Job `Complete` làm tiêu chí duy nhất cho send success hoặc telemetry delivery.

## 4. Performance protocol

1. Xác minh từng metric endpoint trước khi đo.
2. Kiểm tra context, target, pod/deployment và node name.
3. Xác nhận OTel internal metrics endpoint nếu sampler phụ thuộc `:8888`.
4. Xác nhận cAdvisor endpoint nếu dùng container metrics.
5. Xác nhận workload generator endpoint/port-forward.
6. Chạy thử thời lượng ngắn và kiểm tra raw samples.
7. Chỉ chạy benchmark chính khi metric bắt buộc có sample hợp lệ.
8. Lưu missing counts và lỗi theo target/metric.
9. Summarize gauge/rate/counter theo đúng loại metric.
10. Đánh dấu run không hợp lệ nếu dữ liệu đầu vào thiếu.

## 5. Trạng thái run

- `SUCCESS`: dữ liệu bắt buộc được thu thập và đáp ứng tiêu chí đã định.
- `PARTIAL`: một phần dữ liệu thiếu nhưng vẫn có phần kết quả giới hạn diễn giải được.
- `FAILED`: run không hoàn thành hoặc không đáp ứng điều kiện thực nghiệm.
- `UNAVAILABLE`: thiếu endpoint/metric cần thiết để thực hiện phép đo.

Không thay missing data bằng 0. Không loại bỏ run thất bại khỏi báo cáo mà không ghi nhận nguyên nhân.

## 6. Post-run checklist

- [ ] Metadata khớp experiment ID/config.
- [ ] Ground truth tồn tại và đúng scenario/seed.
- [ ] Generator summary được lưu.
- [ ] Raw samples có dữ liệu và timestamp hợp lệ.
- [ ] Collection summary không có lỗi chưa giải thích.
- [ ] Missing counts được báo cáo.
- [ ] Accuracy/Performance summary có thể truy vết về raw data.
- [ ] Các giới hạn scrape, clock skew, cardinality và endpoint được nêu.
- [ ] Kết quả không hợp lệ không được dùng để kết luận định lượng.
