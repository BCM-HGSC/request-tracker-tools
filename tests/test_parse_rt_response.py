"""Unit tests for parse_rt_response function."""

from unittest.mock import Mock

import pytest

from rt_tools import RTResponseData, RTResponseError, parse_rt_response


def test_valid_200_ok_response():
    """Test parsing a valid 200 Ok RT response."""
    response = Mock()
    response.content = b"RT/4.4.3 200 Ok\n\nTicket data here\n\n\n"

    result = parse_rt_response(response)

    assert isinstance(result, RTResponseData)
    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b"Ticket data here"


def test_valid_404_response():
    """Test parsing a valid 404 Not Found RT response."""
    response = Mock()
    response.content = b"RT/5.0.1 404 Not Found\n\nTicket not found\n\n\n"

    result = parse_rt_response(response)

    assert result.version == "5.0.1"
    assert result.status_code == 404
    assert result.status_text == "Not Found"
    assert result.is_ok is False
    assert result.payload == b"Ticket not found"


def test_valid_500_response():
    """Test parsing a valid 500 Internal Server Error RT response."""
    response = Mock()
    response.content = (
        b"RT/3.8.10 500 Internal Server Error\n\nServer error details\n\n\n"
    )

    result = parse_rt_response(response)

    assert result.version == "3.8.10"
    assert result.status_code == 500
    assert result.status_text == "Internal Server Error"
    assert result.is_ok is False
    assert result.payload == b"Server error details"


def test_response_without_trailing_suffix():
    """Test parsing RT response without the 3-newline suffix."""
    response = Mock()
    response.content = b"RT/4.4.3 200 Ok\n\nTicket data without suffix"

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b"Ticket data without suffix"


def test_response_with_crlf_line_endings():
    """Test parsing RT response with Windows CRLF line endings."""
    response = Mock()
    response.content = b"RT/4.4.3 200 Ok\r\n\r\nTicket data\r\n\r\n\r\n"

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b"Ticket data"  # Trailing suffix is stripped


def test_response_200_with_different_status_text():
    """Test that is_ok is False for 200 status with non-'Ok' text."""
    response = Mock()
    response.content = b"RT/4.4.3 200 Success\n\nTicket data\n\n\n"

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Success"
    assert result.is_ok is False  # Only "Ok" makes is_ok True
    assert result.payload == b"Ticket data"


def test_empty_payload():
    """Test parsing RT response with empty payload."""
    response = Mock()
    response.content = b"RT/4.4.3 200 Ok\n\n\n\n\n"

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b""


def test_multiline_payload():
    """Test parsing RT response with multiline payload."""
    response = Mock()
    response.content = b"RT/4.4.3 200 Ok\n\nLine 1\nLine 2\nLine 3\n\n\n"

    result = parse_rt_response(response)

    assert result.payload == b"Line 1\nLine 2\nLine 3"


def test_empty_response_content():
    """Test that empty response content raises RTResponseError."""
    response = Mock()
    response.content = b""

    with pytest.raises(RTResponseError, match="Empty response content"):
        parse_rt_response(response)


def test_invalid_response_format():
    """Test that invalid response format raises RTResponseError."""
    response = Mock()
    response.content = b"<html><body>Not an RT response</body></html>"

    with pytest.raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


def test_malformed_rt_header_missing_version():
    """Test malformed RT header missing version number."""
    response = Mock()
    response.content = b"RT/ 200 Ok\n\nData"

    with pytest.raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


def test_malformed_rt_header_missing_status_code():
    """Test malformed RT header missing status code."""
    response = Mock()
    response.content = b"RT/4.4.3 Ok\n\nData"

    with pytest.raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


def test_malformed_rt_header_missing_double_newline():
    """Test malformed RT header missing double newline separator."""
    response = Mock()
    response.content = b"RT/4.4.3 200 Ok\nData"

    with pytest.raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


@pytest.mark.parametrize(
    "content,expected_version",
    [
        (b"RT/1.0 200 Ok\n\nData\n\n\n", "1.0"),
        (b"RT/4.4.3 200 Ok\n\nData\n\n\n", "4.4.3"),
        (b"RT/5.0.1.beta 200 Ok\n\nData\n\n\n", "5.0.1.beta"),
    ],
)
def test_different_version_formats(content, expected_version):
    """Test parsing responses with different version number formats."""
    response = Mock()
    response.content = content

    result = parse_rt_response(response)
    assert result.version == expected_version


def test_response_error_includes_response_object():
    """Test that RTResponseError includes the original response object."""
    response = Mock()
    response.content = b"Invalid content"

    with pytest.raises(RTResponseError) as exc_info:
        parse_rt_response(response)

    assert exc_info.value.response is response
