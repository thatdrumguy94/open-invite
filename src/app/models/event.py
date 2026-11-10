from datetime import datetime, timezone
from src.app import db


class Event(db.Model):
    """Event model representing social gatherings (showers, birthdays, etc.)."""
    __tablename__ = "events"

    event_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    organizer_id = db.Column(
        db.Integer,
        db.ForeignKey("users.user_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = db.Column(db.String(200), nullable=False)
    event_type = db.Column(db.String(50), nullable=False)  # "Birthday", "Shower", "Party", "Other"
    event_date = db.Column(db.DateTime(timezone=True), nullable=False)
    location = db.Column(db.String(255), nullable=False)
    pdf_storage_path = db.Column(db.String(500), nullable=True)  # S3 Key or local path
    is_custom_pdf = db.Column(db.Boolean, default=False, nullable=False)
    description = db.Column(db.Text, nullable=True)
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    organizer = db.relationship("User", back_populates="events")
    guests = db.relationship(
        "Guest",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
    )
    communications = db.relationship(
        "Communication",
        back_populates="event",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="desc(Communication.sent_at)",
    )

    @property
    def rsvp_summary(self) -> dict:
        """Calculate counts of RSVPs grouped by status."""
        summary = {
            "total_invited": len(self.guests),
            "accepted": 0,
            "declined": 0,
            "pending": 0,
            "total_attendees": 0,  # accepted guests + accepted plus_ones
        }
        for guest in self.guests:
            status = (guest.rsvp_status or "Pending").capitalize()
            if status == "Accepted":
                summary["accepted"] += 1
                summary["total_attendees"] += 1 + (guest.plus_ones or 0)
            elif status == "Declined":
                summary["declined"] += 1
            else:
                summary["pending"] += 1
        return summary

    def to_dict(self) -> dict:
        """Serialize event to dictionary."""
        return {
            "event_id": self.event_id,
            "organizer_id": self.organizer_id,
            "title": self.title,
            "event_type": self.event_type,
            "event_date": self.event_date.isoformat() if self.event_date else None,
            "location": self.location,
            "pdf_storage_path": self.pdf_storage_path,
            "is_custom_pdf": self.is_custom_pdf,
            "description": self.description,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "rsvp_summary": self.rsvp_summary,
        }

    def __repr__(self) -> str:
        return f"<Event {self.event_id}: '{self.title}'>"
