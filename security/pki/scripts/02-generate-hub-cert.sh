#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CA_DIR="${PKI_DIR}/ca"
HUB_DIR="${PKI_DIR}/certs-hub"

FORCE=0
for arg in "$@"; do
  if [[ "$arg" == "--force" ]]; then
    FORCE=1
  fi
done

umask 077
mkdir -p "${HUB_DIR}"

if [[ ! -f "${CA_DIR}/ca.key" || ! -f "${CA_DIR}/ca.crt" ]]; then
  echo "Error: Root CA not found in ${CA_DIR}. Run 01-generate-ca.sh first."
  exit 1
fi

CERT_FILE="${HUB_DIR}/server.crt"
KEY_FILE="${HUB_DIR}/server.key"
CA_CERT="${CA_DIR}/ca.crt"

# Check idempotency:
# (a) Both .key and .crt exist
# (b) Certificate signature verifies against current ca.crt
# (c) Certificate valid for at least 7 days (604800 seconds)
if [[ $FORCE -eq 0 && -f "$KEY_FILE" && -f "$CERT_FILE" ]]; then
  if openssl verify -CAfile "$CA_CERT" "$CERT_FILE" >/dev/null 2>&1 && \
     openssl x509 -checkend 604800 -noout -in "$CERT_FILE" >/dev/null 2>&1; then
    echo "Hub Server certificate is cryptographically valid and signed by current CA (>7 days remaining). Skipping generation (use --force to recreate)."
    cp "${CA_DIR}/ca.crt" "${HUB_DIR}/ca.crt"
    chmod 600 "$KEY_FILE"
    chmod 644 "$CERT_FILE" "${HUB_DIR}/ca.crt"
    exit 0
  else
    echo "Hub Server certificate is missing, invalid against current CA, or expiring within 7 days. Regenerating..."
  fi
fi

echo "Generating Hub Server private key..."
openssl genrsa -out "${HUB_DIR}/server.key" 2048

echo "Creating Hub Server SAN configuration..."
cat <<EOF > "${HUB_DIR}/server_ext.cnf"
[req]
req_extensions = v3_req
distinguished_name = req_distinguished_name
prompt = no

[req_distinguished_name]
C = VN
ST = HCM
O = MultiCloud-Monitoring
CN = otel-collector-hub

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = serverAuth, clientAuth
subjectAltName = @alt_names

[alt_names]
DNS.1 = otel-collector-hub
DNS.2 = otel-collector-hub.monitoring.svc.cluster.local
DNS.3 = k3d-hub-k3d-serverlb
DNS.4 = k3d-hub-k3d-server-0
DNS.5 = localhost
IP.1 = 127.0.0.1
IP.2 = 172.28.0.3
IP.3 = 172.28.0.2
EOF

echo "Generating CSR for Hub Server..."
openssl req -new -key "${HUB_DIR}/server.key" \
  -out "${HUB_DIR}/server.csr" \
  -config "${HUB_DIR}/server_ext.cnf"

echo "Signing Hub Server certificate with Root CA..."
openssl x509 -req -in "${HUB_DIR}/server.csr" \
  -CA "${CA_DIR}/ca.crt" -CAkey "${CA_DIR}/ca.key" -CAcreateserial \
  -out "${HUB_DIR}/server.crt" -days 365 -sha256 \
  -extfile "${HUB_DIR}/server_ext.cnf" -extensions v3_req

cp "${CA_DIR}/ca.crt" "${HUB_DIR}/ca.crt"
chmod 600 "${HUB_DIR}/server.key"
chmod 644 "${HUB_DIR}/server.crt" "${HUB_DIR}/ca.crt"

echo "Hub Server certificate generated successfully at ${HUB_DIR}/server.crt"
