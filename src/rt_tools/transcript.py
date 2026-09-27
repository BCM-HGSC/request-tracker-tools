"""Chronological Markdown transcript for a downloaded RT ticket.

Renders `ticket.md`, an index over the downloaded ticket tree that answers
"who said what, when, with which attachment" in a single read. The tree
itself is unchanged; the transcript points into it with relative paths.

Rendering here is pure: it takes already-parsed data and returns text, so it
can be tested without an RT session or a filesystem.
"""

from dataclasses import dataclass
from dataclasses import field as dc_field
from re import MULTILINE, findall

from .parser import TicketMetadata

TRANSCRIPT_FILENAME = "ticket.md"

#: Structural version of the rendered transcript, carried in the frontmatter.
#: Bump only when the *structure* changes — frontmatter keys, heading grammar,
#: fence convention, attachment-block grammar. Adding a subsection or improving
#: what lands inside an existing block is additive and does not bump.
TRANSCRIPT_VERSION = 1

#: Body text is fenced so that a line of it can never be mistaken for the
#: transcript's own structure. Tildes rather than backticks because stray
#: backticks are common in email and stray tildes are not.
FENCE_CHAR = "~"
FENCE_INFO = "text"
MIN_FENCE = 4


@dataclass
class TranscriptAttachment:
    """One attachment as cited by the transcript.

    Args:
        id: RT attachment ID as string
        name: Original filename from the ticket attachment list
        size: Human-readable size string (e.g., "21.2k")
        path: Path to the saved file, relative to the ticket directory
        conversions: (sheet name, relative path) pairs for derived TSV files
    """

    id: str
    name: str
    size: str
    path: str
    conversions: list[tuple[str, str]] = dc_field(default_factory=list)


@dataclass
class TranscriptEntry:
    """One history entry as rendered by the transcript.

    Args:
        history_id: RT history item ID, also the subdirectory name
        creator: Username who created the entry
        created: RT-formatted timestamp (UTC, "2025-07-30 17:23:55")
        type: RT history type (e.g., "Create", "Correspond", "Status")
        description: RT's human-readable description of the event
        subject: RT's Data field, the email subject line; "" when absent
        content: Quote-stripped message body, None when the entry has none
        external_quotes: Quoted text with no RT entry of its own, preserved
            because this entry is its only record
        attachments: Attachments saved under this entry's directory
    """

    history_id: str
    creator: str
    created: str
    type: str
    description: str
    subject: str = ""
    content: str | None = None
    external_quotes: list[str] = dc_field(default_factory=list)
    attachments: list[TranscriptAttachment] = dc_field(default_factory=list)


def render_transcript(metadata: TicketMetadata, entries: list[TranscriptEntry]) -> str:
    """Render a complete ticket transcript as Markdown.

    Args:
        metadata: Ticket-level fields for the YAML frontmatter
        entries: History entries in chronological order

    Returns:
        Markdown text ending with a single trailing newline
    """
    sections = [_render_frontmatter(metadata)]
    sections.extend(_render_entry(entry) for entry in entries)
    # Each section ends with a blank line, which separates it from the next;
    # rstrip drops the one that would otherwise trail the whole document.
    return "\n".join(sections).rstrip("\n") + "\n"


def _render_frontmatter(metadata: TicketMetadata) -> str:
    """Render the YAML frontmatter block for a ticket."""
    lines = [
        "---",
        f"version: {TRANSCRIPT_VERSION}",
        f"id: {metadata.id}",
        f"subject: {_yaml_scalar(metadata.subject)}",
        f"queue: {_yaml_scalar(metadata.queue)}",
        f"status: {_yaml_scalar(metadata.status)}",
        f"owner: {_yaml_scalar(metadata.owner)}",
        f"requestors: [{', '.join(_yaml_scalar(r) for r in metadata.requestors)}]",
        f"created: {_yaml_scalar(metadata.created)}",
        f"last_updated: {_yaml_scalar(metadata.last_updated)}",
        "---",
        "",
    ]
    return "\n".join(lines)


def _render_entry(entry: TranscriptEntry) -> str:
    """Render one history entry: heading, description, body, attachments."""
    parts = [
        f"## {entry.history_id} — {entry.creator} — {entry.created} — {entry.type}",
        "",
    ]
    if entry.description:
        parts.extend([f"*{entry.description}*", ""])
    if entry.subject:
        parts.extend([f"Subject: {entry.subject}", ""])
    if entry.content:
        parts.extend(_render_fenced(entry.content.strip()))
        parts.append("")
    if entry.external_quotes:
        parts.extend(["**Quoted from outside this ticket**", ""])
        for quote in entry.external_quotes:
            parts.extend(_render_fenced(quote.strip()))
            parts.append("")
    if entry.attachments:
        parts.append("**Attachments**")
        for attachment in entry.attachments:
            parts.extend(_render_attachment(attachment))
        parts.append("")
    return "\n".join(parts)


def _render_fenced(body: str) -> list[str]:
    """Wrap untrusted body text in a fence long enough to contain it.

    CommonMark closes a fenced block only with a run of the same character at
    least as long as the opener, so sizing the fence to the body makes the
    block unambiguous without altering a single byte of the body. A parser
    reads the opening run's length and scans for the first line that is a run
    of at least that many tildes.
    """
    runs = findall(rf"^{FENCE_CHAR}{{3,}}", body, MULTILINE)
    length = max(MIN_FENCE, max((len(run) for run in runs), default=0) + 1)
    fence = FENCE_CHAR * length
    return [f"{fence}{FENCE_INFO}", body, fence]


def _render_attachment(attachment: TranscriptAttachment) -> list[str]:
    """Render one attachment bullet plus a sub-bullet per derived file."""
    lines = [
        f"- `{attachment.path}` — {attachment.name} ({attachment.size})",
    ]
    for sheet_name, tsv_path in attachment.conversions:
        lines.append(f'  - converted: `{tsv_path}` (sheet "{sheet_name}")')
    return lines


def _yaml_scalar(value: str) -> str:
    """Quote a value so it survives YAML frontmatter parsing.

    RT subjects routinely start with "[", which YAML would otherwise read as
    a flow sequence, and may contain colons and quotes.
    """
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'
