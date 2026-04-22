from unittest.mock import MagicMock

from rt_tools import RTSession, get_ticket_statuses
from rt_tools.parser import parse_ticket_status
from rt_tools.session import RTResponseData

TICKET_SHOW_TEMPLATE = b"""\
id: ticket/{ticket_id}
Queue: Submissions
Owner: Nobody
Creator: user001
Subject: Test ticket
Status: {status}
Priority: 0
InitialPriority: 0
FinalPriority: 0
Requestors: user001@example.com
Cc:
AdminCc:
Created: 2024-01-01 00:00:00
Starts: Not set
Started: Not set
Due: Not set
Resolved: Not set
Told: Not set
TimeEstimated: 0
TimeWorked: 0
TimeLeft: 0
"""


def _make_payload(ticket_id: str, status: str) -> bytes:
    return TICKET_SHOW_TEMPLATE.replace(b"{ticket_id}", ticket_id.encode()).replace(
        b"{status}", status.encode()
    )


def _make_ok_response(ticket_id: str, status: str) -> RTResponseData:
    return RTResponseData(
        version="4.4.3",
        status_code=200,
        status_text="Ok",
        is_ok=True,
        payload=_make_payload(ticket_id, status),
    )


def _make_error_response() -> RTResponseData:
    return RTResponseData(
        version="4.4.3",
        status_code=404,
        status_text="Not Found",
        is_ok=False,
        payload=b"No ticket found",
    )


def test_parse_ticket_status_open():
    assert parse_ticket_status(_make_payload("1", "open")) == "open"


def test_parse_ticket_status_new():
    assert parse_ticket_status(_make_payload("1", "new")) == "open"


def test_parse_ticket_status_stalled():
    assert parse_ticket_status(_make_payload("1", "stalled")) == "open"


def test_parse_ticket_status_resolved():
    assert parse_ticket_status(_make_payload("1", "resolved")) == "resolved"


def test_parse_ticket_status_deleted():
    assert parse_ticket_status(_make_payload("1", "deleted")) == "unknown"


def test_parse_ticket_status_missing_field():
    assert parse_ticket_status(b"id: ticket/1\nQueue: Submissions\n") == "unknown"


def test_parse_ticket_status_case_insensitive():
    assert parse_ticket_status(_make_payload("1", "Open")) == "open"
    assert parse_ticket_status(_make_payload("1", "Resolved")) == "resolved"


def test_get_ticket_statuses_single():
    session = MagicMock(spec=RTSession)
    session.fetch_rest.return_value = _make_ok_response("1234", "open")
    result = get_ticket_statuses(["1234"], session)
    assert result == {"1234": "open"}
    session.fetch_rest.assert_called_once_with("ticket", "1234")


def test_get_ticket_statuses_multiple():
    session = MagicMock(spec=RTSession)
    session.fetch_rest.side_effect = [
        _make_ok_response("1001", "open"),
        _make_ok_response("1002", "resolved"),
        _make_ok_response("1003", "stalled"),
    ]
    result = get_ticket_statuses(["1001", "1002", "1003"], session)
    assert result == {"1001": "open", "1002": "resolved", "1003": "open"}


def test_get_ticket_statuses_error_response():
    session = MagicMock(spec=RTSession)
    session.fetch_rest.return_value = _make_error_response()
    result = get_ticket_statuses(["9999"], session)
    assert result == {"9999": "unknown"}


def test_get_ticket_statuses_empty():
    session = MagicMock(spec=RTSession)
    result = get_ticket_statuses([], session)
    assert result == {}
    session.fetch_rest.assert_not_called()
