#!/usr/bin/env bash
# ==============================================================================
# Script tự động sinh tải và thu thập dữ liệu huấn luyện bình thường (4 Giờ)
# ==============================================================================

set -e

DURATION=${1:-14400}  # Mặc định 14400 giây = 4 giờ (truyền tham số khác nếu muốn chạy ngắn hơn)
INTERVAL=${2:-10}     # Chu kỳ lấy mẫu: 10 giây/lần
MIN_USERS=10          # Tải thấp điểm khởi động
MAX_USERS=50          # Tải đỉnh điểm cao nhất
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_FILE="${PROJECT_ROOT}/ai-engine/data/raw/normal_baseline_4h.csv"

echo "======================================================================"
echo "  MULTI-CLOUD MONITORING - NORMAL DATASET GENERATOR"
echo "======================================================================"
echo "  Thời gian chạy: ${DURATION} giây (~$(awk "BEGIN {printf \"%.1f\", ${DURATION}/3600}") giờ)"
echo "  Chu kỳ mẫu:     ${INTERVAL} giây/mẫu"
echo "  File lưu trữ:   ${OUTPUT_FILE}"
echo "======================================================================"

# 1. Kiểm tra kết nối tới TeaStore WebUI
echo "[1/3] Kiểm tra trạng thái ứng dụng TeaStore..."
CONNECTED=false
for i in {1..5}; do
    if curl -s -m 8 -o /dev/null "http://localhost:8080/tools.descartes.teastore.webui/status"; then
        CONNECTED=true
        break
    fi
    echo "      Đang đợi TeaStore phản hồi (thử lần $i/5)..."
    sleep 2
done

if [ "$CONNECTED" = false ]; then
    echo "[LỖI] Không thể kết nối tới TeaStore tại http://localhost:8080/tools.descartes.teastore.webui/status!"
    echo "      Vui lòng kiểm tra lại dịch vụ:"
    echo "      curl -I http://localhost:8080/tools.descartes.teastore.webui/status"
    exit 1
fi
echo "      TeaStore đang hoạt động tốt!"

# 2. Khởi động bộ sinh tải người dùng (Background)
echo "[2/3] Bật tiến trình sinh tải người dùng (Traffic Generator)..."
python3 "${PROJECT_ROOT}/tests/locust/traffic_generator.py" \
    --url "http://localhost:8080/tools.descartes.teastore.webui" \
    --min-users "${MIN_USERS}" \
    --max-users "${MAX_USERS}" \
    --duration "${DURATION}" > /dev/null 2>&1 &
TRAFFIC_PID=$!
echo "      Đã khởi động Traffic Generator (PID: ${TRAFFIC_PID})"

# Dọn dẹp tiến trình nền khi kết thúc hoặc nhận Ctrl+C
cleanup() {
    echo ""
    echo "[!] Đang dừng hệ thống thu thập..."
    kill -TERM "${TRAFFIC_PID}" 2>/dev/null || true
    wait "${TRAFFIC_PID}" 2>/dev/null || true
    echo "[V] Hoàn tất dừng tiến trình sinh tải. Dữ liệu đã được lưu an toàn tại:"
    echo "    ${OUTPUT_FILE}"
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

# 3. Khởi động bộ cào metric từ Prometheus
echo "[3/3] Bắt đầu cào dữ liệu từ Prometheus..."
python3 "${PROJECT_ROOT}/ai-engine/data/collector.py" \
    --duration "${DURATION}" \
    --interval "${INTERVAL}" \
    --output "${OUTPUT_FILE}" \
    --label 0

echo "======================================================================"
echo "  ĐÃ THU THẬP XONG DỮ LIỆU HUẤN LUYỆN!"
echo "  File output: ${OUTPUT_FILE}"
echo "======================================================================"

