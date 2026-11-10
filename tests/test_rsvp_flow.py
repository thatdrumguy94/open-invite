from datetime import datetime, timezone, timedelta
from src.app import db
from src.app.models.user import User
from src.app.models.event import Event
from src.app.models.guest import Guest


def test_public_rsvp_portal_view(client):
    """Test loading the public RSVP portal for an invited guest."""
    host = User(email="rsvphost@example.com", name="Host User")
    host.set_password("pass123")
    db.session.add(host)
    db.session.commit()

    event = Event(
        organizer_id=host.user_id,
        title="Family Reunion",
        event_type="Social Gathering",
        event_date=datetime.now(timezone.utc) + timedelta(days=14),
        location="Lake Pavilion",
        description="Annual family reunion and barbecue.",
    )
    db.session.add(event)
    db.session.commit()

    guest = Guest(
        event_id=event.event_id,
        guest_name="Sarah Connor",
        guest_email="sarah@example.com",
        allowed_additional_guests=3,
    )
    db.session.add(guest)
    db.session.commit()

    # GET request to public RSVP token URL
    response = client.get(f"/rsvp/{guest.rsvp_token}")
    assert response.status_code == 200
    assert b"Family Reunion" in response.data
    assert b"Sarah Connor" in response.data
    assert b"3 additional guest(s)" in response.data


def test_submit_rsvp_accepted_with_attendees(client):
    """Test submitting RSVP with additional attendees and dietary details."""
    host = User(email="host_attendee@example.com", name="Host")
    host.set_password("pass123")
    db.session.add(host)
    db.session.commit()

    event = Event(
        organizer_id=host.user_id,
        title="Wedding Reception",
        event_type="Wedding",
        event_date=datetime.now(timezone.utc) + timedelta(days=30),
        location="Sunset Gardens",
    )
    db.session.add(event)
    db.session.commit()

    guest = Guest(
        event_id=event.event_id,
        guest_name="Michael Scott",
        guest_email="michael@example.com",
        allowed_additional_guests=2,
    )
    db.session.add(guest)
    db.session.commit()

    # POST response with 2 additional guests
    post_data = {
        "status": "Accepted",
        "plus_ones": "2",
        "additional_name_1": "Holly Flax",
        "additional_diet_1": "Vegetarian",
        "additional_name_2": "Dwight Schrute",
        "additional_diet_2": "Gluten-Free / Beets Only",
        "notes": "Thrilled to celebrate!",
    }

    response = client.post(f"/rsvp/{guest.rsvp_token}", data=post_data, follow_redirects=True)
    assert response.status_code == 200
    assert b"confirmed for 3 attendee(s)" in response.data

    # Verify database persistence
    refreshed_guest = db.session.get(Guest, guest.guest_id)
    assert refreshed_guest.rsvp_status == "Accepted"
    assert refreshed_guest.plus_ones == 2
    assert len(refreshed_guest.additional_attendees) == 2

    att_names = {a.name: a.dietary_notes for a in refreshed_guest.additional_attendees}
    assert "Holly Flax" in att_names
    assert att_names["Holly Flax"] == "Vegetarian"
    assert "Dwight Schrute" in att_names
    assert "Gluten-Free / Beets Only" in att_names["Dwight Schrute"]

    # Verify event summary counts 1 primary + 2 plus-ones = 3 total attendees
    assert event.rsvp_summary["total_attendees"] == 3


def test_submit_rsvp_declined_clears_attendees(client):
    """Test that declining RSVP clears plus ones and attendees."""
    host = User(email="host_decline@example.com", name="Host")
    host.set_password("pass123")
    db.session.add(host)
    db.session.commit()

    event = Event(
        organizer_id=host.user_id,
        title="Dinner",
        event_type="Banquet",
        event_date=datetime.now(timezone.utc) + timedelta(days=7),
        location="Club",
    )
    db.session.add(event)
    db.session.commit()

    guest = Guest(
        event_id=event.event_id,
        guest_name="Jim Halpert",
        guest_email="jim@example.com",
        allowed_additional_guests=1,
    )
    # Initially accepted
    guest.submit_rsvp("Accepted", plus_ones=1, additional_guests_data=[{"name": "Pam Beesly"}])
    db.session.add(guest)
    db.session.commit()

    assert len(guest.additional_attendees) == 1

    # Now declines via portal
    response = client.post(
        f"/rsvp/{guest.rsvp_token}",
        data={"status": "Declined", "notes": "Conflict with work"},
        follow_redirects=True,
    )
    assert response.status_code == 200
    assert b"decline has been recorded" in response.data

    refreshed_guest = db.session.get(Guest, guest.guest_id)
    assert refreshed_guest.rsvp_status == "Declined"
    assert refreshed_guest.plus_ones == 0
    assert len(refreshed_guest.additional_attendees) == 0


def test_plus_ones_strictly_enforces_host_limit(client):
    """Test that a guest cannot exceed the host-defined additional guest allowance."""
    host = User(email="host_limit@example.com", name="Host")
    host.set_password("pass123")
    db.session.add(host)
    db.session.commit()

    event = Event(
        organizer_id=host.user_id,
        title="Strict Event",
        event_type="Party",
        event_date=datetime.now(timezone.utc) + timedelta(days=2),
        location="Hall",
    )
    db.session.add(event)
    db.session.commit()

    guest = Guest(
        event_id=event.event_id,
        guest_name="Solo Invitee",
        guest_email="solo@example.com",
        allowed_additional_guests=1,  # Only allows 1 additional guest
    )
    db.session.add(guest)
    db.session.commit()

    # Attempt to submit 5 plus ones
    post_data = {
        "status": "Accepted",
        "plus_ones": "5",
        "additional_name_1": "Guest A",
        "additional_name_2": "Guest B",
        "additional_name_3": "Guest C",
    }
    client.post(f"/rsvp/{guest.rsvp_token}", data=post_data, follow_redirects=True)

    refreshed = db.session.get(Guest, guest.guest_id)
    # Strictly clamped at 1
    assert refreshed.plus_ones == 1
    assert len(refreshed.additional_attendees) == 1
    assert refreshed.additional_attendees[0].name == "Guest A"
