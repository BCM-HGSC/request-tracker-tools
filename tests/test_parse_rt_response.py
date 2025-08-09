"""Unit tests for parse_rt_response function."""

from unittest.mock import Mock

from pytest import mark, raises

from rt_tools import RTResponseData, RTResponseError, parse_rt_response


def create_mock_response(
    content: bytes, url: str = "https://rt.example.com/REST/1.0/ticket/123"
) -> Mock:
    """Create a mock response with content and URL."""
    response = Mock()
    response.content = content
    response.url = url
    return response


def test_valid_200_ok_response():
    """Test parsing a valid 200 Ok RT response (non-content URL)."""
    response = create_mock_response(
        b"RT/4.4.3 200 Ok\n\nTicket data here",
        "https://rt.example.com/REST/1.0/ticket/123",
    )

    result = parse_rt_response(response)

    assert isinstance(result, RTResponseData)
    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b"Ticket data here"


def test_valid_404_response():
    """Test parsing a valid 404 Not Found RT response."""
    response = create_mock_response(b"RT/5.0.1 404 Not Found\n\nTicket not found")

    result = parse_rt_response(response)

    assert result.version == "5.0.1"
    assert result.status_code == 404
    assert result.status_text == "Not Found"
    assert result.is_ok is False
    assert result.payload == b"Ticket not found"


def test_valid_500_response():
    """Test parsing a valid 500 Internal Server Error RT response."""
    response = create_mock_response(
        b"RT/3.8.10 500 Internal Server Error\n\nServer error details"
    )

    result = parse_rt_response(response)

    assert result.version == "3.8.10"
    assert result.status_code == 500
    assert result.status_text == "Internal Server Error"
    assert result.is_ok is False
    assert result.payload == b"Server error details"


def test_response_without_trailing_suffix():
    """Test parsing RT response without the 3-newline suffix (non-content URL)."""
    response = create_mock_response(b"RT/4.4.3 200 Ok\n\nTicket data without suffix")

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b"Ticket data without suffix"


def test_content_url_with_trailing_suffix():
    """Test parsing RT response from /content URL with 3-newline suffix."""
    response = create_mock_response(
        b"RT/4.4.3 200 Ok\n\nAttachment content\n\n\n",
        "https://rt.example.com/REST/1.0/ticket/123/attachments/456/content",
    )

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b"Attachment content"


def test_response_200_with_different_status_text():
    """Test that is_ok is False for 200 status with non-'Ok' text."""
    response = create_mock_response(b"RT/4.4.3 200 Success\n\nTicket data")

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Success"
    assert result.is_ok is False  # Only "Ok" makes is_ok True
    assert result.payload == b"Ticket data"


def test_empty_payload():
    """Test parsing RT response with empty payload."""
    response = create_mock_response(b"RT/4.4.3 200 Ok\n\n")

    result = parse_rt_response(response)

    assert result.version == "4.4.3"
    assert result.status_code == 200
    assert result.status_text == "Ok"
    assert result.is_ok is True
    assert result.payload == b""


def test_multiline_payload():
    """Test parsing RT response with multiline payload."""
    response = create_mock_response(b"RT/4.4.3 200 Ok\n\nLine 1\nLine 2\nLine 3")

    result = parse_rt_response(response)

    assert result.payload == b"Line 1\nLine 2\nLine 3"


def test_empty_response_content():
    """Test that empty response content raises RTResponseError."""
    response = create_mock_response(b"")

    with raises(RTResponseError, match="Empty response content"):
        parse_rt_response(response)


def test_invalid_response_format():
    """Test that invalid response format raises RTResponseError."""
    response = create_mock_response(b"<html><body>Not an RT response</body></html>")

    with raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


def test_malformed_rt_header_missing_version():
    """Test malformed RT header missing version number."""
    response = create_mock_response(b"RT/ 200 Ok\n\nData")

    with raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


def test_malformed_rt_header_missing_status_code():
    """Test malformed RT header missing status code."""
    response = create_mock_response(b"RT/4.4.3 Ok\n\nData")

    with raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


def test_malformed_rt_header_missing_double_newline():
    """Test malformed RT header missing double newline separator."""
    response = create_mock_response(b"RT/4.4.3 200 Ok\nData")

    with raises(RTResponseError, match="Invalid RT response format"):
        parse_rt_response(response)


@mark.parametrize(
    "content,expected_version",
    [
        (b"RT/1.0 200 Ok\n\nData", "1.0"),
        (b"RT/4.4.3 200 Ok\n\nData", "4.4.3"),
        (b"RT/5.0.1.beta 200 Ok\n\nData", "5.0.1.beta"),
    ],
)
def test_different_version_formats(content, expected_version):
    """Test parsing responses with different version number formats."""
    response = create_mock_response(content)

    result = parse_rt_response(response)
    assert result.version == expected_version


def test_content_url_missing_suffix_logs_error(caplog):
    """Test that /content URL missing suffix logs an error but still works."""
    response = create_mock_response(
        b"RT/4.4.3 200 Ok\n\nAttachment without suffix",
        "https://rt.example.com/REST/1.0/ticket/123/attachments/456/content",
    )

    result = parse_rt_response(response)

    assert result.payload == b"Attachment without suffix"
    assert "Abnormal end of content payload" in caplog.text


def test_content_url_with_trailing_slash():
    """Test that /content/ URL with trailing slash works."""
    response = create_mock_response(
        b"RT/4.4.3 200 Ok\n\nAttachment content\n\n\n",
        "https://rt.example.com/REST/1.0/ticket/123/attachments/456/content/",
    )

    result = parse_rt_response(response)

    assert result.payload == b"Attachment content"


def test_response_error_includes_response_object():
    """Test that RTResponseError includes the original response object."""
    response = create_mock_response(b"Invalid content")

    with raises(RTResponseError) as exc_info:
        parse_rt_response(response)

    assert exc_info.value.response is response
