from datetime import datetime, timezone
from src.app import db


class Communication(db.Model):
    """Log of dispatched event emails (invitations, reminders, updates)."""
    __tablename__ = "communications"

    comm_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    event_id = db.Column(
        db.Integer,
        db.ForeignKey("events.event_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    message_type = db.Column(
        db.String(50),
        nullable=False,
    )  # "Invitation", "Reminder", "Update"
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    sent_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    recipients_count = db.Column(db.Integer, default=0, nullable=False)

    # Relationships
    event = db.relationship("Event", back_populates="communications")

    def to_dict(self) -> dict:
        """Serialize communication log record to dictionary."""
        return {
            "comm_id": self.comm_id,
            "event_id": self.event_id,
            "message_type": self.message_type,
            "subject": self.subject,
            "body": self.body,
            "sent_at": self.sent_at.isoformat() if self.sent_at else None,
            "recipients_count": self.recipients_count,
        }

    def __repr__(self) -> str:
        return f"<Communication {self.comm_id}: {self.message_type} ({self.recipients_count} recipients)>"
