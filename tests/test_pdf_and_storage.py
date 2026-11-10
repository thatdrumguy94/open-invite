import io
from datetime import datetime, timezone
import pytest
from src.app.services.pdf_service import PDFService
from src.app.services.s3_service import StorageService


def test_pdf_generation_valid_output():
    """Test that PDFService generates a valid PDF starting with %PDF- header."""
    pdf_bytes = PDFService.generate_invitation_pdf(
        title="Graduation Gala",
        event_type="Celebration",
        event_date=datetime(2026, 12, 15, 18, 30, tzinfo=timezone.utc),
        location="Grand Ballroom, San Antonio",
        host_name="Demo Host",
        description="Celebrating academic achievement and graduation!",
        rsvp_url="https://example.com/rsvp/sample-token",
    )

    assert isinstance(pdf_bytes, bytes)
    assert len(pdf_bytes) > 1000
    assert pdf_bytes.startswith(b"%PDF-")


def test_validate_custom_pdf_success():
    """Test validation passes for a valid PDF stream."""
    valid_pdf_bytes = PDFService.generate_invitation_pdf(
        title="Test Event",
        event_type="Birthday",
        event_date=datetime.now(timezone.utc),
        location="123 Street",
    )
    stream = io.BytesIO(valid_pdf_bytes)

    is_valid, error = PDFService.validate_custom_pdf(stream)
    assert is_valid is True
    assert error == ""
    # Ensure stream position was reset
    assert stream.tell() == 0


def test_validate_custom_pdf_invalid_header():
    """Test validation fails for non-PDF files."""
    fake_stream = io.BytesIO(b"This is just plain text, not a PDF.")
    is_valid, error = PDFService.validate_custom_pdf(fake_stream)

    assert is_valid is False
    assert "not a valid PDF" in error


def test_validate_custom_pdf_empty_file():
    """Test validation fails for an empty file."""
    empty_stream = io.BytesIO(b"")
    is_valid, error = PDFService.validate_custom_pdf(empty_stream)

    assert is_valid is False
    assert "empty" in error


def test_storage_service_local_operations(tmp_path):
    """Test StorageService local save, get, existence check, and delete."""
    storage = StorageService(backend="local", local_path=tmp_path)

    sample_content = b"PDF mock content or bytes"
    key = "events/1/invitation.pdf"

    # Save file
    saved_key = storage.save_file(sample_content, key)
    assert saved_key == key

    # Check existence
    assert storage.file_exists(key) is True

    # Get file content
    retrieved = storage.get_file(key)
    assert retrieved == sample_content

    # Delete file
    deleted = storage.delete_file(key)
    assert deleted is True
    assert storage.file_exists(key) is False


def test_pdf_generation_with_special_xml_chars():
    """Test that special characters like &, <, >, unclosed tags do not crash PDF generation."""
    pdf_bytes = PDFService.generate_invitation_pdf(
        title="Tom & Jerry's <Epic> Bash",
        event_type="Birthday Party",
        event_date=datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc),
        location="123 4th Ave & Main St <Suite 100>",
        host_name="Alice & Bob <Hosts>",
        description="Join us for food & drinks! <Unclosed tag test",
    )
    assert isinstance(pdf_bytes, bytes)
    assert pdf_bytes.startswith(b"%PDF-")
