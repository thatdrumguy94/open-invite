import io
from datetime import datetime
from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    g,
    send_file,
    abort,
)
from src.app import db
from src.app.models.event import Event
from src.app.routes.auth import login_required
from src.app.services.s3_service import get_storage_service
from src.app.services.pdf_service import generate_invitation_pdf, validate_custom_pdf

events_bp = Blueprint("events", __name__, url_prefix="/events")


@events_bp.route("/")
@login_required
def list_events():
    """Display dashboard with all events organized by current host."""
    events = (
        Event.query.filter_by(organizer_id=g.current_user.user_id)
        .order_by(Event.event_date.asc())
        .all()
    )
    return render_template("events/list.html", events=events)


@events_bp.route("/new", methods=["GET", "POST"])
@login_required
def create_event():
    """Event creation wizard: metadata, PDF choice (ReportLab auto vs custom upload)."""
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        event_type = request.form.get("event_type", "Other").strip()
        date_str = request.form.get("event_date", "").strip()
        location = request.form.get("location", "").strip()
        description = request.form.get("description", "").strip()
        invitation_mode = request.form.get("invitation_mode", "auto")

        # Basic validations
        if not title or not event_type or not date_str or not location:
            flash("Please fill in all required fields (Title, Type, Date, Location).", "danger")
            return render_template("events/create.html", form=request.form)

        try:
            # Parse HTML5 datetime-local (YYYY-MM-DDTHH:MM)
            event_date = datetime.fromisoformat(date_str)
        except ValueError:
            flash("Invalid date and time format. Please use the date picker.", "danger")
            return render_template("events/create.html", form=request.form)

        # Create initial Event model instance
        event = Event(
            organizer_id=g.current_user.user_id,
            title=title,
            event_type=event_type,
            event_date=event_date,
            location=location,
            description=description,
            is_custom_pdf=(invitation_mode == "custom"),
        )
        db.session.add(event)
        db.session.flush()  # Generates event.event_id for storage key

        storage = get_storage_service()
        storage_key = f"events/{event.event_id}/invitation.pdf"

        # Handle PDF Invitation Generation or Upload
        if invitation_mode == "custom":
            uploaded_file = request.files.get("custom_pdf")
            if not uploaded_file or uploaded_file.filename == "":
                flash("Please select a PDF file to upload.", "danger")
                db.session.rollback()
                return render_template("events/create.html", form=request.form)

            is_valid, err_msg = validate_custom_pdf(uploaded_file.stream)
            if not is_valid:
                flash(f"Custom PDF validation failed: {err_msg}", "danger")
                db.session.rollback()
                return render_template("events/create.html", form=request.form)

            # Save validated custom PDF
            uploaded_file.stream.seek(0)
            saved_key = storage.save_file(
                uploaded_file.stream, storage_key, content_type="application/pdf"
            )
            event.pdf_storage_path = saved_key
            event.is_custom_pdf = True
        else:
            # Auto-generate with ReportLab
            pdf_bytes = generate_invitation_pdf(
                title=event.title,
                event_type=event.event_type,
                event_date=event.event_date,
                location=event.location,
                host_name=g.current_user.name,
                description=event.description,
            )
            saved_key = storage.save_file(
                pdf_bytes, storage_key, content_type="application/pdf"
            )
            event.pdf_storage_path = saved_key
            event.is_custom_pdf = False

        db.session.commit()
        flash(f"Event '{event.title}' created successfully!", "success")
        return redirect(url_for("events.view_event", event_id=event.event_id))

    return render_template("events/create.html", form={})


def ensure_event_pdf(event: Event, host_name: str = None) -> str:
    """Ensure invitation PDF exists for the event; auto-generates if missing."""
    storage = get_storage_service()
    need_build = False

    if not event.pdf_storage_path or not storage.file_exists(event.pdf_storage_path):
        need_build = True

    if need_build and not event.is_custom_pdf:
        storage_key = f"events/{event.event_id}/invitation.pdf"
        effective_host = host_name or (event.organizer.name if event.organizer else "Event Host")
        pdf_bytes = generate_invitation_pdf(
            title=event.title,
            event_type=event.event_type,
            event_date=event.event_date,
            location=event.location,
            host_name=effective_host,
            description=event.description,
        )
        saved_key = storage.save_file(
            pdf_bytes, storage_key, content_type="application/pdf"
        )
        event.pdf_storage_path = saved_key
        db.session.commit()

    return event.pdf_storage_path


@events_bp.route("/<int:event_id>")
@login_required
def view_event(event_id: int):
    """Event detail dashboard: RSVP metrics, guest roster, PDF download link."""
    event = db.get_or_404(Event, event_id)

    # Authorization guard: host can only view their own events
    if event.organizer_id != g.current_user.user_id:
        abort(403)

    # Ensure PDF exists (auto-generate if missing)
    ensure_event_pdf(event, g.current_user.name)

    storage = get_storage_service()
    pdf_url = None
    if event.pdf_storage_path:
        pdf_url = storage.get_url(event.pdf_storage_path)

    return render_template(
        "events/detail.html",
        event=event,
        guests=event.guests,
        summary=event.rsvp_summary,
        pdf_url=pdf_url,
    )


@events_bp.route("/storage/<path:key>")
def serve_storage_file(key: str):
    """Serve files stored in local filesystem storage mode."""
    storage = get_storage_service()
    if storage.backend == "local":
        file_path = (storage.local_path / key.lstrip("/")).resolve()

        # If file is missing on disk, attempt auto-generation for event invitations
        if not file_path.exists():
            parts = key.lstrip("/").split("/")
            if len(parts) >= 2 and parts[0] == "events":
                try:
                    event_id = int(parts[1])
                    event = db.session.get(Event, event_id)
                    if event and not event.is_custom_pdf:
                        host_name = event.organizer.name if event.organizer else "Event Host"
                        ensure_event_pdf(event, host_name)
                except (ValueError, Exception):
                    pass

        if file_path.exists():
            as_attachment = request.args.get("download", "0") in ("1", "true", "True")
            return send_file(
                file_path,
                mimetype="application/pdf",
                as_attachment=as_attachment,
            )
    abort(404)


@events_bp.route("/<int:event_id>/pdf")
def download_invitation(event_id: int):
    """Serve or redirect to stored invitation PDF (with auto-generation fallback)."""
    event = db.get_or_404(Event, event_id)

    # Note: Event invitations are public documents intended for hosts and guests alike.
    # No login required so guests, preview iframes, and hosts can all view or download.
    host_name = event.organizer.name if event.organizer else "Event Host"
    ensure_event_pdf(event, host_name)

    if not event.pdf_storage_path:
        flash("No invitation PDF found for this event.", "warning")
        return redirect(url_for("events.view_event", event_id=event.event_id))

    storage = get_storage_service()

    # If using local storage, send file directly with inline display or download
    if storage.backend == "local":
        file_path = (storage.local_path / event.pdf_storage_path).resolve()
        if file_path.exists():
            as_attachment = request.args.get("download", "0") in ("1", "true", "True")
            return send_file(
                file_path,
                mimetype="application/pdf",
                as_attachment=as_attachment,
                download_name=f"invitation_{event.event_id}.pdf",
            )
        else:
            abort(404)

    # If S3, redirect to presigned URL
    presigned_url = storage.get_url(event.pdf_storage_path)
    return redirect(presigned_url)

    # If S3, redirect to presigned URL
    presigned_url = storage.get_url(event.pdf_storage_path)
    return redirect(presigned_url)


@events_bp.route("/<int:event_id>/regenerate-pdf", methods=["POST"])
@login_required
def regenerate_invitation_pdf(event_id: int):
    """Explicitly recompile ReportLab PDF with latest event details."""
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != g.current_user.user_id:
        abort(403)

    storage = get_storage_service()
    storage_key = f"events/{event.event_id}/invitation.pdf"

    pdf_bytes = generate_invitation_pdf(
        title=event.title,
        event_type=event.event_type,
        event_date=event.event_date,
        location=event.location,
        host_name=g.current_user.name,
        description=event.description,
    )
    saved_key = storage.save_file(
        pdf_bytes, storage_key, content_type="application/pdf"
    )
    event.pdf_storage_path = saved_key
    event.is_custom_pdf = False
    db.session.commit()

    flash("Invitation PDF regenerated successfully!", "success")
    return redirect(url_for("events.view_event", event_id=event.event_id))


@events_bp.route("/<int:event_id>/delete", methods=["POST"])
@login_required
def delete_event(event_id: int):
    """Delete an event and cascaded records and stored PDF."""
    event = db.get_or_404(Event, event_id)
    if event.organizer_id != g.current_user.user_id:
        abort(403)

    title = event.title
    storage = get_storage_service()
    if event.pdf_storage_path:
        storage.delete_file(event.pdf_storage_path)

    db.session.delete(event)
    db.session.commit()
    flash(f"Event '{title}' has been deleted.", "info")
    return redirect(url_for("events.list_events"))
