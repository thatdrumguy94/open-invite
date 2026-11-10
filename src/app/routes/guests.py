import csv
import io
import re
from flask import (
    Blueprint,
    request,
    redirect,
    url_for,
    flash,
    g,
    abort,
)
from src.app import db
from src.app.models.event import Event
from src.app.models.guest import Guest
from src.app.routes.auth import login_required

guests_bp = Blueprint("guests", __name__, url_prefix="/events/<int:event_id>/guests")

EMAIL_REGEX = re.compile(r"^[^@]+@[^@]+\.[^@]+$")


def get_authorized_event(event_id: int) -> Event:
    """Helper to ensure the event exists and belongs to the currently authenticated host."""
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != g.current_user.user_id:
        abort(403)
    return event


@guests_bp.route("/add", methods=["POST"])
@login_required
def add_guest(event_id: int):
    """Add a single guest manually to the event roster with host-defined allowed additional guests."""
    event = get_authorized_event(event_id)

    name = request.form.get("guest_name", "").strip()
    email = request.form.get("guest_email", "").strip().lower()
    try:
        allowed_additional = max(0, int(request.form.get("allowed_additional_guests", 0)))
    except (ValueError, TypeError):
        allowed_additional = 0

    if not name or not email:
        flash("Guest name and email address are required.", "danger")
        return redirect(url_for("events.view_event", event_id=event.event_id))

    if not EMAIL_REGEX.match(email):
        flash(f"Invalid email address: '{email}'", "danger")
        return redirect(url_for("events.view_event", event_id=event.event_id))

    # Check for existing guest in this event
    existing = Guest.query.filter_by(event_id=event.event_id, guest_email=email).first()
    if existing:
        flash(f"Guest with email '{email}' is already on the guest list.", "warning")
        return redirect(url_for("events.view_event", event_id=event.event_id))

    guest = Guest(
        event_id=event.event_id,
        guest_name=name,
        guest_email=email,
        allowed_additional_guests=allowed_additional,
    )
    db.session.add(guest)
    db.session.commit()

    flash(
        f"Added guest '{guest.guest_name}' (Allowed additional guests: {allowed_additional}).",
        "success",
    )
    return redirect(url_for("events.view_event", event_id=event.event_id))


@guests_bp.route("/upload-csv", methods=["POST"])
@login_required
def upload_csv(event_id: int):
    """
    Bulk import guests via CSV file upload.
    Expects columns: Name, Email, and optional Additional Guests / Plus Ones.
    """
    event = get_authorized_event(event_id)

    uploaded_file = request.files.get("csv_file")
    if not uploaded_file or uploaded_file.filename == "":
        flash("Please select a CSV file to upload.", "danger")
        return redirect(url_for("events.view_event", event_id=event.event_id))

    try:
        content = uploaded_file.stream.read().decode("utf-8-sig")
        reader = csv.reader(io.StringIO(content))
        rows = list(reader)

        if not rows:
            flash("The uploaded CSV file is empty.", "warning")
            return redirect(url_for("events.view_event", event_id=event.event_id))

        # Identify header indices
        header = [col.strip().lower() for col in rows[0]]
        name_idx = None
        email_idx = None
        allowed_idx = None

        for idx, raw_col in enumerate(header):
            col = raw_col.strip().lower().replace(" ", "_").replace("-", "_")
            if col in ("name", "guest_name", "full_name"):
                name_idx = idx
            elif col in ("email", "guest_email", "email_address"):
                email_idx = idx
            elif col in (
                "additional_guests",
                "additional_guest",
                "plus_ones",
                "plus_one",
                "additional_guests_allowed",
                "plus_ones_allowed",
                "allowed_additional_guests",
            ):
                allowed_idx = idx

        # Default fallback to col 0 = name, col 1 = email if header row contains actual email
        if name_idx is None or email_idx is None:
            if len(header) >= 2 and "@" in header[1]:
                name_idx, email_idx = 0, 1
                data_rows = rows  # Header was actually the first data row
            else:
                flash(
                    "CSV must contain 'Name' and 'Email' columns in the header (optional: 'Additional Guests').",
                    "danger",
                )
                return redirect(url_for("events.view_event", event_id=event.event_id))
        else:
            data_rows = rows[1:]

        # Collect existing emails for deduplication
        existing_emails = {
            g.guest_email.lower()
            for g in Guest.query.filter_by(event_id=event.event_id).all()
        }

        imported_count = 0
        skipped_count = 0

        for row in data_rows:
            if not row or len(row) <= max(name_idx, email_idx):
                continue

            guest_name = row[name_idx].strip()
            guest_email = row[email_idx].strip().lower()

            if not guest_name or not guest_email or not EMAIL_REGEX.match(guest_email):
                skipped_count += 1
                continue

            if guest_email in existing_emails:
                skipped_count += 1
                continue

            allowed_additional = 0
            if allowed_idx is not None and len(row) > allowed_idx:
                try:
                    allowed_additional = max(0, int(row[allowed_idx].strip()))
                except (ValueError, TypeError):
                    allowed_additional = 0

            guest = Guest(
                event_id=event.event_id,
                guest_name=guest_name,
                guest_email=guest_email,
                allowed_additional_guests=allowed_additional,
            )
            db.session.add(guest)
            existing_emails.add(guest_email)
            imported_count += 1

        db.session.commit()
        msg = f"Successfully imported {imported_count} guests."
        if skipped_count > 0:
            msg += f" ({skipped_count} invalid or duplicate rows skipped)."
        flash(msg, "success" if imported_count > 0 else "warning")

    except Exception as e:
        db.session.rollback()
        flash(f"Error parsing CSV file: {str(e)}", "danger")

    return redirect(url_for("events.view_event", event_id=event.event_id))


@guests_bp.route("/<int:guest_id>/delete", methods=["POST"])
@login_required
def delete_guest(event_id: int, guest_id: int):
    """Remove a guest from the event roster."""
    event = get_authorized_event(event_id)
    guest = Guest.query.filter_by(guest_id=guest_id, event_id=event.event_id).first_or_404()

    name = guest.guest_name
    db.session.delete(guest)
    db.session.commit()
    flash(f"Removed '{name}' from the guest list.", "info")
    return redirect(url_for("events.view_event", event_id=event.event_id))
