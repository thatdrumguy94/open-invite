import io
import xml.sax.saxutils as saxutils
from datetime import datetime
from typing import BinaryIO, Tuple, Union
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.colors import HexColor
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)

# Executive Cloud Color Palette
ROYAL_NAVY = HexColor("#1E3A8A")
AZURE_SLATE = HexColor("#0284C7")
MIDNIGHT_SLATE = HexColor("#0F172A")
TEXT_SLATE = HexColor("#1E293B")
MUTED_SLATE = HexColor("#64748B")
BG_LIGHT = HexColor("#F8FAFC")
BORDER_COLOR = HexColor("#E2E8F0")
CARD_BG = HexColor("#F1F5F9")


class PDFService:
    """PDF generation and validation service."""

    @staticmethod
    def generate_invitation_pdf(
        title: str,
        event_type: str,
        event_date: Union[datetime, str],
        location: str,
        host_name: str = None,
        description: str = None,
        rsvp_url: str = None,
    ) -> bytes:
        """
        Generate an elegant, professional PDF event invitation using ReportLab.
        Returns the raw PDF bytes.
        """
        buffer = io.BytesIO()

        # Target standard Letter with 0.5-inch margins for an expansive card layout
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            rightMargin=36,
            leftMargin=36,
            topMargin=36,
            bottomMargin=36,
        )

        styles = getSampleStyleSheet()

        # Custom typography styles
        styles.add(
            ParagraphStyle(
                name="ExecutiveBadge",
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=14,
                textColor=AZURE_SLATE,
                alignment=1,  # Center
                spaceAfter=6,
            )
        )
        styles.add(
            ParagraphStyle(
                name="ExecutiveTitle",
                fontName="Helvetica-Bold",
                fontSize=26,
                leading=32,
                textColor=ROYAL_NAVY,
                alignment=1,  # Center
                spaceAfter=8,
            )
        )
        styles.add(
            ParagraphStyle(
                name="ExecutiveSubtitle",
                fontName="Helvetica-Oblique",
                fontSize=14,
                leading=18,
                textColor=MUTED_SLATE,
                alignment=1,  # Center
                spaceAfter=14,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DetailLabel",
                fontName="Helvetica-Bold",
                fontSize=11,
                leading=15,
                textColor=ROYAL_NAVY,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DetailValue",
                fontName="Helvetica",
                fontSize=11,
                leading=15,
                textColor=TEXT_SLATE,
            )
        )
        styles.add(
            ParagraphStyle(
                name="DescriptionText",
                fontName="Helvetica",
                fontSize=11,
                leading=16,
                textColor=TEXT_SLATE,
                alignment=1,  # Center
            )
        )
        styles.add(
            ParagraphStyle(
                name="RSVPCallout",
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=16,
                textColor=ROYAL_NAVY,
                alignment=1,  # Center
            )
        )
        styles.add(
            ParagraphStyle(
                name="FooterText",
                fontName="Helvetica",
                fontSize=9,
                leading=12,
                textColor=MUTED_SLATE,
                alignment=1,  # Center
            )
        )

        story = []

        # Sanitize text inputs for ReportLab XML parser
        safe_title = saxutils.escape(title or "")
        safe_type = saxutils.escape((event_type or "EVENT").upper())
        safe_location = saxutils.escape(location or "")
        safe_host = saxutils.escape(host_name or "") if host_name else None
        safe_desc = saxutils.escape(description.strip()) if description and description.strip() else None

        # Top Executive 3-Stop Gradient Representation (Decorative accent bar)
        story.append(HRFlowable(width="100%", thickness=6, color=ROYAL_NAVY, spaceAfter=20, spaceBefore=0))

        # Invitation Header
        story.append(Paragraph("YOU ARE CORDIALLY INVITED TO", styles["ExecutiveBadge"]))
        story.append(Paragraph(safe_title, styles["ExecutiveTitle"]))
        story.append(Paragraph(f"— {safe_type} —", styles["ExecutiveSubtitle"]))
        story.append(Spacer(1, 12))

        # Event Description block (if provided)
        if safe_desc:
            desc_table = Table(
                [[Paragraph(f"<i>&ldquo;{safe_desc}&rdquo;</i>", styles["DescriptionText"])]],
                colWidths=[540],
            )
            desc_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), CARD_BG),
                        ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                        ("PADDING", (0, 0), (-1, -1), 12),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                    ]
                )
            )
            story.append(desc_table)
            story.append(Spacer(1, 16))

        # Format Event Date & Time
        if isinstance(event_date, datetime):
            formatted_date = event_date.strftime("%A, %B %d, %Y")
            formatted_time = event_date.strftime("%I:%M %p %Z").strip()
            datetime_str = f"{formatted_date} at {formatted_time}"
        else:
            datetime_str = str(event_date)
        safe_datetime = saxutils.escape(datetime_str)

        # Event Details Table
        details_data = [
            [
                Paragraph("DATE & TIME", styles["DetailLabel"]),
                Paragraph(safe_datetime, styles["DetailValue"]),
            ],
            [
                Paragraph("LOCATION", styles["DetailLabel"]),
                Paragraph(safe_location, styles["DetailValue"]),
            ],
        ]

        if safe_host:
            details_data.append(
                [
                    Paragraph("HOSTED BY", styles["DetailLabel"]),
                    Paragraph(safe_host, styles["DetailValue"]),
                ]
            )

        details_table = Table(details_data, colWidths=[150, 390])
        details_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.white),
                    ("BOX", (0, 0), (-1, -1), 1, BORDER_COLOR),
                    ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_COLOR),
                    ("PADDING", (0, 0), (-1, -1), 12),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(details_table)
        story.append(Spacer(1, 20))

        # RSVP Action Callout Box
        rsvp_content = [
            [Paragraph("PLEASE CONFIRM YOUR ATTENDANCE", styles["RSVPCallout"])],
            [
                Paragraph(
                    "Kindly respond via the personalized RSVP link delivered with your invitation email.",
                    styles["DescriptionText"],
                )
            ],
        ]
        if rsvp_url:
            rsvp_content.append([Paragraph(f"RSVP URL: {rsvp_url}", styles["DescriptionText"])])

        rsvp_box = Table(rsvp_content, colWidths=[540])
        rsvp_box.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), HexColor("#EFF6FF")),
                    ("BOX", (0, 0), (-1, -1), 1.5, AZURE_SLATE),
                    ("PADDING", (0, 0), (-1, -1), 12),
                    ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ]
            )
        )
        story.append(rsvp_box)
        story.append(Spacer(1, 24))

        # Bottom Accent & System Footer
        story.append(HRFlowable(width="100%", thickness=1, color=BORDER_COLOR, spaceAfter=8, spaceBefore=0))
        story.append(
            Paragraph(
                "OpenInvite &bull; Self-Hosted Event Invitation Platform",
                styles["FooterText"],
            )
        )

        doc.build(story)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes

    @staticmethod
    def validate_custom_pdf(
        file_stream: BinaryIO, max_size_bytes: int = 10 * 1024 * 1024
    ) -> Tuple[bool, str]:
        """
        Validate host-uploaded PDF file:
        - Confirms '%PDF-' magic bytes header.
        - Enforces size limit (default 10MB).
        - Resets file stream position for subsequent writes.
        """
        if not file_stream:
            return False, "No file stream provided."

        try:
            file_stream.seek(0, io.SEEK_END)
            size = file_stream.tell()
            file_stream.seek(0)

            if size == 0:
                return False, "The uploaded file is empty."

            if size > max_size_bytes:
                max_mb = max_size_bytes // (1024 * 1024)
                return False, f"File size exceeds the {max_mb}MB limit."

            # Verify magic bytes header
            header = file_stream.read(5)
            file_stream.seek(0)

            if not header.startswith(b"%PDF-"):
                return False, "Invalid document: uploaded file is not a valid PDF."

            return True, ""
        except Exception as e:
            return False, f"Failed to validate PDF: {str(e)}"


# Module-level convenience functions
generate_invitation_pdf = PDFService.generate_invitation_pdf
validate_custom_pdf = PDFService.validate_custom_pdf
