import os
from datetime import datetime, timedelta, timezone
import click
from flask.cli import with_appcontext
from src.app import db
from src.app.models import User, Event, Guest, AdditionalAttendee, Communication
from src.app.services.s3_service import get_storage_service
from src.app.services.pdf_service import PDFService


@click.command("init-db")
@with_appcontext
def init_db_command():
    """Create all database tables."""
    db.create_all()
    click.echo("Initialized database tables.")


@click.command("seed-db")
@with_appcontext
def seed_db_command():
    """Seed sample data for testing and demonstration."""
    db.create_all()

    # Create demo host user if not existing
    host = User.query.filter_by(email="host@example.com").first()
    default_pass = os.environ.get("ADMIN_PASSWORD", "OpenInvite2026!")
    if not host:
        host = User(
            email="host@example.com",
            name="Demo Host",
        )
        host.set_password(default_pass)
        db.session.add(host)
        db.session.commit()
        click.echo(f"Created demo host user: host@example.com (Password: {default_pass})")

    # Create sample event
    sample_event = Event.query.filter_by(title="Annual Community Celebration").first()
    if not sample_event:
        sample_event = Event(
            organizer_id=host.user_id,
            title="Annual Community Celebration",
            event_type="Banquet",
            event_date=datetime.now(timezone.utc) + timedelta(days=14),
            location="Grand Ballroom, Downtown Center",
            description="Welcome to the official launch and celebration!",
            is_custom_pdf=False,
        )
        db.session.add(sample_event)
        db.session.commit()

        # Generate and save actual ReportLab PDF
        storage = get_storage_service()
        pdf_bytes = PDFService.generate_invitation_pdf(
            title=sample_event.title,
            event_type=sample_event.event_type,
            event_date=sample_event.event_date,
            location=sample_event.location,
            host_name=host.name,
            description=sample_event.description,
        )
        saved_key = storage.save_file(
            pdf_bytes, f"events/{sample_event.event_id}/invitation.pdf", content_type="application/pdf"
        )
        sample_event.pdf_storage_path = saved_key
        db.session.commit()
        click.echo(f"Created sample event with generated ReportLab PDF: '{sample_event.title}'")

    # Create sample guests with allowed_additional_guests and attendee details
    if not sample_event.guests:
        # Guests: (name, email, status, allowed_plus_ones, attending_plus_ones, attendees_list, notes)
        guests_data = [
            (
                "Alice Johnson",
                "alice@example.com",
                "Accepted",
                2,  # allowed 2
                1,  # confirmed 1
                [{"name": "Mark Johnson", "dietary_notes": "Vegetarian"}],
                "Looking forward to the event!",
            ),
            (
                "Bob Smith",
                "bob@example.com",
                "Pending",
                1,  # allowed 1
                0,
                [],
                None,
            ),
            (
                "Carol Davis",
                "carol@example.com",
                "Declined",
                2,  # allowed 2
                0,
                [],
                "Sorry, will be out of town.",
            ),
            (
                "David Lee",
                "david@example.com",
                "Accepted",
                0,  # solo invite
                0,
                [],
                "Dietary note: Gluten-Free",
            ),
        ]
        for name, email, status, allowed, plus_ones, attendees, notes in guests_data:
            g = Guest(
                event_id=sample_event.event_id,
                guest_name=name,
                guest_email=email,
                allowed_additional_guests=allowed,
            )
            g.submit_rsvp(
                status=status,
                plus_ones=plus_ones,
                notes=notes,
                additional_guests_data=attendees,
            )
            db.session.add(g)

        # Log an initial communication
        comm = Communication(
            event_id=sample_event.event_id,
            message_type="Invitation",
            subject=f"You're Invited: {sample_event.title}",
            body="We are delighted to invite you to our celebration. Please RSVP using your link.",
            recipients_count=len(guests_data),
        )
        db.session.add(comm)
        db.session.commit()
        click.echo(f"Seeded {len(guests_data)} sample guests with plus-ones and initial communication log.")

    click.echo("Database seeding complete!")
