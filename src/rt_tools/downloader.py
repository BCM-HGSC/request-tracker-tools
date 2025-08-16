"""RT ticket download automation."""

import logging
from pathlib import Path

try:
    import openpyxl
except ImportError:
    openpyxl = None

from .parser import parse_attachment_list, parse_history_list, parse_history_message
from .session import RTSession

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

        attachment_list_payload = self._download_attachment_ist(ticket_id, target_dir)
        attachment_index = parse_attachment_list(
            attachment_list_payload.decode("ascii")
        )

        # Download ticket history and cache the payload for reuse
        history_payload = self._download_history(ticket_id, target_dir)
        if not history_payload:
            logger.error(
                f"Failed to get history for ticket {ticket_id}, "
                f"skipping remaining downloads"
            )
            return

        history_text = history_payload.decode("utf-8")
        logger.debug(f"Downloading individual history items for ticket {ticket_id}")
        for history_meta in parse_history_list(history_text):
            history_id = history_meta.history_id
            history_item_payload = self._download_individual_history_item(
                ticket_id, target_dir, history_id
            )
            history_item_text = history_item_payload.decode("ascii")
            history_message = parse_history_message(history_item_text)
            for attachment in history_message.attachments:
                if attachment.size != "0b":
                    mime_type = attachment_index[attachment.id].mime_type
                    self._download_history_attachment(
                        ticket_id,
                        target_dir,
                        history_id,
                        attachment.id,
                        mime_type,
                    )
                    pass  # TODO

        logger.info(f"Completed downloading ticket {ticket_id}")

    def _download_metadata(self, ticket_id: str, target_dir: Path) -> None:
        """Download ticket metadata to metadata.txt."""
        logger.debug(f"Downloading metadata for ticket {ticket_id}")

        rt_data = self.session.fetch_rest("ticket", ticket_id)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get metadata for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        metadata_file = target_dir / "metadata.txt"
        metadata_file.write_bytes(rt_data.payload)
        logger.info(f"Created {metadata_file}")

    def _download_history(self, ticket_id: str, target_dir: Path) -> bytes | None:
        """Download ticket history to history.txt and return payload for reuse.

        Returns:
            History payload bytes if successful, None if failed
        """
        logger.debug(f"Downloading history for ticket {ticket_id}")

        rt_data = self.session.fetch_rest("ticket", ticket_id, "history")

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get history for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return None

        history_file = target_dir / "history.txt"
        history_file.write_bytes(rt_data.payload)
        logger.info(f"Created {history_file}")

        return rt_data.payload

    def _download_individual_history_item(
        self, ticket_id: str, target_dir: Path, history_id: str
    ) -> bytes | None:
        """Download an individual history item to its directory.

        Each history item is saved as {history_id}/message.txt, equivalent to:
        dump-ticket -q {ticket_id} history/id/{history_id} > {history_id}/message.txt

        Args:
            ticket_id: RT ticket ID
            target_dir: Directory to save files
            history_id: history item ID
        """
        logger.debug(f"Downloading history item {history_id} for ticket {ticket_id}")
        rt_data = self.session.fetch_rest(
            "ticket", ticket_id, "history", "id", history_id
        )
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
        return rt_data.payload

    def _download_attachment_ist(
        self, ticket_id: str, target_dir: Path
    ) -> bytes | None:
        """Download attachment list from ticket.

        Args:
            ticket_id: RT ticket ID
            target_dir: Directory to save attachments.txt
        """
        logger.debug(f"Downloading attachment list for ticket {ticket_id}")
        rt_data = self.session.fetch_rest("ticket", ticket_id, "attachments")

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get attachment list for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )

        metadata_file = target_dir / "attachments.txt"
        metadata_file.write_bytes(rt_data.payload)
        logger.info(f"Created {metadata_file}")

        return rt_data.payload

    def _download_history_attachment(
        self,
        ticket_id: str,
        target_dir: Path,
        history_id: str,
        attachment_id: str,
        mime_type: str,
    ) -> None:
        """Download attachment using n{attachment_id} filename format."""
        logger.debug(
            f"Downloading attachment {attachment_id} from history {history_id} "
            f"for ticket {ticket_id}"
        )

        rt_data = self.session.fetch_rest(
            "ticket", ticket_id, "attachments", attachment_id, "content"
        )

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get content for attachment {attachment_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return

        extension = self._mime_type_to_extension(mime_type)

        # Create filename: n{attachment_id}.{extension}
        filename = f"n{attachment_id}.{extension}"

        # Save attachment content
        attachment_file = target_dir / history_id / filename
        attachment_file.write_bytes(rt_data.payload)
        logger.info(f"Created {attachment_file}")

        # If this is an XLSX file, automatically convert to TSV
        if extension == "xlsx":
            tsv_file = attachment_file.with_suffix(".tsv")
            self._convert_xlsx_to_tsv(attachment_file, tsv_file)

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
