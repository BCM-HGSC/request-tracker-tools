"""RT response parsing utilities.

This module provides centralized parsing functionality for RT (Request Tracker)
server responses, including attachment lists, history items, and individual
history messages. All parsing functions return structured data using dataclasses
with string attributes to match RT API response format.

The module handles:
- Attachment metadata parsing from RT attachment lists
- History item filtering (excluding outgoing emails)
- Individual history message parsing including content and attachments
- Consistent string-based dataclass representation
"""

from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field as dc_field
from logging import getLogger
from re import DOTALL, compile, findall, search
from textwrap import dedent

logger = getLogger(__name__)


@dataclass
class AttachmentMeta:
    """Metadata for an RT attachment from attachment list.

    Args:
        name: Attachment filename or "(Unnamed)" for unnamed attachments
        mime_type: MIME type of the attachment (e.g., "application/pdf")
        size_str: Human-readable size string (e.g., "1.2k", "21.2k")
    """

    name: str
    mime_type: str
    size_str: str


def parse_attachment_list(text: str) -> dict[str, AttachmentMeta]:
    """Parse RT attachment list response into structured attachment metadata.

    Parses text format like:
    "456: Example.pdf (application/pdf / 21.2k),
     789: (Unnamed) (text/plain / 1.2k)"

    Args:
        text: Raw RT attachment list response text

    Returns:
        Dictionary mapping attachment IDs to AttachmentMeta objects
    """
    pattern = compile(r"(\d+): (.*?) \(([^/]+/[^/\s]+) / ([^\)]+)\)")
    result = {}

    for match in pattern.finditer(text):
        attachment_id, name, mime_type, size_str = match.groups()
        logger.debug(f"found {attachment_id}: {name} ({mime_type})")
        result[attachment_id] = AttachmentMeta(name, mime_type, size_str)

    return result


@dataclass
class HistoryItemMeta:
    """Metadata for an RT history item from history list.

    Args:
        history_id: RT history item ID as string
        history_event: Description of the history event (e.g., "Ticket created by user")
    """

    history_id: str
    history_event: str


def parse_history_list(text: str) -> Iterator[HistoryItemMeta]:
    """Parse the list of history items and generate the individual items,
    skipping items that are just outgoing email."""
    pattern = compile(r"(\d+): (.*)")

    for match in pattern.finditer(text):
        history_id, history_event = match.groups()
        if history_event != "Outgoing email recorded by RT_System":
            yield HistoryItemMeta(history_id, history_event)


@dataclass
class Attachment:
    """Individual attachment from RT history message.

    Args:
        id: Attachment ID as string
        name: Attachment filename or description
        size: Size string (e.g., "1.2k", "0b")
    """

    id: str
    name: str
    size: str


@dataclass
class HistoryMessage:
    """Complete RT history message with all fields and attachments.

    Represents a parsed individual history item from RT with all metadata
    and associated attachments. All fields are strings to match RT API format.

    Args:
        id: History message ID
        ticket: Ticket ID this history belongs to
        time_taken: Time taken for this action (usually "0")
        type: Type of history event (e.g., "Create", "Correspond")
        field: Field that was modified (None if not applicable)
        old_value: Previous value of modified field (None if not applicable)
        new_value: New value of modified field (None if not applicable)
        data: Additional data associated with the history item (None if not applicable)
        description: Human-readable description of the history event
        content: Message content/body (None if no content)
        creator: Username who created this history item
        created: Timestamp when this history item was created
        attachments: List of attachments associated with this history item
    """

    id: str
    ticket: str
    time_taken: str
    type: str
    field: str | None
    old_value: str | None
    new_value: str | None
    data: str | None
    description: str
    content: str
    creator: str
    created: str
    attachments: list[Attachment] = dc_field(default_factory=list)


def parse_history_message(text: str) -> HistoryMessage:
    """Parse individual RT history message into structured HistoryMessage object.

    Parses the complete RT history message format including all metadata fields,
    message content, and associated attachments. Handles multi-line content
    and properly extracts attachment information.

    Args:
        text: Raw RT history message response text

    Returns:
        HistoryMessage object with all parsed fields and attachments
    """
    logger.debug(repr(text))
    # Extract basic fields using regex
    id = search(r"id: (\d+)", text).group(1)
    ticket = search(r"Ticket: (\d+)", text).group(1)
    time_taken = search(r"TimeTaken: (\d+)", text).group(1)
    type_ = search(r"Type: (\w+)", text).group(1)
    field_ = search(r"Field: *(.*)", text).group(1).strip() or None
    old_value = search(r"OldValue: *(.*)", text).group(1).strip() or None
    new_value = search(r"NewValue: *(.*)", text).group(1).strip() or None
    data = search(r"Data: *(.*)", text).group(1).strip() or None
    description = search(r"Description: (.+)", text).group(1).strip()
    content_match = search(r"Content: (.*\n?)Creator:", text, DOTALL)
    if content_match:
        raw_content = content_match.group(1).removesuffix("\n\n\n")
        content = dedent("         " + raw_content)
    else:
        content = None
    creator = search(r"Creator: (.+)", text).group(1)
    created = search(r"Created: (.+)", text).group(1)

    # Extract attachments
    attachments = []
    attachment_matches = findall(r"(\d+): (.+?) \((.+?)\)", text)
    for match in attachment_matches:
        attachments.append(Attachment(id=match[0], name=match[1], size=match[2]))

    return HistoryMessage(
        id=id,
        ticket=ticket,
        time_taken=time_taken,
        type=type_,
        field=field_,
        old_value=old_value,
        new_value=new_value,
        data=data,
        description=description,
        content=content,
        creator=creator,
        created=created,
        attachments=attachments,
    )
