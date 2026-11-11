#!/usr/bin/env python3
"""
AWS Infrastructure Management Utility for OpenInvite.
Provides automated management and diagnostics for Amazon S3, Amazon SES, Amazon ECR,
Amazon RDS, and AWS CloudFormation using Boto3.
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import boto3
    from botocore.exceptions import ClientError, NoCredentialsError
    from dotenv import load_dotenv

    load_dotenv(PROJECT_ROOT / ".env")
except ImportError as err:
    print(f"Error: Missing required packages: {err}")
    print("Run: source .venv/bin/activate && pip install boto3 python-dotenv")
    sys.exit(1)


def get_aws_session(region: str = None) -> boto3.Session:
    """Create a Boto3 session from environment or AWS credentials file."""
    selected_region = (
        region
        or os.environ.get("AWS_REGION")
        or "us-east-1"
    )
    return boto3.Session(region_name=selected_region)


def cmd_check_auth(args):
    """Check active AWS credentials and print caller identity."""
    print("=" * 60)
    print("AWS Authentication & Identity Check")
    print("=" * 60)
    session = get_aws_session(args.region)
    sts = session.client("sts")

    try:
        identity = sts.get_caller_identity()
        print("Status:      [AUTHENTICATED]")
        print(f"Account ID:  {identity.get('Account')}")
        print(f"User / Role: {identity.get('Arn')}")
        print(f"User ID:     {identity.get('UserId')}")
        print(f"Region:      {session.region_name}")
        return True
    except (NoCredentialsError, ClientError) as e:
        print("Status:      [NOT AUTHENTICATED]")
        print(f"Error:       {e}")
        print("\nTo authenticate, either:")
        print("  1. Run 'aws configure' in your terminal, or")
        print("  2. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY in your .env file or environment.")
        return False


def cmd_create_s3(args):
    """Create and configure the private Amazon S3 bucket for PDF storage."""
    session = get_aws_session(args.region)
    s3 = session.client("s3")
    sts = session.client("sts")

    try:
        account_id = sts.get_caller_identity().get("Account")
    except Exception as e:
        print(f"Error checking AWS identity: {e}")
        return False

    bucket_name = args.bucket or os.environ.get(
        "S3_BUCKET_NAME", f"open-invite-storage-{account_id}"
    )

    print(f"Configuring S3 Bucket: '{bucket_name}' in '{session.region_name}'...")

    try:
        # Create bucket with region-appropriate configuration
        if session.region_name == "us-east-1":
            s3.create_bucket(Bucket=bucket_name)
        else:
            s3.create_bucket(
                Bucket=bucket_name,
                CreateBucketConfiguration={"LocationConstraint": session.region_name},
            )
        print(f"  [+] Bucket '{bucket_name}' created successfully.")
    except ClientError as e:
        code = e.response.get("Error", {}).get("Code")
        if code in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            print(f"  [*] Bucket '{bucket_name}' already exists.")
        else:
            print(f"  [-] Failed to create bucket: {e}")
            return False

    # 1. Enforce Server-Side Encryption (AES256)
    try:
        s3.put_bucket_encryption(
            Bucket=bucket_name,
            ServerSideEncryptionConfiguration={
                "Rules": [
                    {
                        "ApplyServerSideEncryptionByDefault": {
                            "SSEAlgorithm": "AES256"
                        }
                    }
                ]
            },
        )
        print("  [+] Server-Side Encryption (AES256) enabled.")
    except ClientError as e:
        print(f"  [-] Failed to enable encryption: {e}")

    # 2. Block all public access (presigned URL security model)
    try:
        s3.put_public_access_block(
            Bucket=bucket_name,
            PublicAccessBlockConfiguration={
                "BlockPublicAcls": True,
                "IgnorePublicAcls": True,
                "BlockPublicPolicy": True,
                "RestrictPublicBuckets": True,
            },
        )
        print("  [+] Block Public Access (all 4 flags) enforced.")
    except ClientError as e:
        print(f"  [-] Failed to enforce public access block: {e}")

    # 3. Configure CORS for client PDF downloads
    try:
        s3.put_bucket_cors(
            Bucket=bucket_name,
            CORSConfiguration={
                "CORSRules": [
                    {
                        "AllowedHeaders": ["*"],
                        "AllowedMethods": ["GET", "HEAD"],
                        "AllowedOrigins": ["*"],
                        "MaxAgeSeconds": 3600,
                    }
                ]
            },
        )
        print("  [+] CORS rule configured for GET/HEAD presigned requests.")
    except ClientError as e:
        print(f"  [-] Failed to configure CORS: {e}")

    print("\nS3 Setup Complete! Update your .env or AWS App Runner configuration:")
    print(f"  STORAGE_BACKEND=s3")
    print(f"  S3_BUCKET_NAME={bucket_name}")
    return True


def cmd_test_s3(args):
    """Test S3 bucket upload, presigned URL generation, and deletion."""
    session = get_aws_session(args.region)
    s3 = session.client("s3")
    sts = session.client("sts")

    try:
        account_id = sts.get_caller_identity().get("Account")
    except Exception as e:
        print(f"Error checking AWS identity: {e}")
        return False

    bucket_name = args.bucket or os.environ.get(
        "S3_BUCKET_NAME", f"open-invite-storage-{account_id}"
    )

    print(f"Testing S3 operations on bucket: '{bucket_name}'...")
    test_key = "diagnostics/test_probe.txt"
    test_content = b"Amazon Web Services: Event Invitation Management System S3 Connectivity Probe"

    try:
        # 1. Put object
        s3.put_object(
            Bucket=bucket_name,
            Key=test_key,
            Body=test_content,
            ContentType="text/plain",
        )
        print("  [+] S3 PutObject succeeded.")

        # 2. Generate presigned URL
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name, "Key": test_key},
            ExpiresIn=300,
        )
        print(f"  [+] S3 Presigned URL generated: {url[:80]}...")

        # 3. Get object back
        resp = s3.get_object(Bucket=bucket_name, Key=test_key)
        retrieved = resp["Body"].read()
        assert retrieved == test_content, "Retrieved body did not match uploaded content"
        print("  [+] S3 GetObject verified: payload integrity confirmed.")

        # 4. Clean up test object
        s3.delete_object(Bucket=bucket_name, Key=test_key)
        print("  [+] S3 DeleteObject cleaned up test probe.")
        print("\nAll S3 operations PASSED.")
        return True
    except ClientError as e:
        print(f"  [-] S3 Test Failed: {e}")
        return False


def cmd_setup_ses(args):
    """Verify sender email identity in Amazon SES and check sandbox status."""
    session = get_aws_session(args.region)
    ses = session.client("ses")
    email = args.email or os.environ.get("MAIL_DEFAULT_SENDER", "invitations@example.com")

    print(f"Configuring Amazon SES in region '{session.region_name}' for '{email}'...")

    try:
        # Check quota & sandbox status
        quota = ses.get_send_quota()
        print(f"  Max 24hr Send: {quota.get('Max24HourSend', 0):.0f} emails")
        print(f"  Max Send Rate: {quota.get('MaxSendRate', 0):.0f} emails/sec")
        print(f"  Sent Last 24hr: {quota.get('SentLast24Hours', 0):.0f}")

        # Request verification
        ses.verify_email_identity(EmailAddress=email)
        print(f"  [+] Verification email dispatched to: {email}")
        print("      Please check your inbox and click the AWS verification link.")
    except ClientError as e:
        print(f"  [-] SES Error: {e}")
        return False
    return True


def cmd_test_ses(args):
    """Send a transactional test email through Amazon SES."""
    session = get_aws_session(args.region)
    ses = session.client("ses")
    sender = args.sender or os.environ.get("MAIL_DEFAULT_SENDER", "invitations@example.com")
    recipient = args.recipient or sender

    print(f"Testing SES email delivery from '{sender}' to '{recipient}'...")
    try:
        response = ses.send_email(
            Source=sender,
            Destination={"ToAddresses": [recipient]},
            Message={
                "Subject": {
                    "Data": "OpenInvite - SES Diagnostic Probe",
                    "Charset": "UTF-8",
                },
                "Body": {
                    "Html": {
                        "Data": (
                            "<div style='font-family:sans-serif;padding:20px;border-left:4px solid #1E3A8A;'>"
                            "<h2 style='color:#1E3A8A;'>AWS SES Verification Probe Successful</h2>"
                            "<p>This email confirms that transactional email delivery is active on Amazon SES.</p>"
                            "<p style='color:#64748B;'>OpenInvite Self-Hosted Event Invitation Platform</p>"
                            "</div>"
                        ),
                        "Charset": "UTF-8",
                    },
                    "Text": {
                        "Data": "AWS SES Verification Probe Successful.\n\nOpenInvite Self-Hosted Event Invitation Platform",
                        "Charset": "UTF-8",
                    },
                },
            },
        )
        print(f"  [+] Email sent successfully! MessageId: {response.get('MessageId')}")
        return True
    except ClientError as e:
        print(f"  [-] SES Send Error: {e}")
        print("      Note: In SES Sandbox mode, both sender AND recipient must be verified email addresses.")
        return False


def cmd_create_ecr(args):
    """Create the Amazon ECR repository and print Docker push commands."""
    session = get_aws_session(args.region)
    ecr = session.client("ecr")
    sts = session.client("sts")

    try:
        identity = sts.get_caller_identity()
        account_id = identity.get("Account")
    except Exception as e:
        print(f"Error checking AWS identity: {e}")
        return False

    repo_name = args.name or "event-invitation-system"
    region = session.region_name
    print(f"Ensuring ECR Repository: '{repo_name}' in '{region}'...")

    try:
        resp = ecr.create_repository(
            repositoryName=repo_name,
            imageScanningConfiguration={"scanOnPush": True},
        )
        repo_uri = resp["repository"]["repositoryUri"]
        print(f"  [+] Created ECR repository: {repo_uri}")
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "RepositoryAlreadyExistsException":
            repo_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repo_name}"
            print(f"  [*] ECR repository already exists: {repo_uri}")
        else:
            print(f"  [-] ECR Error: {e}")
            return False

    print("\n" + "=" * 60)
    print("Docker Build & Push Instructions:")
    print("=" * 60)
    print(f"1. Authenticate Docker with Amazon ECR:")
    print(f"   aws ecr get-login-password --region {region} | docker login --username AWS --password-stdin {account_id}.dkr.ecr.{region}.amazonaws.com")
    print(f"\n2. Build the production container:")
    print(f"   docker build -f docker/Dockerfile -t {repo_name}:latest .")
    print(f"\n3. Tag for ECR:")
    print(f"   docker tag {repo_name}:latest {repo_uri}:latest")
    print(f"\n4. Push image:")
    print(f"   docker push {repo_uri}:latest")
    return True


def cmd_deploy_cf(args):
    """Deploy or update the infrastructure via AWS CloudFormation."""
    session = get_aws_session(args.region)
    cf = session.client("cloudformation")
    ec2 = session.client("ec2")
    sts = session.client("sts")

    stack_name = args.stack_name or "prod-event-invitation-system"
    template_path = PROJECT_ROOT / "infra" / "cloudformation" / "template.yaml"

    if not template_path.exists():
        print(f"Error: Template file not found: {template_path}")
        return False

    print("=" * 60)
    print(f"Deploying CloudFormation Stack: '{stack_name}' ({session.region_name})")
    print("=" * 60)

    try:
        template_body = template_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"Error reading template: {e}")
        return False

    # Auto-detect VPC and Subnets if not provided
    vpc_id = args.vpc_id
    subnet_ids = args.subnet_ids

    if not vpc_id or not subnet_ids:
        print("Resolving default VPC and Subnet configuration...")
        try:
            vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}]).get("Vpcs", [])
            if not vpcs:
                vpcs = ec2.describe_vpcs().get("Vpcs", [])
            if not vpcs:
                print("Error: No VPCs found in region.")
                return False
            vpc_id = vpcs[0]["VpcId"]
            print(f"  [+] Target VPC: {vpc_id}")

            subnets = ec2.describe_subnets(Filters=[{"Name": "vpc-id", "Values": [vpc_id]}]).get("Subnets", [])
            if len(subnets) < 2:
                print(f"Error: Need at least 2 subnets across AZs for RDS, found {len(subnets)}")
                return False
            subnet_ids = [s["SubnetId"] for s in subnets[:3]]
            print(f"  [+] Selected Subnets: {', '.join(subnet_ids)}")
        except ClientError as e:
            print(f"Error detecting VPC/Subnets: {e}")
            return False

    parameters = [
        {"ParameterKey": "EnvironmentName", "ParameterValue": args.env or "prod"},
        {"ParameterKey": "VpcId", "ParameterValue": vpc_id},
        {"ParameterKey": "SubnetIds", "ParameterValue": ",".join(subnet_ids)},
        {"ParameterKey": "DBMasterUsername", "ParameterValue": args.db_user or "postgres"},
        {"ParameterKey": "DBMasterPassword", "ParameterValue": args.db_pass or "AdminPassword2026!"},
        {"ParameterKey": "SenderEmailAddress", "ParameterValue": args.sender_email or "invitations@example.com"},
        {"ParameterKey": "DBPubliclyAccessible", "ParameterValue": "true" if getattr(args, "db_public", True) else "false"},
        {"ParameterKey": "EnableAppRunner", "ParameterValue": "true" if getattr(args, "enable_apprunner", False) else "false"},
        {"ParameterKey": "EnableEcsFargate", "ParameterValue": "true" if getattr(args, "enable_ecs", False) else "false"},
        {"ParameterKey": "AcmCertificateArn", "ParameterValue": getattr(args, "acm_cert_arn", None) or ""},
        {"ParameterKey": "EnableCloudFrontHttps", "ParameterValue": "false" if getattr(args, "disable_cloudfront", False) else "true"},
    ]

    capabilities = ["CAPABILITY_IAM", "CAPABILITY_NAMED_IAM"]

    # Check if stack already exists
    stack_exists = False
    try:
        cf.describe_stacks(StackName=stack_name)
        stack_exists = True
    except ClientError:
        stack_exists = False

    try:
        if stack_exists:
            print(f"Updating existing stack '{stack_name}'...")
            cf.update_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=capabilities,
            )
            waiter = cf.get_waiter("stack_update_complete")
        else:
            print(f"Creating new stack '{stack_name}' (this provisions S3, RDS, ECR, IAM, and App Runner)...")
            cf.create_stack(
                StackName=stack_name,
                TemplateBody=template_body,
                Parameters=parameters,
                Capabilities=capabilities,
            )
            waiter = cf.get_waiter("stack_create_complete")

        print("Provisioning in progress... (this typically takes 10-15 minutes for RDS and App Runner)")
        waiter.wait(
            StackName=stack_name,
            WaiterConfig={"Delay": 20, "MaxAttempts": 60},
        )
        print("\n[+] Stack deployment completed successfully!")

        # Print outputs
        desc = cf.describe_stacks(StackName=stack_name)
        outputs = desc["Stacks"][0].get("Outputs", [])
        print("\n" + "=" * 60)
        print("Stack Outputs:")
        print("=" * 60)
        for out in outputs:
            print(f"  {out.get('OutputKey')}: {out.get('OutputValue')}")
        return True

    except ClientError as e:
        if "No updates are to be performed" in str(e):
            print("Stack is already up-to-date. No changes needed.")
            return True
        print(f"CloudFormation Deployment Error: {e}")
        return False


def cmd_status_cf(args):
    """View status, events, and outputs for the CloudFormation stack."""
    session = get_aws_session(args.region)
    cf = session.client("cloudformation")
    stack_name = args.stack_name or "prod-event-invitation-system"

    print("=" * 60)
    print(f"CloudFormation Stack Status: '{stack_name}' ({session.region_name})")
    print("=" * 60)

    try:
        resp = cf.describe_stacks(StackName=stack_name)
        stack = resp["Stacks"][0]
        print(f"Status:      {stack.get('StackStatus')}")
        print(f"Created:     {stack.get('CreationTime')}")
        if "LastUpdatedTime" in stack:
            print(f"Updated:     {stack.get('LastUpdatedTime')}")

        outputs = stack.get("Outputs", [])
        if outputs:
            print("\nOutputs:")
            for o in outputs:
                print(f"  - {o.get('OutputKey')}: {o.get('OutputValue')}")

        # List last 5 events
        events_resp = cf.describe_stack_events(StackName=stack_name)
        events = events_resp.get("StackEvents", [])[:5]
        if events:
            print("\nRecent Stack Events:")
            for ev in events:
                print(f"  [{ev.get('Timestamp').strftime('%H:%M:%S')}] {ev.get('LogicalResourceId')}: {ev.get('ResourceStatus')} ({ev.get('ResourceStatusReason', '')})")
    except ClientError as e:
        print(f"Error fetching stack: {e}")


def cmd_status(args):
    """Comprehensive status check of S3, RDS, SES, ECR, and App Runner."""
    session = get_aws_session(args.region)
    print("=" * 60)
    print(f"AWS Infrastructure Status ({session.region_name})")
    print("=" * 60)

    # 1. Identity
    sts = session.client("sts")
    try:
        id_info = sts.get_caller_identity()
        print(f"Account:     {id_info.get('Account')} ({id_info.get('Arn')})")
    except Exception as e:
        print(f"Authentication: Failed ({e})")
        return

    # 2. S3
    s3 = session.client("s3")
    bucket = os.environ.get("S3_BUCKET_NAME", f"open-invite-storage-{id_info.get('Account')}")
    try:
        s3.head_bucket(Bucket=bucket)
        print(f"Amazon S3:   [ACTIVE] Bucket '{bucket}' exists and is accessible.")
    except Exception:
        print(f"Amazon S3:   [NOT FOUND] Bucket '{bucket}' does not exist or access denied.")

    # 3. RDS
    rds = session.client("rds")
    try:
        instances = rds.describe_db_instances()
        matched = [
            i for i in instances.get("DBInstances", [])
            if "event" in i.get("DBInstanceIdentifier", "")
        ]
        if matched:
            db_inst = matched[0]
            print(f"Amazon RDS:  [{db_inst.get('DBInstanceStatus', '').upper()}] Identifier: {db_inst.get('DBInstanceIdentifier')} (Endpoint: {db_inst.get('Endpoint', {}).get('Address')})")
        else:
            print("Amazon RDS:  [NOT PROVISIONED] No matching RDS instance found.")
    except Exception as e:
        print(f"Amazon RDS:  Check error ({e})")

    # 4. ECR
    ecr = session.client("ecr")
    try:
        repos = ecr.describe_repositories(repositoryNames=["event-invitation-system"])
        if repos.get("repositories"):
            print(f"Amazon ECR:  [ACTIVE] URI: {repos['repositories'][0].get('repositoryUri')}")
    except Exception:
        print("Amazon ECR:  [NOT CREATED] Repository 'event-invitation-system' not found.")

    # 5. SES
    ses = session.client("ses")
    try:
        identities = ses.list_identities(IdentityType="EmailAddress").get("Identities", [])
        verified = ses.get_identity_verification_attributes(Identities=identities).get("VerificationAttributes", {})
        print(f"Amazon SES:  Found {len(identities)} identity/identities:")
        for id_name in identities:
            status = verified.get(id_name, {}).get("VerificationStatus", "Unknown")
            print(f"             - {id_name}: [{status}]")
    except Exception as e:
        print(f"Amazon SES:  Check error ({e})")

    # 6. App Runner
    apprunner = session.client("apprunner")
    try:
        services = apprunner.list_services().get("ServiceSummaryList", [])
        matched_services = [s for s in services if "event" in s.get("ServiceName", "")]
        if matched_services:
            for s in matched_services:
                print(f"App Runner:  [{s.get('Status')}] {s.get('ServiceName')} (URL: https://{s.get('ServiceUrl')})")
        else:
            print("App Runner:  [NOT PROVISIONED] Service not deployed.")
    except Exception as e:
        print(f"App Runner:  Check error ({e})")

    # 7. Amazon ECS Fargate & Managed HTTPS Edges (ALB / CloudFront)
    https_endpoints = discover_https_endpoints(session, include_apprunner=False)
    for ep in https_endpoints:
        print(f"{ep['provider']}: [{ep['status']}] URL: {ep['url']}")

    ecs = session.client("ecs")
    try:
        ip = get_fargate_public_ip(session)
        if ip:
            print(f"ECS Fargate: [RUNNING] Task IP: {ip} (Direct HTTP: http://{ip}:5000)")
        else:
            prod_services = ecs.describe_services(
                cluster="prod-event-invitation-cluster",
                services=["prod-event-invitation-service"],
            ).get("services", [])
            if isinstance(prod_services, list) and prod_services and prod_services[0].get("runningCount", 0) > 0:
                svc = prod_services[0]
                print(
                    f"ECS Fargate: [{svc.get('status', 'ACTIVE')}] {svc.get('serviceName')} "
                    f"(Running: {svc.get('runningCount')}/{svc.get('desiredCount')})"
                )
            else:
                services = ecs.describe_services(cluster="event-invitation-cluster", services=["event-invitation-service"]).get("services", [])
                if isinstance(services, list) and services and services[0].get("desiredCount", 0) == 0:
                    print("ECS Fargate: [STOPPED] Service is scaled to 0 (run 'python infra/aws_manager.py public-on' to start).")
                else:
                    print("ECS Fargate: [PENDING / STARTING] Container task starting...")
    except Exception as e:
        print(f"ECS Fargate: Check error ({e})")


def discover_https_endpoints(session, include_apprunner: bool = True) -> list[dict]:
    """Discover active HTTPS endpoints across App Runner, CloudFront, and ALB."""
    endpoints: list[dict] = []

    # 1. App Runner
    if include_apprunner:
        try:
            apprunner = session.client("apprunner")
            services = apprunner.list_services().get("ServiceSummaryList", [])
            if isinstance(services, list):
                for s in services:
                    name = s.get("ServiceName", "").lower()
                    if "event" in name or "openinvite" in name:
                        svc_url = s.get("ServiceUrl")
                        if svc_url:
                            endpoints.append(
                                {
                                    "provider": "App Runner",
                                    "url": f"https://{svc_url}",
                                    "status": s.get("Status", "UNKNOWN"),
                                }
                            )
        except Exception:
            pass

    # 2. CloudFront HTTPS distributions
    try:
        cf_client = session.client("cloudfront")
        dist_list = cf_client.list_distributions().get("DistributionList", {})
        items = dist_list.get("Items", []) if isinstance(dist_list, dict) else []
        if isinstance(items, list):
            for dist in items:
                comment = (dist.get("Comment") or "").lower()
                origins = dist.get("Origins", {}).get("Items", [])
                origin_match = any(
                    "openinvite" in (o.get("DomainName") or "").lower()
                    or "event" in (o.get("DomainName") or "").lower()
                    for o in (origins if isinstance(origins, list) else [])
                )
                if "openinvite" in comment or "event" in comment or origin_match:
                    domain = dist.get("DomainName")
                    if domain:
                        endpoints.append(
                            {
                                "provider": "CloudFront HTTPS",
                                "url": f"https://{domain}",
                                "status": dist.get("Status", "Deployed"),
                            }
                        )
    except Exception:
        pass

    # 3. Application Load Balancer (HTTPS:443 listeners)
    try:
        elbv2 = session.client("elbv2")
        lbs = elbv2.describe_load_balancers().get("LoadBalancers", [])
        if isinstance(lbs, list):
            for lb in lbs:
                lb_name = (lb.get("LoadBalancerName") or "").lower()
                if "openinvite" in lb_name or "event" in lb_name:
                    listeners = elbv2.describe_listeners(
                        LoadBalancerArn=lb.get("LoadBalancerArn", "")
                    ).get("Listeners", [])
                    has_https = isinstance(listeners, list) and any(
                        l.get("Protocol") == "HTTPS" for l in listeners
                    )
                    if has_https and lb.get("DNSName"):
                        endpoints.append(
                            {
                                "provider": "ALB HTTPS",
                                "url": f"https://{lb['DNSName']}",
                                "status": lb.get("State", {}).get("Code", "active"),
                            }
                        )
    except Exception:
        pass

    return endpoints


def _print_endpoint_urls(base_url: str) -> None:
    """Print standard application endpoints for a discovered base URL."""
    print(f"Web Base URL:  {base_url}")
    print(f"Host Login:    {base_url}/auth/login")
    print(f"Dashboard:     {base_url}/events/1")
    print(f"Health Probe:  {base_url}/health")
    print(f"Guest RSVP:    {base_url}/rsvp/770b7b9e-2f66-4867-89b6-673b2fbe48a1")
    print(f"PDF Download:  {base_url}/events/1/pdf?download=1")


def get_fargate_public_ip(session, cluster_name: str = "event-invitation-cluster", service_name: str = "event-invitation-service"):
    """Retrieve the public IP address for the active ECS Fargate task."""
    ecs = session.client("ecs")
    ec2 = session.client("ec2")

    try:
        tasks = ecs.list_tasks(cluster=cluster_name, serviceName=service_name, desiredStatus="RUNNING").get("taskArns", [])
        if not tasks:
            # Also check for standalone running tasks in cluster
            tasks = ecs.list_tasks(cluster=cluster_name, desiredStatus="RUNNING").get("taskArns", [])
        if not tasks:
            return None

        desc = ecs.describe_tasks(cluster=cluster_name, tasks=tasks).get("tasks", [])
        for task in desc:
            if task.get("lastStatus") == "RUNNING":
                for att in task.get("attachments", []):
                    if att.get("type") == "ElasticNetworkInterface":
                        for d in att.get("details", []):
                            if d.get("name") == "networkInterfaceId":
                                eni_id = d.get("value")
                                eni = ec2.describe_network_interfaces(NetworkInterfaceIds=[eni_id])["NetworkInterfaces"][0]
                                return eni.get("Association", {}).get("PublicIp")
    except Exception:
        return None
    return None


def cmd_public_url(args):
    """Retrieve and display the current live public URL and access endpoints."""
    session = get_aws_session(args.region)
    print("=" * 60)
    print("AWS Public Endpoint Discovery")
    print("=" * 60)

    https_endpoints = discover_https_endpoints(session)
    if https_endpoints:
        primary = https_endpoints[0]
        print(f"Status:        [ONLINE - {primary['provider']}]")
        _print_endpoint_urls(primary["url"])
        return

    ip = get_fargate_public_ip(session)
    if ip:
        scheme = "https" if getattr(args, "https", False) else "http"
        print("Status:        [ONLINE - Direct Task IP]")
        if scheme == "http":
            print("Note:          Direct Fargate IP is HTTP-only. Deploy behind ALB/CloudFront or App Runner for HTTPS.")
        print(f"Public IP:     {ip}")
        _print_endpoint_urls(f"{scheme}://{ip}:5000")
    else:
        print("Status:        [OFFLINE / NOT RUNNING]")
        print("The AWS Fargate container is currently stopped.")
        print("Run 'python infra/aws_manager.py public-on' to spin it up.")


def cmd_public_on(args):
    """Start the public AWS Fargate container and display its new public address."""
    session = get_aws_session(args.region)
    ecs = session.client("ecs")
    cluster_name = "event-invitation-cluster"
    service_name = "event-invitation-service"

    print("Scaling AWS Fargate service ON (desiredCount=1)...")
    try:
        ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=1,
        )
    except ClientError as e:
        print(f"Error updating service: {e}")
        return False

    print("Waiting for container to reach RUNNING state and obtain public IP...", end="", flush=True)
    for attempt in range(25):
        time.sleep(3)
        ip = get_fargate_public_ip(session, cluster_name=cluster_name, service_name=service_name)
        if ip:
            print(f"\n[+] AWS Fargate container is ONLINE!")
            https_endpoints = discover_https_endpoints(session)
            if https_endpoints:
                primary = https_endpoints[0]
                print(f"HTTPS Edge:    {primary['provider']}")
                _print_endpoint_urls(primary["url"])
            else:
                print(f"Public IP:     {ip}")
                _print_endpoint_urls(f"http://{ip}:5000")
            return True
        print(".", end="", flush=True)

    print("\nContainer is starting up. Check status in a few moments with 'python infra/aws_manager.py public-url'.")
    return True


def cmd_public_off(args):
    """Stop the public AWS Fargate container to release the public IP and halt compute billing."""
    session = get_aws_session(args.region)
    ecs = session.client("ecs")
    cluster_name = "event-invitation-cluster"
    service_name = "event-invitation-service"

    print("Scaling AWS Fargate service OFF (desiredCount=0)...")
    try:
        ecs.update_service(
            cluster=cluster_name,
            service=service_name,
            desiredCount=0,
        )
    except ClientError as e:
        print(f"Warning on updating service: {e}")

    # Immediately stop any running tasks in the cluster (both service-managed and standalone tasks)
    try:
        task_arns = ecs.list_tasks(cluster=cluster_name).get("taskArns", [])
        if task_arns:
            print(f"Terminating {len(task_arns)} active task(s) in cluster...")
            for arn in task_arns:
                try:
                    ecs.stop_task(
                        cluster=cluster_name,
                        task=arn,
                        reason="Explicit scale-down to 0 via aws_manager public-off",
                    )
                except ClientError as stop_err:
                    print(f"  Note on stopping {arn.split('/')[-1]}: {stop_err}")

        # Wait briefly for tasks to fully transition to STOPPED
        print("Waiting for tasks to stop and release public endpoints...", end="", flush=True)
        for _ in range(12):
            running = ecs.list_tasks(cluster=cluster_name, desiredStatus="RUNNING").get("taskArns", [])
            if not running:
                break
            time.sleep(1)
            print(".", end="", flush=True)
        print()

        print("[+] AWS Fargate compute scaled to 0. All public endpoints released and compute billing paused.")
        return True
    except ClientError as e:
        print(f"Error terminating tasks: {e}")
        return False


def cmd_toggle_public(args):
    """Toggle the AWS Fargate container between ONLINE and OFFLINE."""
    session = get_aws_session(args.region)
    ecs = session.client("ecs")
    cluster_name = "event-invitation-cluster"
    service_name = "event-invitation-service"

    try:
        running_tasks = ecs.list_tasks(cluster=cluster_name, desiredStatus="RUNNING").get("taskArns", [])
        services = ecs.describe_services(
            cluster=cluster_name,
            services=[service_name],
        ).get("services", [])

        current_desired = services[0].get("desiredCount", 0) if services else 0
        is_active = (current_desired > 0) or (len(running_tasks) > 0)

        if is_active:
            print(f"Current state: ONLINE ({len(running_tasks)} running task(s), desiredCount={current_desired}). Toggling OFF...")
            return cmd_public_off(args)
        else:
            print("Current state: OFFLINE (0 running tasks, desiredCount=0). Toggling ON...")
            return cmd_public_on(args)
    except ClientError as e:
        print(f"Error toggling public state: {e}")
        return False


def cmd_toggle_rds(args):
    """Toggle public inbound access (0.0.0.0/0 on port 5432) on Amazon RDS."""
    session = get_aws_session(args.region)
    ec2 = session.client("ec2")

    try:
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}]).get("Vpcs", [])
        vpc_id = vpcs[0]["VpcId"] if vpcs else None

        sgs = ec2.describe_security_groups(
            Filters=[{"Name": "vpc-id", "Values": [vpc_id]}] if vpc_id else []
        ).get("SecurityGroups", [])

        target_sg = None
        for sg in sgs:
            if "DatabaseSecurityGroup" in sg["GroupName"]:
                target_sg = sg
                break

        if not target_sg:
            print("Error: Could not locate RDS DatabaseSecurityGroup.")
            return False

        sg_id = target_sg["GroupId"]
        has_public = any(
            p.get("FromPort") == 5432 and any(r.get("CidrIp") == "0.0.0.0/0" for r in p.get("IpRanges", []))
            for p in target_sg.get("IpPermissions", [])
        )

        if has_public:
            print(f"RDS currently has Public Access (0.0.0.0/0:5432 enabled on {sg_id}).")
            print("Revoking public access rule (making RDS private to VPC only)...")
            ec2.revoke_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
                }]
            )
            print("[+] RDS is now PRIVATE (accessible only within VPC compute).")
        else:
            print(f"RDS currently has Private Access only on {sg_id}.")
            print("Authorizing public access rule (0.0.0.0/0:5432 for external tools/tests)...")
            ec2.authorize_security_group_ingress(
                GroupId=sg_id,
                IpPermissions=[{
                    "IpProtocol": "tcp",
                    "FromPort": 5432,
                    "ToPort": 5432,
                    "IpRanges": [{"CidrIp": "0.0.0.0/0"}]
                }]
            )
            print("[+] RDS is now PUBLICLY ACCESSIBLE (0.0.0.0/0 on port 5432).")
        return True
    except ClientError as e:
        print(f"Error toggling RDS access: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="AWS Infrastructure Manager for OpenInvite"
    )
    parser.add_argument("--region", default=None, help="AWS Region (default: us-east-1)")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # check-auth
    subparsers.add_parser("check-auth", help="Verify active AWS authentication and identity")

    # create-s3
    s3_parser = subparsers.add_parser("create-s3", help="Create and configure S3 bucket")
    s3_parser.add_argument("--bucket", default=None, help="Bucket name override")

    # test-s3
    test_s3_parser = subparsers.add_parser("test-s3", help="Upload and verify a probe PDF to S3")
    test_s3_parser.add_argument("--bucket", default=None, help="Bucket name override")

    # setup-ses
    ses_parser = subparsers.add_parser("setup-ses", help="Verify SES sender email")
    ses_parser.add_argument("--email", default=None, help="Email address to verify")

    # test-ses
    test_ses_parser = subparsers.add_parser("test-ses", help="Send a test diagnostic email via SES")
    test_ses_parser.add_argument("--sender", default=None, help="Sender email address")
    test_ses_parser.add_argument("--recipient", default=None, help="Recipient email address")

    # create-ecr
    ecr_parser = subparsers.add_parser("create-ecr", help="Create ECR repository")
    ecr_parser.add_argument("--name", default=None, help="ECR repository name")

    # deploy-cf
    cf_parser = subparsers.add_parser("deploy-cf", help="Deploy infrastructure stack via AWS CloudFormation")
    cf_parser.add_argument("--stack-name", default="prod-event-invitation-system", help="CloudFormation stack name")
    cf_parser.add_argument("--env", default="prod", help="Environment name (prod/staging/dev)")
    cf_parser.add_argument("--vpc-id", default=None, help="Target AWS VPC ID (auto-detected if omitted)")
    cf_parser.add_argument("--subnet-ids", nargs="+", default=None, help="Subnet IDs for RDS and App Runner")
    cf_parser.add_argument("--db-user", default="postgres", help="RDS master username")
    cf_parser.add_argument("--db-pass", default="AdminPassword2026!", help="RDS master password")
    cf_parser.add_argument("--sender-email", default="invitations@example.com", help="SES verified sender email")
    cf_parser.add_argument("--enable-apprunner", action="store_true", default=False, help="Enable App Runner compute deployment")
    cf_parser.add_argument("--enable-ecs", action="store_true", default=False, help="Enable ECS Fargate + ALB HTTPS deployment")
    cf_parser.add_argument("--acm-cert-arn", default="", help="Optional ACM Certificate ARN for ALB HTTPS:443 listener")
    cf_parser.add_argument("--disable-cloudfront", action="store_true", default=False, help="Disable CloudFront HTTPS distribution for ECS ALB")

    # status-cf
    status_cf_parser = subparsers.add_parser("status-cf", help="View CloudFormation stack status and outputs")
    status_cf_parser.add_argument("--stack-name", default="prod-event-invitation-system", help="Stack name")

    # status
    subparsers.add_parser("status", help="Check status of all AWS infrastructure components")

    # public-url / url
    subparsers.add_parser("public-url", help="Display the active public IP and URLs of the running container")
    subparsers.add_parser("url", help="Alias for public-url")

    # public-on
    subparsers.add_parser("public-on", help="Start the AWS Fargate container and display its public address")

    # public-off
    subparsers.add_parser("public-off", help="Stop the AWS Fargate container and release public address")

    # toggle-public
    subparsers.add_parser("toggle-public", help="Toggle the AWS Fargate public compute between ONLINE and OFFLINE")

    # toggle-rds
    subparsers.add_parser("toggle-rds", help="Toggle external public access (port 5432) on Amazon RDS")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(0)

    commands = {
        "check-auth": cmd_check_auth,
        "create-s3": cmd_create_s3,
        "test-s3": cmd_test_s3,
        "setup-ses": cmd_setup_ses,
        "test-ses": cmd_test_ses,
        "create-ecr": cmd_create_ecr,
        "deploy-cf": cmd_deploy_cf,
        "status-cf": cmd_status_cf,
        "status": cmd_status,
        "public-url": cmd_public_url,
        "url": cmd_public_url,
        "public-on": cmd_public_on,
        "public-off": cmd_public_off,
        "toggle-public": cmd_toggle_public,
        "toggle-rds": cmd_toggle_rds,
    }

    cmd_fn = commands.get(args.command)
    if cmd_fn:
        cmd_fn(args)


if __name__ == "__main__":
    main()
