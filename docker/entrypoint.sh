#!/bin/bash
set -e

echo "=== OpenInvite Container Startup ==="
echo "Runtime: Python $(python --version)"
echo "Environment: ${FLASK_ENV:-development}"

# If DATABASE_URL starts with postgresql, wait for PostgreSQL readiness
if [[ "${DATABASE_URL}" == postgresql* ]]; then
  echo "Checking database connectivity..."
  python -c "
import time, os, sys
import psycopg2
from urllib.parse import urlparse

url = os.environ.get('DATABASE_URL', '')
if not url:
    sys.exit(0)

# Replace prefix if needed
if url.startswith('postgresql://'):
    parsed = urlparse(url)
    max_retries = 30
    for i in range(max_retries):
        try:
            conn = psycopg2.connect(
                dbname=parsed.path.lstrip('/'),
                user=parsed.username,
                password=parsed.password,
                host=parsed.hostname,
                port=parsed.port or 5432,
                connect_timeout=3
            )
            conn.close()
            print('Database is ready!')
            sys.exit(0)
        except Exception as e:
            if i % 5 == 0:
                print(f'Waiting for database connection ({i}/{max_retries})... {e}')
            time.sleep(1)
    print('Error: Database connection timed out.')
    sys.exit(1)
"
fi

# Initialize database schema automatically on startup (works for both SQLite and PostgreSQL)
echo "Ensuring database tables exist..."
python -m flask --app src/wsgi:app init-db || echo "Warning: init-db returned non-zero (tables may already exist)."

if [[ "${AUTO_SEED}" == "true" || "${AUTO_SEED}" == "1" ]]; then
  echo "AUTO_SEED=true: Seeding sample event, host, and guest data..."
  python -m flask --app src/wsgi:app seed-db || echo "Warning: seed-db returned non-zero (data may already exist)."
fi

# Optional direct TLS support for standalone container deployments without a reverse proxy
TLS_LOWER=$(echo "${TLS_ENABLED:-false}" | tr '[:upper:]' '[:lower:]')
CERT_FILE=""
KEY_FILE=""

if [[ -n "${SSL_CERTFILE:-}" && -n "${SSL_KEYFILE:-}" ]]; then
  CERT_FILE="${SSL_CERTFILE}"
  KEY_FILE="${SSL_KEYFILE}"
elif [[ "${TLS_LOWER}" == "true" || "${TLS_LOWER}" == "1" || "${TLS_LOWER}" == "yes" || "${TLS_LOWER}" == "on" ]]; then
  CERT_DIR="${TLS_CERT_DIR:-/tmp/openinvite-certs}"
  echo "TLS_ENABLED=true: Ensuring self-signed TLS certificate in ${CERT_DIR}..."
  python -c "from pathlib import Path; from src.app.tls import ensure_self_signed_cert; ensure_self_signed_cert(Path('${CERT_DIR}'), common_name='${TLS_DOMAIN:-localhost}')"
  CERT_FILE="${CERT_DIR}/server.crt"
  KEY_FILE="${CERT_DIR}/server.key"
fi

# Execute the main command passed to the container
if [[ -n "${CERT_FILE}" && -n "${KEY_FILE}" && "$1" == "gunicorn" ]]; then
  shift
  exec gunicorn --certfile="${CERT_FILE}" --keyfile="${KEY_FILE}" "$@"
fi

exec "$@"
