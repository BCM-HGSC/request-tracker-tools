"""End-to-end tests for TicketDownloader with real server connections.

These tests connect to the actual RT server and download real ticket data.
They verify the complete download workflow including authentication,
data fetching, file organization, and XLSX conversion.

Note: Downloaded data will not exactly match sanitized fixture data
due to the fixtures being sanitized versions of the original.
"""

import tempfile
from pathlib import Path

import pytest

from rt_tools import RTSession
from rt_tools.downloader import TicketDownloader


@pytest.mark.e2e
def test_downloader_full_ticket_download():
    """Test complete ticket download workflow with real RT server."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "ticket_37525"

        # Create authenticated session
        session = RTSession()
        session.authenticate()

        # Download the ticket
        downloader = TicketDownloader(session)
        downloader.download_ticket("37525", target_dir)

        # Verify basic files are created
        assert target_dir.exists(), "Target directory should be created"
        assert (target_dir / "metadata.txt").exists(), "Metadata file should exist"
        assert (target_dir / "history.txt").exists(), "History file should exist"
        assert (target_dir / "attachments.txt").exists(), (
            "Attachments file should exist"
        )

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
def test_downloader_xlsx_conversion_e2e():
    """Test XLSX to TSV conversion with real downloaded data."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "ticket_37525"

        # Create authenticated session and download ticket
        session = RTSession()
        session.authenticate()
        downloader = TicketDownloader(session)
        downloader.download_ticket("37525", target_dir)

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
def test_downloader_attachment_filtering():
    """Test that downloader properly handles attachment filtering."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "ticket_37525"

        session = RTSession()
        session.authenticate()
        downloader = TicketDownloader(session)
        downloader.download_ticket("37525", target_dir)

        # Count attachment files actually downloaded

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
def test_downloader_outgoing_email_filtering():
    """Test that downloader filters out outgoing emails."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "ticket_37525"

        session = RTSession()
        session.authenticate()
        downloader = TicketDownloader(session)
        downloader.download_ticket("37525", target_dir)

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
        target_dir = Path(temp_dir) / "ticket_999999"

        session = RTSession()
        session.authenticate()
        downloader = TicketDownloader(session)

        # Should handle invalid ticket gracefully (not crash)
        downloader.download_ticket("999999", target_dir)

        # Should still create target directory
        assert target_dir.exists(), (
            "Should create target directory even for invalid ticket"
        )

        # May or may not create files depending on RT server response
        # The important thing is that it doesn't crash


@pytest.mark.e2e
def test_downloader_directory_structure():
    """Test that downloader creates expected directory structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "nested" / "path" / "ticket_37525"

        session = RTSession()
        session.authenticate()
        downloader = TicketDownloader(session)

        # Should create nested directories automatically
        downloader.download_ticket("37525", target_dir)

        assert target_dir.exists(), "Should create nested target directory"
        assert (target_dir / "metadata.txt").exists(), "Should create metadata file"

        # Verify parent directories were created
        assert target_dir.parent.exists(), "Should create parent directories"
        assert (temp_dir / "nested" / "path").exists(), "Should create full nested path"


@pytest.mark.e2e
def test_downloader_content_validation():
    """Test that downloaded content has expected structure and format."""
    with tempfile.TemporaryDirectory() as temp_dir:
        target_dir = Path(temp_dir) / "ticket_37525"

        session = RTSession()
        session.authenticate()
        downloader = TicketDownloader(session)
        downloader.download_ticket("37525", target_dir)

        # Verify metadata has expected RT format
        metadata_content = (target_dir / "metadata.txt").read_text()
        assert metadata_content.startswith("RT/"), (
            "Metadata should start with RT version"
        )
        assert "200 Ok" in metadata_content, "Metadata should indicate success"

        # Verify history has expected format
        history_content = (target_dir / "history.txt").read_text()
        assert history_content.startswith("RT/"), "History should start with RT version"
        assert "200 Ok" in history_content, "History should indicate success"

        # Verify attachments list format
        attachments_content = (target_dir / "attachments.txt").read_text()
        assert attachments_content.startswith("RT/"), (
            "Attachments should start with RT version"
        )
        assert "200 Ok" in attachments_content, "Attachments should indicate success"

        # Verify individual history messages
        for history_dir in target_dir.iterdir():
            if history_dir.is_dir():
                message_content = (history_dir / "message.txt").read_text()
                assert message_content.startswith("RT/"), (
                    f"Message in {history_dir.name} should start with RT version"
                )
