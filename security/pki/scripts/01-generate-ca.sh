#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PKI_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
CA_DIR="${PKI_DIR}/ca"

mkdir -p "${CA_DIR}"

if [[ -f "${CA_DIR}/ca.key" && -f "${CA_DIR}/ca.crt" ]]; then
  echo "Root CA already exists in ${CA_DIR}."
  exit 0
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

