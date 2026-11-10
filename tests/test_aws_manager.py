"""
Unit tests for the AWS Infrastructure Manager CLI (infra/aws_manager.py).
Tests all subcommands using mocked boto3 clients without requiring real AWS credentials.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch
import pytest

from infra.aws_manager import (
    cmd_check_auth,
    cmd_create_ecr,
    cmd_create_s3,
    cmd_setup_ses,
    cmd_status,
    cmd_test_s3,
    cmd_test_ses,
    get_aws_session,
)


@pytest.fixture
def mock_session():
    """Fixture providing a mocked boto3 Session."""
    session = MagicMock()
    return session


def test_get_aws_session_custom_region():
    session = get_aws_session("us-west-2")
    assert session.region_name == "us-west-2"


def test_cmd_check_auth_success(mock_session):
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {
        "Account": "123456789012",
        "Arn": "arn:aws:iam::123456789012:user/tester",
        "UserId": "AIDAXXXXXXXXXXXXXXXXX",
    }
    mock_session.client.return_value = mock_sts

    args = MagicMock(region="us-east-1")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        result = cmd_check_auth(args)
        assert result is True
        mock_sts.get_caller_identity.assert_called_once()


def test_cmd_check_auth_no_credentials():
    from botocore.exceptions import NoCredentialsError

    mock_session = MagicMock()
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.side_effect = NoCredentialsError()
    mock_session.client.return_value = mock_sts

    args = MagicMock(region="us-east-1")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        result = cmd_check_auth(args)
        assert result is False


def test_cmd_create_s3_success():
    mock_session = MagicMock()
    mock_session.region_name = "us-east-1"
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
    mock_s3 = MagicMock()

    def client_side_effect(name):
        if name == "sts":
            return mock_sts
        if name == "s3":
            return mock_s3
        return MagicMock()

    mock_session.client.side_effect = client_side_effect

    args = MagicMock(region="us-east-1", bucket="test-custom-bucket")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        result = cmd_create_s3(args)
        assert result is True
        mock_s3.create_bucket.assert_called_once_with(Bucket="test-custom-bucket")
        mock_s3.put_bucket_encryption.assert_called_once()
        mock_s3.put_public_access_block.assert_called_once()
        mock_s3.put_bucket_cors.assert_called_once()


def test_cmd_test_s3_success():
    mock_session = MagicMock()
    mock_session.region_name = "us-east-1"
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
    mock_s3 = MagicMock()

    test_bytes = b"Amazon Web Services: Event Invitation Management System S3 Connectivity Probe"
    mock_s3.get_object.return_value = {"Body": BytesIO(test_bytes)}
    mock_s3.generate_presigned_url.return_value = "https://s3.amazonaws.com/test-bucket/test_probe.txt?signature=xyz"

    def client_side_effect(name):
        if name == "sts":
            return mock_sts
        if name == "s3":
            return mock_s3
        return MagicMock()

    mock_session.client.side_effect = client_side_effect

    args = MagicMock(region="us-east-1", bucket="test-bucket")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        result = cmd_test_s3(args)
        assert result is True
        mock_s3.put_object.assert_called_once()
        mock_s3.generate_presigned_url.assert_called_once()
        mock_s3.get_object.assert_called_once()
        mock_s3.delete_object.assert_called_once()


def test_cmd_setup_ses_success():
    mock_session = MagicMock()
    mock_session.region_name = "us-east-1"
    mock_ses = MagicMock()
    mock_ses.get_send_quota.return_value = {
        "Max24HourSend": 200.0,
        "MaxSendRate": 1.0,
        "SentLast24Hours": 0.0,
    }
    mock_session.client.return_value = mock_ses

    args = MagicMock(region="us-east-1", email="host@example.com")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        result = cmd_setup_ses(args)
        assert result is True
        mock_ses.verify_email_identity.assert_called_once_with(EmailAddress="host@example.com")


def test_cmd_test_ses_success():
    mock_session = MagicMock()
    mock_session.region_name = "us-east-1"
    mock_ses = MagicMock()
    mock_ses.send_email.return_value = {"MessageId": "msg-12345-abcde"}
    mock_session.client.return_value = mock_ses

    args = MagicMock(
        region="us-east-1",
        sender="invitations@example.com",
        recipient="guest@example.com",
    )
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        result = cmd_test_ses(args)
        assert result is True
        mock_ses.send_email.assert_called_once()


def test_cmd_create_ecr_success():
    mock_session = MagicMock()
    mock_session.region_name = "us-east-1"
    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "123456789012"}
    mock_ecr = MagicMock()
    mock_ecr.create_repository.return_value = {
        "repository": {"repositoryUri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/test-repo"}
    }

    def client_side_effect(name):
        if name == "sts":
            return mock_sts
        if name == "ecr":
            return mock_ecr
        return MagicMock()

    mock_session.client.side_effect = client_side_effect

    args = MagicMock(region="us-east-1", name="test-repo")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        result = cmd_create_ecr(args)
        assert result is True
        mock_ecr.create_repository.assert_called_once()


def test_cmd_status_success():
    mock_session = MagicMock()
    mock_session.region_name = "us-east-1"

    mock_sts = MagicMock()
    mock_sts.get_caller_identity.return_value = {"Account": "123456789012", "Arn": "arn:aws:iam::..."}
    mock_s3 = MagicMock()
    mock_rds = MagicMock()
    mock_rds.describe_db_instances.return_value = {
        "DBInstances": [
            {
                "DBInstanceIdentifier": "prod-event-db",
                "DBInstanceStatus": "available",
                "Endpoint": {"Address": "db.xyz.us-east-1.rds.amazonaws.com"},
            }
        ]
    }
    mock_ecr = MagicMock()
    mock_ecr.describe_repositories.return_value = {
        "repositories": [{"repositoryUri": "123456789012.dkr.ecr.us-east-1.amazonaws.com/event-invitation-system"}]
    }
    mock_ses = MagicMock()
    mock_ses.list_identities.return_value = {"Identities": ["host@example.com"]}
    mock_ses.get_identity_verification_attributes.return_value = {
        "VerificationAttributes": {"host@example.com": {"VerificationStatus": "Success"}}
    }
    mock_apprunner = MagicMock()
    mock_apprunner.list_services.return_value = {
        "ServiceSummaryList": [
            {
                "ServiceName": "prod-event-invitation-app",
                "Status": "RUNNING",
                "ServiceUrl": "prod-app.us-east-1.awsapprunner.com",
            }
        ]
    }

    def client_side_effect(name):
        mapping = {
            "sts": mock_sts,
            "s3": mock_s3,
            "rds": mock_rds,
            "ecr": mock_ecr,
            "ses": mock_ses,
            "apprunner": mock_apprunner,
        }
        return mapping.get(name, MagicMock())

    mock_session.client.side_effect = client_side_effect

    args = MagicMock(region="us-east-1")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        cmd_status(args)
        mock_sts.get_caller_identity.assert_called_once()
        mock_s3.head_bucket.assert_called_once()
        mock_rds.describe_db_instances.assert_called_once()
        mock_ecr.describe_repositories.assert_called_once()
        mock_ses.list_identities.assert_called_once()
        mock_apprunner.list_services.assert_called_once()


def test_cmd_public_url_online():
    from infra.aws_manager import cmd_public_url

    mock_session = MagicMock()
    args = MagicMock(region="us-east-1")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session), \
         patch("infra.aws_manager.get_fargate_public_ip", return_value="54.90.128.233"):
        cmd_public_url(args)


def test_cmd_public_off_success():
    from infra.aws_manager import cmd_public_off

    mock_session = MagicMock()
    mock_ecs = MagicMock()
    mock_session.client.return_value = mock_ecs

    args = MagicMock(region="us-east-1")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session):
        res = cmd_public_off(args)
        assert res is True
        mock_ecs.update_service.assert_called_once_with(
            cluster="event-invitation-cluster",
            service="event-invitation-service",
            desiredCount=0,
        )


def test_cmd_toggle_public_switching():
    from infra.aws_manager import cmd_toggle_public

    mock_session = MagicMock()
    mock_ecs = MagicMock()
    mock_ecs.describe_services.return_value = {"services": [{"desiredCount": 1}]}
    mock_session.client.return_value = mock_ecs

    args = MagicMock(region="us-east-1")
    with patch("infra.aws_manager.get_aws_session", return_value=mock_session), \
         patch("infra.aws_manager.cmd_public_off", return_value=True) as mock_off:
        res = cmd_toggle_public(args)
        assert res is True
        mock_off.assert_called_once()
