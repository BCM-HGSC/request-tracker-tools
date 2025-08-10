"""Tests for RT ticket download automation."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

from pytest import fixture

from rt_tools import RTSession, download_ticket


@fixture
def fixture_data_path(fixtures_dir):
    """Return path to test fixture data."""
    return fixtures_dir / "rt_ticket_data"


@fixture
def mock_rt_responses(fixture_data_path):
    """Create mock RT responses using fixture data."""
    responses = {}

    # Load all fixture files
    for fixture_file in fixture_data_path.glob("*.bin"):
        with open(fixture_file, "rb") as f:
            content = f.read()

        # Map fixture files to RT endpoints
        filename = fixture_file.stem
        if filename == "metadata":
            responses["ticket/123"] = content
        elif filename == "history":
            responses["ticket/123/history"] = content
            responses["ticket/123/history?format=l"] = content
        elif filename == "attachments":
            responses["ticket/123/attachments"] = content
        elif filename.startswith("attachment_") and not filename.endswith("_content"):
            attachment_id = filename.split("_")[1]
            responses[f"ticket/123/attachments/{attachment_id}"] = content
        elif filename.endswith("_content"):
            attachment_id = filename.split("_")[1]
            responses[f"ticket/123/attachments/{attachment_id}/content"] = content
        elif filename.startswith("history_"):
            history_id = filename.split("_")[1]
            responses[f"ticket/123/history/id/{history_id}"] = content

    return responses


@fixture
def mock_session(mock_rt_responses):
    """Create mock RTSession with fixture responses."""
    session = Mock(spec=RTSession)

    def mock_get(url):
        """Mock GET requests to return fixture data."""
        response = Mock()

        # Extract endpoint from URL
        if "/REST/1.0/" in url:
            endpoint = url.split("/REST/1.0/")[1]
            # Handle query parameters by checking if base endpoint exists
            if endpoint in mock_rt_responses:
                response.content = mock_rt_responses[endpoint]
                response.url = url
                response.status_code = 200
            elif "?" in endpoint:
                # Try without query parameters
                base_endpoint = endpoint.split("?")[0]
                if base_endpoint in mock_rt_responses:
                    response.content = mock_rt_responses[base_endpoint]
                    response.url = url
                    response.status_code = 200
                else:
                    response.content = b"RT/4.4.3 404 Not Found\n\nEndpoint not found"
                    response.url = url
                    response.status_code = 404
            else:
                response.content = b"RT/4.4.3 404 Not Found\n\nEndpoint not found"
                response.url = url
                response.status_code = 404
        else:
            response.content = b"RT/4.4.3 404 Not Found\n\nInvalid URL"
            response.url = url
            response.status_code = 404

        return response

    def mock_rest_url(*parts):
        """Mock rest_url method."""
        return "https://rt.example.com/REST/1.0/" + "/".join(parts)

    session.get.side_effect = mock_get
    session.rest_url.side_effect = mock_rest_url
    return session


def test_fixture_data_exists(fixture_data_path):
    """Test that all required fixture files exist."""
    required_files = [
        "metadata.bin",
        "history.bin",
        "history_456.bin",
        "history_457.bin",
        "history_458.bin",
        "attachments.bin",
        "attachment_456.bin",
        "attachment_456_content.bin",
        "attachment_789.bin",
        "attachment_789_content.bin",
        "attachment_790.bin",
        "attachment_790_content.bin",
        "attachment_800.bin",
        "attachment_800_content.bin",
        "attachment_801.bin",
        "attachment_801_content.bin",
    ]

    for filename in required_files:
        filepath = fixture_data_path / filename
        assert filepath.exists(), f"Missing fixture file: {filename}"
        assert filepath.stat().st_size > 0, f"Empty fixture file: {filename}"


def test_mock_rt_responses_structure(mock_rt_responses):
    """Test that mock responses are properly structured."""
    expected_endpoints = [
        "ticket/123",
        "ticket/123/history",
        "ticket/123/history/id/456",
        "ticket/123/history/id/457",
        "ticket/123/history/id/458",
        "ticket/123/attachments",
        "ticket/123/attachments/456",
        "ticket/123/attachments/456/content",
        "ticket/123/attachments/789",
        "ticket/123/attachments/789/content",
        "ticket/123/attachments/790",
        "ticket/123/attachments/790/content",
        "ticket/123/attachments/800",
        "ticket/123/attachments/800/content",
        "ticket/123/attachments/801",
        "ticket/123/attachments/801/content",
    ]

    for endpoint in expected_endpoints:
        assert endpoint in mock_rt_responses, f"Missing mock response for: {endpoint}"
        assert mock_rt_responses[endpoint].startswith(b"RT/"), (
            f"Invalid RT response format for: {endpoint}"
        )


def test_mock_session_get_requests(mock_session):
    """Test that mock session returns correct responses."""
    # Test ticket metadata
    response = mock_session.get("https://rt.example.com/REST/1.0/ticket/123")
    assert response.status_code == 200
    assert b"id: ticket/123" in response.content

    # Test ticket history
    response = mock_session.get("https://rt.example.com/REST/1.0/ticket/123/history")
    assert response.status_code == 200
    assert b"# 3/3" in response.content
    assert b"456: Ticket created by" in response.content

    # Test ticket history with long format (now returns same as basic)
    response = mock_session.get(
        "https://rt.example.com/REST/1.0/ticket/123/history?format=l"
    )
    assert response.status_code == 200
    assert b"# 3/3" in response.content

    # Test attachments list
    response = mock_session.get(
        "https://rt.example.com/REST/1.0/ticket/123/attachments"
    )
    assert response.status_code == 200
    assert b"456: (Unnamed)" in response.content

    # Test attachment content
    response = mock_session.get(
        "https://rt.example.com/REST/1.0/ticket/123/attachments/789/content"
    )
    assert response.status_code == 200
    assert b"%PDF-1.4" in response.content


def test_download_ticket_automation(mock_session):
    """Test the complete ticket download automation functionality."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "ticket_123"

        # Run ticket download automation
        download_ticket(mock_session, "123", target_dir)

        # Verify directory structure was created
        assert target_dir.exists()
        assert (target_dir / "metadata.txt").exists()
        assert (target_dir / "history.txt").exists()
        assert (target_dir / "attachments").exists()

        # Verify metadata content
        metadata_content = (target_dir / "metadata.txt").read_text()
        assert "id: ticket/123" in metadata_content
        assert "Subject: Sample ticket for testing automation" in metadata_content

        # Verify history content
        history_content = (target_dir / "history.txt").read_text()
        assert "# 3/3" in history_content
        assert "456: Ticket created by reporter@example.com" in history_content

        # Verify attachments were downloaded
        attachments_dir = target_dir / "attachments"
        attachment_files = list(attachments_dir.glob("*"))

        # Should have 2 non-email attachments:
        # - History 457 (Correspond) attachments 789, 790 are skipped
        #   (X-RT-Loop-Prevention)
        # - History 458 (AddWatcher) attachments 800, 801 are downloaded
        # Expected filenames: 458-800.pdf and 458-801.xlsx
        assert len(attachment_files) == 2

        # Check that we have the correct filenames based on history-attachment format
        filenames = [f.name for f in attachment_files]
        assert "458-800.pdf" in filenames
        assert "458-801.xlsx" in filenames

        # Verify PDF content
        pdf_file = attachments_dir / "458-800.pdf"
        assert pdf_file.exists()
        pdf_content = pdf_file.read_bytes()
        assert b"%PDF-1.4" in pdf_content
        assert b"Real PDF Document Content" in pdf_content

        # Verify Excel content
        xlsx_file = attachments_dir / "458-801.xlsx"
        assert xlsx_file.exists()
        xlsx_content = xlsx_file.read_text()
        assert "Real Excel file content" in xlsx_content
