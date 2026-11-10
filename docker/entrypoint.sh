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

# Execute the main command passed to the container
exec "$@"
