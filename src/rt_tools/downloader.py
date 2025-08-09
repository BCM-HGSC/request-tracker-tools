"""RT ticket download automation."""

import logging
import re
from pathlib import Path

from .session import RTSession, parse_rt_response

logger = logging.getLogger(__name__)


class TicketDownloader:
    """Downloads complete RT ticket data to organized directory structure."""

    def __init__(self, session: RTSession):
        self.session = session

    def download_ticket(self, ticket_id: str, target_dir: Path) -> None:
        """Download all relevant content for a ticket to target directory.

        Creates directory structure:
        ticket_{id}/
        ├── metadata.txt      # Ticket basic information
        ├── history.txt       # Complete ticket history
        └── attachments/      # Directory for attachment files
            ├── {filename1}   # Original filename when available
            ├── {filename2}   # Or attachment_{id} when no filename
            └── ...

        Args:
            ticket_id: RT ticket ID (without 'ticket/' prefix)
            target_dir: Directory where ticket data should be saved
        """
        target_dir = Path(target_dir)
        target_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading ticket {ticket_id} to {target_dir}")

        # Download ticket metadata
        self._download_metadata(ticket_id, target_dir)

        # Download ticket history
        self._download_history(ticket_id, target_dir)

        # Download attachments
        self._download_attachments(ticket_id, target_dir)

        logger.info(f"Completed downloading ticket {ticket_id}")

    def _download_metadata(self, ticket_id: str, target_dir: Path) -> None:
        """Download ticket metadata to metadata.txt."""
        logger.debug(f"Downloading metadata for ticket {ticket_id}")

        response = self.session.get(f"{self.session.rest_url('ticket', ticket_id)}")
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get metadata for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        metadata_file = target_dir / "metadata.txt"
        metadata_file.write_bytes(rt_data.payload)
        logger.debug(f"Saved metadata to {metadata_file}")

    def _download_history(self, ticket_id: str, target_dir: Path) -> None:
        """Download ticket history to history.txt."""
        logger.debug(f"Downloading history for ticket {ticket_id}")

        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'history')}"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get history for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        history_file = target_dir / "history.txt"
        history_file.write_bytes(rt_data.payload)
        logger.debug(f"Saved history to {history_file}")

    def _download_attachments(self, ticket_id: str, target_dir: Path) -> None:
        """Download all relevant attachments to attachments/ subdirectory."""
        logger.debug(f"Downloading attachments for ticket {ticket_id}")

        # Get attachments list
        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'attachments')}"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get attachments for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        attachment_ids = self._parse_attachment_ids(rt_data.payload.decode("utf-8"))
        if not attachment_ids:
            logger.debug(f"No attachments found for ticket {ticket_id}")
            return

        # Create attachments directory
        attachments_dir = target_dir / "attachments"
        attachments_dir.mkdir(exist_ok=True)

        # Download each attachment
        for attachment_id in attachment_ids:
            self._download_single_attachment(ticket_id, attachment_id, attachments_dir)

    def _parse_attachment_ids(self, attachments_text: str) -> list[str]:
        """Parse attachment IDs from attachments list response.

        Parses text like:
        456: (Unnamed) (text/plain / 0.2k)
        789: sample_document.pdf (application/pdf / 45k)

        Returns list of attachment IDs as strings.
        """
        attachment_ids = []
        for line in attachments_text.strip().split("\n"):
            if ":" in line:
                # Extract ID from beginning of line
                match = re.match(r"^(\d+):", line.strip())
                if match:
                    attachment_ids.append(match.group(1))

        logger.debug(f"Found attachment IDs: {attachment_ids}")
        return attachment_ids

    def _download_single_attachment(
        self, ticket_id: str, attachment_id: str, attachments_dir: Path
    ) -> None:
        """Download a single attachment with its metadata and content."""
        logger.debug(f"Downloading attachment {attachment_id} for ticket {ticket_id}")

        # Get attachment metadata to determine filename
        url = self.session.rest_url("ticket", ticket_id, "attachments", attachment_id)
        response = self.session.get(url)
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get metadata for attachment {attachment_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        filename = self._extract_filename(
            rt_data.payload.decode("utf-8"), attachment_id
        )

        # Skip if this is an outgoing email (common pattern to exclude)
        if self._is_outgoing_email(rt_data.payload.decode("utf-8")):
            logger.debug(f"Skipping outgoing email attachment {attachment_id}")
            return

        # Get attachment content
        url = self.session.rest_url(
            "ticket", ticket_id, "attachments", attachment_id, "content"
        )
        response = self.session.get(url)
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get content for attachment {attachment_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        # Save attachment content
        attachment_file = attachments_dir / filename
        attachment_file.write_bytes(rt_data.payload)
        logger.debug(f"Saved attachment to {attachment_file}")

    def _extract_filename(self, attachment_metadata: str, attachment_id: str) -> str:
        """Extract filename from attachment metadata or generate default name."""
        # Look for Filename: field
        for line in attachment_metadata.split("\n"):
            if line.startswith("Filename:"):
                filename = line.split(":", 1)[1].strip()
                if filename and filename != "":
                    return filename

        # Look for Subject: field as fallback
        for line in attachment_metadata.split("\n"):
            if line.startswith("Subject:"):
                subject = line.split(":", 1)[1].strip()
                if subject and subject not in ["(Unnamed)", ""]:
                    # Clean subject to be filesystem-safe
                    safe_subject = re.sub(r"[^\w\-_\.]", "_", subject)
                    return safe_subject

        # Default to attachment ID
        return f"attachment_{attachment_id}"

    def _is_outgoing_email(self, attachment_metadata: str) -> bool:
        """Check if attachment represents an outgoing email to be excluded."""
        # Look for indicators of outgoing emails in headers
        headers_section = False
        for line in attachment_metadata.split("\n"):
            if line.startswith("Headers:"):
                headers_section = True
                continue
            if headers_section and line.startswith("Content:"):
                break
            if headers_section and "X-RT-Loop-Prevention:" in line:
                # This is typically present in RT-generated emails
                return True

        return False


def download_ticket(session: RTSession, ticket_id: str, target_dir: Path) -> None:
    """Convenience function to download a ticket using TicketDownloader.

    Args:
        session: Authenticated RTSession
        ticket_id: RT ticket ID (without 'ticket/' prefix)
        target_dir: Directory where ticket data should be saved
    """
    downloader = TicketDownloader(session)
    downloader.download_ticket(ticket_id, target_dir)
