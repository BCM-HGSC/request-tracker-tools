"""Tests for the search-tickets command and its supporting functions."""

import io
from datetime import date
from unittest.mock import MagicMock

import pytest
from requests import Response

from rt_tools.cli import (
    SEARCH_FIELDS,
    build_ticket_query,
    resolve_queues,
    validate_queues,
    write_ticket_tsv,
)
from rt_tools.parser import TicketSummary, parse_queue_names, parse_search_results
from rt_tools.session import (
    BASE_URL,
    RTResponseData,
    RTResponseError,
    RTSession,
    fetch_queue_names,
    search_tickets,
)

BOTH_QUEUES = "( Queue = 'Managed File Transfer' OR Queue = 'Submissions' )"

KNOWN_QUEUES = ["General", "Managed File Transfer", "Submissions"]

QUEUE_PAYLOAD = b"1: General\n8: Managed File Transfer\n6: Submissions\n\n\n"

SEARCH_PAYLOAD = b"""\

id: ticket/37525
Subject: Delivery of WGS data
Status: resolved
Created: Mon Aug 04 14:22:11 2026
LastUpdated: Tue Aug 12 09:01:45 2026
Owner: hale
Queue: Submissions

--

id: ticket/37603
Subject: MFT account request
Status: open
Created: Wed Aug 06 08:15:00 2026
LastUpdated: Wed Aug 06 08:15:00 2026
Owner: Nobody
Queue: Managed File Transfer

"""


def test_fetch_rest_params_sends_referer():
    """RT serves an HTML CSRF interstitial without a same-origin Referer."""
    session = MagicMock()
    session.get.return_value = _raw_response(
        b"RT/4.4.3 200 Ok\n\nid: ticket/42\n",
        "https://rt.hgsc.bcm.edu/REST/1.0/search/ticket?query=id+%3D+42",
    )

    result = RTSession.fetch_rest_params(
        session, "search", "ticket", params={"query": "id = 42"}
    )

    assert result.is_ok
    (url,) = session.get.call_args.args
    assert url == "https://rt.hgsc.bcm.edu/REST/1.0/search/ticket"
    assert session.get.call_args.kwargs["params"] == {"query": "id = 42"}
    assert session.get.call_args.kwargs["headers"] == {"Referer": f"{BASE_URL}/"}


def test_search_tickets_sends_expected_params():
    session = MagicMock(spec=RTSession)
    session.fetch_rest_params.return_value = _ok_response(SEARCH_PAYLOAD)

    result = search_tickets(session, "Queue = 'Submissions'", SEARCH_FIELDS)

    assert result.is_ok
    session.fetch_rest_params.assert_called_once_with(
        "search",
        "ticket",
        params={
            "query": "Queue = 'Submissions'",
            "orderby": "+Created",
            "format": "l",
            "fields": SEARCH_FIELDS,
        },
    )


def test_search_tickets_honors_orderby():
    session = MagicMock(spec=RTSession)
    session.fetch_rest_params.return_value = _ok_response(SEARCH_PAYLOAD)

    search_tickets(session, "id = 1", SEARCH_FIELDS, orderby="-Created")

    params = session.fetch_rest_params.call_args.kwargs["params"]
    assert params["orderby"] == "-Created"


# build_ticket_query


def test_query_defaults_to_both_queues():
    assert build_ticket_query(None, None, resolve_queues(None)) == BOTH_QUEUES


def test_query_with_both_dates():
    query = build_ticket_query(date(2026, 1, 1), date(2026, 3, 31), ["Submissions"])
    assert query == (
        "( Queue = 'Submissions' ) "
        "AND Created >= '2026-01-01' "
        "AND Created < '2026-04-01'"
    )


def test_query_end_date_is_inclusive():
    """A single-day range must span that whole day."""
    query = build_ticket_query(date(2026, 9, 25), date(2026, 9, 25), ["Submissions"])
    assert "Created >= '2026-09-25'" in query
    assert "Created < '2026-09-26'" in query


def test_query_with_only_start_date():
    query = build_ticket_query(date(2026, 5, 1), None, ["Managed File Transfer"])
    assert query == "( Queue = 'Managed File Transfer' ) AND Created >= '2026-05-01'"


def test_query_with_only_end_date():
    query = build_ticket_query(None, date(2026, 5, 1), ["Managed File Transfer"])
    assert query == "( Queue = 'Managed File Transfer' ) AND Created < '2026-05-02'"


def test_query_with_multiple_queues():
    query = build_ticket_query(None, None, ["Submissions", "Other Queue"])
    assert query == "( Queue = 'Submissions' OR Queue = 'Other Queue' )"


def test_query_escapes_single_quotes():
    query = build_ticket_query(None, None, ["Bob's Queue"])
    assert query == "( Queue = 'Bob''s Queue' )"


# resolve_queues


@pytest.mark.parametrize(
    "given, expected",
    [
        (None, ["Managed File Transfer", "Submissions"]),
        ([], ["Managed File Transfer", "Submissions"]),
        (["mft"], ["Managed File Transfer"]),
        (["sub"], ["Submissions"]),
        (["sub", "mft"], ["Submissions", "Managed File Transfer"]),
        (["General"], ["General"]),
        (["sub", "General"], ["Submissions", "General"]),
    ],
)
def test_resolve_queues(given, expected):
    assert resolve_queues(given) == expected


# validate_queues


def test_validate_queues_accepts_known_names():
    assert validate_queues(["Submissions", "General"], KNOWN_QUEUES) == [
        "Submissions",
        "General",
    ]


def test_validate_queues_normalizes_case():
    """RT's own spelling wins, so the query matches regardless of input case."""
    assert validate_queues(["submissions", "MANAGED FILE TRANSFER"], KNOWN_QUEUES) == [
        "Submissions",
        "Managed File Transfer",
    ]


def test_validate_queues_rejects_unknown_name():
    with pytest.raises(SystemExit) as exc_info:
        validate_queues(["Submisions"], KNOWN_QUEUES)
    assert exc_info.value.code == 2


def test_validate_queues_reports_every_unknown_name(caplog):
    with pytest.raises(SystemExit):
        validate_queues(["Submissions", "Nope", "Also Nope"], KNOWN_QUEUES)

    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "'Nope'" in messages
    assert "'Also Nope'" in messages
    assert "Submissions" in messages  # listed among the known queues


# fetch_queue_names


def test_fetch_queue_names():
    session = MagicMock(spec=RTSession)
    session.fetch_rest_params.return_value = _ok_response(QUEUE_PAYLOAD)

    assert fetch_queue_names(session) == [
        "General",
        "Managed File Transfer",
        "Submissions",
    ]
    session.fetch_rest_params.assert_called_once_with(
        "search", "queue", params={"query": "id > 0"}
    )


def test_fetch_queue_names_raises_on_error_response():
    session = MagicMock(spec=RTSession)
    session.fetch_rest_params.return_value = RTResponseData(
        version="4.4.3",
        status_code=500,
        status_text="Internal Server Error",
        is_ok=False,
        payload=b"",
    )

    with pytest.raises(RTResponseError):
        fetch_queue_names(session)


def test_parse_queue_names_no_matches():
    assert parse_queue_names(b"\nNo matching results.\n\n") == []


# parse_search_results


def test_parse_search_results_full_payload():
    tickets = parse_search_results(SEARCH_PAYLOAD)

    assert [t.id for t in tickets] == ["37525", "37603"]
    assert tickets[0] == TicketSummary(
        id="37525",
        subject="Delivery of WGS data",
        status="resolved",
        created="Mon Aug 04 14:22:11 2026",
        last_updated="Tue Aug 12 09:01:45 2026",
        owner="hale",
        queue="Submissions",
    )
    assert tickets[1].owner == "Nobody"
    assert tickets[1].queue == "Managed File Transfer"


def test_parse_search_results_no_matches():
    assert parse_search_results(b"\nNo matching results.\n\n") == []


def test_parse_search_results_empty_payload():
    assert parse_search_results(b"\n") == []


def test_parse_search_results_missing_field():
    payload = b"\nid: ticket/42\nSubject: No owner recorded\nStatus: new\n"
    (ticket,) = parse_search_results(payload)
    assert ticket.owner == ""
    assert ticket.created == ""
    assert ticket.queue == ""


def test_parse_search_results_continuation_lines():
    payload = b"\nid: ticket/42\nSubject: First line\n    second line\nStatus: open\n"
    (ticket,) = parse_search_results(payload)
    assert ticket.subject == "First line\nsecond line"
    assert ticket.status == "open"


def test_parse_search_results_strips_ticket_prefix():
    (ticket,) = parse_search_results(b"\nid: ticket/99\nSubject: x\n")
    assert ticket.id == "99"


# write_ticket_tsv


def test_write_ticket_tsv_header_and_row():
    out = io.StringIO()
    write_ticket_tsv([_summary()], file=out)

    header, row = out.getvalue().splitlines()
    assert header == "id\tsubject\tstatus\tcreated\tlast_updated\towner\tqueue"
    assert row.split("\t") == [
        "37525",
        "Delivery of WGS data",
        "resolved",
        "Mon Aug 04 14:22:11 2026",
        "Tue Aug 12 09:01:45 2026",
        "hale",
        "Submissions",
    ]


def test_write_ticket_tsv_header_only_when_empty():
    out = io.StringIO()
    write_ticket_tsv([], file=out)
    assert (
        out.getvalue() == "id\tsubject\tstatus\tcreated\tlast_updated\towner\tqueue\n"
    )


def test_write_ticket_tsv_scrubs_tabs_and_newlines():
    out = io.StringIO()
    write_ticket_tsv([_summary(subject="tab\there\nand a break")], file=out)

    lines = out.getvalue().splitlines()
    assert len(lines) == 2
    assert lines[1].split("\t")[1] == "tab here and a break"


# Helpers


def _ok_response(payload: bytes) -> RTResponseData:
    return RTResponseData(
        version="4.4.3",
        status_code=200,
        status_text="Ok",
        is_ok=True,
        payload=payload,
    )


def _raw_response(content: bytes, url: str) -> Response:
    response = Response()
    response._content = content
    response.status_code = 200
    response.url = url
    return response


def _summary(**overrides) -> TicketSummary:
    defaults = {
        "id": "37525",
        "subject": "Delivery of WGS data",
        "status": "resolved",
        "created": "Mon Aug 04 14:22:11 2026",
        "last_updated": "Tue Aug 12 09:01:45 2026",
        "owner": "hale",
        "queue": "Submissions",
    }
    return TicketSummary(**(defaults | overrides))
