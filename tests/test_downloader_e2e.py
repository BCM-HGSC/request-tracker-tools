"""End-to-end tests for TicketDownloader with real server connections.

These tests connect to the actual RT server and download real ticket data.
They verify the complete download workflow including authentication,
data fetching, file organization, and XLSX conversion.

Note: Downloaded data will not exactly match sanitized fixture data
due to the fixtures being sanitized versions of the original.
"""

import subprocess
import tempfile
from pathlib import Path

import pytest

from rt_tools import RTSession
from rt_tools.downloader import TicketDownloader


@pytest.fixture(scope="module")
def ticket_37525(tmp_path_factory) -> Path:
    """Download ticket 37525 to a temporary directory and return the ticket directory"""
    parent_dir = tmp_path_factory.mktemp("ticket_37525")
    session = RTSession()
    session.authenticate()
    downloader = TicketDownloader(session)
    downloader.download_ticket("37525", parent_dir)
    return parent_dir / "rt37525"


@pytest.mark.e2e
def test_downloader_full_ticket_download(ticket_37525):
    """Test complete ticket download workflow with real RT server."""
    target_dir = ticket_37525

    # Verify basic files are created
    assert target_dir.exists(), "Target directory should be created"
    assert (target_dir / "metadata.txt").exists(), "Metadata file should exist"
    assert (target_dir / "history.txt").exists(), "History file should exist"
    assert (target_dir / "attachments.txt").exists(), "Attachments file should exist"

    # Verify metadata content contains expected ticket information
    metadata_content = (target_dir / "metadata.txt").read_text()
    assert "id: ticket/37525" in metadata_content
    assert "Subject:" in metadata_content

    # Verify history content has expected format
    history_content = (target_dir / "history.txt").read_text()
    assert "# " in history_content  # Should have history count header
    assert ":" in history_content  # Should have history entries

    # Verify attachments content
    attachments_content = (target_dir / "attachments.txt").read_text()
    assert "id: ticket/37525/attachments" in attachments_content

    # Verify at least some history directories are created
    history_dirs = [d for d in target_dir.iterdir() if d.is_dir()]
    assert len(history_dirs) > 0, "Should create history directories"

    # Verify each history directory has a message.txt file
    for history_dir in history_dirs:
        message_file = history_dir / "message.txt"
        assert message_file.exists(), f"Missing message.txt in {history_dir.name}"

        # Verify message file has expected format
        message_content = message_file.read_text()
        assert f"id: {history_dir.name}" in message_content


@pytest.mark.e2e
def test_downloader_xlsx_conversion_e2e(ticket_37525):
    """Test XLSX to TSV conversion with real downloaded data."""
    target_dir = ticket_37525

    # Look for XLSX files in history directories
    xlsx_files = []
    tsv_files = []

    for history_dir in target_dir.iterdir():
        if history_dir.is_dir():
            xlsx_files.extend(history_dir.glob("*.xlsx"))
            tsv_files.extend(history_dir.glob("*.tsv"))

    # Should have found some XLSX files (we know 37525 has Example Workbook.xlsx)
    assert len(xlsx_files) > 0, "Should have downloaded XLSX files"

    # For each XLSX file, should have corresponding TSV file
    for xlsx_file in xlsx_files:
        tsv_file = xlsx_file.with_suffix(".tsv")
        assert tsv_file.exists(), f"Missing TSV conversion for {xlsx_file.name}"

        # Verify TSV file has content
        tsv_content = tsv_file.read_text()
        assert len(tsv_content.strip()) > 0, "TSV file should not be empty"

        # Verify TSV format (should be tab-separated)
        lines = tsv_content.strip().split("\n")
        if len(lines) > 0:
            # At least the header should be tab-separated
            assert "\t" in lines[0], "TSV should be tab-separated"


@pytest.mark.e2e
def test_downloader_attachment_filtering(ticket_37525):
    """Test that downloader properly handles attachment filtering."""
    target_dir = ticket_37525

    # Count attachment files actually downloaded
    downloaded_files = []
    for history_dir in target_dir.iterdir():
        if history_dir.is_dir():
            # Look for attachment files (should start with 'n' followed by digits)
            for file in history_dir.iterdir():
                if (
                    file.is_file()
                    and file.name.startswith("n")
                    and file.name != "message.txt"
                ):
                    downloaded_files.append(file)

    # Should have downloaded some attachment files
    # Note: May be fewer than total attachments due to zero-byte filtering
    assert len(downloaded_files) > 0, "Should have downloaded some attachment files"

    # Verify downloaded files have content
    for file in downloaded_files:
        # TSV files might be empty if XLSX is empty
        if not file.name.endswith(".tsv"):
            assert file.stat().st_size > 0, (
                f"Downloaded file {file.name} should not be empty"
            )


@pytest.mark.e2e
def test_downloader_outgoing_email_filtering(ticket_37525):
    """Test that downloader filters out outgoing emails."""
    target_dir = ticket_37525

    # Parse the raw history to see what's available
    history_content = (target_dir / "history.txt").read_text()

    # Count all history entries (including outgoing emails)
    all_history_lines = [
        line
        for line in history_content.split("\n")
        if ":" in line and line.strip() and line.strip()[0].isdigit()
    ]

    # Count directories created (should exclude outgoing emails)
    created_dirs = [d for d in target_dir.iterdir() if d.is_dir()]

    # Should have fewer directories than total history entries due to filtering
    assert len(created_dirs) <= len(all_history_lines)

    # Verify no directory corresponds to "Outgoing email recorded by RT_System"
    for history_dir in created_dirs:
        message_content = (history_dir / "message.txt").read_text()
        assert "Outgoing email recorded by RT_System" not in message_content


@pytest.mark.e2e
def test_downloader_error_handling_invalid_ticket():
    """Test downloader error handling with invalid ticket ID."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_invalid"

        session = RTSession()
        session.authenticate()
        downloader = TicketDownloader(session)

        # Should handle invalid ticket gracefully (not crash)
        downloader.download_ticket("999999", parent_dir)

        # Should still create ticket directory
        ticket_dir = parent_dir / "rt999999"
        assert ticket_dir.exists(), (
            "Should create ticket directory even for invalid ticket"
        )

        # May or may not create files depending on RT server response
        # The important thing is that it doesn't crash


@pytest.mark.e2e
def test_downloader_directory_structure(tmp_path):
    """Test that downloader creates expected directory structure."""
    parent_dir = tmp_path / "nested" / "path"

    session = RTSession()
    session.authenticate()
    downloader = TicketDownloader(session)

    # Should create nested directories automatically
    downloader.download_ticket("37525", parent_dir)

    ticket_dir = parent_dir / "rt37525"
    assert ticket_dir.exists(), "Should create ticket directory"
    assert (ticket_dir / "metadata.txt").exists(), "Should create metadata file"

    # Verify parent directories were created
    assert parent_dir.exists(), "Should create parent directories"
    assert (tmp_path / "nested" / "path").exists(), "Should create full nested path"


@pytest.mark.e2e
def test_downloader_content_validation(ticket_37525):
    """Test that downloaded content has expected structure and format."""
    target_dir = ticket_37525

    # Verify metadata has expected parsed format (not raw RT response)
    metadata_content = (target_dir / "metadata.txt").read_text()
    assert "id: ticket/37525" in metadata_content, "Metadata should contain ticket ID"
    assert "Subject:" in metadata_content, "Metadata should contain subject"
    assert "Queue:" in metadata_content, "Metadata should contain queue"

    # Verify history has expected parsed format
    history_content = (target_dir / "history.txt").read_text()
    assert "# " in history_content, "History should have count header"
    assert ":" in history_content, "History should have history entries"

    # Verify attachments list has expected format
    attachments_content = (target_dir / "attachments.txt").read_text()
    assert "id: ticket/37525/attachments" in attachments_content, (
        "Attachments should contain ticket attachments ID"
    )

    # Verify individual history messages have parsed format
    for history_dir in target_dir.iterdir():
        if history_dir.is_dir():
            message_content = (history_dir / "message.txt").read_text()
            assert f"id: {history_dir.name}" in message_content, (
                f"Message in {history_dir.name} should contain history ID"
            )
            assert "Type:" in message_content, (
                f"Message in {history_dir.name} should contain Type field"
            )


@pytest.mark.e2e
def test_command_line_directory_structure():
    """Test that command line creates correct directory structure using subprocess."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "cli_test"

        # Run the download-ticket command using subprocess
        result = subprocess.run(
            ["download-ticket", "37525", str(parent_dir)],
            capture_output=True,
            text=True,
            timeout=300,  # 5 minute timeout
        )

        # Command should succeed
        assert result.returncode == 0, f"Command failed: {result.stderr}"

        # Verify the expected directory structure was created
        ticket_dir = parent_dir / "rt37525"
        assert ticket_dir.exists(), "Should create rt37525 directory"
        assert ticket_dir.is_dir(), "rt37525 should be a directory"

        # Verify basic files are present
        assert (ticket_dir / "metadata.txt").exists(), "Should create metadata.txt"
        assert (ticket_dir / "history.txt").exists(), "Should create history.txt"
        assert (ticket_dir / "attachments.txt").exists(), (
            "Should create attachments.txt"
        )

        # Verify at least some history directories exist
        history_dirs = [d for d in ticket_dir.iterdir() if d.is_dir()]
        assert len(history_dirs) > 0, "Should create history directories"

        # Verify each history directory has message.txt
        for history_dir in history_dirs:
            message_file = history_dir / "message.txt"
            assert message_file.exists(), f"Missing message.txt in {history_dir.name}"
