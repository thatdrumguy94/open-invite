import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy.exc import IntegrityError
from src.app import db
from src.app.models import User, Event, Guest, Communication


def test_user_password_hashing(app):
    """Test User password hashing and verification."""
    user = User(email="test@example.com", name="Test Host")
    user.set_password("SecretPassword123!")

    assert user.password_hash != "SecretPassword123!"
    assert user.check_password("SecretPassword123!") is True
    assert user.check_password("WrongPassword") is False


def test_user_unique_email_constraint(app):
    """Test that duplicate email addresses are rejected."""
    u1 = User(email="duplicate@example.com", name="User One")
    u1.set_password("pass1")
    db.session.add(u1)
    db.session.commit()

    u2 = User(email="duplicate@example.com", name="User Two")
    u2.set_password("pass2")
    db.session.add(u2)

    with pytest.raises(IntegrityError):
        db.session.commit()
    db.session.rollback()


def test_event_creation_and_rsvp_summary(app):
    """Test Event creation and dynamic rsvp_summary property."""
    host = User(email="event_host@example.com", name="Event Host")
    host.set_password("pass")
    db.session.add(host)
    db.session.commit()

    event = Event(
        organizer_id=host.user_id,
        title="Birthday Bash",
        event_type="Birthday",
        event_date=datetime.now(timezone.utc) + timedelta(days=7),
        location="123 Celebration Lane",
        description="A great birthday party!",
    )
    db.session.add(event)
    db.session.commit()

    # Initial summary with no guests
    assert event.rsvp_summary == {
        "total_invited": 0,
        "accepted": 0,
        "declined": 0,
        "pending": 0,
        "total_attendees": 0,
    }

    # Add guests
    g1 = Guest(
        event_id=event.event_id,
        guest_name="Guest One",
        guest_email="g1@example.com",
        allowed_additional_guests=2,
    )
    g1.submit_rsvp(
        status="Accepted",
        plus_ones=2,
        notes="Excited!",
        additional_guests_data=[
            {"name": "Plus One A", "dietary_notes": "Gluten-Free"},
            {"name": "Plus One B", "dietary_notes": "None"},
        ],
    )

    assert len(g1.additional_attendees) == 2
    assert g1.additional_attendees[0].name == "Plus One A"
    assert g1.additional_attendees[0].dietary_notes == "Gluten-Free"

    g2 = Guest(
        event_id=event.event_id,
        guest_name="Guest Two",
        guest_email="g2@example.com",
    )
    g2.submit_rsvp(status="Declined", notes="Cannot attend")

    g3 = Guest(
        event_id=event.event_id,
        guest_name="Guest Three",
        guest_email="g3@example.com",
    )  # Pending

    db.session.add_all([g1, g2, g3])
    db.session.commit()

    # Verify updated summary
    summary = event.rsvp_summary
    assert summary["total_invited"] == 3
    assert summary["accepted"] == 1
    assert summary["declined"] == 1
    assert summary["pending"] == 1
    assert summary["total_attendees"] == 3  # 1 accepted guest + 2 plus ones


def test_guest_token_generation_and_validation(app):
    """Test that guests receive unique UUID tokens and validate submission."""
    host = User(email="host2@example.com", name="Host 2")
    host.set_password("pass")
    db.session.add(host)
    db.session.commit()

    event = Event(
        organizer_id=host.user_id,
        title="Shower",
        event_type="Baby Shower",
        event_date=datetime.now(timezone.utc) + timedelta(days=5),
        location="Park Pavilion",
    )
    db.session.add(event)
    db.session.commit()

    guest = Guest(
        event_id=event.event_id,
        guest_name="Jane Doe",
        guest_email="jane@example.com",
    )
    db.session.add(guest)
    db.session.commit()

    assert guest.rsvp_token is not None
    assert len(guest.rsvp_token) == 36  # Standard UUID length
    assert guest.rsvp_status == "Pending"

    # Test invalid status raises ValueError
    with pytest.raises(ValueError):
        guest.submit_rsvp("Maybe")


def test_cascade_delete_event(app):
    """Test that deleting an Event cascades to its Guests and Communications."""
    host = User(email="host3@example.com", name="Host 3")
    host.set_password("pass")
    db.session.add(host)
    db.session.commit()

    event = Event(
        organizer_id=host.user_id,
        title="To Be Deleted",
        event_type="Party",
        event_date=datetime.now(timezone.utc) + timedelta(days=2),
        location="Nowhere",
    )
    db.session.add(event)
    db.session.commit()

    guest = Guest(
        event_id=event.event_id,
        guest_name="Temp Guest",
        guest_email="temp@example.com",
    )
    comm = Communication(
        event_id=event.event_id,
        message_type="Invitation",
        subject="Hello",
        body="Body",
        recipients_count=1,
    )
    db.session.add_all([guest, comm])
    db.session.commit()

    event_id = event.event_id
    db.session.delete(event)
    db.session.commit()

    # Verify cascades
    assert Guest.query.filter_by(event_id=event_id).first() is None
    assert Communication.query.filter_by(event_id=event_id).first() is None
