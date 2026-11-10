from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch
import pytest
from src.app import db
from src.app.models.communication import Communication
from src.app.models.event import Event
from src.app.models.guest import Guest
from src.app.models.user import User
from src.app.services.email_service import (
    ConsoleEmailProvider,
    EmailService,
    SESEmailProvider,
    SMTPEmailProvider,
    SendGridEmailProvider,
    get_email_service,
)


def test_console_email_provider():
    """Test ConsoleEmailProvider records sent messages."""
    provider = ConsoleEmailProvider()
    success = provider.send_email(
        to_email="test@example.com",
        to_name="Test User",
        subject="Test Subject",
        html_content="<p>Hello World</p>",
        text_content="Hello World",
        sender="noreply@example.com",
    )
    assert success is True
    assert len(provider.sent_messages) == 1
    assert provider.sent_messages[0]["to_email"] == "test@example.com"
    assert provider.sent_messages[0]["subject"] == "Test Subject"


def test_smtp_email_provider_mock():
    """Test SMTPEmailProvider sends MIME message via smtplib."""
    provider = SMTPEmailProvider(host="localhost", port=1025)

    with patch("smtplib.SMTP") as mock_smtp:
        mock_instance = MagicMock()
        mock_smtp.return_value.__enter__.return_value = mock_instance

        success = provider.send_email(
            to_email="guest@example.com",
            to_name="Guest User",
            subject="Event Invite",
            html_content="<b>You are invited!</b>",
            text_content="You are invited!",
        )

        assert success is True
        assert mock_instance.sendmail.called
        call_args = mock_instance.sendmail.call_args[0]
        # Sender, Recipient, Message data
        assert call_args[0] == "noreply@event-system.local"
        assert call_args[1] == ["guest@example.com"]
        assert "Subject: Event Invite" in call_args[2]


def test_ses_email_provider_mock():
    """Test SESEmailProvider dispatches via boto3 ses client."""
    provider = SESEmailProvider(region="us-east-1", default_sender="sender@example.com")
    mock_ses = MagicMock()
    provider.ses_client = mock_ses

    success = provider.send_email(
        to_email="ses_guest@example.com",
        to_name="SES Guest",
        subject="SES Invitation",
        html_content="<p>Join us</p>",
        text_content="Join us",
    )

    assert success is True
    assert mock_ses.send_email.called
    kwargs = mock_ses.send_email.call_args[1]
    assert kwargs["Source"] == "sender@example.com"
    assert kwargs["Destination"]["ToAddresses"] == ["ses_guest@example.com"]
    assert kwargs["Message"]["Subject"]["Data"] == "SES Invitation"


def test_sendgrid_email_provider_mock():
    """Test SendGridEmailProvider dispatches via SendGrid client."""
    provider = SendGridEmailProvider(api_key="SG.fake_key_for_testing", default_sender="sg@example.com")
    mock_sg = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 202
    mock_sg.send.return_value = mock_resp
    provider.sg_client = mock_sg

    success = provider.send_email(
        to_email="sg_guest@example.com",
        to_name="SG Guest",
        subject="SendGrid Invite",
        html_content="<p>Welcome</p>",
        text_content="Welcome",
    )

    assert success is True
    assert mock_sg.send.called


def test_email_service_content_builders():
    """Test HTML and text content generation for invitations and reminders."""
    service = EmailService()

    # 1. Invitation content
    subj, html, text = service.build_invitation_content(
        guest_name="Sarah Connor",
        event_title="Tech Symposium 2026",
        event_type="Banquet",
        event_date_str="Monday, Nov 16, 2026 at 6:00 PM",
        location="Civic Center",
        host_name="John Connor",
        rsvp_url="https://example.com/rsvp/token-123",
        pdf_url="https://example.com/events/1/pdf",
        allowed_additional_guests=2,
        description="Keynote discussions on cloud architectures.",
    )

    assert "Tech Symposium 2026" in subj
    assert "Sarah Connor" in html
    assert "Tech Symposium 2026" in html
    assert "Keynote discussions on cloud architectures." in html
    assert "https://example.com/rsvp/token-123" in html
    assert "https://example.com/events/1/pdf" in html
    assert "up to 2 additional guest(s)" in html
    assert "https://example.com/rsvp/token-123" in text

    # 2. Reminder content
    r_subj, r_html, r_text = service.build_reminder_content(
        guest_name="Sarah Connor",
        event_title="Tech Symposium 2026",
        event_type="Banquet",
        event_date_str="Monday, Nov 16, 2026 at 6:00 PM",
        location="Civic Center",
        host_name="John Connor",
        rsvp_url="https://example.com/rsvp/token-123",
        pdf_url="https://example.com/events/1/pdf",
        allowed_additional_guests=2,
    )

    assert "Reminder" in r_subj
    assert "haven’t received your response" in r_html or "haven&rsquo;t received your response" in r_html
    assert "https://example.com/rsvp/token-123" in r_html


def test_send_invitations_route_full_workflow(client):
    """Test host triggering invitation emails to all rostered guests."""
    # Setup host and event
    user = User(email="comm_host@example.com", name="Communications Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    event = Event(
        organizer_id=user.user_id,
        title="Gala Dinner",
        event_type="Banquet",
        event_date=datetime.now(timezone.utc) + timedelta(days=5),
        location="Skyline Lounge",
        is_custom_pdf=False,
    )
    db.session.add(event)
    db.session.commit()

    # Add 3 guests
    g1 = Guest(event_id=event.event_id, guest_name="Guest One", guest_email="one@example.com")
    g2 = Guest(event_id=event.event_id, guest_name="Guest Two", guest_email="two@example.com")
    g3 = Guest(event_id=event.event_id, guest_name="Guest Three", guest_email="three@example.com")
    db.session.add_all([g1, g2, g3])
    db.session.commit()

    # Authenticate host
    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    # Post send-invitations
    resp = client.post(f"/events/{event.event_id}/send-invitations", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Successfully dispatched 3 invitation email(s)" in resp.data

    # Verify Communication table entry
    comms = Communication.query.filter_by(event_id=event.event_id).all()
    assert len(comms) == 1
    assert comms[0].message_type == "Invitation"
    assert comms[0].recipients_count == 3
    assert "Gala Dinner" in comms[0].subject

    # Verify detail page displays communication log
    detail_resp = client.get(f"/events/{event.event_id}")
    assert b"Communications History &amp; Audit Log" in detail_resp.data or b"Communications History & Audit Log" in detail_resp.data
    assert b"Invitation: Gala Dinner" in detail_resp.data


def test_send_reminders_route_only_pending_guests(client):
    """Test host sending reminders only targets guests with 'Pending' status."""
    user = User(email="remind_host@example.com", name="Reminder Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    event = Event(
        organizer_id=user.user_id,
        title="Birthday Bash",
        event_type="Birthday",
        event_date=datetime.now(timezone.utc) + timedelta(days=3),
        location="Park Pavilion",
        is_custom_pdf=False,
    )
    db.session.add(event)
    db.session.commit()

    # 1 Accepted, 1 Declined, 2 Pending
    g_acc = Guest(event_id=event.event_id, guest_name="Accepted Guest", guest_email="acc@example.com", rsvp_status="Accepted")
    g_dec = Guest(event_id=event.event_id, guest_name="Declined Guest", guest_email="dec@example.com", rsvp_status="Declined")
    g_pend1 = Guest(event_id=event.event_id, guest_name="Pending 1", guest_email="p1@example.com", rsvp_status="Pending")
    g_pend2 = Guest(event_id=event.event_id, guest_name="Pending 2", guest_email="p2@example.com", rsvp_status="Pending")
    db.session.add_all([g_acc, g_dec, g_pend1, g_pend2])
    db.session.commit()

    # Authenticate host
    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    # Post send-reminders
    resp = client.post(f"/events/{event.event_id}/send-reminders", follow_redirects=True)
    assert resp.status_code == 200
    assert b"Successfully dispatched 2 reminder email(s) to pending guests" in resp.data

    # Verify audit record
    reminder_comm = Communication.query.filter_by(event_id=event.event_id, message_type="Reminder").first()
    assert reminder_comm is not None
    assert reminder_comm.recipients_count == 2
    assert "Reminder: Please RSVP for Birthday Bash" in reminder_comm.subject


def test_send_reminders_when_no_pending_guests(client):
    """Test that reminder dispatch informs host when all guests have already responded."""
    user = User(email="all_done@example.com", name="Done Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    event = Event(
        organizer_id=user.user_id,
        title="Completed Event",
        event_type="Party",
        event_date=datetime.now(timezone.utc) + timedelta(days=1),
        location="Restaurant",
    )
    db.session.add(event)
    db.session.commit()

    g1 = Guest(event_id=event.event_id, guest_name="Responded", guest_email="resp@example.com", rsvp_status="Accepted")
    db.session.add(g1)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    resp = client.post(f"/events/{event.event_id}/send-reminders", follow_redirects=True)
    assert resp.status_code == 200
    assert b"All invited guests have already responded" in resp.data
