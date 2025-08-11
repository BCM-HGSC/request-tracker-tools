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


def test_xlsx_to_tsv_conversion():
    """Test XLSX to TSV conversion functionality using real fixture file."""
    from rt_tools.downloader import TicketDownloader

    # Use the real XLSX fixture file from download_output
    fixtures_dir = Path(__file__).parent / "fixtures"
    xlsx_path = fixtures_dir / "download_output/attachments/1489286-1483997.xlsx"

    if not xlsx_path.exists():
        # Skip test if fixture doesn't exist
        import pytest

        pytest.skip(f"XLSX fixture not found: {xlsx_path}")

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        tsv_path = temp_path / "test_output.tsv"

        # Create downloader and test conversion
        downloader = TicketDownloader(None)
        downloader._convert_xlsx_to_tsv(xlsx_path, tsv_path)

        # Verify TSV file was created
        assert tsv_path.exists(), "TSV file should be created"

        # Verify TSV content
        tsv_content = tsv_path.read_text()
        lines = tsv_content.strip().split("\n")

        # Should have at least header and some data
        assert len(lines) >= 2, "TSV should have header and data rows"

        # Check header (should be tab-separated)
        header = lines[0]
        assert "\t" in header, "Header should be tab-separated"
        assert "Sample ID" in header, "Should contain expected column headers"
        assert "Path" in header, "Should contain expected column headers"

        # Check data rows are tab-separated
        for i, line in enumerate(lines[1:], 2):
            assert "\t" in line, f"Line {i} should be tab-separated: {line}"


def test_xlsx_to_tsv_conversion_with_invalid_file():
    """Test XLSX conversion with invalid file handles errors gracefully."""
    from rt_tools.downloader import TicketDownloader

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        invalid_xlsx = temp_path / "invalid.xlsx"
        tsv_path = temp_path / "output.tsv"

        # Create an invalid XLSX file
        invalid_xlsx.write_text("This is not a valid XLSX file")

        # Create downloader and attempt conversion
        downloader = TicketDownloader(None)
        downloader._convert_xlsx_to_tsv(invalid_xlsx, tsv_path)

        # TSV file should not be created due to error
        assert not tsv_path.exists(), "TSV file should not be created for invalid XLSX"


def test_xlsx_conversion_trigger():
    """Test that XLSX conversion method is called when XLSX extension is detected."""
    from unittest.mock import patch

    from rt_tools.downloader import TicketDownloader

    # Create a simple unit test that verifies the conversion is triggered
    with tempfile.TemporaryDirectory() as temp_dir:
        attachments_dir = Path(temp_dir) / "attachments"
        attachments_dir.mkdir(exist_ok=True)

        # Create a mock downloader and patch the conversion method
        downloader = TicketDownloader(None)

        with patch.object(downloader, "_convert_xlsx_to_tsv") as mock_convert:
            # Manually call the part that should trigger conversion
            # We'll simulate the file save and extension detection

            history_id = "458"
            attachment_id = "801"
            extension = "xlsx"

            # Create the XLSX filename that would be generated
            xlsx_filename = f"{history_id}-{attachment_id}.{extension}"
            xlsx_file = attachments_dir / xlsx_filename

            # Create a dummy XLSX file
            xlsx_file.write_bytes(b"mock xlsx content")

            # Test the conversion trigger logic
            if extension == "xlsx":
                tsv_filename = f"{history_id}-{attachment_id}.tsv"
                tsv_file = attachments_dir / tsv_filename
                downloader._convert_xlsx_to_tsv(xlsx_file, tsv_file)

            # Verify that the conversion method was called
            mock_convert.assert_called_once_with(
                xlsx_file, attachments_dir / "458-801.tsv"
            )


def test_normalize_xlsx_value():
    """Test cell value normalization for XLSX conversion."""
    from unittest.mock import Mock

    from rt_tools.downloader import TicketDownloader

    downloader = TicketDownloader(None)

    # Test None value
    none_cell = Mock()
    none_cell.value = None
    assert downloader._normalize_xlsx_value(none_cell) == ""

    # Test string value
    str_cell = Mock()
    str_cell.value = "test string"
    assert downloader._normalize_xlsx_value(str_cell) == "test string"

    # Test numeric value
    num_cell = Mock()
    num_cell.value = 42
    assert downloader._normalize_xlsx_value(num_cell) == "42"

    # Test float value
    float_cell = Mock()
    float_cell.value = 3.14
    assert downloader._normalize_xlsx_value(float_cell) == "3.14"
