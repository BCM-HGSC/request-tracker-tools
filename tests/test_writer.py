"""Tests for RT write support: content blocks, requests, and responses."""

from unittest.mock import MagicMock

import pytest
from requests import Response

from rt_tools.parser import (
    build_content_block,
    parse_content_block,
    parse_write_response,
)
from rt_tools.session import BASE_URL, RTResponseData, RTResponseError, RTSession
from rt_tools.writer import (
    ACTION_COMMENT,
    ACTION_CORRESPOND,
    send,
    ticket_create_request,
    ticket_transaction_request,
)

#: The head of what RT actually serves for a POST without a Referer, verbatim.
CSRF_INTERSTITIAL = (
    b'<!DOCTYPE html>\n\n<html lang="en">\n  <head>\n'
    b"    <title>Possible cross-site request forgery</title>\n"
)


# Write requests


def test_create_request_puts_id_first_and_keeps_fields():
    request = ticket_create_request(
        {"Queue": "Submissions", "Subject": "Delivery of WGS data", "Text": "Hello."}
    )

    assert request.parts == ("ticket", "new")
    assert request.content == (
        "id: ticket/new\n"
        "Queue: Submissions\n"
        "Subject: Delivery of WGS data\n"
        "Text: Hello.\n"
    )
    assert request.mails_requestors


def test_create_request_requires_a_queue():
    with pytest.raises(ValueError, match="Queue is required"):
        ticket_create_request({"Subject": "No queue"})


def test_create_request_does_not_mutate_the_caller_fields():
    fields = {"Queue": "Submissions"}

    ticket_create_request(fields)

    assert fields == {"Queue": "Submissions"}


def test_comment_request_targets_the_comment_endpoint():
    request = ticket_transaction_request("37525", ACTION_COMMENT, "Internal note.")

    assert request.parts == ("ticket", "37525", "comment")
    assert request.content == ("id: 37525\nAction: comment\nText: Internal note.\n")
    assert not request.mails_requestors


def test_reply_request_differs_only_in_action_and_mails_requestors():
    request = ticket_transaction_request("37525", ACTION_CORRESPOND, "Sent the data.")

    assert request.parts == ("ticket", "37525", "comment")
    assert "Action: correspond\n" in request.content
    assert request.mails_requestors


def test_comment_with_cc_counts_as_outbound_mail():
    """A Cc'd comment still leaves RT as email, so it warrants the same warning."""
    request = ticket_transaction_request(
        "37525", ACTION_COMMENT, "Note.", cc=["someone@example.org"]
    )

    assert request.mails_requestors
    assert "Cc: someone@example.org\n" in request.content


def test_transaction_request_rejects_an_empty_body():
    with pytest.raises(ValueError, match="empty message"):
        ticket_transaction_request("37525", ACTION_COMMENT, "   \n  ")


def test_transaction_request_rejects_an_unknown_action():
    with pytest.raises(ValueError, match="comment or correspond"):
        ticket_transaction_request("37525", "resolve", "Text.")


# Content block encoding


def test_multi_line_body_becomes_space_prefixed_continuations():
    """RT reads an unprefixed newline as the end of the field."""
    block = build_content_block({"Text": "line 1\nline 2\nline 3"})

    assert block == "Text: line 1\n line 2\n line 3\n"


def test_blank_line_in_body_becomes_a_single_space():
    """A truly empty continuation would terminate Text and drop the rest."""
    block = build_content_block({"Text": "paragraph one\n\nparagraph two"})

    assert block == "Text: paragraph one\n \n paragraph two\n"


def test_crlf_is_normalized_because_rt_rejects_it():
    block = build_content_block({"Text": "line 1\r\nline 2"})

    assert "\r" not in block
    assert block == "Text: line 1\n line 2\n"


def test_none_valued_fields_are_omitted():
    block = build_content_block({"Queue": "Submissions", "Cc": None, "Owner": None})

    assert block == "Queue: Submissions\n"


def test_list_values_are_joined_for_rt_address_fields():
    block = build_content_block({"Requestor": ["a@example.org", "b@example.org"]})

    assert block == "Requestor: a@example.org, b@example.org\n"


# Content block parsing


def test_parse_content_block_round_trips_a_multi_line_body():
    fields = {"Queue": "Submissions", "Text": "line 1\n\nline 2"}

    assert parse_content_block(build_content_block(fields)) == fields


def test_parse_content_block_drops_comments_and_blank_lines():
    text = "# a template comment\n\nQueue: Submissions\nSubject: Hello\n"

    assert parse_content_block(text) == {"Queue": "Submissions", "Subject": "Hello"}


def test_parse_content_block_rejects_a_line_without_a_colon():
    with pytest.raises(ValueError, match="line 2"):
        parse_content_block("Queue: Submissions\nnot a field\n")


def test_parse_content_block_rejects_a_leading_continuation():
    with pytest.raises(ValueError, match="continuation before any field"):
        parse_content_block(" orphaned\n")


# Write responses


def test_create_response_yields_the_new_ticket_id():
    result = parse_write_response(b"# Ticket 775 created.\n")

    assert result.ok
    assert result.ticket_id == "775"
    assert result.message == "Ticket 775 created."


def test_comment_response_is_ok_without_an_id():
    result = parse_write_response(b"# Message recorded\n")

    assert result.ok
    assert result.ticket_id is None


def test_unrecognized_response_is_not_treated_as_success():
    """RT reports a rejected write as 200 with an error comment in the body."""
    result = parse_write_response(b"# Could not create ticket.\n# Syntax error.\n")

    assert not result.ok
    assert "Could not create ticket." in result.message


# Transport


def test_post_rest_sends_the_content_block_and_a_referer():
    session = MagicMock()
    session.post.return_value = _raw_response(
        b"RT/4.4.3 200 Ok\n\n# Ticket 775 created.\n",
        "https://rt.hgsc.bcm.edu/REST/1.0/ticket/new",
    )

    result = RTSession.post_rest(session, "ticket", "new", content="id: ticket/new\n")

    assert result.is_ok
    (url,) = session.post.call_args.args
    assert url == "https://rt.hgsc.bcm.edu/REST/1.0/ticket/new"
    assert session.post.call_args.kwargs["data"] == {"content": "id: ticket/new\n"}
    assert session.post.call_args.kwargs["headers"] == {"Referer": f"{BASE_URL}/"}


def test_post_rest_names_the_csrf_rejection_for_what_it_is():
    """RT serves this with HTTP 200, so only the body gives the cause away."""
    session = MagicMock()
    session.post.return_value = _raw_response(
        CSRF_INTERSTITIAL, "https://rt.hgsc.bcm.edu/REST/1.0/ticket/39943/comment"
    )

    with pytest.raises(RTResponseError, match="cross-site request forgery"):
        RTSession.post_rest(
            session, "ticket", "39943", "comment", content="id: 39943\n"
        )


def test_live_comment_response_is_recognized():
    """Exactly what rt.hgsc.bcm.edu returned for an accepted comment."""
    result = parse_write_response(b"# Comments added\n\n")

    assert result.ok
    assert result.message == "Comments added"


def test_send_returns_the_parsed_write_result():
    session = MagicMock(spec=RTSession)
    session.post_rest.return_value = _ok_response(b"# Ticket 775 created.\n")

    result = send(session, ticket_create_request({"Queue": "Submissions"}))

    assert result.ok
    assert result.ticket_id == "775"
    assert session.post_rest.call_args.args == ("ticket", "new")


def test_send_reports_a_non_ok_status_line_as_failure():
    session = MagicMock(spec=RTSession)
    session.post_rest.return_value = RTResponseData(
        version="4.4.3",
        status_code=409,
        status_text="Syntax Error",
        is_ok=False,
        payload=b"",
    )

    result = send(session, ticket_create_request({"Queue": "Submissions"}))

    assert not result.ok
    assert "409" in result.message


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
