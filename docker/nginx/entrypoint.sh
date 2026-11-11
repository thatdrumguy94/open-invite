#!/bin/sh
set -eu

CERT_DIR="/etc/nginx/certs"
CERT_FILE="${CERT_DIR}/server.crt"
KEY_FILE="${CERT_DIR}/server.key"
DOMAIN="${TLS_DOMAIN:-localhost}"

mkdir -p "${CERT_DIR}"

if [ ! -f "${CERT_FILE}" ] || [ ! -f "${KEY_FILE}" ]; then
    echo "=== Generating self-signed TLS certificate for '${DOMAIN}' ==="
    SAN_LIST="DNS:localhost,DNS:*.localhost,IP:127.0.0.1"
    if [ "${DOMAIN}" != "localhost" ] && [ -n "${DOMAIN}" ]; then
        SAN_LIST="${SAN_LIST},DNS:${DOMAIN}"
    fi
    if [ -n "${TLS_IP:-}" ]; then
        SAN_LIST="${SAN_LIST},IP:${TLS_IP}"
    fi

    openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "${KEY_FILE}" \
        -out "${CERT_FILE}" \
        -days 365 \
        -subj "/C=US/ST=Texas/L=San Antonio/O=OpenInvite/CN=${DOMAIN}" \
        -addext "subjectAltName=${SAN_LIST}"

    chmod 600 "${KEY_FILE}"
    chmod 644 "${CERT_FILE}"
    echo "TLS certificate generated at ${CERT_FILE}"
else
    echo "Using existing TLS certificate at ${CERT_FILE}"
fi
