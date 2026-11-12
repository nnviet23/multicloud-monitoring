# Semantic Conventions: CAT-03 Network & Transport (L3/L4 & WAN)

**Status**: Stable (Network Metrics) / Experimental (WAN & TLS Attributes)  
**Namespace**: `system.network.*`, `network.*`, `net.*`, `tls.*`  
**OTel SemConv Domain**: `docs/system/system-metrics.md`, `docs/network/`, `docs/general/tls.md`

---

## 1. Tổng Quan & Vai Trò Trong Đồ Án Multi-Cloud

Category `CAT-03` quy định từ điển ngữ nghĩa cho tầng mạng truyền dẫn (Network & Transport Layer L3/L4) và mạng diện rộng đa đám mây (Inter-Cloud WAN).

Trong đồ án nghiên cứu nền tảng giám sát đa đám mây, `CAT-03` là hạt nhân cốt lõi nhằm:
1. **Đo lường Thông lượng & Lỗi Mạng Vật lý/Ảo:** Giám sát lưu lượng byte nhận/gửi (`Rx/Tx`), gói tin (`packets`), số gói tin bị rụng (`dropped`), và số gói tin bị lỗi đường truyền (`errors`) trên các giao diện mạng (`eth0`, `mc-monitoring-net`).
2. **Theo dõi Trạng thái Kết nối TCP (Socket Saturation):** Đếm số lượng kết nối TCP theo trạng thái của hệ điều hành Linux (`ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`) để phát hiện rò rỉ socket hoặc cạn kiệt port ephemeral.
3. **Mô phỏng & Đánh giá Suy giảm Mạng WAN (WAN Impairment):** Thu thập các tham số độ trễ cơ sở (RTT 10ms), độ lệch thời gian (Jitter ±2ms), và tỷ lệ mất gói (Packet Loss 0.1%) được tiêm qua Linux kernel `tc netem`.
4. **Bảo mật Đường truyền Xuyên Biên giới Đám mây (mTLS 1.3 Transport):** Giám sát các tham số bảo mật của giao thức TLS (Cipher suite, ALPN, TLS version 1.3, trạng thái xác thực hai chiều mTLS giữa Edge Spoke và Central Hub).

---

## 2. Attribute Registry (Thuộc Tính Ngữ Cảnh & Nhãn)

| Attribute Key (OTel SemConv) | Prometheus / Loki / Tempo Key | Stability | Requirement Level | Value Type | Description | Project Example Values |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `system.network.interface` | `device` / `interface` | Stable | Required | string | Tên giao diện mạng (Network interface name). [1] | `eth0`, `lo`, `docker0` |
| `network.io.direction` | `direction` | Stable | Required | string | Chiều truyền thông mạng. [2] | `receive`, `transmit` |
| `system.network.state` | `state` | Stable | Conditionally Required [3] | string | Trạng thái của socket kết nối TCP (theo `/proc/net/tcp`). | `ESTABLISHED`, `TIME_WAIT`, `CLOSE_WAIT`, `LISTEN` |
| `network.peer.address` | `net.peer.ip` / `peer_ip` | Stable | Recommended | string | Địa chỉ IP của đối tác mạng ở đầu kết nối bên kia. | `172.18.0.2`, `172.18.0.3` |
| `network.peer.port` | `net.peer.port` / `peer_port` | Stable | Recommended | int | Cổng mạng TCP/UDP của đối tác mạng. | `4317`, `3306`, `1099` |
| `network.transport` | `network_transport` | Stable | Recommended | string | Giao thức tầng vận chuyển L4. | `tcp`, `udp` |
| `tls.protocol.version` | `tls_version` | Experimental | Required | string | Phiên bản giao thức bảo mật Transport Layer Security. [4] | `1.3`, `1.2` |
| `tls.cipher` | `tls_cipher` | Experimental | Recommended | string | Thuật toán mã hóa dòng bắt tay SSL/TLS. | `TLS_AES_128_GCM_SHA256` |
| `tls.client.hash.sha256` | `tls_client_cert_sha256` | Experimental | Recommended | string | Dấu vân tay SHA256 của chứng chỉ mTLS phía máy khách (Spoke Client). | `a3b8...` |

**Ghi chú quy chuẩn thu thập:**
- **[1]:** Bắt buộc trên các metric mạng để phân biệt card mạng vật lý/ảo kết nối ra mạng WAN (`eth0`) và giao diện nội bộ (`lo`).
- **[2]:** Bắt buộc để phân loại lưu lượng nhận vào (`receive` / `Rx`) và truyền đi (`transmit` / `Tx`).
- **[3]:** Bắt buộc trên metric `system.network.connections` để phát hiện nghẽn số lượng socket mở (TCP Connection Saturation).
- **[4]:** Bắt buộc đối với các kênh truyền gRPC OTLP giữa Spoke Collector và Hub Gateway qua mạng diện rộng.

---

## 3. Metric & Signal Definitions (Chỉ Số Đo Lường Chuẩn OTel & TSDB)

| Metric Name (OTel SemConv) | Prometheus TSDB Name | Instrument Type | Unit (UCUM) | Orientation | Description & USE/RED Role |
| :--- | :--- | :--- | :--- | :---: | :--- |
| `system.network.io` | `system_network_io_bytes_total` | Counter | `By` | +1 | Dung lượng byte mạng truyền nhận. Đo **Network Bandwidth (Bps)** (USE Utilization). |
| `system.network.packet.count` | `system_network_packets_total` | Counter | `{packet}` | +1 | Số lượng gói tin IP mạng đã truyền nhận. Đo **Packet Rate (pps)**. |
| `system.network.packet.dropped` | `system_network_dropped_total` | Counter | `{packet}` | +1 | Số lượng gói tin bị rụng do tràn hàng đợi bộ đệm kernel (Drop rate). Đo **Network Saturation**. |
| `system.network.errors` | `system_network_errors_total` | Counter | `{error}` | +1 | Số lượng gói tin bị lỗi truyền dẫn (CRC, Frame, FIFO overrun). Đo **Network Errors**. |
| `system.network.connections` | `system_network_connections` | Gauge | `{connection}` | 0 | Số lượng kết nối socket TCP đang mở theo từng trạng thái (`state`). Đo **Socket Saturation**. |
| `wan.rtt.configured` | `wan_rtt_configured_ms` | Gauge | `ms` | 0 | Độ trễ khứ hồi WAN định hình qua `tc netem` (Baseline: 10.0 ms). |
| `wan.jitter.configured` | `wan_jitter_configured_ms` | Gauge | `ms` | 0 | Độ biến thiên trễ WAN định hình (Baseline: 2.0 ms). |
| `wan.loss.configured` | `wan_packet_loss_configured_pct` | Gauge | `%` | 0 | Tỷ lệ rụng gói WAN giả lập (Baseline: 0.1%). |

---

## 4. Schema Evolution & Backward Compatibility (OTel `schemas/1.21.0 -> 1.45.0`)

1. **Chuyển đổi nhãn `system.network.io.direction` sang `network.io.direction` (`v1.24.0`):**
   - Tương tự như Disk I/O, OTel SemConv v1.24 rút gọn tên thuộc tính nội bộ. Prometheus TSDB duy trì nhãn `direction="receive"` và `direction="transmit"`.
2. **Tiến hóa từ `net.peer.ip` sang `network.peer.address` (`v1.23.0`):**
   - Thuộc tính mạng cổ điển trong OpenTelemetry ban đầu mang tiền tố `net.*` (`net.peer.ip`, `net.peer.name`, `net.peer.port`). Từ phiên bản 1.23.0, OTel tái cấu trúc toàn diện thành `network.*` (`network.peer.address`, `network.peer.port`, `network.transport`).
3. **Cơ chế Fallback Trong Đồ Án:**
   - Trong `ai-engine/inference/detector.py` và các bộ chuyển đổi OTTL tại Hub Gateway, hệ thống hỗ trợ cả hai cú pháp fallback để đảm bảo nhận diện chính xác luồng truyền xuyên cụm:
     `attributes["network.peer.address"] or attributes["net.peer.ip"]`

