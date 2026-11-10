from datetime import datetime, timezone
from flask import (
    Blueprint,
    abort,
    flash,
    g,
    redirect,
    url_for,
)
from src.app import db
from src.app.models.communication import Communication
from src.app.models.event import Event
from src.app.routes.auth import login_required
from src.app.services.email_service import get_email_service

communications_bp = Blueprint("communications", __name__, url_prefix="/events")


@communications_bp.route("/<int:event_id>/send-invitations", methods=["POST"])
@login_required
def send_invitations(event_id: int):
    """Dispatch transactional email invitations to all guests on the event roster."""
    event = db.get_or_404(Event, event_id)

    # Authorization guard: organizer can only send communications for their own events
    if event.organizer_id != g.current_user.user_id:
        abort(403)

    if not event.guests:
        flash(
            "No guests on the roster yet! Please add guests or upload a CSV first.",
            "warning",
        )
        return redirect(url_for("events.view_event", event_id=event.event_id))

    email_service = get_email_service()
    pdf_url = url_for(
        "events.download_invitation",
        event_id=event.event_id,
        download=1,
        _external=True,
    )

    sent_count = 0
    failed_count = 0

    for guest in event.guests:
        rsvp_url = url_for(
            "rsvp.guest_rsvp_portal",
            token=guest.rsvp_token,
            _external=True,
        )
        success = email_service.send_invitation(
            guest=guest,
            event=event,
            rsvp_url=rsvp_url,
            pdf_url=pdf_url,
        )
        if success:
            sent_count += 1
        else:
            failed_count += 1

    # Record communication audit log
    comm = Communication(
        event_id=event.event_id,
        message_type="Invitation",
        subject=f"Invitation: {event.title}",
        body=f"Dispatched event invitation emails to {sent_count} guest(s) ({failed_count} failed).",
        sent_at=datetime.now(timezone.utc),
        recipients_count=sent_count,
    )
    db.session.add(comm)
    db.session.commit()

    if failed_count > 0:
        flash(
            f"Dispatched {sent_count} invitation email(s) successfully ({failed_count} failed to send).",
            "warning",
        )
    else:
        flash(
            f"✉️ Successfully dispatched {sent_count} invitation email(s) with personalized RSVP links!",
            "success",
        )

    return redirect(url_for("events.view_event", event_id=event.event_id))


@communications_bp.route("/<int:event_id>/send-reminders", methods=["POST"])
@login_required
def send_reminders(event_id: int):
    """Dispatch RSVP reminders to all guests with 'Pending' status."""
    event = db.get_or_404(Event, event_id)

    # Authorization guard
    if event.organizer_id != g.current_user.user_id:
        abort(403)

    pending_guests = [g for g in event.guests if g.rsvp_status == "Pending"]

    if not pending_guests:
        flash(
            "All invited guests have already responded! There are no pending guests to remind.",
            "info",
        )
        return redirect(url_for("events.view_event", event_id=event.event_id))

    email_service = get_email_service()
    pdf_url = url_for(
        "events.download_invitation",
        event_id=event.event_id,
        download=1,
        _external=True,
    )

    sent_count = 0
    failed_count = 0

    for guest in pending_guests:
        rsvp_url = url_for(
            "rsvp.guest_rsvp_portal",
            token=guest.rsvp_token,
            _external=True,
        )
        success = email_service.send_reminder(
            guest=guest,
            event=event,
            rsvp_url=rsvp_url,
            pdf_url=pdf_url,
        )
        if success:
            sent_count += 1
        else:
            failed_count += 1

    # Record communication audit log
    comm = Communication(
        event_id=event.event_id,
        message_type="Reminder",
        subject=f"Reminder: Please RSVP for {event.title}",
        body=f"Dispatched RSVP reminder emails to {sent_count} pending guest(s) ({failed_count} failed).",
        sent_at=datetime.now(timezone.utc),
        recipients_count=sent_count,
    )
    db.session.add(comm)
    db.session.commit()

    if failed_count > 0:
        flash(
            f"Sent {sent_count} reminder(s) ({failed_count} delivery attempts failed).",
            "warning",
        )
    else:
        flash(
            f"⏰ Successfully dispatched {sent_count} reminder email(s) to pending guests!",
            "success",
        )

    return redirect(url_for("events.view_event", event_id=event.event_id))
