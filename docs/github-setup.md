# Thiết lập GitHub & Khởi tạo Môi trường (Làm một lần)

> Tài liệu này hướng dẫn các bước thiết lập cấu hình **chỉ cần thực hiện một lần** để chuẩn bị môi trường Git, GitHub Actions, bảo mật biến môi trường và chứng chỉ mật mã cho dự án **Multi-Cloud Observability & Closed-Loop AIOps Platform**.

---

## 0. Cấu hình Định danh Kho Mã Nguồn

Đặt biến môi trường trên terminal của bạn để chuẩn bị thiết lập:

```bash
# Thay thế bằng tài khoản GitHub và tên repo của bạn nếu fork
export GITHUB_USER="your-github-username"
export GITHUB_REPO="multicloud-monitoring"
```

Nếu bạn clone hoặc fork sang tên tổ chức mới, chạy lệnh rà soát để cập nhật tên image trên GitHub Container Registry (GHCR):

```bash
grep -rl "ghcr.io/your-user" .github/ deploy/ | xargs sed -i "s|ghcr.io/your-user|ghcr.io/${GITHUB_USER}|g"
```

---

## 1. Phân quyền GitHub Actions (Permissions & Workflow Security)

Quy tắc bảo mật chuỗi cung ứng ([ADR-0002](adr/ADR-0002-kyverno-policy-as-code.md)) yêu cầu workflow chỉ có quyền đọc (`read`) theo mặc định:

```bash
gh api -X PUT repos/${GITHUB_USER}/${GITHUB_REPO}/actions/permissions/workflow \
  -f default_workflow_permissions=read \
  -F can_approve_pull_request_reviews=true
```

* **`default_workflow_permissions=read`:** Ngăn chặn các script chạy trong CI có quyền ghi ngoài ý muốn. Mọi quyền ghi (như đẩy image lên GHCR hay ký chữ ký Cosign) đều phải được khai báo tường minh trong từng job (`permissions: packages: write`, `id-token: write`).
* **`can_approve_pull_request_reviews=true`:** Cho phép GitHub Actions tự động tạo và phê duyệt Pull Request khi bot tự động hóa nâng cấp image hoặc khi Robusta kích hoạt tự phục hồi ([ADR-0005](adr/ADR-0005-slo-management-smart-alerting.md)).

---

## 2. Thiết lập Biến Môi trường Tập trung (`.env`)

Hệ thống tuân thủ nguyên tắc **Zero Plaintext Secrets** ([ADR-0003](adr/ADR-0003-zero-trust-pki-mtls.md)): toàn bộ credentials được nạp từ tệp `.env` tại thư mục gốc.

Tạo tệp `.env` bằng cách copy từ mẫu:

```bash
cp .env.example .env
```

Cập nhật các giá trị mật khẩu mạnh và token cảnh báo của bạn vào `.env`:

```properties
# 1. Cấu hình MinIO S3 Object Storage
MINIO_ROOT_USER=admin
MINIO_ROOT_PASSWORD=YourStrongS3Password2026!

# 2. Cấu hình Grafana Admin
GF_SECURITY_ADMIN_USER=admin
GF_SECURITY_ADMIN_PASSWORD=YourStrongGrafanaPass2026!

# 3. Kênh Cảnh báo Khẩn cấp Telegram (Robusta & AI Engine)
TELEGRAM_BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ
TELEGRAM_CHAT_ID=-1001234567890

# 4. Mật khẩu cơ sở dữ liệu MySQL TeaStore
MYSQL_ROOT_PASSWORD=YourMySQLRootPassword2026!
MYSQL_PASSWORD=YourTeaStoreDBPassword2026!
```

> [!WARNING] Cảnh báo Bảo mật
> Tệp `.env` đã được cấu hình trong `.gitignore`. Tuyệt đối không xóa khỏi `.gitignore` hoặc commit file `.env` chứa mật khẩu thực lên kho mã nguồn công khai.

---

## 3. Khởi tạo Cặp Chứng chỉ x509 Native mTLS 1.3

Để bảo mật đường truyền viễn trắc OTLP `:4317` giữa 2 Spoke và Central Hub qua mạng WAN ([ADR-0003](adr/ADR-0003-zero-trust-pki-mtls.md)), tiến hành sinh bộ khóa mật mã:

```bash
# Thực thi lệnh tạo Certificate Authority (CA) và Server/Client Certs qua Python Platform CLI
python -m infra.cli certs
```

Kiểm tra các Certificate và Secret do `cert-manager` quản lý trong namespace `monitoring` trên Hub và Spokes:
- `hub-otlp-tls`: Chứng chỉ Server cho Hub OTel Gateway.
- `aws-spoke-otlp-tls`: Chứng chỉ Client cho Spoke 1 Collector (`aws-k3d`).
- `azure-spoke-otlp-tls`: Chứng chỉ Client cho Spoke 2 Collector (`azure-k3d`).

---

## 4. Cấu hình GitHub Secrets & Variables (Cho CI/CD)

Nếu bạn thiết lập quy trình tự động build và promote image qua GitHub Actions, hãy nạp các Secrets sau lên GitHub Repository:

```bash
# Nạp Secret Telegram phục vụ kiểm thử CI
gh secret set TELEGRAM_BOT_TOKEN -b "your-telegram-bot-token"
gh secret set TELEGRAM_CHAT_ID -b "your-telegram-chat-id"

# Nạp Personal Access Token (PAT) để đẩy image lên GHCR
gh secret set CR_PAT -b "your-github-personal-access-token"
```

---

## 5. Xác thực Kênh Telegram Bot (Healthcheck)

Sau khi tạo Bot qua `@BotFather` và lấy `Chat ID` qua `@userinfobot`, kiểm tra xem bot đã sẵn sàng gửi tin nhắn hay chưa bằng script kiểm tra nhanh:

```bash
python3 -c "
import os, urllib.request, json
token = 'YOUR_TELEGRAM_BOT_TOKEN'
chat_id = 'YOUR_TELEGRAM_CHAT_ID'
url = f'https://api.telegram.org/bot{token}/sendMessage'
data = json.dumps({'chat_id': chat_id, 'text': '🚀 [Multi-Cloud Observability] Setup verified successfully!', 'parse_mode': 'HTML'}).encode('utf-8')
req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'})
urllib.request.urlopen(req)
print('Telegram test message sent!')
"
```
