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
mkdir -p "${CA_DIR}"

if [[ $FORCE -eq 0 && -f "${CA_DIR}/ca.key" && -f "${CA_DIR}/ca.crt" ]]; then
  if openssl x509 -checkend 604800 -noout -in "${CA_DIR}/ca.crt" >/dev/null 2>&1; then
    echo "Root CA already exists in ${CA_DIR} and is valid for >7 days. Skipping generation (use --force to recreate)."
    chmod 600 "${CA_DIR}/ca.key"
    chmod 644 "${CA_DIR}/ca.crt"
    exit 0
  else
    echo "Root CA in ${CA_DIR} has expired or will expire within 7 days. Regenerating..."
  fi
fi

echo "Generating Root CA private key..."
openssl genrsa -out "${CA_DIR}/ca.key" 4096

echo "Generating Root CA self-signed certificate..."
openssl req -x509 -new -nodes -key "${CA_DIR}/ca.key" \
  -sha256 -days 365 -out "${CA_DIR}/ca.crt" \
  -subj "/C=VN/ST=HCM/O=MultiCloud-Monitoring/CN=RootCA"

chmod 600 "${CA_DIR}/ca.key"
chmod 644 "${CA_DIR}/ca.crt"

echo "Root CA successfully created at ${CA_DIR}/ca.crt"
