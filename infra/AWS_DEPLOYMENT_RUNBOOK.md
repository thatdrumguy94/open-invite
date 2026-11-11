# OpenInvite AWS Cloud Deployment & Operations Runbook
**Platform:** OpenInvite Self-Hosted Event Invitation & RSVP Platform  
**Target:** Amazon Web Services (AWS) Deployment  
**Architecture:** Multi-Tier Cloud Native (S3, RDS PostgreSQL, ECS Fargate / App Runner, SES)  

---

## 1. Cloud Architecture Overview

OpenInvite can be packaged and deployed as a containerized, cloud-native web service hosted on Amazon Web Services (AWS). It utilizes managed AWS primitives to provide high availability, elasticity, and least-privilege security.

```
                      +---------------------------------------+
                      |       Invited Guests & Hosts          |
                      +---------------------------------------+
                                          |
                                    (HTTPS:443)
                                          v
                      +---------------------------------------+
                      |         AWS App Runner Service        |
                      |   (Managed Ingress + Auto-Scaling)    |
                      |  +---------------------------------+  |
                      |  |     Docker Container (Flask)    |  |
                      |  |   - Python 3.12 / Gunicorn       |  |
                      |  |   - ReportLab Vector PDF Engine |  |
                      |  |   - SQLAlchemy 2.0 ORM          |  |
                      |  +---------------------------------+  |
                      +---------------------------------------+
                            |            |            |
         +------------------+            |            +------------------+
         | (Presigned URLs)              | (Port 5432)|                  | (Boto3 API)
         v                               v            v                  v
+------------------+           +------------------+          +------------------+
|    Amazon S3     |           |    Amazon RDS    |          |    Amazon SES    |
| (Private Bucket) |           |  (PostgreSQL 15) |          | (Transactional)  |
|  Invitation PDFs |           |  Private Subnet  |          |  Event Invites   |
+------------------+           +------------------+          +------------------+
```

### AWS Services Utilized
1. **AWS App Runner / Amazon ECS Fargate + ALB / CloudFront**: Managed HTTPS ingress (`TLSv1.2+` / `TLSv1.3`) running the production Docker container (`python:3.12-slim` + Gunicorn). App Runner provides built-in TLS termination; ECS Fargate sits behind an Application Load Balancer with ACM TLS (`443`) + HTTP (`80`) redirect or a CloudFront HTTPS edge distribution (`https://*.cloudfront.net`). Flask trusts `X-Forwarded-Proto` / `CloudFront-Forwarded-Proto` via `ProxyFix`, enforces HTTPS (`FORCE_HTTPS=true`, exempting internal `/health` probes), and issues `Secure` cookies and HSTS headers.
2. **Amazon RDS (PostgreSQL 15)**: Multi-AZ capable relational database in private VPC subnets. Stores Users, Events, Guests, Additional Attendees, and Communications logs.
3. **Amazon S3**: Private object storage bucket (`AES256` server-side encryption, Block Public Access enabled) storing invitation PDFs accessed securely via time-limited presigned URLs.
4. **Amazon SES (Simple Email Service)**: High-deliverability transactional email service dispatching personalized invitations and RSVP reminders.
5. **Amazon ECR (Elastic Container Registry)**: Private Docker registry with automated vulnerability scanning on image push.
6. **AWS IAM**: Role-based access control enforcing least-privilege permissions between App Runner, S3, and SES.

---

## 2. Prerequisites & Authentication

### Required Local Tools
- Python 3.12 or higher with virtual environment (`.venv`)
- Docker Desktop or Docker Engine
- AWS CLI v2 (optional, if using direct AWS CLI commands)
- Git

### Configuring AWS Credentials
Ensure your active shell or `.env` file contains valid AWS credentials with administrative or provisioning permissions:

```bash
# Method A: Standard AWS CLI
aws configure
# AWS Access Key ID: <YOUR_ACCESS_KEY>
# AWS Secret Access Key: <YOUR_SECRET_KEY>
# Default region name: us-east-1
# Default output format: json

# Method B: Environment Variables
export AWS_ACCESS_KEY_ID="<YOUR_ACCESS_KEY>"
export AWS_SECRET_ACCESS_KEY="<YOUR_SECRET_KEY>"
export AWS_REGION="us-east-1"
```

Verify your authentication using the built-in management utility:
```bash
python infra/aws_manager.py check-auth
```
Expected output:
```text
============================================================
AWS Authentication & Identity Check
============================================================
Status:      [AUTHENTICATED]
Account ID:  123456789012
User / Role: arn:aws:iam::123456789012:user/developer
Region:      us-east-1
```

---

## 3. Deployment Methods

We provide three fully automated deployment pathways:
- **Option A: Python Management Tool (`infra/aws_manager.py`)** *(Fastest & Recommended)*
- **Option B: AWS CloudFormation (`infra/cloudformation/template.yaml`)**
- **Option C: Terraform Modular Infrastructure (`infra/terraform/`)**
- **Option D: AWS Management Console (Manual Walkthrough)**

---

### Option A: Python CLI Tool (`infra/aws_manager.py`) [RECOMMENDED]

The built-in Python manager orchestrates the entire deployment using Boto3 without requiring external CLI installations.

#### Step 1: Provision Core Cloud Infrastructure via CloudFormation
```bash
# Automatically detects default VPC and subnets, then provisions S3, RDS, ECR, IAM, and App Runner
python infra/aws_manager.py deploy-cf --env prod
```
*Note: This step provisions the RDS PostgreSQL 15 database (`db.t3.micro`), S3 bucket, ECR repository, and App Runner VPC connector. Provisioning typically completes in 10–12 minutes.*

#### Step 2: Build and Push Docker Container to ECR
```bash
# Create repository and print Docker push commands
python infra/aws_manager.py create-ecr

# Authenticate Docker to Amazon ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin $(aws sts get-caller-identity --query Account --output text).dkr.ecr.us-east-1.amazonaws.com

# Build and push the container image
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
docker build -f docker/Dockerfile -t event-invitation-system:latest .
docker tag event-invitation-system:latest ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/event-invitation-system:latest
docker push ${ACCOUNT_ID}.dkr.ecr.us-east-1.amazonaws.com/event-invitation-system:latest
```

#### Step 3: Verify Infrastructure Status
```bash
python infra/aws_manager.py status
python infra/aws_manager.py status-cf
```

---

### Option B: Native AWS CloudFormation

The complete infrastructure stack is defined in `infra/cloudformation/template.yaml`.

#### Step 1: Discover Default VPC and Subnet IDs
```bash
# Find Default VPC ID
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)

# Find Subnet IDs (need at least 2 in different Availability Zones)
SUBNET_IDS=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=${VPC_ID}" --query "Subnets[0:3].SubnetId" --output text | tr '\t' ',')

echo "Using VPC: ${VPC_ID}"
echo "Using Subnets: ${SUBNET_IDS}"
```

#### Step 2: Deploy CloudFormation Stack
```bash
aws cloudformation deploy \
  --template-file infra/cloudformation/template.yaml \
  --stack-name prod-event-invitation-system \
  --capabilities CAPABILITY_IAM CAPABILITY_NAMED_IAM \
  --parameter-overrides \
      EnvironmentName=prod \
      VpcId=${VPC_ID} \
      SubnetIds=${SUBNET_IDS} \
      DBMasterUsername=postgres \
      DBMasterPassword="<YOUR_SECURE_PASSWORD>" \
      SenderEmailAddress=invitations@example.com
```

#### Step 3: Retrieve Stack Outputs
```bash
aws cloudformation describe-stacks \
  --stack-name prod-event-invitation-system \
  --query "Stacks[0].Outputs" \
  --output table
```
Key outputs returned:
- `AppRunnerServiceUrl`: Direct public HTTPS endpoint (e.g. `https://xxxxxx.us-east-1.awsapprunner.com`) when `EnableAppRunner=true`
- `EcsHttpsUrl`: Public HTTPS endpoint (`https://<alb-dns>` with `AcmCertificateArn` or `https://<dist>.cloudfront.net`) when `EnableEcsFargate=true`
- `RDSEndpoint`: Private PostgreSQL endpoint
- `S3BucketName`: Dedicated S3 invitation bucket
- `ECRRepositoryUri`: ECR Docker registry URL

---

### Option C: Terraform Modular Infrastructure

The Terraform configuration in `infra/terraform/` defines all resources declaratively.

#### Step 1: Initialize Terraform
```bash
cd infra/terraform
terraform init
```

#### Step 2: Inspect Execution Plan
```bash
terraform plan \
  -var="aws_region=us-east-1" \
  -var="db_password=<YOUR_SECURE_PASSWORD>" \
  -var="sender_email=invitations@example.com"
```

#### Step 3: Apply Infrastructure
```bash
terraform apply -auto-approve \
  -var="aws_region=us-east-1" \
  -var="db_password=<YOUR_SECURE_PASSWORD>" \
  -var="sender_email=invitations@example.com"
```

Outputs will display `app_runner_url`, `rds_endpoint`, `s3_bucket`, and `ecr_repository_url`.

---

### Option D: AWS Management Console (GUI Walkthrough)

For step-by-step manual setup via the AWS Web Console:

#### 1. Amazon S3
1. Navigate to **S3** > **Create bucket**.
2. Bucket name: `open-invite-storage-<ACCOUNT_ID>`.
3. AWS Region: `us-east-1`.
4. Keep **Block all public access** checked (access is via presigned URLs).
5. Default encryption: **Server-side encryption with Amazon S3 managed keys (SSE-S3)**.
6. Under **Permissions** > **Cross-origin resource sharing (CORS)**, paste:
   ```json
   [
     {
       "AllowedHeaders": ["*"],
       "AllowedMethods": ["GET", "HEAD"],
       "AllowedOrigins": ["*"],
       "MaxAgeSeconds": 3600
     }
   ]
   ```

#### 2. Amazon RDS (PostgreSQL)
1. Navigate to **RDS** > **Create database**.
2. Choose **Standard create** > **PostgreSQL** (version 15).
3. Templates: **Free tier** (or Dev/Test).
4. DB instance identifier: `prod-event-invitation-db`.
5. Master username: `postgres`; Master password: `<YOUR_SECURE_PASSWORD>`.
6. DB instance class: `db.t3.micro`.
7. Connectivity: Select default VPC, **Public access: No**.
8. In VPC security group, create a new security group allowing inbound port 5432 from App Runner.
9. Initial database name: `event_db`.

#### 3. Amazon SES (Email Service)
1. Navigate to **Amazon Simple Email Service (SES)**.
2. Go to **Identities** > **Create identity**.
3. Choose **Email address**, enter your sender email (e.g. `invitations@example.com` or your personal email).
4. Click verification link sent to your inbox.
5. In SES Sandbox mode, also verify test recipient email addresses.

#### 4. AWS App Runner
1. Navigate to **AWS App Runner** > **Create service**.
2. Source: **Container registry** > **Amazon ECR**.
3. Select `event-invitation-system:latest`.
4. Deployment trigger: **Automatic**.
5. Service name: `prod-event-invitation-app`.
6. Port: `5000`.
7. Instance role: IAM role with S3 (`s3:PutObject`, `s3:GetObject`) and SES (`ses:SendEmail`) permissions.
8. Network: **Custom VPC** > Create VPC connector pointing to default VPC subnets and security group with egress to RDS.
9. Environment variables:
   - `FLASK_ENV`: `production`
   - `DATABASE_URL`: `postgresql://postgres:<YOUR_SECURE_PASSWORD>@<RDS_ENDPOINT>:5432/event_db`
   - `STORAGE_BACKEND`: `s3`
   - `S3_BUCKET_NAME`: `<YOUR_BUCKET_NAME>`
   - `AWS_REGION`: `us-east-1`
   - `EMAIL_PROVIDER`: `ses`
   - `MAIL_DEFAULT_SENDER`: `<VERIFIED_SES_EMAIL>`
   - `AUTO_SEED`: `true`
   - `SECRET_KEY`: `<RANDOM_SECRET_KEY>`
10. Click **Create & deploy**.

---

## 4. Post-Deployment Verification & Diagnostics

Once deployed, run the comprehensive verification probes to confirm cloud integration:

### 1. Health Endpoint Probe
```bash
curl -I https://<APP_RUNNER_SERVICE_URL>/health
```
Expected HTTP response: `HTTP/1.1 200 OK` with JSON body:
```json
{
  "status": "healthy",
  "storage_backend": "s3",
  "email_provider": "ses"
}
```

### 2. S3 Storage & Presigned URL Probe
```bash
python infra/aws_manager.py test-s3
```
Verifies object write, presigned GET signature generation, object retrieval, and object cleanup.

### 3. Amazon SES Transactional Email Probe
```bash
python infra/aws_manager.py test-ses --sender <VERIFIED_EMAIL> --recipient <VERIFIED_EMAIL>
```
Confirms transactional email deliverability and displays the SES `MessageId`.

### 4. Database Schema Auto-Initialization & Seeding
The container startup script (`docker/entrypoint.sh`) automatically verifies database connectivity, applies `flask init-db`, and seeds sample data (`AUTO_SEED=true`):
- **Default Host Credentials:** `host@example.com` / `OpenInvite2026!` (or value set in `ADMIN_PASSWORD`)
- **Sample Event:** Cloud Computing Tech Gala 2026 (`/events/1`)
- **Sample Guest RSVP Link:** `/rsvp/8027950e-6af4-48ca-bf06-cd0bf01c4633`

---

## 5. CI/CD Automation (GitHub Actions)

The repository includes a production-grade CI/CD workflow at `.github/workflows/ci-cd.yml`.

### Workflow Stages
1. **Test & Security Audit**: Runs all 33 unit/integration tests with `pytest` on Python 3.12, then executes `pip-audit` to ensure zero known vulnerabilities.
2. **Build & Push ECR Image**: Upon merge to `main`, builds the multi-stage Docker container and pushes to Amazon ECR.
3. **Deploy to App Runner**: Automatically triggers zero-downtime deployment on AWS App Runner.

### Setting Repository Secrets
In GitHub, navigate to **Settings** > **Secrets and variables** > **Actions** and add:
- `AWS_ACCESS_KEY_ID`: IAM user access key
- `AWS_SECRET_ACCESS_KEY`: IAM user secret key
- `APPRUNNER_SERVICE_ARN`: ARN of the App Runner service (e.g. `arn:aws:apprunner:us-east-1:123456789012:service/prod-event-invitation-app/...`)

---

## 6. Teardown & Resource Cleanup

To prevent ongoing AWS billing charges when testing or demonstrations conclude:

### Option A: CloudFormation Teardown
```bash
# Empty S3 bucket before stack deletion
aws s3 rm s3://<BUCKET_NAME> --recursive

# Delete CloudFormation stack
aws cloudformation delete-stack --stack-name prod-event-invitation-system
aws cloudformation wait stack-delete-complete --stack-name prod-event-invitation-system
```

### Option B: Terraform Teardown
```bash
cd infra/terraform
terraform destroy -auto-approve \
  -var="aws_region=us-east-1" \
  -var="db_password=<YOUR_SECURE_PASSWORD>" \
  -var="sender_email=invitations@example.com"
```

---

## 7. Troubleshooting Guide

| Issue / Symptom | Probable Cause | Corrective Action |
| :--- | :--- | :--- |
| **App Runner: Cannot connect to RDS** | VPC Connector missing or security group misconfigured | Ensure App Runner has a `VpcConnector` associated and the RDS security group allows inbound port 5432 from the App Runner security group. |
| **S3 403 Forbidden on PDF Download** | Missing IAM S3 permissions or expired URL | Ensure the App Runner Instance Role includes `s3:GetObject` and `s3:PutObject`, and `s3_service.py` expiration is set to 3600 seconds. |
| **SES MessageRejected / 400 Error** | Account is in SES Sandbox | Verify both the sender email and the recipient email address in SES console, or request Production Access in SES settings. |
| **ReportLab XML Syntax Error** | Special characters (`&`, `<`, `>`) in event description | Strings are auto-sanitized via `xml.sax.saxutils.escape`. Always use `escape()` when building ReportLab `Paragraph` instances. |
| **Container Fails Health Check** | Port mismatch or slow DB startup | Ensure container listens on port 5000 (`APP_PORT=5000`) and `entrypoint.sh` is executable (`chmod +x docker/entrypoint.sh`). |
