from collections.abc import Iterator
from dataclasses import dataclass
from dataclasses import field as dc_field
from logging import getLogger
from re import DOTALL, compile, findall, search
from textwrap import dedent

logger = getLogger(__name__)


@dataclass
class AttachmentMeta:
    name: str
    mime_type: str
    size_str: str


def parse_attachment_list(text: str) -> dict[str, AttachmentMeta]:
    pattern = compile(r"(\d+): (.*?) \(([^/]+/[^/\s]+) / ([^\)]+)\)")
    result = {}

    for match in pattern.finditer(text):
        attachment_id, name, mime_type, size_str = match.groups()
        logger.debug(f"found {attachment_id}: {name} ({mime_type})")
        result[attachment_id] = AttachmentMeta(name, mime_type, size_str)

    return result


@dataclass
class HistoryItemMeta:
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
    id: str
    name: str
    size: str


@dataclass
class HistoryMessage:
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
