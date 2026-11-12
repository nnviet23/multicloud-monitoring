#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CA_DIR="${PKI_DIR}/ca"

FORCE=0
for arg in "$@"; do
  if [[ "$arg" == "--force" ]]; then
    FORCE=1
  fi
done

umask 077

if [[ ! -f "${CA_DIR}/ca.key" || ! -f "${CA_DIR}/ca.crt" ]]; then
  echo "Error: Root CA not found in ${CA_DIR}. Run 01-generate-ca.sh first."
  exit 1
fi

CA_CERT="${CA_DIR}/ca.crt"

generate_spoke_cert() {
  local SPOKE_NAME="$1"
  local TARGET_DIR="${PKI_DIR}/${SPOKE_NAME}"
  local CERT_FILE="${TARGET_DIR}/client.crt"
  local KEY_FILE="${TARGET_DIR}/client.key"
  
  mkdir -p "${TARGET_DIR}"

  # Check idempotency:
  # (a) Both .key and .crt exist
  # (b) Certificate signature verifies against current ca.crt
  # (c) Certificate valid for at least 7 days (604800 seconds)
  if [[ $FORCE -eq 0 && -f "$KEY_FILE" && -f "$CERT_FILE" ]]; then
    if openssl verify -CAfile "$CA_CERT" "$CERT_FILE" >/dev/null 2>&1 && \
       openssl x509 -checkend 604800 -noout -in "$CERT_FILE" >/dev/null 2>&1; then
      echo "${SPOKE_NAME} certificate is cryptographically valid and signed by current CA (>7 days remaining). Skipping generation (use --force to recreate)."
      cp "${CA_DIR}/ca.crt" "${TARGET_DIR}/ca.crt"
      chmod 600 "$KEY_FILE"
      chmod 644 "$CERT_FILE" "${TARGET_DIR}/ca.crt"
      return 0
    else
      echo "${SPOKE_NAME} certificate is missing, invalid against current CA, or expiring within 7 days. Regenerating..."
    fi
  fi

  echo "Generating private key for ${SPOKE_NAME}..."
  openssl genrsa -out "${TARGET_DIR}/client.key" 2048

  cat <<EOF > "${TARGET_DIR}/client_ext.cnf"
[req]
distinguished_name = req_distinguished_name
prompt = no

[req_distinguished_name]
C = VN
ST = HCM
O = MultiCloud-Monitoring
CN = ${SPOKE_NAME}-client

[v3_req]
basicConstraints = CA:FALSE
keyUsage = nonRepudiation, digitalSignature, keyEncipherment
extendedKeyUsage = clientAuth, serverAuth
EOF

  echo "Generating CSR for ${SPOKE_NAME}..."
  openssl req -new -key "${TARGET_DIR}/client.key" \
    -out "${TARGET_DIR}/client.csr" \
    -config "${TARGET_DIR}/client_ext.cnf"

  echo "Signing certificate for ${SPOKE_NAME}..."
  openssl x509 -req -in "${TARGET_DIR}/client.csr" \
    -CA "${CA_DIR}/ca.crt" -CAkey "${CA_DIR}/ca.key" -CAcreateserial \
    -out "${TARGET_DIR}/client.crt" -days 365 -sha256 \
    -extfile "${TARGET_DIR}/client_ext.cnf" -extensions v3_req

  cp "${CA_DIR}/ca.crt" "${TARGET_DIR}/ca.crt"
  chmod 600 "${TARGET_DIR}/client.key"
  chmod 644 "${TARGET_DIR}/client.crt" "${TARGET_DIR}/ca.crt"
  echo "${SPOKE_NAME} certificate generated successfully at ${TARGET_DIR}/client.crt"
}

generate_spoke_cert "certs-spoke1"
generate_spoke_cert "certs-spoke2"
