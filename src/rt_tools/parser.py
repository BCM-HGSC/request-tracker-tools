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
from re import DOTALL, IGNORECASE, MULTILINE, compile, search
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

    attachments = _parse_attachments(text)

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


_ATTACHMENTS_HEADER = compile(r"^Attachments:[ \t]*$", MULTILINE)
_ATTACHMENT_LINE = compile(r"^[ \t]+(\d+): (.+?) \((.+?)\)[ \t]*$", MULTILINE)


def _parse_attachments(text: str) -> list[Attachment]:
    """Parse the indented lines of a history message's Attachments section.

    Scoped to that section deliberately. RT's Description line can carry the
    same "N: text (text)" shape — a link entry reads "Member #39174: Help
    deleting files (some detail) added by hale" — so scanning the whole
    message picked up a ticket number as an attachment id, and the download
    then failed with a KeyError against the ticket's attachment index.

    Args:
        text: Raw RT history message response text

    Returns:
        Attachments in the order RT listed them, empty when there are none
    """
    headers = list(_ATTACHMENTS_HEADER.finditer(text))
    if not headers:
        return []
    start = headers[-1].end()
    return [
        Attachment(id=id_, name=name, size=size)
        for id_, name, size in _ATTACHMENT_LINE.findall(text, start)
    ]


_HISTORY_COUNTER_PATTERN = compile(rb"\A# \d+/\d+ \([^)\n]*\)\n\n?")


def strip_history_counter(payload: bytes) -> bytes:
    """Remove RT's leading "# N/M (id/.../total)" counter line from a payload.

    RT prefixes each history item with a running counter over the whole
    history. Adding one entry to a ticket renumbers the counter in every
    item, so saving the counter makes a re-download look like every entry
    changed. The counter carries no information that is not already in
    history.txt.

    Args:
        payload: Raw history item payload bytes

    Returns:
        The payload without the counter line, unchanged if no counter is present
    """
    return _HISTORY_COUNTER_PATTERN.sub(b"", payload, count=1)


@dataclass
class TicketSummary:
    """One ticket from a format=l search result.

    All fields are strings to match RT API response format. Missing fields
    become the empty string rather than None, so the row is always writable.

    Args:
        id: Bare numeric ticket ID, with RT's "ticket/" prefix removed
        subject: Ticket subject line
        status: Raw RT status ("new", "open", "resolved", "rejected", ...)
        created: RT-formatted creation timestamp
        last_updated: RT-formatted last-update timestamp
        owner: Owner username, or "Nobody" for unowned tickets
        queue: Queue name (e.g., "Submissions")
    """

    id: str
    subject: str
    status: str
    created: str
    last_updated: str
    owner: str
    queue: str


def parse_search_results(payload: bytes) -> list[TicketSummary]:
    """Parse a search/ticket format=l response payload into ticket summaries.

    RT returns one "key: value" block per ticket, blocks separated by a line
    containing only "--". Values may continue onto following indented lines.

    Args:
        payload: Raw payload bytes from RTResponseData (RT header already stripped)

    Returns:
        List of TicketSummary objects, empty when nothing matched
    """
    text = payload.decode("utf-8", errors="replace")
    if _NO_MATCH_PATTERN.search(text):
        return []

    result = []
    for block in text.split("\n--\n"):
        fields = _parse_field_block(block)
        if not fields:
            continue
        result.append(
            TicketSummary(
                id=fields.get("id", "").removeprefix("ticket/"),
                subject=fields.get("subject", ""),
                status=fields.get("status", ""),
                created=fields.get("created", ""),
                last_updated=fields.get("lastupdated", ""),
                owner=fields.get("owner", ""),
                queue=fields.get("queue", ""),
            )
        )
    return result


def parse_queue_names(payload: bytes) -> list[str]:
    """Parse a search/queue response payload into queue names.

    RT returns one "{queue-id}: {queue-name}" line per queue.

    Args:
        payload: Raw payload bytes from RTResponseData (RT header already stripped)

    Returns:
        Queue names in the order RT returned them
    """
    text = payload.decode("utf-8", errors="replace")
    if _NO_MATCH_PATTERN.search(text):
        return []
    return [match.group(2) for match in _QUEUE_LINE_PATTERN.finditer(text)]


_QUEUE_LINE_PATTERN = compile(r"^(\d+): (.+)$", MULTILINE)
_NO_MATCH_PATTERN = compile(r"^No matching results\.", MULTILINE)
_FIELD_PATTERN = compile(r"^([A-Za-z][\w.{} ]*): ?(.*)$")


def _parse_field_block(block: str) -> dict[str, str]:
    """Parse one "key: value" block into a dict keyed by lowercased field name.

    Continuation lines (indented, no "key:" of their own) are appended to the
    preceding field, joined with a newline.
    """
    fields: dict[str, str] = {}
    current: str | None = None

    for line in block.split("\n"):
        if not line.strip():
            current = None
            continue
        m = _FIELD_PATTERN.match(line)
        if m:
            current = m.group(1).lower()
            fields[current] = m.group(2).strip()
        elif current is not None:
            fields[current] = f"{fields[current]}\n{line.strip()}".strip()

    return fields


@dataclass
class TicketMetadata:
    """Ticket-level fields from a ticket/{id} REST response.

    All fields are strings, matching RT API format, except requestors which
    RT may return as a comma- or newline-separated list. Missing fields
    become the empty string rather than None.

    Args:
        id: Bare numeric ticket ID, with RT's "ticket/" prefix removed
        subject: Ticket subject line
        queue: Queue name (e.g., "Submissions")
        status: Raw RT status ("new", "open", "resolved", ...)
        owner: Owner username, or "Nobody" for unowned tickets
        creator: Username who created the ticket
        requestors: Requestor addresses, empty when RT reported none
        created: RT-formatted creation timestamp
        last_updated: RT-formatted last-update timestamp
    """

    id: str
    subject: str
    queue: str
    status: str
    owner: str
    creator: str
    requestors: list[str]
    created: str
    last_updated: str


def parse_ticket_metadata(payload: bytes) -> TicketMetadata:
    """Parse a ticket/{id} REST response payload into ticket-level metadata.

    Args:
        payload: Raw payload bytes from RTResponseData (RT header already stripped)

    Returns:
        TicketMetadata with missing fields defaulted to the empty string
    """
    fields = _parse_field_block(payload.decode("utf-8", errors="replace"))
    return TicketMetadata(
        id=fields.get("id", "").removeprefix("ticket/"),
        subject=fields.get("subject", ""),
        queue=fields.get("queue", ""),
        status=fields.get("status", ""),
        owner=fields.get("owner", ""),
        creator=fields.get("creator", ""),
        requestors=_split_addresses(fields.get("requestors", "")),
        created=fields.get("created", ""),
        last_updated=fields.get("lastupdated", ""),
    )


def _split_addresses(value: str) -> list[str]:
    """Split an RT address field on commas and continuation newlines."""
    return [
        part.strip() for part in value.replace("\n", ",").split(",") if part.strip()
    ]


NO_CONTENT_SENTINEL = "This transaction appears to have no content"


def is_no_content(content: str | None) -> bool:
    """Report whether a history item's content is absent or RT's sentinel.

    RT returns the literal string "This transaction appears to have no
    content" for entries such as status changes and ownership assignments.
    """
    return not content or content.strip() == NO_CONTENT_SENTINEL


#: RT answers a request for a ticket that is not there with HTTP 200 and this
#: comment line as the whole body, so is_ok says nothing about whether the
#: ticket exists.
_MISSING_TICKET = compile(rb"^#\s*Ticket\s+\d+\s+does not exist\.", MULTILINE)


def is_missing_ticket(payload: bytes | None) -> bool:
    """Report whether an RT payload is the "no such ticket" response.

    Worth a dedicated check because RT signals this in the body rather than
    the status line: without it a typo'd ticket ID looks like a successful
    download of a ticket with no history.
    """
    return bool(payload) and _MISSING_TICKET.search(payload) is not None


_OPEN_STATUSES = {"new", "open", "stalled"}
_RESOLVED_STATUSES = {"resolved"}


def parse_ticket_status(payload: bytes) -> str:
    """Parse ticket status from a ticket/{id} REST response payload.

    Args:
        payload: Raw payload bytes from RTResponseData (RT header already stripped)

    Returns:
        "open" for new/open/stalled, "resolved" for resolved, "unknown" otherwise
    """
    text = payload.decode("utf-8", errors="replace")
    m = search(r"^Status:\s*(\S+)", text, MULTILINE)
    if not m:
        logger.warning("Status field not found in ticket response")
        return "unknown"
    status = m.group(1).lower()
    if status in _OPEN_STATUSES:
        return "open"
    if status in _RESOLVED_STATUSES:
        return "resolved"
    logger.warning(f"Unrecognized ticket status: {status!r}")
    return "unknown"


# Write operations


def build_content_block(fields: dict[str, str | list[str] | None]) -> str:
    """Render fields as the RFC822-ish block RT's write endpoints expect.

    Every RT write — ticket/new, ticket/{id}/comment, ticket/{id}/edit — posts
    a single form variable named "content" holding "key: value" one per line.
    A value spanning multiple lines continues with a leading space on each
    subsequent line, so a blank line inside a body is rendered as a line
    holding exactly one space. Without that, RT reads the blank line as the end
    of the field and silently drops the rest of the message.

    Fields whose value is None are omitted, which lets callers pass an optional
    field unconditionally. A list value is joined with ", " for RT's
    multi-address fields (Requestor, Cc, AdminCc).

    Args:
        fields: RT field names mapped to values, in the order RT should see them

    Returns:
        The block, newline-terminated. Never contains \\r\\n: RT rejects it.
    """
    lines: list[str] = []
    for key, value in fields.items():
        if value is None:
            continue
        if isinstance(value, list | tuple):
            value = ", ".join(str(item) for item in value if item)
        text = str(value).replace("\r\n", "\n").replace("\r", "\n")
        first, *rest = text.split("\n")
        lines.append(f"{key}: {first}")
        # A bare "" continuation would terminate the field; " " continues it.
        lines.extend(f" {line}" if line else " " for line in rest)
    return "\n".join(lines) + "\n"


def parse_content_block(text: str) -> dict[str, str]:
    """Parse an RT content block back into fields, inverting build_content_block().

    Needed because create-ticket takes the whole block from a file: to let a
    flag override a single field, and to preview what will be sent, the file
    has to be read as fields rather than passed through opaquely.

    Continuation lines — those starting with a space — are appended to the
    preceding field with the leading space removed. A line that is blank or
    starts with "#" is a comment and is dropped, which is what makes an
    $EDITOR template possible.

    Args:
        text: An RT content block

    Returns:
        Field names mapped to values, in the order they appeared

    Raises:
        ValueError: If a continuation line appears before any field, or a
            non-continuation line carries no colon
    """
    fields: dict[str, str] = {}
    last_key: str | None = None
    for number, line in enumerate(text.replace("\r\n", "\n").split("\n"), start=1):
        if line.startswith(" "):
            if last_key is None:
                raise ValueError(f"line {number}: continuation before any field")
            fields[last_key] += "\n" + line[1:]
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"line {number}: expected 'Field: value', got {line!r}")
        last_key = key.strip()
        fields[last_key] = value.strip()
    return fields


#: RT serves this page, with an HTTP 200, when its CSRF guard rejects a
#: request. Confirmed against the live server for POSTs sent without a Referer.
_CSRF_INTERSTITIAL = compile(rb"<title>Possible cross-site request forgery", IGNORECASE)


def is_csrf_interstitial(content: bytes | None) -> bool:
    """Report whether a response body is RT's CSRF rejection page.

    Like a missing ticket, RT signals this with a 200 and an unexpected body,
    so nothing in the status line gives it away. Worth naming because the
    generic "invalid RT response format" error points at the HTML rather than
    at the missing Referer that caused it.
    """
    return bool(content) and _CSRF_INTERSTITIAL.search(content) is not None


@dataclass
class WriteResult:
    """Outcome of an RT write, parsed from the response body.

    Args:
        ok: Whether RT reported the write as successful
        message: RT's own comment line, hash stripped, for logging and errors
        ticket_id: The new ticket ID for a create, None for every other write
    """

    ok: bool
    message: str
    ticket_id: str | None = None


#: "# Ticket 775 created." — the only write response carrying an id.
_TICKET_CREATED = compile(r"^#\s*Ticket\s+(\d+)\s+created\.", MULTILINE)

#: RT's success comments for comment/correspond, which carry no id.
_WRITE_SUCCEEDED = compile(
    r"^#\s*(Message recorded|Correspondence added|Comments added|"
    r"Ticket\s+\d+\s+updated)",
    MULTILINE,
)


def parse_write_response(payload: bytes) -> WriteResult:
    """Parse the body of an RT write response into a WriteResult.

    RT reports the real outcome of a write in the body, not the status line: a
    rejected create still arrives as "200 Ok" with "# Could not create ticket."
    as the payload. Anything not matching a known success comment is therefore
    treated as a failure rather than assumed fine.

    Args:
        payload: Raw payload bytes from RTResponseData (RT header stripped)

    Returns:
        WriteResult with ok, RT's comment line, and the new id for a create
    """
    text = payload.decode("utf-8", errors="replace").strip()
    message = "\n".join(
        line.lstrip("#").strip() for line in text.splitlines() if line.strip()
    )
    created = _TICKET_CREATED.search(text)
    if created:
        return WriteResult(ok=True, message=message, ticket_id=created.group(1))
    if _WRITE_SUCCEEDED.search(text):
        return WriteResult(ok=True, message=message)
    logger.warning(f"RT write not confirmed: {message!r}")
    return WriteResult(ok=False, message=message)


_QUOTE_BOUNDARY = r"(^|\n)(On .+, .+ wrote:|From: .+\nSent: )"
_OUTLOOK_BOUNDARY = r"(^|\n)From: .+\nSent: "


def split_quoted_reply(content: str) -> tuple[str, list[str]]:
    """Split content into new text plus quoted text worth preserving.

    `strip_quoted_reply()` discards everything from the first quote boundary
    onward, which is correct for RT quoting its own entries — the transcript
    holds those entries in full. It is wrong for a thread forwarded or CC'd
    into RT, where the quoted text is the only record of a message that never
    became its own history entry.

    This increment separates the two cheaply, by marker style: RT and webmail
    generate "On <date>, <user> wrote:" when quoting an RT entry, while an
    Outlook-style "From: ...\\nSent: ..." block is almost always a forwarded
    external thread. Matching quoted blocks back to sibling entries would be
    more robust; see the follow-up issue.

    Args:
        content: Dedented message content from parse_history_message()

    Returns:
        (new_content, external_quotes). `new_content` is what
        `strip_quoted_reply()` would return. `external_quotes` holds at most
        one block: the tail from the first Outlook-style marker, if any.
    """
    new_content = strip_quoted_reply(content)
    match = search(_OUTLOOK_BOUNDARY, content, MULTILINE)
    if not match:
        return new_content, []
    start = match.start() if content[match.start()] == "\n" else 0
    quoted = content[start:].strip()
    return new_content, [quoted] if quoted else []


def strip_quoted_reply(content: str) -> str:
    """Strip quoted reply sections, keeping only new content.

    RT emails include accumulated quoted replies using two patterns:
    - RT/webmail style: "On <date>, <username> wrote:"
    - Outlook style: "From: <sender>\\nSent: <date>"

    Since each history entry is preserved separately, quoted text is
    redundant.

    Args:
        content: Dedented message content from parse_history_message()

    Returns:
        Content up to the first quoted reply boundary, rstripped.
        Returns the original content rstripped if no quoting is found.
    """
    match = search(_QUOTE_BOUNDARY, content, MULTILINE)
    if match:
        cut = match.start() if content[match.start()] == "\n" else 0
        return content[:cut].rstrip()
    return content.rstrip()
