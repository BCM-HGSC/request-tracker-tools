"""RT ticket download automation.

This module provides the TicketDownloader class for automated downloading of
complete RT ticket data to organized directory structures. The downloader
fetches all ticket metadata, history, and attachments while applying consistent
filtering to exclude outgoing emails and zero-byte attachments.

Key features:
- Downloads ticket metadata, history, and attachments in organized directory structure
- Filters out outgoing emails and zero-byte attachments
- Uses centralized parser for consistent data handling
- Automatically converts XLSX attachments to TSV format
- Provides comprehensive error handling and logging
- Supports both Path objects and string paths for target directories

The module integrates with the RT session module for authenticated API access
and uses the parser module for consistent response parsing.
"""

import logging
from dataclasses import dataclass
from dataclasses import field as dc_field
from mimetypes import guess_extension
from pathlib import Path
from re import compile as compile_pattern

try:
    import openpyxl
except ImportError:
    openpyxl = None

from .parser import (
    is_missing_ticket,
    is_no_content,
    parse_attachment_list,
    parse_history_list,
    parse_history_message,
    parse_ticket_metadata,
    split_quoted_reply,
    strip_history_counter,
    strip_quoted_reply,
)
from .session import RTSession
from .transcript import (
    TRANSCRIPT_FILENAME,
    TranscriptAttachment,
    TranscriptEntry,
    render_transcript,
)

logger = logging.getLogger(__name__)

#: Files the downloader writes at the top of a ticket directory. Anything else
#: found there -- analysis.yaml, a note, whatever an --into DIR already held --
#: is not ours and --clean leaves it alone.
TICKET_FILES = ("metadata.txt", "history.txt", "attachments.txt", TRANSCRIPT_FILENAME)

#: Files the downloader writes inside a {history_id}/ directory.
ENTRY_FILES = ("message.txt", "content.txt")

#: Attachments and their conversions: n{attachment_id}.{ext}, including the
#: n{id}.{sheet}.tsv form a multi-sheet workbook produces.
ATTACHMENT_PATTERN = compile_pattern(r"n\d+\..+")


@dataclass
class SavedAttachment:
    """An attachment written to disk, plus any files derived from it.

    Args:
        path: Absolute path to the saved attachment
        conversions: (sheet name, TSV path) pairs for XLSX conversions
    """

    path: Path
    conversions: list[tuple[str, Path]] = dc_field(default_factory=list)


class TicketDownloader:
    """Downloads complete RT ticket data to organized directory structure."""

    def __init__(self, session: RTSession):
        """Initialize TicketDownloader with authenticated RT session.

        Args:
            session: Authenticated RTSession for making RT API calls
        """
        self.session = session
        #: Files the current download_ticket call has written. Reset per call
        #: and consulted only by the --clean pass.
        self._written: set[Path] = set()

    def download_ticket(
        self,
        ticket_id: str,
        target_dir: Path,
        *,
        create_ticket_dir: bool = True,
        transcript: bool = False,
        prune: bool = False,
        lean: bool = False,
        clean: bool = False,
    ) -> None:
        """Download all relevant content for a ticket to target directory.

        Creates directory structure:
        target_dir/
        └── rt{ticket_id}/    # Ticket subdirectory
            ├── ticket.md         # Chronological transcript (only with transcript=True)
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
            target_dir: Parent directory where rt{ticket_id} subdirectory will be
                created, or the ticket directory itself when create_ticket_dir
                is False
            create_ticket_dir: Create an rt{ticket_id} level under target_dir
            transcript: Also write ticket.md, a chronological Markdown index
            prune: Skip message.txt and content.txt, whose information the
                transcript already carries, and remove history directories
                left empty. After pruning, a history directory exists if and
                only if the entry had at least one non-empty attachment.
                Requires transcript.
            lean: Additionally skip downloading the (Unnamed) text/html body
                alternates that no mode cites in the transcript. Implies
                transcript and prune. ticket.md is byte-identical across all
                three modes; they differ only in the files beside it.
            clean: After a complete download, delete the downloader's own
                files that this run did not write, making a re-download into
                an existing tree equivalent to one into an empty directory.
                Skipped when the download aborts early, so a failed run never
                deletes what it merely did not reach.
        """
        if lean:
            transcript = True
            prune = True
        self._written = set()
        target_dir = Path(target_dir)
        ticket_dir = target_dir / f"rt{ticket_id}" if create_ticket_dir else target_dir
        ticket_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading ticket {ticket_id} to {ticket_dir}")

        # Download ticket metadata
        metadata_payload = self._download_metadata(ticket_id, ticket_dir)
        if not metadata_payload:
            logger.error(
                f"No metadata for ticket {ticket_id}, skipping remaining downloads"
            )
            return

        attachment_list_payload = self._download_attachment_ist(ticket_id, ticket_dir)
        if not attachment_list_payload:
            logger.error(
                f"Failed to get attachment list for ticket {ticket_id}, "
                f"skipping downloads"
            )
            return
        # RT serves UTF-8, and attachment filenames routinely carry em dashes
        # and curly quotes out of Word, Outlook or macOS. errors="replace"
        # keeps one odd byte from costing the whole ticket.
        attachment_index = parse_attachment_list(
            attachment_list_payload.decode("utf-8", errors="replace")
        )

        # Download ticket history and cache the payload for reuse
        history_payload = self._download_history(ticket_id, ticket_dir)
        if not history_payload:
            logger.error(
                f"Failed to get history for ticket {ticket_id}, "
                f"skipping remaining downloads"
            )
            return

        history_text = history_payload.decode("utf-8", errors="replace")
        logger.debug(f"Downloading individual history items for ticket {ticket_id}")
        entries: list[TranscriptEntry] = []
        for history_meta in parse_history_list(history_text):
            history_id = history_meta.history_id
            history_item_payload = self._download_individual_history_item(
                ticket_id, ticket_dir, history_id, write_message=not prune
            )
            if not history_item_payload:
                continue
            history_item_text = history_item_payload.decode("utf-8", errors="replace")
            history_message = parse_history_message(history_item_text)
            if not prune:
                self._save_stripped_content(
                    ticket_dir, history_id, history_message.content
                )
            content, external_quotes = _entry_body(history_message)
            transcript_attachments = []
            for attachment in history_message.attachments:
                if attachment.size == "0b":
                    continue
                meta = attachment_index.get(attachment.id)
                if meta is None:
                    logger.warning(
                        f"Attachment {attachment.id} cited by history "
                        f"{history_id} is not in the attachment index for "
                        f"ticket {ticket_id}; skipping"
                    )
                    continue
                redundant = is_redundant_html_alternate(meta, content is not None)
                if redundant and lean:
                    logger.debug(
                        f"Skipping redundant HTML alternate {attachment.id} "
                        f"for history {history_id}"
                    )
                    continue
                saved = self._download_history_attachment(
                    ticket_id,
                    ticket_dir,
                    history_id,
                    attachment.id,
                    meta.mime_type,
                )
                if saved and not redundant:
                    transcript_attachments.append(
                        self._describe_attachment(
                            ticket_dir, attachment.id, meta, saved
                        )
                    )
            if prune:
                self._prune_history_dir(ticket_dir, history_id)
            entries.append(
                self._build_transcript_entry(
                    history_id,
                    history_message,
                    content,
                    external_quotes,
                    transcript_attachments,
                )
            )

        if transcript:
            self._write_transcript(ticket_dir, metadata_payload, entries)

        if clean:
            self._clean_tree(ticket_dir)

        logger.info(f"Completed downloading ticket {ticket_id}")

    def _clean_tree(self, ticket_dir: Path) -> None:
        """Delete the downloader's own files that this run did not write.

        Scoped deliberately: only the filenames this downloader produces are
        candidates, so an analysis.yaml sitting in the ticket directory or an
        unrelated file under an --into DIR survives. The downloader cleans up
        after itself, and only after itself.

        Deletion is driven by the set of paths actually written, not by
        re-deriving what should have been written, so a converted
        n{id}.{sheet}.tsv this run produced is never mistaken for an orphan.
        """
        for filename in TICKET_FILES:
            path = ticket_dir / filename
            if path.exists() and path not in self._written:
                self._remove_orphan(path)
        for history_dir in sorted(ticket_dir.iterdir()):
            if not history_dir.is_dir() or not history_dir.name.isdigit():
                continue
            for path in sorted(history_dir.iterdir()):
                if path in self._written or not path.is_file():
                    continue
                if is_downloader_entry_file(path.name):
                    self._remove_orphan(path)
            if not any(history_dir.iterdir()):
                history_dir.rmdir()
                logger.debug(f"Removed stale empty {history_dir}")

    def _remove_orphan(self, path: Path) -> None:
        """Delete one file left behind by an earlier download."""
        path.unlink()
        logger.info(f"Removed stale {path}")

    def _prune_history_dir(self, ticket_dir: Path, history_id: str) -> None:
        """Remove transcript-redundant files from one history directory.

        Deletes only message.txt and content.txt, then removes the directory
        itself if that left it empty. Attachments, converted TSVs, and
        anything else the downloader did not put there are never touched.
        Handles re-downloading over a tree written by an earlier unpruned run.
        """
        history_dir = ticket_dir / history_id
        for filename in ("message.txt", "content.txt"):
            path = history_dir / filename
            if path.exists():
                path.unlink()
                logger.debug(f"Pruned {path}")
        if not any(history_dir.iterdir()):
            history_dir.rmdir()
            logger.debug(f"Pruned empty {history_dir}")

    def _write_transcript(
        self,
        ticket_dir: Path,
        metadata_payload: bytes | None,
        entries: list[TranscriptEntry],
    ) -> None:
        """Render and write ticket.md at the top of the ticket directory."""
        if not metadata_payload:
            logger.warning("No ticket metadata available, skipping transcript")
            return
        metadata = parse_ticket_metadata(metadata_payload)
        transcript_file = ticket_dir / TRANSCRIPT_FILENAME
        transcript_file.write_text(
            render_transcript(metadata, entries), encoding="utf-8"
        )
        self._created(transcript_file)

    def _build_transcript_entry(
        self,
        history_id: str,
        history_message,
        content: str | None,
        external_quotes: list[str],
        attachments: list[TranscriptAttachment],
    ) -> TranscriptEntry:
        """Build one transcript entry from a parsed history message."""
        return TranscriptEntry(
            history_id=history_id,
            creator=history_message.creator,
            created=history_message.created,
            type=history_message.type,
            description=history_message.description,
            subject=_entry_subject(history_message),
            content=content,
            external_quotes=external_quotes,
            attachments=attachments,
        )

    def _describe_attachment(
        self,
        ticket_dir: Path,
        attachment_id: str,
        meta,
        saved: "SavedAttachment",
    ) -> TranscriptAttachment:
        """Describe a saved attachment with ticket-directory-relative paths."""
        return TranscriptAttachment(
            id=attachment_id,
            name=meta.name,
            size=meta.size_str,
            path=saved.path.relative_to(ticket_dir).as_posix(),
            conversions=[
                (sheet_name, tsv_path.relative_to(ticket_dir).as_posix())
                for sheet_name, tsv_path in saved.conversions
            ],
        )

    def _download_metadata(self, ticket_id: str, target_dir: Path) -> bytes | None:
        """Download ticket metadata to metadata.txt and return payload for reuse.

        Returns:
            Metadata payload bytes if successful, None if failed
        """
        logger.debug(f"Downloading metadata for ticket {ticket_id}")

        rt_data = self.session.fetch_rest("ticket", ticket_id)

        if not rt_data.is_ok:
            logger.error(
                f"Failed to get metadata for ticket {ticket_id}: "
                f"{rt_data.status_code} {rt_data.status_text}"
            )
            return None

        # RT reports a missing ticket in the body, with a 200 status. Checked
        # before writing anything: a typo'd ticket ID used to overwrite the
        # metadata of whatever tree it was pointed at with the error text.
        if is_missing_ticket(rt_data.payload):
            logger.error(f"Ticket {ticket_id} does not exist")
            return None

        metadata_file = target_dir / "metadata.txt"
        metadata_file.write_bytes(rt_data.payload)
        self._created(metadata_file)

        return rt_data.payload

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
        self._created(history_file)

        return rt_data.payload

    def _download_individual_history_item(
        self,
        ticket_id: str,
        target_dir: Path,
        history_id: str,
        write_message: bool = True,
    ) -> bytes | None:
        """Download an individual history item to its directory.

        Each history item is saved as {history_id}/message.txt, equivalent to:
        dump-ticket -q {ticket_id} history/id/{history_id} > {history_id}/message.txt

        RT's leading "# N/M (id/.../total)" counter is stripped before saving,
        so adding one entry to a ticket does not rewrite every message.txt.

        Args:
            ticket_id: RT ticket ID
            target_dir: Directory to save files
            history_id: history item ID
            write_message: Save message.txt. The payload is returned either
                way, since the parse of it drives everything downstream.
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
        # Create history ID directory; attachments land here even when pruning
        history_item_dir = target_dir / history_id
        history_item_dir.mkdir(exist_ok=True)
        if write_message:
            message_file = history_item_dir / "message.txt"
            message_file.write_bytes(strip_history_counter(rt_data.payload))
            self._created(message_file)
        return rt_data.payload

    def _save_stripped_content(
        self, target_dir: Path, history_id: str, content: str | None
    ) -> None:
        """Save non-quoted message content to content.txt.

        Skips saving if content is None or entirely quoted (empty after strip).
        """
        if not content:
            return
        stripped = strip_quoted_reply(content)
        if not stripped:
            return
        content_file = target_dir / history_id / "content.txt"
        content_file.write_text(stripped + "\n", encoding="utf-8")
        self._created(content_file)

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
            return None

        metadata_file = target_dir / "attachments.txt"
        metadata_file.write_bytes(rt_data.payload)
        self._created(metadata_file)

        return rt_data.payload

    def _download_history_attachment(
        self,
        ticket_id: str,
        target_dir: Path,
        history_id: str,
        attachment_id: str,
        mime_type: str,
    ) -> "SavedAttachment | None":
        """Download attachment using n{attachment_id} filename format.

        Returns:
            SavedAttachment describing the saved file and any derived TSV
            files, or None if the download failed
        """
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
            return None

        extension = self._mime_type_to_extension(mime_type)

        # Create filename: n{attachment_id}.{extension}
        filename = f"n{attachment_id}.{extension}"

        # Save attachment content
        attachment_file = target_dir / history_id / filename
        attachment_file.write_bytes(rt_data.payload)
        self._created(attachment_file)

        # If this is an XLSX file, automatically convert to TSV
        conversions = []
        if extension == "xlsx":
            conversions = self._convert_xlsx_to_tsv(attachment_file)

        return SavedAttachment(path=attachment_file, conversions=conversions)

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

        # The table stays authoritative, since it encodes choices the stdlib
        # does not make (x-zip-compressed -> zip, jpeg -> jpg). Falling back to
        # mimetypes covers the long tail for free: a text/tab-separated-values
        # attachment was landing as an opaque .bin.
        mime_type = mime_type.split(";")[0].strip().lower()
        if mime_type in mime_to_ext:
            return mime_to_ext[mime_type]
        guessed = guess_extension(mime_type)
        return guessed.removeprefix(".") if guessed else "bin"

    def _convert_xlsx_to_tsv(self, xlsx_path: Path) -> list[tuple[str, Path]]:
        """Convert every worksheet of an XLSX file to TSV using openpyxl.

        A single-sheet workbook produces n{id}.tsv, as before. A workbook with
        more than one sheet produces n{id}.{sheet}.tsv per sheet and no bare
        n{id}.tsv, because silently attaching one sheet's data to the
        unqualified name is exactly the ambiguity being avoided.

        Args:
            xlsx_path: Path to the source XLSX file

        Returns:
            (sheet name, TSV path) pairs for each sheet written, empty on failure
        """
        if not openpyxl:
            logger.warning("openpyxl not available, skipping XLSX conversion")
            return []

        try:
            logger.debug(f"Converting {xlsx_path} to TSV format")
            wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
            sheet_names = wb.sheetnames
            if len(sheet_names) > 1:
                logger.warning(
                    f"{xlsx_path.name} has {len(sheet_names)} worksheets "
                    f"({', '.join(sheet_names)}); converting each separately"
                )

            written = []
            for sheet_name in sheet_names:
                tsv_path = self._tsv_path_for_sheet(
                    xlsx_path, sheet_name, qualify=len(sheet_names) > 1
                )
                self._write_worksheet_tsv(wb[sheet_name], tsv_path)
                self._created(tsv_path)
                written.append((sheet_name, tsv_path))

            return written

        except Exception as e:
            logger.error(f"Failed to convert {xlsx_path} to TSV: {e}")
            return []

    def _write_worksheet_tsv(self, worksheet, tsv_path: Path) -> None:
        """Write one worksheet to a TSV file, one row per line."""
        with open(tsv_path, "w", encoding="utf-8") as f:
            for row in worksheet.rows:
                values = [self._normalize_xlsx_value(cell) for cell in row]
                f.write("\t".join(values) + "\n")

    def _tsv_path_for_sheet(
        self, xlsx_path: Path, sheet_name: str, qualify: bool
    ) -> Path:
        """Build the TSV path for one worksheet of an XLSX attachment."""
        if not qualify:
            return xlsx_path.with_suffix(".tsv")
        slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in sheet_name)
        return xlsx_path.with_name(f"{xlsx_path.stem}.{slug}.tsv")

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

    def _created(self, path: Path) -> None:
        """Log a file this run wrote and record it for the --clean pass.

        Every file the downloader produces goes through here, which is what
        makes "delete our own files this run did not write" a complete rule
        rather than a list that can drift.
        """
        self._written.add(path)
        logger.info(f"Created {path}")


# Cleanup helpers


def is_downloader_entry_file(name: str) -> bool:
    """Report whether a file inside {history_id}/ is one the downloader writes.

    Only these are candidates for --clean. A file the downloader never
    produces -- a hand-written note, an analysis artifact -- is left alone
    even when it sits in a directory the downloader created.
    """
    return name in ENTRY_FILES or ATTACHMENT_PATTERN.fullmatch(name) is not None


# Transcript helpers

#: RT's placeholder for a mail with no Subject header. Rendering it would put
#: a line carrying no information on most Correspond entries.
_NO_SUBJECT = "No Subject"


def _entry_subject(history_message) -> str:
    """Return the entry's email subject line, or "" when there is none."""
    subject = (history_message.data or "").strip()
    return "" if subject == _NO_SUBJECT else subject


def _entry_body(history_message) -> tuple[str | None, list[str]]:
    """Split a history message into transcript body and preserved quotes.

    RT's no-content sentinel becomes None, so such an entry renders as its
    description alone. The sentinel is still written verbatim to content.txt,
    which keeps existing consumers unchanged.
    """
    content = history_message.content
    if is_no_content(content):
        return None, []
    body, external_quotes = split_quoted_reply(content)
    return body or None, external_quotes


def is_redundant_html_alternate(meta, entry_has_content: bool) -> bool:
    """Report whether an attachment is just the HTML twin of the entry body.

    Every RT `Correspond` entry sourced from a multipart email carries an
    unnamed text/html part holding the same words as the entry text. Citing it
    in the transcript adds a path and no information.

    The `entry_has_content` guard is the important half: when the entry has no
    text body, the HTML part is the only record of what was said, so it is kept
    and cited. That way the transcript never omits an entry's only content.
    """
    return (
        entry_has_content
        and meta.name == "(Unnamed)"
        and meta.mime_type.split(";")[0].strip().lower() == "text/html"
    )


def download_ticket(
    session: RTSession,
    ticket_id: str,
    target_dir: Path,
    *,
    create_ticket_dir: bool = True,
    transcript: bool = False,
    prune: bool = False,
    lean: bool = False,
    clean: bool = False,
) -> None:
    """Convenience function to download a ticket using TicketDownloader.

    Args:
        session: Authenticated RTSession
        ticket_id: RT ticket ID (without 'ticket/' prefix)
        target_dir: Parent directory where rt{ticket_id} subdirectory will be
            created, or the ticket directory itself when create_ticket_dir is
            False
        create_ticket_dir: Create an rt{ticket_id} level under target_dir
        transcript: Also write ticket.md, a chronological Markdown index
        prune: Skip message.txt and content.txt and remove emptied history
            directories; requires transcript
        lean: Also skip the redundant HTML body alternates; implies transcript
            and prune
        clean: Delete the downloader's own files this run did not write, so a
            re-download into an existing tree leaves no orphans
    """
    downloader = TicketDownloader(session)
    downloader.download_ticket(
        ticket_id,
        target_dir,
        create_ticket_dir=create_ticket_dir,
        lean=lean,
        transcript=transcript,
        prune=prune,
        clean=clean,
    )
