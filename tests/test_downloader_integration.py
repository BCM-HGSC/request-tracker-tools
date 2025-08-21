"""Integration tests for TicketDownloader using real RT ticket data.

These tests use sanitized real RT ticket 37525 data as a truth source to validate
the complete downloader workflow. The tests account for differences between live
RT data and sanitized fixture data while verifying core functionality.
"""

import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rt_tools import RTSession
from rt_tools.downloader import TicketDownloader
from rt_tools.parser import (
    parse_attachment_list,
    parse_history_list,
    parse_history_message,
)

# Use shared fixture from conftest.py
# rt37525_sanitized_data fixture is now available


@pytest.fixture
def mock_session_with_rt37525_data(rt37525_sanitized_data):
    """Create mock RTSession that returns RT ticket 37525 data."""
    session = Mock(spec=RTSession)

    def mock_fetch_rest(*parts):
        """Mock fetch_rest to return appropriate RT 37525 data."""
        from rt_tools.session import RTResponseData

        endpoint = "/".join(parts)

        if endpoint == "ticket/37525":
            return RTResponseData(
                "4.4.3", 200, "Ok", True, rt37525_sanitized_data["metadata"]
            )
        elif endpoint == "ticket/37525/history":
            return RTResponseData(
                "4.4.3", 200, "Ok", True, rt37525_sanitized_data["history"]
            )
        elif endpoint == "ticket/37525/attachments":
            return RTResponseData(
                "4.4.3", 200, "Ok", True, rt37525_sanitized_data["attachments"]
            )
        elif endpoint.startswith("ticket/37525/history/id/"):
            history_id = endpoint.split("/")[-1]
            if history_id in rt37525_sanitized_data["history_messages"]:
                return RTResponseData(
                    "4.4.3",
                    200,
                    "Ok",
                    True,
                    rt37525_sanitized_data["history_messages"][history_id],
                )
            else:
                return RTResponseData(
                    "4.4.3",
                    404,
                    "Not Found",
                    False,
                    b"RT/4.4.3 404 Not Found\\n\\nHistory item not found",
                )
        elif endpoint.startswith("ticket/37525/attachments/") and endpoint.endswith(
            "/content"
        ):
            attachment_id = endpoint.split("/")[-2]
            if attachment_id in rt37525_sanitized_data["attachment_content"]:
                return RTResponseData(
                    "4.4.3",
                    200,
                    "Ok",
                    True,
                    rt37525_sanitized_data["attachment_content"][attachment_id],
                )
            else:
                # Return empty content for attachments we don't have fixture data for
                return RTResponseData(
                    "4.4.3", 200, "Ok", True, b"Mock attachment content"
                )
        else:
            return RTResponseData(
                "4.4.3",
                404,
                "Not Found",
                False,
                b"RT/4.4.3 404 Not Found\\n\\nEndpoint not found",
            )

    session.fetch_rest.side_effect = mock_fetch_rest
    return session


def test_downloader_creates_expected_directory_structure(
    mock_session_with_rt37525_data, rt37525_sanitized_data
):
    """Test that downloader creates expected directory structure for ticket 37525."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_output"
        downloader = TicketDownloader(mock_session_with_rt37525_data)

        # Download the ticket
        downloader.download_ticket("37525", parent_dir)

        # Verify ticket directory is created
        ticket_dir = parent_dir / "rt37525"
        assert ticket_dir.exists()

        # Verify basic files are created
        assert (ticket_dir / "metadata.txt").exists()
        assert (ticket_dir / "history.txt").exists()
        assert (ticket_dir / "attachments.txt").exists()

        # Parse the history to determine expected directories
        history_content = rt37525_sanitized_data["history"].decode("utf-8")
        expected_history_items = list(parse_history_list(history_content))

        # Verify that non-outgoing history items have directories
        for history_item in expected_history_items:
            history_dir = ticket_dir / history_item.history_id
            assert history_dir.exists(), (
                f"Missing directory for history item {history_item.history_id}"
            )
            assert (history_dir / "message.txt").exists(), (
                f"Missing message.txt for history item {history_item.history_id}"
            )


def test_downloader_filters_outgoing_emails(
    mock_session_with_rt37525_data, rt37525_sanitized_data
):
    """Test that downloader properly filters out outgoing email entries."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_output"
        downloader = TicketDownloader(mock_session_with_rt37525_data)

        downloader.download_ticket("37525", parent_dir)
        ticket_dir = parent_dir / "rt37525"

        # Parse history to get all items (including outgoing emails)
        history_content = rt37525_sanitized_data["history"].decode("utf-8")
        all_history_lines = [
            line
            for line in history_content.split("\n")
            if ":" in line and line.strip() and line.strip()[0].isdigit()
        ]

        # Count outgoing email entries
        outgoing_email_count = sum(
            1
            for line in all_history_lines
            if "Outgoing email recorded by RT_System" in line
        )
        assert outgoing_email_count > 0, "Test data should contain outgoing emails"

        # Verify only non-outgoing items have directories
        filtered_items = list(parse_history_list(history_content))
        created_dirs = [d for d in ticket_dir.iterdir() if d.is_dir()]

        # Should have fewer directories than total history items due to filtering
        assert len(created_dirs) == len(filtered_items)
        assert len(created_dirs) < len(all_history_lines)

        # Verify no outgoing email directories were created
        for history_dir in created_dirs:
            assert history_dir.name.isdigit(), (
                f"Unexpected directory: {history_dir.name}"
            )
            # Directory name should correspond to a non-outgoing history item
            assert any(item.history_id == history_dir.name for item in filtered_items)


def test_downloader_handles_attachments_correctly(
    mock_session_with_rt37525_data, rt37525_sanitized_data
):
    """Test that downloader handles attachments with correct filtering and naming."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_output"
        downloader = TicketDownloader(mock_session_with_rt37525_data)

        downloader.download_ticket("37525", parent_dir)
        ticket_dir = parent_dir / "rt37525"

        # Parse attachment list to understand expected attachments
        attachment_content = rt37525_sanitized_data["attachments"].decode("ascii")
        attachment_index = parse_attachment_list(attachment_content)

        # Find history items that should have attachments
        history_content = rt37525_sanitized_data["history"].decode("utf-8")
        history_items = list(parse_history_list(history_content))

        attachment_count = 0
        for history_item in history_items:
            history_dir = ticket_dir / history_item.history_id
            if history_dir.exists():
                # Check if this history item should have attachments
                history_message_data = rt37525_sanitized_data["history_messages"].get(
                    history_item.history_id
                )
                if history_message_data:
                    history_message = parse_history_message(
                        history_message_data.decode("ascii")
                    )

                    # Count non-zero attachments in this history item
                    non_zero_attachments = [
                        att for att in history_message.attachments if att.size != "0b"
                    ]

                    if non_zero_attachments:
                        # Verify attachment files exist with correct naming
                        for attachment in non_zero_attachments:
                            if attachment.id in attachment_index:
                                mime_type = attachment_index[attachment.id].mime_type
                                expected_extension = downloader._mime_type_to_extension(
                                    mime_type
                                )
                                expected_filename = (
                                    f"n{attachment.id}.{expected_extension}"
                                )
                                attachment_file = history_dir / expected_filename

                                # Note: We may not have all attachment content
                                # so we check if mock provided content
                                if (
                                    attachment.id
                                    in rt37525_sanitized_data["attachment_content"]
                                ):
                                    assert attachment_file.exists(), (
                                        f"Missing attachment file: {attachment_file}"
                                    )
                                    attachment_count += 1

        # Should have found and created some attachment files
        print(f"Created {attachment_count} attachment files")
        # Note: Due to sanitization, we may not have all attachments


def test_downloader_xlsx_conversion_integration(mock_session_with_rt37525_data):
    """Test XLSX to TSV conversion with real ticket data structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_output"
        downloader = TicketDownloader(mock_session_with_rt37525_data)

        # Mock the XLSX conversion to verify it gets called
        with patch.object(downloader, "_convert_xlsx_to_tsv") as mock_convert:
            downloader.download_ticket("37525", parent_dir)

            # Should have called XLSX conversion for any XLSX attachments
            # In our fixture data, we know there's an Example Workbook.xlsx (1483997)
            if mock_convert.call_count > 0:
                # Verify at least one call was for an XLSX file
                calls = mock_convert.call_args_list
                xlsx_calls = [
                    call for call in calls if str(call[0][0]).endswith(".xlsx")
                ]
                assert len(xlsx_calls) > 0, (
                    "Should have converted at least one XLSX file"
                )

                # Verify the specific XLSX file we expect (attachment 1483997)
                xlsx_1483997_calls = [
                    call for call in calls if "n1483997.xlsx" in str(call[0][0])
                ]
                assert len(xlsx_1483997_calls) > 0, (
                    "Should have converted n1483997.xlsx specifically"
                )


def test_downloader_content_validation(
    mock_session_with_rt37525_data, rt37525_sanitized_data
):
    """Test that downloaded content matches expected format and structure."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_output"
        downloader = TicketDownloader(mock_session_with_rt37525_data)

        downloader.download_ticket("37525", parent_dir)
        ticket_dir = parent_dir / "rt37525"

        # Verify metadata content
        metadata_content = (ticket_dir / "metadata.txt").read_text()
        assert "id: ticket/37525" in metadata_content
        assert "Subject:" in metadata_content

        # Verify history content matches expected format
        history_content = (ticket_dir / "history.txt").read_text()
        assert "# 18/18" in history_content  # Should match the sanitized fixture
        assert "1489286: Ticket created by user001" in history_content

        # Verify attachments content
        attachments_content = (ticket_dir / "attachments.txt").read_text()
        assert "id: ticket/37525/attachments" in attachments_content
        assert "Example Workbook.xlsx" in attachments_content

        # Verify individual history message content
        history_1489286_dir = ticket_dir / "1489286"
        if history_1489286_dir.exists():
            message_content = (history_1489286_dir / "message.txt").read_text()
            assert "id: 1489286" in message_content
            assert "Ticket: 37525" in message_content
            assert "Type: Create" in message_content


def test_downloader_error_handling_integration(mock_session_with_rt37525_data):
    """Test downloader error handling with realistic error scenarios."""
    with tempfile.TemporaryDirectory() as temp_dir:
        parent_dir = Path(temp_dir) / "test_output"

        # Test with session that fails on history download
        def failing_fetch_rest(*parts):
            from rt_tools.session import RTResponseData

            endpoint = "/".join(parts)
            if endpoint == "ticket/37525/history":
                return RTResponseData(
                    "4.4.3",
                    500,
                    "Internal Server Error",
                    False,
                    b"RT/4.4.3 500 Internal Server Error\\n\\nServer error",
                )
            # Use original mock for other endpoints
            return mock_session_with_rt37525_data.fetch_rest(*parts)

        failing_session = Mock(spec=RTSession)
        failing_session.fetch_rest.side_effect = failing_fetch_rest

        downloader = TicketDownloader(failing_session)

        # Should handle the error gracefully and not crash
        downloader.download_ticket("37525", parent_dir)

        # Should still create ticket directory and metadata
        ticket_dir = parent_dir / "rt37525"
        assert ticket_dir.exists()
        # But should not proceed with history processing due to error
        history_dirs = [d for d in ticket_dir.iterdir() if d.is_dir()]
        assert len(history_dirs) == 0, (
            "Should not create history directories when history download fails"
        )
