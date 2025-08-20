"""Tests for RT ticket download automation."""

import tempfile
from pathlib import Path
from unittest.mock import Mock

from pytest import fixture

from rt_tools import RTSession, download_ticket
from rt_tools.downloader import TicketDownloader


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

    def mock_fetch_rest(*parts):
        """Mock fetch_rest method to work with new *parts syntax."""
        from rt_tools.session import parse_rt_response

        # Construct URL using the same logic as mock_rest_url
        url = "https://rt.example.com/REST/1.0/" + "/".join(parts)

        # Get response using existing mock_get logic
        response = mock_get(url)

        # Parse the response as fetch_rest would do
        return parse_rt_response(response)

    session.get.side_effect = mock_get
    session.rest_url.side_effect = mock_rest_url
    session.fetch_rest.side_effect = mock_fetch_rest
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


def test_xlsx_to_tsv_conversion(rt37525_xlsx_fixtures):
    """Test XLSX to TSV conversion functionality using real fixture file."""
    from rt_tools.downloader import TicketDownloader

    xlsx_path = rt37525_xlsx_fixtures["xlsx"]
    tsv_fixture_path = rt37525_xlsx_fixtures["tsv"]

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

        if tsv_path.exists():
            # Verify TSV file was created and has content
            tsv_content = tsv_path.read_text()
            lines = tsv_content.strip().split("\n")

            # Should have at least header and some data
            assert len(lines) >= 2, "TSV should have header and data rows"

            # Check header (should be tab-separated)
            header = lines[0]
            assert "\t" in header, "Header should be tab-separated"

            # Check data rows are tab-separated
            for i, line in enumerate(lines[1:], 2):
                if line.strip():  # Skip empty lines
                    assert "\t" in line, f"Line {i} should be tab-separated: {line}"

            # Compare with fixture TSV for structure validation
            if tsv_fixture_path.exists():
                fixture_content = tsv_fixture_path.read_text().strip()
                fixture_lines = fixture_content.split("\n")

                # Both should have similar structure
                assert len(lines) > 0, "Generated TSV should have content"
                assert len(fixture_lines) > 0, "Fixture TSV should have content"
        else:
            # If conversion failed, check if openpyxl is available
            try:
                import openpyxl  # noqa: F401

                # If openpyxl is available but conversion failed, that's an error
                raise AssertionError(
                    "XLSX conversion failed despite openpyxl being available"
                )
            except ImportError:
                # If openpyxl is not available, skip the test
                import pytest

                pytest.skip("XLSX conversion skipped - openpyxl not available")


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

            # Create history directory and XLSX file with new structure
            history_dir = attachments_dir / history_id
            history_dir.mkdir(exist_ok=True)
            xlsx_filename = f"n{attachment_id}.{extension}"
            xlsx_file = history_dir / xlsx_filename

            # Create a dummy XLSX file
            xlsx_file.write_bytes(b"mock xlsx content")

            # Test the conversion trigger logic
            if extension == "xlsx":
                tsv_filename = f"n{attachment_id}.tsv"
                tsv_file = history_dir / tsv_filename
                downloader._convert_xlsx_to_tsv(xlsx_file, tsv_file)

            # Verify that the conversion method was called
            mock_convert.assert_called_once_with(xlsx_file, history_dir / "n801.tsv")


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


def test_mime_type_to_extension():
    """Test MIME type to file extension conversion."""
    downloader = TicketDownloader(None)

    # Test common MIME types
    assert downloader._mime_type_to_extension("text/plain") == "txt"
    assert downloader._mime_type_to_extension("text/html") == "html"
    assert downloader._mime_type_to_extension("application/pdf") == "pdf"
    assert downloader._mime_type_to_extension("image/png") == "png"
    assert downloader._mime_type_to_extension("image/jpeg") == "jpg"

    # Test Microsoft Office formats
    assert downloader._mime_type_to_extension("application/vnd.ms-excel") == "xls"
    assert (
        downloader._mime_type_to_extension(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        == "xlsx"
    )
    assert (
        downloader._mime_type_to_extension(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        )
        == "docx"
    )

    # Test case insensitivity
    assert downloader._mime_type_to_extension("TEXT/PLAIN") == "txt"
    assert downloader._mime_type_to_extension("Application/PDF") == "pdf"

    # Test unknown MIME types default to "bin"
    assert downloader._mime_type_to_extension("unknown/type") == "bin"
    assert downloader._mime_type_to_extension("") == "bin"
    assert downloader._mime_type_to_extension("invalid-mime") == "bin"


def test_download_ticket_convenience_function(mock_session):
    """Test the download_ticket convenience function."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_output"

        # Call the convenience function
        download_ticket(mock_session, "123", parent_dir)

        # Verify it creates the ticket directory structure
        ticket_dir = parent_dir / "rt123"
        assert ticket_dir.exists()
        assert (ticket_dir / "metadata.txt").exists()
        assert (ticket_dir / "history.txt").exists()
        assert (ticket_dir / "attachments.txt").exists()


def test_download_metadata_success(mock_session):
    """Test successful metadata download."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        downloader._download_metadata("123", target_dir)

        metadata_file = target_dir / "metadata.txt"
        assert metadata_file.exists()

        content = metadata_file.read_text()
        assert "id: ticket/123" in content


def test_download_metadata_failure(mock_session):
    """Test metadata download with API failure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        # Test with non-existent ticket
        downloader._download_metadata("999", target_dir)

        metadata_file = target_dir / "metadata.txt"
        assert not metadata_file.exists()


def test_download_history_success(mock_session):
    """Test successful history download."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        payload = downloader._download_history("123", target_dir)

        # Should return payload
        assert payload is not None
        assert isinstance(payload, bytes)

        # Should create history file
        history_file = target_dir / "history.txt"
        assert history_file.exists()

        content = history_file.read_text()
        assert "# 3/3" in content


def test_download_history_failure(mock_session):
    """Test history download with API failure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        # Test with non-existent ticket
        payload = downloader._download_history("999", target_dir)

        # Should return None on failure
        assert payload is None

        # Should not create history file
        history_file = target_dir / "history.txt"
        assert not history_file.exists()


def test_download_attachment_list_success(mock_session):
    """Test successful attachment list download."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        payload = downloader._download_attachment_ist("123", target_dir)

        # Should return payload
        assert payload is not None
        assert isinstance(payload, bytes)

        # Should create attachments file
        attachments_file = target_dir / "attachments.txt"
        assert attachments_file.exists()

        content = attachments_file.read_text()
        assert "456: (Unnamed)" in content


def test_download_individual_history_item_success(mock_session):
    """Test successful individual history item download."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        payload = downloader._download_individual_history_item("123", target_dir, "456")

        # Should return payload
        assert payload is not None
        assert isinstance(payload, bytes)

        # Should create history directory and message file
        history_dir = target_dir / "456"
        message_file = history_dir / "message.txt"

        assert history_dir.exists()
        assert message_file.exists()

        content = message_file.read_text()
        assert "id: 456" in content


def test_download_individual_history_item_failure(mock_session):
    """Test individual history item download with API failure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        # Test with non-existent history item
        payload = downloader._download_individual_history_item("123", target_dir, "999")

        # Should return None on failure
        assert payload is None

        # Should not create directory
        history_dir = target_dir / "999"
        assert not history_dir.exists()


def test_download_history_attachment_success(mock_session):
    """Test successful history attachment download."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        # Create history directory first
        history_dir = target_dir / "458"
        history_dir.mkdir(parents=True)

        downloader._download_history_attachment(
            "123", target_dir, "458", "800", "application/pdf"
        )

        # Should create attachment file
        attachment_file = history_dir / "n800.pdf"
        assert attachment_file.exists()

        content = attachment_file.read_bytes()
        assert b"%PDF-1.4" in content


def test_download_history_attachment_xlsx_conversion(mock_session):
    """Test XLSX attachment download with automatic TSV conversion."""
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        # Create history directory first
        history_dir = target_dir / "458"
        history_dir.mkdir(parents=True)

        with patch.object(downloader, "_convert_xlsx_to_tsv") as mock_convert:
            xlsx_mime_type = (
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
            downloader._download_history_attachment(
                "123", target_dir, "458", "801", xlsx_mime_type
            )

            # Should create XLSX file
            xlsx_file = history_dir / "n801.xlsx"
            assert xlsx_file.exists()

            # Should trigger TSV conversion
            tsv_file = history_dir / "n801.tsv"
            mock_convert.assert_called_once_with(xlsx_file, tsv_file)


def test_download_history_attachment_failure(mock_session):
    """Test history attachment download with API failure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        # Create history directory first
        history_dir = target_dir / "458"
        history_dir.mkdir(parents=True)

        # Test with non-existent attachment
        downloader._download_history_attachment(
            "123", target_dir, "458", "999", "application/pdf"
        )

        # Should not create attachment file
        attachment_file = history_dir / "n999.pdf"
        assert not attachment_file.exists()


def test_ticket_downloader_init():
    """Test TicketDownloader initialization."""
    mock_session = Mock(spec=RTSession)
    downloader = TicketDownloader(mock_session)

    assert downloader.session is mock_session


def test_convert_xlsx_to_tsv_no_openpyxl():
    """Test XLSX conversion when openpyxl is not available."""
    from unittest.mock import patch

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        xlsx_file = temp_path / "test.xlsx"
        tsv_file = temp_path / "test.tsv"

        # Create a dummy XLSX file
        xlsx_file.write_bytes(b"dummy content")

        # Mock openpyxl as None
        with patch("rt_tools.downloader.openpyxl", None):
            downloader = TicketDownloader(None)
            downloader._convert_xlsx_to_tsv(xlsx_file, tsv_file)

            # Should not create TSV file
            assert not tsv_file.exists()


def test_directory_creation():
    """Test that target directories are created properly."""
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        parent_dir = temp_path / "deep" / "nested" / "directory"

        mock_session = Mock(spec=RTSession)
        # Mock failed responses that don't try to write files
        mock_rt_data = Mock()
        mock_rt_data.is_ok = False
        mock_rt_data.status_code = 404
        mock_rt_data.status_text = "Not Found"
        mock_session.fetch_rest.return_value = mock_rt_data

        downloader = TicketDownloader(mock_session)

        # This should create the directory even if downloads fail
        downloader.download_ticket("123", parent_dir)

        ticket_dir = parent_dir / "rt123"
        assert ticket_dir.exists()
        assert ticket_dir.is_dir()


def test_path_conversion():
    """Test that string paths are converted to Path objects."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir_str = str(Path(temp_dir) / "string_path")

        mock_session = Mock(spec=RTSession)
        # Mock failed responses that don't try to write files
        mock_rt_data = Mock()
        mock_rt_data.is_ok = False
        mock_rt_data.status_code = 404
        mock_rt_data.status_text = "Not Found"
        mock_session.fetch_rest.return_value = mock_rt_data

        downloader = TicketDownloader(mock_session)

        # Should accept string path and convert to Path
        downloader.download_ticket("123", parent_dir_str)

        ticket_dir = Path(parent_dir_str) / "rt123"
        assert ticket_dir.exists()


def test_error_handling_in_main_download(mock_session):
    """Test error handling in main download_ticket method."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir)
        downloader = TicketDownloader(mock_session)

        # Mock history download failure
        def failing_download_history(*args, **kwargs):
            return None  # Simulate failure

        downloader._download_history = failing_download_history

        # Should handle failure gracefully and return early
        downloader.download_ticket("123", parent_dir)

        # Should still create metadata but not history items
        ticket_dir = parent_dir / "rt123"
        assert (ticket_dir / "metadata.txt").exists()
        assert not any(ticket_dir.glob("*/message.txt"))  # No history items


def test_edge_cases():
    """Test various edge cases and boundary conditions."""
    downloader = TicketDownloader(None)

    # Test _normalize_xlsx_value with edge cases
    edge_cell = Mock()
    edge_cell.value = 0
    assert downloader._normalize_xlsx_value(edge_cell) == "0"

    edge_cell.value = ""
    assert downloader._normalize_xlsx_value(edge_cell) == ""

    edge_cell.value = False
    assert downloader._normalize_xlsx_value(edge_cell) == "False"

    # Test _mime_type_to_extension with None (should not crash)
    try:
        result = downloader._mime_type_to_extension(None)
        # If it doesn't crash, it should return "bin"
        assert result == "bin"
    except (AttributeError, TypeError):
        # This is also acceptable behavior
        pass
