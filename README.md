# OpenInvite

[![Python 3.12](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-2496ED.svg?logo=docker&logoColor=white)](https://www.docker.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Tests](https://img.shields.io/badge/tests-45%20passed-brightgreen.svg)]()

**OpenInvite** is a modern, lightweight, self-hosted event invitation and RSVP platform. It gives event organizers an independent, privacy-first alternative to ad-laden corporate event websites.

Run it in seconds as a zero-dependency standalone Docker container using local storage and SQLite, or scale it up across your own cloud infrastructure (Amazon S3, PostgreSQL / Amazon RDS, and Amazon SES / SendGrid).

---

## Features

- **Host Event Dashboard**: Create and organize celebrations, showers, birthdays, weddings, banquets, and social gatherings.
- **Automated Vector PDF Invitations**: Built-in ReportLab rendering engine compiles elegant, print-ready PDF invitations on the fly, with support for custom host-uploaded PDF documents.
- **Frictionless RSVP Portal**: Mobile-responsive guest portal accessed via secure, single-click magic tokens (no guest account required).
- **Plus-One & Dietary Tracking**: Host-configurable plus-one allowances with individual attendee names and dietary requirement collection.
- **Transactional Email Gateway**: Pluggable email dispatch supporting local SMTP (Mailpit), standard SMTP, Amazon SES, SendGrid, or console logging with full delivery audit trails.
- **Dual Architecture (Standalone or Cloud)**:
  - **Standalone Mode**: Runs self-contained with SQLite and local file storage. Zero external infrastructure needed.
  - **Cloud Mode**: Connects seamlessly to Amazon S3 for object storage, Amazon RDS / PostgreSQL for relational data, and Amazon SES for transactional notifications.
- **Security-First Container**: Multi-stage minimal runtime based on `python:3.12-slim` executing under a non-root user (`appuser` UID 10001) with automated health probes.

---

## 30-Second Quickstart (Standalone Docker)

Run OpenInvite immediately with persistent local storage:

```bash
docker run -d \
  --name openinvite \
  -p 5000:5000 \
  -v openinvite_data:/app/instance \
  -v openinvite_uploads:/app/uploads \
  -e SECRET_KEY="replace-with-a-secure-random-string" \
  -e AUTO_SEED="true" \
  open-invite:latest
```

Open your browser to [http://localhost:5000](http://localhost:5000).

> When `AUTO_SEED="true"` is set, the application pre-seeds a demo host account (`host@example.com` / `OpenInvite2026!`) and a sample celebration event to explore immediately.

---

## Docker Compose Quickstart

For local development or home-server deployment with a dedicated PostgreSQL database and a local webmail inspector:

```bash
# Clone the repository
git clone https://github.com/your-username/open-invite.git
cd open-invite

# Start the full stack (App + PostgreSQL + Mailpit)
docker compose up -d
```

- **OpenInvite Web App**: [http://localhost:5000](http://localhost:5000)
- **Mailpit Webmail Inspector**: [http://localhost:8025](http://localhost:8025) (preview all outgoing invitations locally)

To shut down:
```bash
docker compose down
```

---

## Configuration Reference

OpenInvite is configured entirely via environment variables:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `SECRET_KEY` | `dev-secret-...` | Flask session encryption key. **Set a secure secret in production.** |
| `FLASK_ENV` | `production` | Set to `production` or `development`. |
| `DATABASE_URL` | *(empty / SQLite)* | PostgreSQL connection URI (`postgresql://user:pass@host:5432/dbname`). If left empty, SQLite is used automatically in `/app/instance/open_invite.db`. |
| `STORAGE_BACKEND` | `local` | Document storage engine: `local` (filesystem) or `s3` (Amazon S3). |
| `LOCAL_STORAGE_PATH` | `/app/uploads` | Filesystem path for uploaded and generated PDFs when in `local` mode. |
| `S3_BUCKET_NAME` | `open-invite-storage` | Target Amazon S3 bucket name (when `STORAGE_BACKEND=s3`). |
| `AWS_REGION` | `us-east-1` | AWS region for S3 and SES operations. |
| `AWS_ACCESS_KEY_ID` | *(empty)* | AWS Access Key (leave empty if using IAM Instance/Task Roles). |
| `AWS_SECRET_ACCESS_KEY` | *(empty)* | AWS Secret Access Key. |
| `EMAIL_PROVIDER` | `console` | Email provider: `console` (prints to stdout), `smtp`, `ses`, or `sendgrid`. |
| `SMTP_HOST` | `localhost` | Outgoing SMTP server hostname. |
| `SMTP_PORT` | `1025` | Outgoing SMTP server port. |
| `MAIL_DEFAULT_SENDER` | `invitations@example.com` | From-address displayed on outgoing invitation emails. |
| `SENDGRID_API_KEY` | *(empty)* | SendGrid API Key (required if `EMAIL_PROVIDER=sendgrid`). |
| `SES_SENDER_EMAIL` | *(empty)* | Verified Amazon SES sender address (required if `EMAIL_PROVIDER=ses`). |
| `AUTO_SEED` | `false` | Automatically seed demo host, event, and guests on startup if `true`. |
| `ADMIN_PASSWORD` | `OpenInvite2026!` | Initial password for demo host account when `AUTO_SEED=true`. |

---

## Bring-Your-Own-AWS Deployment

OpenInvite is cloud-native and connects directly to managed AWS services:

1. **Amazon RDS (PostgreSQL)**:
   ```env
   DATABASE_URL=postgresql://dbuser:securepass@your-rds-endpoint.amazonaws.com:5432/event_db
   ```
2. **Amazon S3**:
   Create a private S3 bucket with Block Public Access enabled and configure:
   ```env
   STORAGE_BACKEND=s3
   S3_BUCKET_NAME=your-private-bucket-name
   AWS_REGION=us-east-1
   ```
   Invitations are fetched through time-limited presigned URLs (60-minute expiry).
3. **Amazon SES**:
   Verify your sending identity in SES and set:
   ```env
   EMAIL_PROVIDER=ses
   SES_SENDER_EMAIL=invitations@yourdomain.com
   ```
4. **Infrastructure as Code**:
   Ready-to-use CloudFormation (`infra/cloudformation/template.yaml`) and Terraform (`infra/terraform/`) modules are provided in the [`infra/`](infra/) directory.

---

## Local Development & Testing

```bash
# 1. Create and activate a Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# 3. Run the automated test suite
PYTHONPATH=. pytest -v
```

The test suite covers:
- Host authentication, session management, and access controls.
- Event creation and vector PDF generation with XML sanitization.
- Guest CSV import and personalized RSVP token hashing.
- Plus-one validation and attendee dietary requirements.
- Multi-channel transactional email dispatch and audit logging.
- Storage service operations (local disk and S3).

---

## Contributing

Contributions, issue reports, and feature suggestions are welcome! Please feel free to open an issue or submit a pull request.

---

## License

OpenInvite is open-source software licensed under the [MIT License](LICENSE).
