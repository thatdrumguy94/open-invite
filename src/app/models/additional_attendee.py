from datetime import datetime, timezone
from src.app import db


class AdditionalAttendee(db.Model):
    """Details collected for each additional guest attending under a primary invitation."""
    __tablename__ = "additional_attendees"

    attendee_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    guest_id = db.Column(
        db.Integer,
        db.ForeignKey("guests.guest_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name = db.Column(db.String(100), nullable=False)
    dietary_notes = db.Column(db.String(255), nullable=True)  # Dietary requirements, allergies, or notes
    created_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    # Relationships
    primary_guest = db.relationship("Guest", back_populates="additional_attendees")

    def to_dict(self) -> dict:
        """Serialize attendee to dictionary."""
        return {
            "attendee_id": self.attendee_id,
            "guest_id": self.guest_id,
            "name": self.name,
            "dietary_notes": self.dietary_notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<AdditionalAttendee {self.attendee_id}: '{self.name}'>"
