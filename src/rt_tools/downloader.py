"""RT ticket download automation."""

import logging
import re
from pathlib import Path

try:
    import openpyxl
except ImportError:
    openpyxl = None

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
        ├── {history_id}/     # Directory for each history entry
        │   ├── message.txt   # Individual history entry content
        │   ├── n{attachment_id}.{ext}  # Attachments for this history entry
        │   └── ...
        └── {history_id}/     # Additional history directories
            ├── message.txt
            ├── n{attachment_id}.{ext}
            └── ...

        Applies consistent filtering to both history items and attachments:
        - Skips outgoing emails (identified by X-RT-Loop-Prevention headers)
        - Skips zero-byte attachments
        - Uses MIME type from attachment list to determine file extensions

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

        # Download individual history items
        self._download_individual_history_items(ticket_id, target_dir)

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
        logger.info(f"Created {metadata_file}")

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
        logger.info(f"Created {history_file}")

    def _download_individual_history_items(
        self, ticket_id: str, target_dir: Path
    ) -> None:
        """Download individual history items to separate directories.

        Each history item is saved as {history_id}/message.txt, equivalent to:
        dump-ticket -q {ticket_id} history/id/{history_id} > {history_id}/message.txt
        """
        logger.debug(f"Downloading individual history items for ticket {ticket_id}")

        # Get basic history list to find all history IDs
        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'history')}"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get history list for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        # Parse history IDs from the basic list
        history_ids = self._parse_history_ids(rt_data.payload.decode("utf-8"))
        logger.debug(f"Found {len(history_ids)} history items to download")

        # Get detailed history entries to determine which ones to skip
        # We reuse the same logic as attachment processing for consistency
        detailed_history_entries = self._get_history_entries(ticket_id)

        # Create a set of history IDs to skip (outgoing emails)
        skip_history_ids = set()
        for history_entry in detailed_history_entries:
            if self._is_outgoing_email_history(history_entry, ticket_id):
                entry_id = history_entry.get("id")
                if entry_id:
                    skip_history_ids.add(entry_id)
                    logger.debug(f"Will skip history item {entry_id} (outgoing email)")

        # Download each history item individually (excluding outgoing emails)
        for history_id in history_ids:
            if history_id in skip_history_ids:
                logger.debug(f"Skipping outgoing email history item {history_id}")
                continue
            self._download_single_history_item(ticket_id, history_id, target_dir)

    def _download_single_history_item(
        self, ticket_id: str, history_id: str, target_dir: Path
    ) -> None:
        """Download a single history item to {history_id}/message.txt."""
        logger.debug(f"Downloading history item {history_id} for ticket {ticket_id}")

        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'history', 'id', history_id)}"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.warning(
                f"Failed to get history item {history_id} for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        # Create history ID directory and save message
        history_item_dir = target_dir / history_id
        history_item_dir.mkdir(exist_ok=True)

        message_file = history_item_dir / "message.txt"
        message_file.write_bytes(rt_data.payload)
        logger.info(f"Created {message_file}")

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

        # Process each history entry
        for history_entry in history_entries:
            if self._is_outgoing_email_history(history_entry, ticket_id):
                entry_id = history_entry.get("id", "unknown")
                logger.debug(f"Skipping outgoing email history entry {entry_id}")
                continue

            history_id = history_entry["id"]

            # Create history directory for this entry if it has attachments
            if history_entry.get("attachment_ids"):
                history_dir = target_dir / history_id
                history_dir.mkdir(exist_ok=True)

                # Download attachments for this history entry
                for attachment_id in history_entry.get("attachment_ids", []):
                    self._download_history_attachment(
                        ticket_id,
                        history_id,
                        attachment_id,
                        attachment_cache,
                        history_dir,
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

        Returns dict mapping attachment_id -> {filename, mime_type, size}
        """
        cache = {}
        for line in attachments_text.strip().split("\n"):
            # Remove "Attachments: " prefix if present, and trailing comma
            line = line.strip().rstrip(",")
            if line.startswith("Attachments: "):
                line = line[13:]  # Remove "Attachments: " prefix

            if ":" in line and re.match(r"^\d+:", line):
                # Extract ID, filename, and mime type - match last parentheses
                pattern = r"^(\d+):\s*(.*?)\s*\(([^)]+)\)$"
                match = re.match(pattern, line)
                if match:
                    attachment_id = match.group(1)
                    filename = match.group(2).strip()
                    type_and_size = match.group(3).strip()

                    # Extract MIME type and size from "mime/type / size" format
                    if " / " in type_and_size:
                        parts = type_and_size.split(" / ")
                        mime_type = parts[0].strip()
                        size_str = parts[1].strip() if len(parts) > 1 else ""
                    else:
                        mime_type = "application/octet-stream"
                        size_str = ""

                    # Clean up filename
                    if filename == "(Unnamed)" or not filename:
                        filename = ""

                    cache[attachment_id] = {
                        "filename": filename,
                        "mime_type": mime_type,
                        "size": size_str,
                    }

        logger.debug(f"Built attachment cache: {cache}")
        return cache

    def _get_history_entries(self, ticket_id: str) -> list[dict]:
        """Get detailed history entries with attachment information.

        Uses recursive fetching due to broken format=l parameter.
        Fetches basic history list first, then individual entries.
        """
        # Get basic history list first
        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'history')}"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get history list for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return []

        # Parse history IDs from the basic list
        history_ids = self._parse_history_ids(rt_data.payload.decode("utf-8"))
        logger.debug(f"Found {len(history_ids)} history entries to fetch")

        # Recursively fetch detailed information for each history entry
        detailed_entries = []
        for history_id in history_ids:
            entry = self._get_single_history_entry(ticket_id, history_id)
            if entry:
                detailed_entries.append(entry)

        logger.debug(
            f"Successfully fetched {len(detailed_entries)} detailed history entries"
        )
        return detailed_entries

    def _parse_history_ids(self, history_text: str) -> list[str]:
        """Parse history IDs from basic history list response.

        Parses text like:
        # 3/3 (/total)
        456: Ticket created by user@example.com
        457: Correspondence added by user@example.com
        458: Files added by support@example.com
        """
        history_ids = []
        for line in history_text.strip().split("\n"):
            if ":" in line and not line.strip().startswith("#"):
                # Extract ID from beginning of line
                match = re.match(r"^(\d+):", line.strip())
                if match:
                    history_ids.append(match.group(1))

        logger.debug(f"Parsed history IDs: {history_ids}")
        return history_ids

    def _get_single_history_entry(self, ticket_id: str, history_id: str) -> dict:
        """Get detailed information for a single history entry."""
        response = self.session.get(
            f"{self.session.rest_url('ticket', ticket_id, 'history', 'id', history_id)}"
        )
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.warning(
                f"Failed to get history entry {history_id} for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return None

        return self._parse_single_history_entry(rt_data.payload.decode("utf-8"))

    def _parse_single_history_entry(self, entry_text: str) -> dict:
        """Parse a single history entry from detailed format.

        Handles responses from /REST/1.0/ticket/{id}/history/id/{history_id}
        """
        entry = {"attachment_ids": []}

        lines = entry_text.split("\n")
        in_attachments_section = False

        for original_line in lines:
            line = original_line.strip()
            if not line:
                continue

            if line.startswith("id:"):
                entry["id"] = line.split(":", 1)[1].strip()
            elif line.startswith("Type:"):
                entry["type"] = line.split(":", 1)[1].strip()
            elif line.startswith("Content:"):
                entry["content"] = line.split(":", 1)[1].strip()
            elif line.startswith("Attachments:"):
                in_attachments_section = True
                # Parse attachment info on same line if present
                attachments_part = line.split(":", 1)[1].strip()
                if attachments_part:
                    attachment_ids = self._extract_attachment_ids_from_line(
                        attachments_part
                    )
                    entry["attachment_ids"].extend(attachment_ids)
            elif in_attachments_section:
                # Check if this line starts a new field (not indented)
                if not original_line.startswith((" ", "\t")):
                    # This line starts a new field, end attachments section
                    in_attachments_section = False
                else:
                    # Parse attachment line: "123: filename (size)"
                    attachment_ids = self._extract_attachment_ids_from_line(line)
                    entry["attachment_ids"].extend(attachment_ids)

        # Ensure we have an ID - if not, try to extract from header comment
        if "id" not in entry and "#" in entry_text:
            # Look for header like "# 70/70 (id/114856/total)"
            for line in lines:
                if line.strip().startswith("#") and "id/" in line:
                    match = re.search(r"id/(\d+)/", line)
                    if match:
                        entry["id"] = match.group(1)
                        break

        return entry if "id" in entry else None

    def _extract_attachment_ids_from_line(self, line: str) -> list[str]:
        """Extract attachment IDs from an attachment line."""
        ids = []
        # Look for patterns like "123: filename" or just "123:"
        matches = re.finditer(r"(\d+):", line)
        for match in matches:
            ids.append(match.group(1))
        return ids

    def _is_outgoing_email_history(self, history_entry: dict, ticket_id: str) -> bool:
        """Check if a history entry represents an outgoing email.

        Uses consistent logic with attachment filtering to identify RT-generated
        outgoing emails that should be excluded from downloads.

        Args:
            history_entry: Dictionary containing history entry information
            ticket_id: RT ticket ID for API calls if needed

        Returns:
            True if this history entry represents an outgoing email
        """
        # Check if this history entry has attachments
        attachment_ids = history_entry.get("attachment_ids", [])

        # If no attachments, this is not an outgoing email
        if not attachment_ids:
            return False

        # Check the first attachment to determine if this is an outgoing email history
        # Since outgoing emails typically have all attachments being outgoing emails,
        # checking the first one is sufficient to determine the history entry type
        first_attachment_id = attachment_ids[0]

        # Use the existing _is_outgoing_attachment method for consistency
        # This ensures both history and attachment filtering use identical logic
        return self._is_outgoing_attachment(ticket_id, first_attachment_id)

    def _download_history_attachment(
        self,
        ticket_id: str,
        history_id: str,
        attachment_id: str,
        attachment_cache: dict,
        history_dir: Path,
    ) -> None:
        """Download attachment using n{attachment_id} filename format."""
        logger.debug(
            f"Downloading attachment {attachment_id} from history {history_id} "
            f"for ticket {ticket_id}"
        )

        # Check if this attachment is zero-byte based on cached size info
        attachment_info = attachment_cache.get(attachment_id, {})
        size_str = attachment_info.get("size", "")
        if size_str == "0b":
            logger.debug(f"Skipping zero-byte attachment {attachment_id}")
            return

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
        mime_type = attachment_info.get("mime_type", "application/octet-stream")
        extension = self._mime_type_to_extension(mime_type)

        # Create filename: n{attachment_id}.{extension}
        filename = f"n{attachment_id}.{extension}"

        # Save attachment content
        attachment_file = history_dir / filename
        attachment_file.write_bytes(rt_data.payload)
        logger.info(f"Created {attachment_file}")

        # If this is an XLSX file, automatically convert to TSV
        if extension == "xlsx":
            tsv_filename = f"n{attachment_id}.tsv"
            tsv_file = history_dir / tsv_filename
            self._convert_xlsx_to_tsv(attachment_file, tsv_file)

    def _is_outgoing_attachment(self, ticket_id: str, attachment_id: str) -> bool:
        """Check if attachment represents an outgoing email to be excluded."""
        # Get attachment metadata to check for outgoing email indicators
        url = self.session.rest_url("ticket", ticket_id, "attachments", attachment_id)
        response = self.session.get(url)
        rt_data = parse_rt_response(response)

        if not rt_data.is_ok:
            logger.debug(f"Could not get metadata for attachment {attachment_id}")
            return False

        try:
            attachment_metadata = rt_data.payload.decode("utf-8")
        except UnicodeDecodeError:
            # If metadata contains non-UTF-8 data, it's likely binary content
            logger.debug(f"Attachment {attachment_id} metadata contains binary data")
            return False

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
            "text/plain": "txt",
            "text/html": "html",
            "text/csv": "csv",
            "application/pdf": "pdf",
            "application/msword": "doc",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",  # noqa: E501
            "application/vnd.ms-excel": "xls",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",  # noqa: E501
            "application/vnd.ms-powerpoint": "ppt",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation": "pptx",  # noqa: E501
            "application/zip": "zip",
            "application/x-zip-compressed": "zip",
            "application/gzip": "gz",
            "application/x-tar": "tar",
            "application/json": "json",
            "application/xml": "xml",
            "image/png": "png",
            "image/jpeg": "jpg",
            "image/gif": "gif",
            "image/svg+xml": "svg",
            "image/tiff": "tiff",
            "application/octet-stream": "bin",
        }

        return mime_to_ext.get(mime_type.lower(), "bin")

    def _convert_xlsx_to_tsv(self, xlsx_path: Path, tsv_path: Path) -> None:
        """Convert XLSX file to TSV format using openpyxl.

        Args:
            xlsx_path: Path to the source XLSX file
            tsv_path: Path where the TSV file should be saved
        """
        if not openpyxl:
            logger.warning("openpyxl not available, skipping XLSX conversion")
            return

        try:
            logger.debug(f"Converting {xlsx_path} to TSV format")
            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            worksheet = wb.active  # Use active worksheet

            with open(tsv_path, "w", encoding="utf-8") as f:
                for row in worksheet.rows:
                    values = [self._normalize_xlsx_value(cell) for cell in row]
                    f.write("\t".join(values) + "\n")

            logger.info(f"Created {tsv_path}")
            logger.debug("Successfully converted XLSX to TSV format")

        except Exception as e:
            logger.error(f"Failed to convert {xlsx_path} to TSV: {e}")

    def _normalize_xlsx_value(self, cell) -> str:
        """Normalize Excel cell value to string (from vxlsx script).

        Args:
            cell: openpyxl cell object

        Returns:
            String representation of cell value
        """
        value = cell.value
        if value is None:
            return ""
        return str(value)


def download_ticket(session: RTSession, ticket_id: str, target_dir: Path) -> None:
    """Convenience function to download a ticket using TicketDownloader.

    Args:
        session: Authenticated RTSession
        ticket_id: RT ticket ID (without 'ticket/' prefix)
        target_dir: Directory where ticket data should be saved
    """
    downloader = TicketDownloader(session)
    downloader.download_ticket(ticket_id, target_dir)
