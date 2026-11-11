import os
import stat
import subprocess
from datetime import datetime, timedelta, timezone
from src.app import db
from src.app.config import ProductionConfig
from src.app.models.event import Event
from src.app.models.guest import Guest
from src.app.models.user import User
from src.app.services.email_service import ConsoleEmailProvider, EmailService
from src.app.tls import ensure_self_signed_cert


def test_production_config_https_defaults():
    """ProductionConfig defaults to enforced HTTPS and secure cookies."""
    assert ProductionConfig.FORCE_HTTPS is True
    assert ProductionConfig.PREFERRED_URL_SCHEME == "https"
    assert ProductionConfig.SESSION_COOKIE_SECURE is True
    assert ProductionConfig.SESSION_COOKIE_HTTPONLY is True
    assert ProductionConfig.TRUST_PROXY_HEADERS is True


def test_testing_config_http_defaults(app):
    """TestingConfig keeps HTTPS redirect disabled by default for local test execution."""
    assert app.config["FORCE_HTTPS"] is False
    assert app.config["PREFERRED_URL_SCHEME"] == "http"
    assert app.config["SESSION_COOKIE_SECURE"] is False


def test_https_redirect_enforced_for_http_requests(app, client):
    """Plain HTTP requests redirect to HTTPS when FORCE_HTTPS is enabled."""
    app.config["FORCE_HTTPS"] = True

    get_resp = client.get("/events/", base_url="http://openinvite.example.com")
    assert get_resp.status_code == 301
    assert get_resp.headers["Location"] == "https://openinvite.example.com/events/"

    post_resp = client.post("/auth/login", base_url="http://openinvite.example.com")
    assert post_resp.status_code == 308
    assert post_resp.headers["Location"] == "https://openinvite.example.com/auth/login"


def test_health_endpoint_exempt_from_https_redirect(app, client):
    """/health stays accessible over plain HTTP for container, ALB, and App Runner probes."""
    app.config["FORCE_HTTPS"] = True

    resp = client.get("/health", base_url="http://localhost:5000")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["status"] == "ok"
    assert data["https_enforced"] is True
    assert data["scheme"] == "http"


def test_proxy_fix_x_forwarded_proto_https_and_headers(app, client):
    """ProxyFix recognizes X-Forwarded-Proto: https, generates https URLs, and emits HSTS."""
    app.config["FORCE_HTTPS"] = True

    headers = {
        "X-Forwarded-Proto": "https",
        "X-Forwarded-Host": "invite.example.com",
        "X-Forwarded-For": "203.0.113.10",
    }
    resp = client.get("/", headers=headers)
    assert resp.status_code == 200
    assert resp.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
    assert resp.headers["X-Content-Type-Options"] == "nosniff"
    assert resp.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert resp.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    # Protected route redirect through ProxyFix uses https:// and X-Forwarded-Host
    protected_resp = client.get("/events/", headers=headers)
    assert protected_resp.status_code == 302
    assert (
        protected_resp.headers["Location"]
        == "/auth/login?next=https://invite.example.com/events/"
    )


def test_cloudfront_forwarded_proto_normalized(app, client):
    """CloudFront-Forwarded-Proto: https overrides internal HTTP ALB X-Forwarded-Proto/Port."""
    app.config["FORCE_HTTPS"] = True

    cf_headers = {
        "CloudFront-Forwarded-Proto": "https",
        "X-Forwarded-Proto": "http",
        "X-Forwarded-Port": "80",
        "Host": "d123456.cloudfront.net",
    }
    resp = client.get("/", headers=cf_headers)
    assert resp.status_code == 200
    assert "Strict-Transport-Security" in resp.headers

    protected_resp = client.get("/events/", headers=cf_headers)
    assert protected_resp.status_code == 302
    assert (
        protected_resp.headers["Location"]
        == "/auth/login?next=https://d123456.cloudfront.net/events/"
    )


def test_hsts_not_emitted_over_plain_http(app, client):
    """HSTS must not be emitted over plain HTTP connections."""
    app.config["FORCE_HTTPS"] = False

    resp = client.get("/")
    assert resp.status_code == 200
    assert "Strict-Transport-Security" not in resp.headers
    assert resp.headers["X-Content-Type-Options"] == "nosniff"


def test_secure_session_cookie_attribute(app, client):
    """Session cookies include Secure and HttpOnly when SESSION_COOKIE_SECURE is enabled."""
    app.config["FORCE_HTTPS"] = True
    app.config["SESSION_COOKIE_SECURE"] = True

    user = User(email="cookiehost@example.com", name="Cookie Host")
    user.set_password("SecurePass123!")
    db.session.add(user)
    db.session.commit()

    resp = client.post(
        "/auth/login",
        data={"email": "cookiehost@example.com", "password": "SecurePass123!"},
        headers={"X-Forwarded-Proto": "https", "Host": "invite.example.com"},
    )
    assert resp.status_code == 302
    set_cookie_headers = resp.headers.getlist("Set-Cookie")
    assert set_cookie_headers
    session_cookie = set_cookie_headers[0]
    assert "Secure" in session_cookie
    assert "HttpOnly" in session_cookie


def test_email_dispatch_generates_https_links_behind_proxy(app, client, monkeypatch):
    """Invitation emails sent behind HTTPS proxy contain https:// RSVP and PDF links."""
    app.config["FORCE_HTTPS"] = True

    user = User(email="https_mail@example.com", name="HTTPS Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    event = Event(
        organizer_id=user.user_id,
        title="TLS Gala",
        event_type="Banquet",
        event_date=datetime.now(timezone.utc) + timedelta(days=5),
        location="Cloud Center",
    )
    db.session.add(event)
    db.session.commit()

    guest = Guest(
        event_id=event.event_id,
        guest_name="Alice HTTPS",
        guest_email="alice_https@example.com",
    )
    db.session.add(guest)
    db.session.commit()

    console_provider = ConsoleEmailProvider()
    email_svc = EmailService(provider=console_provider)
    monkeypatch.setattr("src.app.routes.communications.get_email_service", lambda: email_svc)

    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    resp = client.post(
        f"/events/{event.event_id}/send-invitations",
        headers={
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": "events.example.com",
        },
    )
    assert resp.status_code == 302
    assert len(console_provider.sent_messages) == 1
    body_text = console_provider.sent_messages[0]["text_content"]
    assert f"https://events.example.com/rsvp/{guest.rsvp_token}" in body_text
    assert f"https://events.example.com/events/{event.event_id}/pdf?download=1" in body_text


def test_ensure_self_signed_cert_generates_valid_x509(tmp_path):
    """ensure_self_signed_cert creates a valid RSA X.509 cert with SANs and reuses it."""
    cert_path, key_path = ensure_self_signed_cert(tmp_path, common_name="openinvite.local")

    assert os.path.exists(cert_path)
    assert os.path.exists(key_path)
    assert stat.S_IMODE(os.stat(key_path).st_mode) == 0o600

    cert_text = subprocess.check_output(
        ["openssl", "x509", "-in", cert_path, "-noout", "-text"],
        text=True,
    )
    assert "Subject:" in cert_text
    assert "openinvite.local" in cert_text
    assert "DNS:localhost" in cert_text
    assert "IP Address:127.0.0.1" in cert_text

    # Calling again returns existing cert/key without regenerating
    mtime_before = os.stat(cert_path).st_mtime_ns
    cert_path_2, key_path_2 = ensure_self_signed_cert(tmp_path, common_name="openinvite.local")
    assert cert_path_2 == cert_path
    assert key_path_2 == key_path
    assert os.stat(cert_path).st_mtime_ns == mtime_before
