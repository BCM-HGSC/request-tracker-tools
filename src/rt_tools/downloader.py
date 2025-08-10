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
            ├── {history_id}-{attachment_id}.{ext}  # Attachment files
            └── ...

        Skips outgoing emails and zero-byte attachments.
        Uses MIME type from attachment list to determine file extensions.

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

        # Download attachments from history
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
        """Download attachments from history entries, skipping outgoing emails."""
        logger.debug(f"Downloading attachments for ticket {ticket_id}")

        # Build attachment cache (ID -> {filename, mime_type})
        attachment_cache = self._build_attachment_cache(ticket_id)
        if not attachment_cache:
            logger.debug(f"No attachments found for ticket {ticket_id}")
            return

        # Get detailed history with attachments
        history_entries = self._get_history_entries(ticket_id)
        if not history_entries:
            logger.debug(f"No history entries found for ticket {ticket_id}")
            return

        # Create attachments directory
        attachments_dir = target_dir / "attachments"
        attachments_dir.mkdir(exist_ok=True)

        # Process each history entry
        for history_entry in history_entries:
            if self._is_outgoing_email_history(history_entry):
                entry_id = history_entry.get('id', 'unknown')
                logger.debug(f"Skipping outgoing email history entry {entry_id}")
                continue

            # Download attachments for this history entry
            for attachment_id in history_entry.get('attachment_ids', []):
                self._download_history_attachment(
                    ticket_id, history_entry['id'], attachment_id,
                    attachment_cache, attachments_dir
                )

    def _build_attachment_cache(self, ticket_id: str) -> dict[str, dict[str, str]]:
        """Build cache of attachment metadata from attachments list.

        Returns dict mapping attachment_id -> {filename, mime_type}
        """
        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'attachments')}"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get attachments for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return {}

        return self._parse_attachment_cache(rt_data.payload.decode("utf-8"))

    def _parse_attachment_cache(
        self, attachments_text: str
    ) -> dict[str, dict[str, str]]:
        """Parse attachment cache from attachments list response.

        Parses text like:
        456: (Unnamed) (text/plain / 0.2k)
        789: sample_document.pdf (application/pdf / 45k)

        Returns dict mapping attachment_id -> {filename, mime_type}
        """
        cache = {}
        for line in attachments_text.strip().split("\n"):
            if ":" in line:
                # Extract ID, filename, and mime type
                pattern = r"^(\d+):\s*([^(]+?)\s*\(([^)]+)\)"
                match = re.match(pattern, line.strip())
                if match:
                    attachment_id = match.group(1)
                    filename = match.group(2).strip()
                    type_and_size = match.group(3).strip()

                    # Extract MIME type from "mime/type / size" format
                    if '/' in type_and_size:
                        mime_type = type_and_size.split(' / ')[0].strip()
                    else:
                        mime_type = 'application/octet-stream'

                    # Clean up filename
                    if filename == "(Unnamed)" or not filename:
                        filename = ""

                    cache[attachment_id] = {
                        'filename': filename,
                        'mime_type': mime_type
                    }

        logger.debug(f"Built attachment cache: {cache}")
        return cache

    def _get_history_entries(self, ticket_id: str) -> list[dict]:
        """Get detailed history entries with attachment information."""
        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'history')}?format=l"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get detailed history for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return []

        return self._parse_history_entries(rt_data.payload.decode("utf-8"))

    def _parse_history_entries(self, history_text: str) -> list[dict]:
        """Parse detailed history entries from long format response."""
        entries = []

        # Split on '--' separators
        raw_entries = history_text.split('--')

        for raw_entry in raw_entries:
            if not raw_entry.strip():
                continue

            entry = self._parse_single_history_entry(raw_entry.strip())
            if entry:
                entries.append(entry)

        logger.debug(f"Parsed {len(entries)} history entries")
        return entries

    def _parse_single_history_entry(self, entry_text: str) -> dict:
        """Parse a single history entry from detailed format."""
        entry = {'attachment_ids': []}

        lines = entry_text.split('\n')
        in_attachments_section = False

        for original_line in lines:
            line = original_line.strip()
            if not line:
                continue

            if line.startswith('id:'):
                entry['id'] = line.split(':', 1)[1].strip()
            elif line.startswith('Type:'):
                entry['type'] = line.split(':', 1)[1].strip()
            elif line.startswith('Content:'):
                entry['content'] = line.split(':', 1)[1].strip()
            elif line.startswith('Attachments:'):
                in_attachments_section = True
                # Parse attachment info on same line if present
                attachments_part = line.split(':', 1)[1].strip()
                if attachments_part:
                    attachment_ids = self._extract_attachment_ids_from_line(
                        attachments_part
                    )
                    entry['attachment_ids'].extend(attachment_ids)
            elif in_attachments_section:
                # Check if this line starts a new field (not indented)
                if not original_line.startswith((' ', '\t')):
                    # This line starts a new field, end attachments section
                    in_attachments_section = False
                else:
                    # Parse attachment line: "123: filename (size)"
                    attachment_ids = self._extract_attachment_ids_from_line(line)
                    entry['attachment_ids'].extend(attachment_ids)

        return entry

    def _extract_attachment_ids_from_line(self, line: str) -> list[str]:
        """Extract attachment IDs from an attachment line."""
        ids = []
        # Look for patterns like "123: filename" or just "123:"
        matches = re.finditer(r'(\d+):', line)
        for match in matches:
            ids.append(match.group(1))
        return ids

    def _is_outgoing_email_history(self, history_entry: dict) -> bool:
        """Check if a history entry represents an outgoing email.

        For now, we don't skip any history entries at this level.
        Instead, we'll check individual attachments for outgoing email patterns
        in the _is_outgoing_attachment method.
        """
        return False

    def _download_history_attachment(
        self, ticket_id: str, history_id: str, attachment_id: str,
        attachment_cache: dict, attachments_dir: Path
    ) -> None:
        """Download attachment using history-based filename format."""
        logger.debug(
            f"Downloading attachment {attachment_id} from history {history_id} "
            f"for ticket {ticket_id}"
        )

        # Check if this attachment is an outgoing email by examining its metadata
        if self._is_outgoing_attachment(ticket_id, attachment_id):
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

        # Skip zero-byte attachments
        if len(rt_data.payload) == 0:
            logger.debug(f"Skipping zero-byte attachment {attachment_id}")
            return

        # Determine file extension from cached mime type
        attachment_info = attachment_cache.get(attachment_id, {})
        mime_type = attachment_info.get('mime_type', 'application/octet-stream')
        extension = self._mime_type_to_extension(mime_type)

        # Create filename: {history_id}-{attachment_id}.{extension}
        filename = f"{history_id}-{attachment_id}.{extension}"

        # Save attachment content
        attachment_file = attachments_dir / filename
        attachment_file.write_bytes(rt_data.payload)
        logger.debug(f"Saved attachment to {attachment_file}")

    def _is_outgoing_attachment(self, ticket_id: str, attachment_id: str) -> bool:
        """Check if attachment represents an outgoing email to be excluded."""
        # Get attachment metadata to check for outgoing email indicators
        url = self.session.rest_url("ticket", ticket_id, "attachments", attachment_id)
        response = self.session.get(url)
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.debug(f"Could not get metadata for attachment {attachment_id}")
            return False

        attachment_metadata = rt_data.payload.decode("utf-8")

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

    def _mime_type_to_extension(self, mime_type: str) -> str:
        """Convert MIME type to file extension."""
        mime_to_ext = {
            'text/plain': 'txt',
            'text/html': 'html',
            'text/csv': 'csv',
            'application/pdf': 'pdf',
            'application/msword': 'doc',
            'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'docx',  # noqa: E501
            'application/vnd.ms-excel': 'xls',
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet': 'xlsx',  # noqa: E501
            'application/vnd.ms-powerpoint': 'ppt',
            'application/vnd.openxmlformats-officedocument.presentationml.presentation': 'pptx',  # noqa: E501
            'application/zip': 'zip',
            'application/x-zip-compressed': 'zip',
            'application/gzip': 'gz',
            'application/x-tar': 'tar',
            'application/json': 'json',
            'application/xml': 'xml',
            'image/png': 'png',
            'image/jpeg': 'jpg',
            'image/gif': 'gif',
            'image/svg+xml': 'svg',
            'image/tiff': 'tiff',
            'application/octet-stream': 'bin',
        }

        return mime_to_ext.get(mime_type.lower(), 'bin')



def download_ticket(session: RTSession, ticket_id: str, target_dir: Path) -> None:
    """Convenience function to download a ticket using TicketDownloader.

    Args:
        session: Authenticated RTSession
        ticket_id: RT ticket ID (without 'ticket/' prefix)
        target_dir: Directory where ticket data should be saved
    """
    downloader = TicketDownloader(session)
    downloader.download_ticket(ticket_id, target_dir)
