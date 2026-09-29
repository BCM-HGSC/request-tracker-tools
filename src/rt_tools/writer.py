"""RT write operations: create a ticket, comment on one, reply to one.

Every write is built before it is sent. `ticket_create_request()` and
`ticket_transaction_request()` return a `WriteRequest` — the endpoint and the
exact content block, and nothing else — which `send()` then posts. Splitting it
that way is what makes `--dry-run` and the confirmation preview honest: they
display the very object that would be sent, and neither needs a session, which
in turn makes both testable without touching RT.
"""

from dataclasses import dataclass
from logging import getLogger

from .parser import WriteResult, build_content_block, parse_write_response
from .session import RTSession

logger = getLogger(__name__)

#: Action field for an internal note. Mails nobody.
ACTION_COMMENT = "comment"

#: Action field for a reply. RT mails this to the requestors.
ACTION_CORRESPOND = "correspond"


@dataclass
class WriteRequest:
    """A write RT has not seen yet.

    Args:
        parts: REST URL path parts, e.g. ("ticket", "new")
        content: The content block to post as the "content" form variable
        summary: One line naming what this does, for previews and logging
        mails_requestors: Whether sending this causes RT to mail the
            requestors. Drives how loudly the confirmation prompt warns.
    """

    parts: tuple[str, ...]
    content: str
    summary: str
    mails_requestors: bool = False


def ticket_create_request(fields: dict[str, str]) -> WriteRequest:
    """Build the request that creates a ticket.

    Args:
        fields: RT fields for the new ticket — Queue, Subject, Requestor, Text,
            CF-*, and so on. Typically parser.parse_content_block() of a file,
            with any command-line overrides already applied.

    Returns:
        The unsent WriteRequest

    Raises:
        ValueError: If Queue is missing. RT would reject it, but it reports
            that as a 200 with an error comment, so catching it here gives a
            better message and costs nothing.
    """
    if not fields.get("Queue"):
        raise ValueError("Queue is required to create a ticket")
    # RT wants the id pseudo-field first, naming the endpoint rather than a
    # ticket. Rebuilt rather than mutated so the caller's dict is left alone.
    content = build_content_block({"id": "ticket/new"} | dict(fields))
    subject = fields.get("Subject", "(no subject)")
    return WriteRequest(
        parts=("ticket", "new"),
        content=content,
        summary=f"create ticket in queue {fields['Queue']}: {subject}",
        mails_requestors=True,
    )


def ticket_transaction_request(
    ticket_id: str,
    action: str,
    text: str,
    *,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    time_worked: str | None = None,
) -> WriteRequest:
    """Build the request that adds a comment or a reply to an existing ticket.

    Both go to the same endpoint and differ only in the Action field, which is
    also the difference between a note nobody is mailed and a reply everyone
    is. The caller names the action explicitly for that reason.

    Args:
        ticket_id: The ticket to write to
        action: ACTION_COMMENT or ACTION_CORRESPOND
        text: The message body
        cc: Addresses to Cc on this transaction only
        bcc: Addresses to Bcc on this transaction only
        time_worked: Minutes to record against the ticket

    Returns:
        The unsent WriteRequest

    Raises:
        ValueError: If action is not one of the two RT accepts, or text is empty
    """
    if action not in (ACTION_COMMENT, ACTION_CORRESPOND):
        raise ValueError(f"action must be comment or correspond, got {action!r}")
    if not text.strip():
        raise ValueError("refusing to send an empty message")
    content = build_content_block(
        {
            "id": ticket_id,
            "Action": action,
            "Text": text,
            "Cc": cc,
            "Bcc": bcc,
            "TimeWorked": time_worked,
        }
    )
    correspond = action == ACTION_CORRESPOND
    verb = "reply to" if correspond else "comment on"
    return WriteRequest(
        parts=("ticket", ticket_id, "comment"),
        content=content,
        summary=f"{verb} ticket {ticket_id}",
        # A Cc on a comment is still outbound mail, even though the requestors
        # are not on it.
        mails_requestors=correspond or bool(cc) or bool(bcc),
    )


def send(session: RTSession, request: WriteRequest) -> WriteResult:
    """Post a WriteRequest and return what RT reported.

    Args:
        session: Authenticated RTSession
        request: The request to send

    Returns:
        WriteResult; check .ok, since RT reports write failures in the body
        with a 200 status line
    """
    logger.info(f"sending: {request.summary}")
    response = session.post_rest(*request.parts, content=request.content)
    if not response.is_ok:
        return WriteResult(
            ok=False,
            message=f"RT returned {response.status_code} {response.status_text}",
        )
    return parse_write_response(response.payload)
