import io
from datetime import datetime, timezone, timedelta
from src.app import db
from src.app.models.user import User
from src.app.models.event import Event
from src.app.models.guest import Guest
from src.app.services.pdf_service import generate_invitation_pdf


def test_auth_registration_and_login(client):
    """Test user registration, login, and logout."""
    # Register
    reg_response = client.post(
        "/auth/register",
        data={
            "name": "Jane Host",
            "email": "jane@example.com",
            "password": "Password123!",
            "confirm_password": "Password123!",
        },
        follow_redirects=True,
    )
    assert reg_response.status_code == 200
    assert b"Welcome to the Event Invitation System" in reg_response.data

    user = User.query.filter_by(email="jane@example.com").first()
    assert user is not None
    assert user.name == "Jane Host"

    # Logout
    logout_response = client.get("/auth/logout", follow_redirects=True)
    assert logout_response.status_code == 200
    assert b"You have been signed out" in logout_response.data

    # Login
    login_response = client.post(
        "/auth/login",
        data={"email": "jane@example.com", "password": "Password123!"},
        follow_redirects=True,
    )
    assert login_response.status_code == 200
    assert b"Welcome back, Jane Host" in login_response.data


def test_login_required_protection(client):
    """Test that protected event routes redirect unauthenticated users to login."""
    response = client.get("/events/")
    assert response.status_code == 302
    assert "/auth/login" in response.headers["Location"]


def test_create_event_auto_pdf(client):
    """Test creating an event with ReportLab auto-generated PDF."""
    # Login host
    user = User(email="autohost@example.com", name="Auto Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    future_date = (datetime.now(timezone.utc) + timedelta(days=10)).strftime("%Y-%m-%dT18:00")

    response = client.post(
        "/events/new",
        data={
            "title": "Baby Shower for Sarah",
            "event_type": "Baby Shower",
            "event_date": future_date,
            "location": "Community Center Room A",
            "description": "Celebrating our baby girl!",
            "invitation_mode": "auto",
        },
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"Baby Shower for Sarah" in response.data

    event = Event.query.filter_by(title="Baby Shower for Sarah").first()
    assert event is not None
    assert event.is_custom_pdf is False
    assert event.pdf_storage_path is not None
    assert "events/" in event.pdf_storage_path


def test_create_event_custom_pdf(client):
    """Test creating an event with custom uploaded PDF."""
    user = User(email="customhost@example.com", name="Custom Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    # Create dummy valid PDF stream
    dummy_pdf = generate_invitation_pdf(
        title="Custom Art",
        event_type="Art Gala",
        event_date=datetime.now(timezone.utc),
        location="Gallery",
    )
    pdf_stream = (io.BytesIO(dummy_pdf), "custom_invite.pdf")

    future_date = (datetime.now(timezone.utc) + timedelta(days=5)).strftime("%Y-%m-%dT19:00")

    response = client.post(
        "/events/new",
        data={
            "title": "Custom Art Gala",
            "event_type": "Other",
            "event_date": future_date,
            "location": "Modern Art Gallery",
            "description": "Exclusive exhibition.",
            "invitation_mode": "custom",
            "custom_pdf": pdf_stream,
        },
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert response.status_code == 200
    assert b"Custom Art Gala" in response.data

    event = Event.query.filter_by(title="Custom Art Gala").first()
    assert event is not None
    assert event.is_custom_pdf is True


def test_guest_manual_add_and_csv_import(client):
    """Test adding single guest and importing bulk CSV."""
    user = User(email="rosterhost@example.com", name="Roster Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    event = Event(
        organizer_id=user.user_id,
        title="Dinner Party",
        event_type="Social Gathering",
        event_date=datetime.now(timezone.utc) + timedelta(days=3),
        location="Host Home",
    )
    db.session.add(event)
    db.session.commit()

    # Manual add guest with allowed additional guests
    add_resp = client.post(
        f"/events/{event.event_id}/guests/add",
        data={
            "guest_name": "Single Guest",
            "guest_email": "single@example.com",
            "allowed_additional_guests": "2",
        },
        follow_redirects=True,
    )
    assert add_resp.status_code == 200
    assert b"Single Guest" in add_resp.data

    single_guest = Guest.query.filter_by(guest_email="single@example.com").first()
    assert single_guest.allowed_additional_guests == 2

    # Bulk CSV import with additional guests column
    csv_data = (
        b"Name,Email,Additional Guests\n"
        b"Charlie Brown,charlie@example.com,1\n"
        b"Lucy Van Pelt,lucy@example.com,3\n"
    )
    csv_stream = (io.BytesIO(csv_data), "guests.csv")

    csv_resp = client.post(
        f"/events/{event.event_id}/guests/upload-csv",
        data={"csv_file": csv_stream},
        follow_redirects=True,
        content_type="multipart/form-data",
    )
    assert csv_resp.status_code == 200
    assert b"Successfully imported 2 guests" in csv_resp.data

    # Verify database
    guests = Guest.query.filter_by(event_id=event.event_id).all()
    assert len(guests) == 3
    emails = {g.guest_email: g.allowed_additional_guests for g in guests}
    assert emails["single@example.com"] == 2
    assert emails["charlie@example.com"] == 1
    assert emails["lucy@example.com"] == 3


def test_pdf_auto_regeneration_on_download(client):
    """Test that downloading an event without a pre-existing PDF automatically builds it on the fly."""
    user = User(email="pdf_regen@example.com", name="Regen Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    event = Event(
        organizer_id=user.user_id,
        title="Regenerate Test Party",
        event_type="Birthday",
        event_date=datetime.now(timezone.utc) + timedelta(days=7),
        location="Banquet Hall",
        pdf_storage_path=None,  # No PDF yet!
        is_custom_pdf=False,
    )
    db.session.add(event)
    db.session.commit()

    # Request download
    resp = client.get(f"/events/{event.event_id}/pdf")
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.data.startswith(b"%PDF-")

    # Verify model was updated with generated storage path
    refreshed = db.session.get(Event, event.event_id)
    assert refreshed.pdf_storage_path is not None
    assert f"events/{event.event_id}/invitation.pdf" in refreshed.pdf_storage_path


def test_explicit_pdf_regeneration(client):
    """Test explicitly regenerating ReportLab PDF via POST /events/<id>/regenerate-pdf."""
    user = User(email="pdf_explicit@example.com", name="Explicit Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    with client.session_transaction() as sess:
        sess["user_id"] = user.user_id
        sess["user_name"] = user.name

    event = Event(
        organizer_id=user.user_id,
        title="Initial Title",
        event_type="Shower",
        event_date=datetime.now(timezone.utc) + timedelta(days=4),
        location="Venue 1",
        is_custom_pdf=False,
    )
    db.session.add(event)
    db.session.commit()

    # Trigger explicit regeneration
    regen_resp = client.post(
        f"/events/{event.event_id}/regenerate-pdf",
        follow_redirects=True,
    )
    assert regen_resp.status_code == 200
    assert b"Invitation PDF regenerated successfully!" in regen_resp.data


def test_public_pdf_access_and_download_disposition(client):
    """Test that invitation PDF is accessible without login, and respects ?download=1."""
    user = User(email="public_pdf@example.com", name="Public Host")
    user.set_password("pass123")
    db.session.add(user)
    db.session.commit()

    event = Event(
        organizer_id=user.user_id,
        title="Public Event",
        event_type="Banquet",
        event_date=datetime.now(timezone.utc) + timedelta(days=2),
        location="Grand Hall",
        is_custom_pdf=False,
    )
    db.session.add(event)
    db.session.commit()

    # Clear any session: public access without authentication
    with client.session_transaction() as sess:
        sess.clear()

    # Inline preview
    resp_inline = client.get(f"/events/{event.event_id}/pdf")
    assert resp_inline.status_code == 200
    assert resp_inline.mimetype == "application/pdf"
    assert "inline" in resp_inline.headers.get("Content-Disposition", "")
    assert resp_inline.data.startswith(b"%PDF-")

    # Download attachment
    resp_download = client.get(f"/events/{event.event_id}/pdf?download=1")
    assert resp_download.status_code == 200
    assert "attachment" in resp_download.headers.get("Content-Disposition", "")

    # Storage route access
    resp_storage = client.get(f"/events/storage/events/{event.event_id}/invitation.pdf")
    assert resp_storage.status_code == 200
    assert resp_storage.data.startswith(b"%PDF-")
