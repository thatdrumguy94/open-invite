import logging
import os
import smtplib
from abc import ABC, abstractmethod
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List, Optional, Tuple
from flask import current_app

logger = logging.getLogger(__name__)


class BaseEmailProvider(ABC):
    """Abstract base class for email delivery providers."""

    @abstractmethod
    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
        sender: Optional[str] = None,
    ) -> bool:
        """Deliver a transactional email. Returns True on success, False on error."""
        pass


class ConsoleEmailProvider(BaseEmailProvider):
    """Local offline provider that logs email details to stdout/logger for testing."""

    def __init__(self):
        self.sent_messages: List[dict] = []

    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
        sender: Optional[str] = None,
    ) -> bool:
        msg = {
            "to_email": to_email,
            "to_name": to_name,
            "sender": sender,
            "subject": subject,
            "html_content": html_content,
            "text_content": text_content,
        }
        self.sent_messages.append(msg)
        print(f"\n[ConsoleEmailProvider] Dispatched email to '{to_name}' <{to_email}>")
        print(f"  Subject: {subject}")
        print(f"  Sender:  {sender}")
        print(f"  Text preview: {text_content[:120]}...\n")
        return True


class SMTPEmailProvider(BaseEmailProvider):
    """Standard SMTP provider (e.g. Mailpit/MailHog on localhost:1025 or AWS SES SMTP)."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1025,
        default_sender: str = "noreply@event-system.local",
    ):
        self.host = host
        self.port = port
        self.default_sender = default_sender

    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
        sender: Optional[str] = None,
    ) -> bool:
        from_address = sender or self.default_sender
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"Event Invitation System <{from_address}>"
        msg["To"] = f"{to_name} <{to_email}>" if to_name else to_email

        part_text = MIMEText(text_content, "plain", "utf-8")
        part_html = MIMEText(html_content, "html", "utf-8")
        msg.attach(part_text)
        msg.attach(part_html)

        try:
            with smtplib.SMTP(self.host, self.port, timeout=5) as server:
                server.sendmail(from_address, [to_email], msg.as_string())
            return True
        except Exception as e:
            logger.error(f"SMTP email dispatch error to {to_email}: {e}")
            return False


class SESEmailProvider(BaseEmailProvider):
    """Amazon SES transactional email provider via Boto3."""

    def __init__(
        self,
        region: str = "us-east-1",
        default_sender: str = "noreply@event-system.local",
    ):
        self.region = region
        self.default_sender = default_sender
        self.ses_client = None

        try:
            import boto3

            self.ses_client = boto3.client("ses", region_name=self.region)
        except Exception as e:
            logger.warning(f"Could not initialize Boto3 SES client: {e}")

    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
        sender: Optional[str] = None,
    ) -> bool:
        if not self.ses_client:
            logger.error("SES client is not configured.")
            return False

        from_address = sender or self.default_sender

        try:
            destination = {"ToAddresses": [to_email]}
            message = {
                "Subject": {"Data": subject, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": text_content, "Charset": "UTF-8"},
                    "Html": {"Data": html_content, "Charset": "UTF-8"},
                },
            }
            self.ses_client.send_email(
                Source=from_address,
                Destination=destination,
                Message=message,
            )
            return True
        except Exception as e:
            logger.error(f"AWS SES dispatch failed for {to_email}: {e}")
            return False


class SendGridEmailProvider(BaseEmailProvider):
    """SendGrid API transactional email provider."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        default_sender: str = "noreply@event-system.local",
    ):
        self.api_key = api_key or os.environ.get("SENDGRID_API_KEY", "")
        self.default_sender = default_sender
        self.sg_client = None

        if self.api_key:
            try:
                from sendgrid import SendGridAPIClient

                self.sg_client = SendGridAPIClient(self.api_key)
            except Exception as e:
                logger.warning(f"Could not initialize SendGrid client: {e}")

    def send_email(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_content: str,
        text_content: str,
        sender: Optional[str] = None,
    ) -> bool:
        if not self.sg_client:
            logger.error("SendGrid API client is not configured or missing API key.")
            return False

        from_address = sender or self.default_sender

        try:
            from sendgrid.helpers.mail import Mail, Email, To, Content

            message = Mail(
                from_email=Email(from_address, "Event Invitation System"),
                to_emails=To(to_email, to_name or to_email),
                subject=subject,
                plain_text_content=Content("text/plain", text_content),
                html_content=Content("text/html", html_content),
            )
            response = self.sg_client.send(message)
            return response.status_code in (200, 201, 202)
        except Exception as e:
            logger.error(f"SendGrid dispatch failed for {to_email}: {e}")
            return False


class EmailService:
    """Service orchestrating email generation, template rendering, and delivery."""

    def __init__(
        self,
        provider: Optional[BaseEmailProvider] = None,
        default_sender: str = "invitations@example.com",
    ):
        self.provider = provider or ConsoleEmailProvider()
        self.default_sender = default_sender

    def build_invitation_content(
        self,
        guest_name: str,
        event_title: str,
        event_type: str,
        event_date_str: str,
        location: str,
        host_name: str,
        rsvp_url: str,
        pdf_url: Optional[str] = None,
        allowed_additional_guests: int = 0,
        description: Optional[str] = None,
    ) -> Tuple[str, str, str]:
        """Generate subject, responsive HTML body, and plaintext fallback for an initial invitation."""
        subject = f"Invitation: {event_title}"

        allowance_text = (
            f"Your invitation includes 1 primary guest plus up to {allowed_additional_guests} additional guest(s)."
            if allowed_additional_guests > 0
            else "This invitation is reserved for 1 guest."
        )

        desc_block_html = ""
        desc_block_text = ""
        if description and description.strip():
            desc_block_html = f"""
            <div style="background-color: #F8FAFC; border-left: 4px solid #0284C7; padding: 12px 16px; margin: 16px 0; border-radius: 4px; font-style: italic; color: #334155;">
              &ldquo;{description.strip()}&rdquo;
            </div>
            """
            desc_block_text = f"\nNote from Host: \"{description.strip()}\"\n"

        pdf_button_html = ""
        pdf_button_text = ""
        if pdf_url:
            pdf_button_html = f"""
            <a href="{pdf_url}" target="_blank" style="display: inline-block; background-color: #0284C7; color: #FFFFFF; font-size: 13px; font-weight: 600; text-decoration: none; padding: 10px 18px; border-radius: 6px; margin-left: 8px;">
              📄 View Invitation PDF
            </a>
            """
            pdf_button_text = f"\nView Invitation PDF: {pdf_url}"

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F1F5F9; margin: 0; padding: 24px 12px; color: #1E293B;">
  <div style="max-width: 600px; margin: 0 auto; background-color: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08); border: 1px solid #E2E8F0;">
    <!-- Top Executive Gradient Accent Bar -->
    <div style="height: 6px; background: linear-gradient(90deg, #0F172A 0%, #1E3A8A 50%, #0284C7 100%);"></div>

    <div style="padding: 32px 28px;">
      <!-- Badge & Title -->
      <div style="text-align: center; margin-bottom: 24px;">
        <span style="display: inline-block; background-color: #EFF6FF; color: #1E3A8A; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; padding: 4px 12px; border-radius: 9999px; margin-bottom: 8px;">
          {event_type}
        </span>
        <h1 style="color: #1E3A8A; font-size: 24px; font-weight: 800; margin: 0 0 6px 0; line-height: 1.25;">
          {event_title}
        </h1>
        <div style="color: #64748B; font-size: 13px;">
          Hosted by <strong style="color: #1E293B;">{host_name}</strong>
        </div>
      </div>

      <!-- Salutation -->
      <p style="font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
        Hello <strong>{guest_name}</strong>,
      </p>
      <p style="font-size: 14px; line-height: 1.6; color: #475569; margin: 0 0 16px 0;">
        You are cordially invited to attend <strong>{event_title}</strong>. Please find the event details below and confirm your attendance at your earliest convenience.
      </p>

      {desc_block_html}

      <!-- Event Details Card -->
      <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
          <tr>
            <td style="padding: 6px 0; color: #64748B; font-weight: 600; width: 110px;">📅 Date & Time:</td>
            <td style="padding: 6px 0; color: #0F172A; font-weight: 700;">{event_date_str}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #64748B; font-weight: 600;">📍 Location:</td>
            <td style="padding: 6px 0; color: #0F172A; font-weight: 600;">{location}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #64748B; font-weight: 600;">👥 Guest Allowance:</td>
            <td style="padding: 6px 0; color: #1E3A8A; font-weight: 600;">{allowance_text}</td>
          </tr>
        </table>
      </div>

      <!-- Call to Action Box -->
      <div style="text-align: center; margin: 28px 0; padding: 20px; background-color: #EFF6FF; border-radius: 8px; border: 1.5px solid #BFDBFE;">
        <div style="font-size: 14px; font-weight: 700; color: #1E3A8A; margin-bottom: 12px;">
          Please let us know if you can make it!
        </div>
        <div style="display: inline-block;">
          <a href="{rsvp_url}" target="_blank" style="display: inline-block; background-color: #1E3A8A; color: #FFFFFF; font-size: 14px; font-weight: 700; text-decoration: none; padding: 11px 24px; border-radius: 6px; box-shadow: 0 2px 4px rgba(30, 58, 138, 0.2);">
            ✉️ Confirm Attendance / RSVP
          </a>
          {pdf_button_html}
        </div>
      </div>

      <p style="font-size: 12px; color: #94A3B8; text-align: center; margin: 24px 0 0 0; line-height: 1.5;">
        If you are unable to click the button above, copy and paste this link into your browser:<br>
        <a href="{rsvp_url}" style="color: #0284C7; word-break: break-all;">{rsvp_url}</a>
      </p>
    </div>

    <!-- Executive Footer -->
    <div style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 14px 20px; text-align: center; font-size: 11px; color: #94A3B8;">
      OpenInvite &bull; Automated Invitation Notification
    </div>
  </div>
</body>
</html>"""

        text_body = f"""INVITATION: {event_title}
Type: {event_type}
Hosted by: {host_name}

Hello {guest_name},

You are cordially invited to attend {event_title}.

Event Details:
- Date & Time: {event_date_str}
- Location: {location}
- Allowance: {allowance_text}
{desc_block_text}
Please confirm your attendance via your personalized RSVP link:
{rsvp_url}
{pdf_button_text}

---
OpenInvite • Automated Invitation Notification
"""
        return subject, html_body, text_body

    def build_reminder_content(
        self,
        guest_name: str,
        event_title: str,
        event_type: str,
        event_date_str: str,
        location: str,
        host_name: str,
        rsvp_url: str,
        pdf_url: Optional[str] = None,
        allowed_additional_guests: int = 0,
    ) -> Tuple[str, str, str]:
        """Generate subject, responsive HTML body, and plaintext fallback for an RSVP reminder."""
        subject = f"Reminder: Please RSVP for {event_title}"

        allowance_text = (
            f"Your invitation includes 1 primary guest plus up to {allowed_additional_guests} additional guest(s)."
            if allowed_additional_guests > 0
            else "This invitation is reserved for 1 guest."
        )

        pdf_button_html = ""
        pdf_button_text = ""
        if pdf_url:
            pdf_button_html = f"""
            <a href="{pdf_url}" target="_blank" style="display: inline-block; background-color: #0284C7; color: #FFFFFF; font-size: 13px; font-weight: 600; text-decoration: none; padding: 10px 18px; border-radius: 6px; margin-left: 8px;">
              📄 View Invitation PDF
            </a>
            """
            pdf_button_text = f"\nView Invitation PDF: {pdf_url}"

        html_body = f"""<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{subject}</title>
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #F1F5F9; margin: 0; padding: 24px 12px; color: #1E293B;">
  <div style="max-width: 600px; margin: 0 auto; background-color: #FFFFFF; border-radius: 12px; overflow: hidden; box-shadow: 0 4px 12px rgba(15, 23, 42, 0.08); border: 1px solid #E2E8F0;">
    <!-- Top Executive Gradient Bar -->
    <div style="height: 6px; background: linear-gradient(90deg, #D97706 0%, #EA580C 50%, #DC2626 100%);"></div>

    <div style="padding: 32px 28px;">
      <!-- Reminder Badge & Title -->
      <div style="text-align: center; margin-bottom: 24px;">
        <span style="display: inline-block; background-color: #FEF3C7; color: #92400E; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; padding: 4px 12px; border-radius: 9999px; margin-bottom: 8px;">
          ⏰ RSVP Reminder
        </span>
        <h1 style="color: #1E3A8A; font-size: 24px; font-weight: 800; margin: 0 0 6px 0; line-height: 1.25;">
          {event_title}
        </h1>
        <div style="color: #64748B; font-size: 13px;">
          Hosted by <strong style="color: #1E293B;">{host_name}</strong>
        </div>
      </div>

      <p style="font-size: 15px; line-height: 1.6; margin: 0 0 16px 0;">
        Hello <strong>{guest_name}</strong>,
      </p>
      <p style="font-size: 14px; line-height: 1.6; color: #475569; margin: 0 0 16px 0;">
        We are finalizing our guest count for <strong>{event_title}</strong> and haven&rsquo;t received your response yet. Please take a moment to let us know if you will be attending.
      </p>

      <!-- Details Summary -->
      <div style="background-color: #F8FAFC; border: 1px solid #E2E8F0; border-radius: 8px; padding: 16px; margin: 20px 0;">
        <table style="width: 100%; border-collapse: collapse; font-size: 14px;">
          <tr>
            <td style="padding: 6px 0; color: #64748B; font-weight: 600; width: 110px;">📅 Date & Time:</td>
            <td style="padding: 6px 0; color: #0F172A; font-weight: 700;">{event_date_str}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #64748B; font-weight: 600;">📍 Location:</td>
            <td style="padding: 6px 0; color: #0F172A; font-weight: 600;">{location}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; color: #64748B; font-weight: 600;">👥 Allowance:</td>
            <td style="padding: 6px 0; color: #1E3A8A; font-weight: 600;">{allowance_text}</td>
          </tr>
        </table>
      </div>

      <!-- Action Box -->
      <div style="text-align: center; margin: 28px 0; padding: 20px; background-color: #FFFBEB; border-radius: 8px; border: 1.5px solid #FDE68A;">
        <div style="font-size: 14px; font-weight: 700; color: #92400E; margin-bottom: 12px;">
          Kindly confirm your attendance today
        </div>
        <div style="display: inline-block;">
          <a href="{rsvp_url}" target="_blank" style="display: inline-block; background-color: #D97706; color: #FFFFFF; font-size: 14px; font-weight: 700; text-decoration: none; padding: 11px 24px; border-radius: 6px; box-shadow: 0 2px 4px rgba(217, 119, 6, 0.2);">
            ✉️ Submit Your RSVP Now
          </a>
          {pdf_button_html}
        </div>
      </div>

      <p style="font-size: 12px; color: #94A3B8; text-align: center; margin: 24px 0 0 0; line-height: 1.5;">
        Link: <a href="{rsvp_url}" style="color: #0284C7; word-break: break-all;">{rsvp_url}</a>
      </p>
    </div>

    <!-- Executive Footer -->
    <div style="background-color: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 14px 20px; text-align: center; font-size: 11px; color: #94A3B8;">
      OpenInvite &bull; Automated Invitation Notification
    </div>
  </div>
</body>
</html>"""

        text_body = f"""REMINDER: PLEASE RSVP FOR {event_title}
Type: {event_type}
Hosted by: {host_name}

Hello {guest_name},

We are finalizing our guest count for {event_title} and haven't received your response yet.

Event Details:
- Date & Time: {event_date_str}
- Location: {location}
- Allowance: {allowance_text}

Please submit your RSVP response via your personalized link:
{rsvp_url}
{pdf_button_text}

---
OpenInvite • Automated Invitation Notification
"""
        return subject, html_body, text_body

    def send_invitation(
        self,
        guest,
        event,
        rsvp_url: str,
        pdf_url: Optional[str] = None,
    ) -> bool:
        """Render and deliver an initial event invitation email to a single guest."""
        formatted_date = (
            event.event_date.strftime("%A, %B %d, %Y at %I:%M %p")
            if hasattr(event.event_date, "strftime")
            else str(event.event_date)
        )
        host_name = event.organizer.name if event.organizer else "Event Host"

        subject, html_body, text_body = self.build_invitation_content(
            guest_name=guest.guest_name,
            event_title=event.title,
            event_type=event.event_type,
            event_date_str=formatted_date,
            location=event.location,
            host_name=host_name,
            rsvp_url=rsvp_url,
            pdf_url=pdf_url,
            allowed_additional_guests=guest.allowed_additional_guests,
            description=event.description,
        )

        return self.provider.send_email(
            to_email=guest.guest_email,
            to_name=guest.guest_name,
            subject=subject,
            html_content=html_body,
            text_content=text_body,
            sender=self.default_sender,
        )

    def send_reminder(
        self,
        guest,
        event,
        rsvp_url: str,
        pdf_url: Optional[str] = None,
    ) -> bool:
        """Render and deliver an RSVP reminder email to a single guest."""
        formatted_date = (
            event.event_date.strftime("%A, %B %d, %Y at %I:%M %p")
            if hasattr(event.event_date, "strftime")
            else str(event.event_date)
        )
        host_name = event.organizer.name if event.organizer else "Event Host"

        subject, html_body, text_body = self.build_reminder_content(
            guest_name=guest.guest_name,
            event_title=event.title,
            event_type=event.event_type,
            event_date_str=formatted_date,
            location=event.location,
            host_name=host_name,
            rsvp_url=rsvp_url,
            pdf_url=pdf_url,
            allowed_additional_guests=guest.allowed_additional_guests,
        )

        return self.provider.send_email(
            to_email=guest.guest_email,
            to_name=guest.guest_name,
            subject=subject,
            html_content=html_body,
            text_content=text_body,
            sender=self.default_sender,
        )


def get_email_service() -> EmailService:
    """Factory helper creating configured EmailService from Flask app context or env."""
    provider_type = "console"
    default_sender = "invitations@example.com"
    smtp_host = "localhost"
    smtp_port = 1025
    region = "us-east-1"
    sendgrid_key = None

    if current_app:
        provider_type = current_app.config.get("EMAIL_PROVIDER", "console").lower()
        default_sender = current_app.config.get(
            "MAIL_DEFAULT_SENDER", "invitations@example.com"
        )
        smtp_host = current_app.config.get("SMTP_HOST", "localhost")
        smtp_port = int(current_app.config.get("SMTP_PORT", 1025))
        region = current_app.config.get("AWS_REGION", "us-east-1")
        sendgrid_key = current_app.config.get("SENDGRID_API_KEY")
    else:
        provider_type = os.environ.get("EMAIL_PROVIDER", "console").lower()
        default_sender = os.environ.get(
            "MAIL_DEFAULT_SENDER", "invitations@example.com"
        )
        smtp_host = os.environ.get("SMTP_HOST", "localhost")
        smtp_port = int(os.environ.get("SMTP_PORT", 1025))
        region = os.environ.get("AWS_REGION", "us-east-1")
        sendgrid_key = os.environ.get("SENDGRID_API_KEY")

    if provider_type == "smtp":
        provider = SMTPEmailProvider(
            host=smtp_host, port=smtp_port, default_sender=default_sender
        )
    elif provider_type == "ses":
        provider = SESEmailProvider(region=region, default_sender=default_sender)
    elif provider_type == "sendgrid":
        provider = SendGridEmailProvider(
            api_key=sendgrid_key, default_sender=default_sender
        )
    else:
        provider = ConsoleEmailProvider()

    return EmailService(provider=provider, default_sender=default_sender)
