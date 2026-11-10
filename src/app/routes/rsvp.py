from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
)
from src.app import db
from src.app.models.guest import Guest
from src.app.services.s3_service import get_storage_service

rsvp_bp = Blueprint("rsvp", __name__, url_prefix="/rsvp")


@rsvp_bp.route("/<string:token>", methods=["GET", "POST"])
def guest_rsvp_portal(token: str):
    """Public guest RSVP response portal."""
    guest = Guest.query.filter_by(rsvp_token=token).first_or_404()
    event = guest.event

    storage = get_storage_service()
    pdf_url = None
    if event.pdf_storage_path:
        pdf_url = storage.get_url(event.pdf_storage_path)

    if request.method == "POST":
        status = request.form.get("status", "").strip().capitalize()
        notes = request.form.get("notes", "").strip()

        if status not in ("Accepted", "Declined"):
            flash("Please indicate whether you will be attending or declining.", "danger")
            return render_template(
                "rsvp/portal.html",
                guest=guest,
                event=event,
                pdf_url=pdf_url,
            )

        additional_attendees_list = []
        plus_ones = 0

        if status == "Accepted":
            try:
                plus_ones_raw = int(request.form.get("plus_ones", 0))
            except (ValueError, TypeError):
                plus_ones_raw = 0

            # Enforce host-defined limit
            plus_ones = max(0, min(plus_ones_raw, guest.allowed_additional_guests))

            # Collect details for each attending additional guest
            for i in range(1, plus_ones + 1):
                att_name = request.form.get(f"additional_name_{i}", "").strip()
                att_diet = request.form.get(f"additional_diet_{i}", "").strip()

                if not att_name:
                    att_name = f"Guest #{i} of {guest.guest_name}"

                additional_attendees_list.append(
                    {"name": att_name, "dietary_notes": att_diet or None}
                )

        # Update database model
        guest.submit_rsvp(
            status=status,
            plus_ones=plus_ones,
            notes=notes,
            additional_guests_data=additional_attendees_list,
        )
        db.session.commit()

        if status == "Accepted":
            total = 1 + plus_ones
            flash(
                f"Thank you, {guest.guest_name}! Your RSVP has been confirmed for {total} attendee(s).",
                "success",
            )
        else:
            flash(
                f"Thank you, {guest.guest_name}. Your decline has been recorded.",
                "info",
            )

        return render_template(
            "rsvp/portal.html",
            guest=guest,
            event=event,
            pdf_url=pdf_url,
            submitted=True,
        )

    return render_template(
        "rsvp/portal.html",
        guest=guest,
        event=event,
        pdf_url=pdf_url,
        submitted=False,
    )
