import uuid
from datetime import datetime, timezone
from src.app import db
from src.app.models.additional_attendee import AdditionalAttendee


def generate_rsvp_token() -> str:
    """Generate a secure, random UUID string for public RSVP links."""
    return str(uuid.uuid4())


class Guest(db.Model):
    """Guest invited to an event with a personalized RSVP token."""
    __tablename__ = "guests"

    guest_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("events.event_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    guest_name = db.Column(db.String(100), nullable=False)
    guest_email = db.Column(db.String(120), nullable=False, index=True)
    rsvp_token = db.Column(
        db.String(64),
        unique=True,
        nullable=False,
        index=True,
        default=generate_rsvp_token,
    )
    rsvp_status = db.Column(
        db.String(20),
        default="Pending",
        nullable=False,
    )  # "Pending", "Accepted", "Declined"

    # Host-defined allowance: maximum number of additional attendees permitted with this invite
    allowed_additional_guests = db.Column(db.Integer, default=0, nullable=False)

    # Guest-confirmed response: number of additional attendees actually attending
    plus_ones = db.Column(db.Integer, default=0, nullable=False)

    notes = db.Column(db.Text, nullable=True)
    rsvp_updated_at = db.Column(db.DateTime(timezone=True), nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    event = db.relationship("Event", back_populates="guests")
    additional_attendees = db.relationship(
        "AdditionalAttendee",
        back_populates="primary_guest",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def submit_rsvp(
        self,
        status: str,
        plus_ones: int = 0,
        notes: str = None,
        additional_guests_data: list = None,
    ) -> None:
        """
        Submit or update guest RSVP response.
        additional_guests_data: optional list of dicts [{'name': '...', 'dietary_notes': '...'}, ...]
        """
        normalized_status = status.capitalize()
        if normalized_status not in ("Pending", "Accepted", "Declined"):
            raise ValueError(f"Invalid RSVP status: {status}")

        self.rsvp_status = normalized_status

        if normalized_status == "Accepted":
            # Cap confirmed plus ones by host-defined limit
            requested_plus_ones = max(0, int(plus_ones))
            self.plus_ones = min(requested_plus_ones, self.allowed_additional_guests)

            # Clear existing attendee records before re-adding
            self.additional_attendees.clear()
            if additional_guests_data:
                for item in additional_guests_data[: self.plus_ones]:
                    if isinstance(item, dict):
                        raw_name = item.get("name", "")
                        raw_diet = item.get("dietary_notes")
                        att_name = raw_name.strip() if isinstance(raw_name, str) else str(raw_name)
                        att_notes = raw_diet.strip() if isinstance(raw_diet, str) else None
                    else:
                        att_name = str(item).strip()
                        att_notes = None

                    if att_name:
                        attendee = AdditionalAttendee(
                            guest_id=self.guest_id,
                            name=att_name,
                            dietary_notes=att_notes,
                        )
                        self.additional_attendees.append(attendee)
        else:
            self.plus_ones = 0
            self.additional_attendees.clear()

        if notes is not None:
            self.notes = notes.strip()
        self.rsvp_updated_at = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Serialize guest to dictionary."""
        return {
            "guest_id": self.guest_id,
            "event_id": self.event_id,
            "guest_name": self.guest_name,
            "guest_email": self.guest_email,
            "rsvp_token": self.rsvp_token,
            "rsvp_status": self.rsvp_status,
            "allowed_additional_guests": self.allowed_additional_guests,
            "plus_ones": self.plus_ones,
            "additional_attendees": [a.to_dict() for a in self.additional_attendees],
            "notes": self.notes,
            "rsvp_updated_at": (
                self.rsvp_updated_at.isoformat() if self.rsvp_updated_at else None
            ),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<Guest {self.guest_id}: '{self.guest_name}' ({self.rsvp_status}, allowed +{self.allowed_additional_guests})>"
