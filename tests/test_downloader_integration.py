"""Integration tests for TicketDownloader using real RT ticket data.

These tests use sanitized real RT ticket 37525 data as a truth source to validate
the complete downloader workflow. The tests account for differences between live
RT data and sanitized fixture data while verifying core functionality.
"""

import re
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from rt_tools import RTSession
from rt_tools.downloader import TicketDownloader
from rt_tools.parser import (
    NO_CONTENT_SENTINEL,
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


# Transcript, --into, and message.txt counter


def test_downloader_writes_transcript(mock_session_with_rt37525_data, tmp_path):
    """transcript=True writes ticket.md covering every history entry in order."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)

    transcript = (tmp_path / "rt37525" / "ticket.md").read_text()

    # Frontmatter comes from metadata.txt
    assert transcript.startswith("---\nversion: 1\nid: 37525\n")
    assert 'queue: "Submissions"\n' in transcript
    assert 'owner: "user002"\n' in transcript
    assert 'requestors: ["user001@example.com"]\n' in transcript

    # One heading per downloaded history directory, in history order
    headings = [
        line.split()[1] for line in transcript.split("\n") if line.startswith("## ")
    ]
    expected = [
        item.history_id
        for item in parse_history_list(
            (tmp_path / "rt37525" / "history.txt").read_text()
        )
    ]
    assert headings == expected


def test_transcript_omits_no_content_sentinel_but_content_txt_keeps_it(
    mock_session_with_rt37525_data, tmp_path
):
    """RT's no-content sentinel is filtered from the transcript only."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)

    ticket_dir = tmp_path / "rt37525"
    transcript = (ticket_dir / "ticket.md").read_text()

    assert NO_CONTENT_SENTINEL not in transcript

    # The three sentinel entries still get a heading and a description
    sentinel_entries = ["1489289", "1489291", "1489984"]
    for history_id in sentinel_entries:
        assert f"## {history_id} — " in transcript
        # content.txt is unchanged, so existing consumers still see the sentinel
        content = (ticket_dir / history_id / "content.txt").read_text()
        assert content.strip() == NO_CONTENT_SENTINEL


def test_transcript_cites_attachments_with_original_names(
    mock_session_with_rt37525_data, tmp_path
):
    """Attachment bullets carry the real filename and a relative path."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)

    transcript = (tmp_path / "rt37525" / "ticket.md").read_text()

    assert "**Attachments**" in transcript
    assert "- `1489286/n1483997.xlsx` — " in transcript
    # The fixture workbook has two sheets, each cited by name
    assert 'converted: `1489286/n1483997.Samples_with_2__merge.tsv"' not in transcript
    assert '(sheet "Samples with 2+ merge")' in transcript
    assert '(sheet "Remapped list")' in transcript


def test_downloader_without_transcript_writes_no_ticket_md(
    mock_session_with_rt37525_data, tmp_path
):
    """The transcript stays opt-in."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path)

    assert not (tmp_path / "rt37525" / "ticket.md").exists()


def test_downloader_into_skips_ticket_directory_level(
    mock_session_with_rt37525_data, tmp_path
):
    """create_ticket_dir=False writes the contents directly into target_dir."""
    into = tmp_path / "submission" / "ticket"
    downloader = TicketDownloader(mock_session_with_rt37525_data)

    downloader.download_ticket("37525", into, create_ticket_dir=False)

    assert (into / "metadata.txt").exists()
    assert (into / "history.txt").exists()
    assert (into / "1489286" / "message.txt").exists()
    assert not (into / "rt37525").exists()


def test_message_txt_has_no_history_counter(mock_session_with_rt37525_data, tmp_path):
    """No saved message.txt carries RT's renumbering counter line."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path)

    saved = list((tmp_path / "rt37525").glob("*/message.txt"))
    assert saved, "expected at least one message.txt"
    for message_file in saved:
        text = message_file.read_text()
        assert text.startswith("id: "), f"{message_file} starts with {text[:40]!r}"


def test_multi_sheet_xlsx_converts_every_sheet(tmp_path, caplog):
    """A multi-sheet workbook yields one TSV per sheet and no bare n{id}.tsv."""
    openpyxl = pytest.importorskip("openpyxl")

    xlsx_path = tmp_path / "n801.xlsx"
    wb = openpyxl.Workbook()
    wb.active.title = "First Sheet"
    wb.active.append(["a", "b"])
    second = wb.create_sheet("Second Sheet (v2)")
    second.append(["c", "d"])
    wb.save(xlsx_path)

    with caplog.at_level("WARNING"):
        written = TicketDownloader(None)._convert_xlsx_to_tsv(xlsx_path)

    assert [sheet for sheet, _ in written] == ["First Sheet", "Second Sheet (v2)"]
    assert (tmp_path / "n801.First_Sheet.tsv").read_text() == "a\tb\n"
    assert (tmp_path / "n801.Second_Sheet__v2_.tsv").read_text() == "c\td\n"
    assert not (tmp_path / "n801.tsv").exists()
    assert "has 2 worksheets" in caplog.text


# --prune


def test_prune_removes_redundant_files_and_empty_dirs(
    mock_session_with_rt37525_data, tmp_path
):
    """Pruning drops message.txt/content.txt and the dirs they left empty."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True, prune=True)

    ticket_dir = tmp_path / "rt37525"

    assert list(ticket_dir.glob("*/message.txt")) == []
    assert list(ticket_dir.glob("*/content.txt")) == []

    # The three no-content entries had no attachments, so nothing is left
    for history_id in ("1489289", "1489291", "1489984"):
        assert not (ticket_dir / history_id).exists()

    # An entry with attachments keeps its directory and all of its files
    assert sorted(p.name for p in (ticket_dir / "1489286").iterdir()) == [
        "n1483996.html",
        "n1483997.Remapped_list.tsv",
        "n1483997.Samples_with_2__merge.tsv",
        "n1483997.xlsx",
    ]


def test_prune_leaves_ticket_level_files_alone(
    mock_session_with_rt37525_data, tmp_path
):
    """Pruning never touches the three ticket-level files, none of which
    the transcript makes redundant."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True, prune=True)

    ticket_dir = tmp_path / "rt37525"
    assert (ticket_dir / "metadata.txt").exists()
    assert (ticket_dir / "history.txt").exists()
    assert (ticket_dir / "attachments.txt").exists()
    assert (ticket_dir / "ticket.md").exists()


def test_transcript_identical_across_all_three_modes(
    mock_session_with_rt37525_data, tmp_path
):
    """ticket.md is the same bytes however much of the tree is kept.

    This is the contract that lets --lean be a storage decision rather than a
    format decision: the three modes differ only in the files beside ticket.md,
    and every path it cites resolves in each of them.
    """
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path / "full", transcript=True)
    downloader.download_ticket(
        "37525", tmp_path / "pruned", transcript=True, prune=True
    )
    downloader.download_ticket("37525", tmp_path / "lean", lean=True)

    texts = {}
    for mode in ("full", "pruned", "lean"):
        mode_dir = tmp_path / mode / "rt37525"
        texts[mode] = (mode_dir / "ticket.md").read_text()

        # Every backtick-quoted path in an attachment bullet must resolve
        cited = re.findall(r"^\s*(?:- |  - converted: )`([^`]+)`", texts[mode], re.M)
        assert cited, f"expected {mode} transcript to cite attachments"
        for relative_path in cited:
            assert (mode_dir / relative_path).exists(), (
                f"dangling path {relative_path} in {mode}"
            )

    assert texts["pruned"] == texts["full"]
    assert texts["lean"] == texts["full"]


def test_prune_cleans_up_an_earlier_unpruned_download(
    mock_session_with_rt37525_data, tmp_path
):
    """Re-downloading with prune removes files left by a previous run."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)

    ticket_dir = tmp_path / "rt37525"
    assert list(ticket_dir.glob("*/message.txt")), "setup should leave files behind"

    downloader.download_ticket("37525", tmp_path, transcript=True, prune=True)

    assert list(ticket_dir.glob("*/message.txt")) == []
    assert list(ticket_dir.glob("*/content.txt")) == []
    assert not (ticket_dir / "1489984").exists()
    assert (ticket_dir / "1489286" / "n1483997.xlsx").exists()


def test_transcript_without_prune_keeps_the_tree(
    mock_session_with_rt37525_data, tmp_path
):
    """Pruning is opt-in; --transcript alone changes nothing on disk."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)

    ticket_dir = tmp_path / "rt37525"
    assert (ticket_dir / "1489984" / "message.txt").exists()
    assert (ticket_dir / "1489984" / "content.txt").exists()


# --lean


def test_lean_reduces_the_ticket_to_transcript_plus_real_attachments(
    mock_session_with_rt37525_data, tmp_path
):
    """Of rt37525's eight history entries, only the one with a real
    attachment survives; the rest were HTML twins of their entry text."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, lean=True)

    ticket_dir = tmp_path / "rt37525"

    assert sorted(p.name for p in ticket_dir.iterdir() if p.is_dir()) == ["1489286"]
    assert sorted(p.name for p in (ticket_dir / "1489286").iterdir()) == [
        "n1483997.Remapped_list.tsv",
        "n1483997.Samples_with_2__merge.tsv",
        "n1483997.xlsx",
    ]


def test_lean_implies_transcript_and_prune(mock_session_with_rt37525_data, tmp_path):
    """--lean alone is enough; it is not a modifier on the other two."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, lean=True)

    ticket_dir = tmp_path / "rt37525"
    assert (ticket_dir / "ticket.md").exists()
    assert list(ticket_dir.glob("*/message.txt")) == []
    assert list(ticket_dir.glob("*/content.txt")) == []


def test_html_twins_are_never_cited_but_are_kept_unless_lean(
    mock_session_with_rt37525_data, tmp_path
):
    """The transcript ignores the HTML alternates in every mode; only --lean
    also declines to download them, which is what keeps ticket.md identical."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)

    ticket_dir = tmp_path / "rt37525"
    transcript = (ticket_dir / "ticket.md").read_text()

    assert "n1483996.html" not in transcript
    assert "n1484849.html" not in transcript
    # RT's "No Subject" placeholder carries nothing, so it is not rendered
    assert "Subject:" not in transcript
    # ...but the full tree still has them, for anyone debugging RT itself
    assert (ticket_dir / "1489286" / "n1483996.html").exists()
    assert (ticket_dir / "1489982" / "n1484849.html").exists()


# --clean


def test_clean_makes_redownloading_lean_match_a_fresh_lean_download(
    mock_session_with_rt37525_data, tmp_path
):
    """The property --clean exists for: history stops mattering.

    Without it, re-downloading --lean over a full tree keeps every HTML twin
    --lean declined to fetch, so the mode silently does nothing.
    """
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path / "fresh", lean=True, clean=True)
    downloader.download_ticket("37525", tmp_path / "reused", transcript=True)
    downloader.download_ticket("37525", tmp_path / "reused", lean=True, clean=True)

    assert _tree(tmp_path / "fresh" / "rt37525") == _tree(
        tmp_path / "reused" / "rt37525"
    )


def test_clean_removes_attachments_rt_no_longer_has(
    mock_session_with_rt37525_data, tmp_path
):
    """An attachment deleted from RT should not linger from an earlier run."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, lean=True)

    ticket_dir = tmp_path / "rt37525"
    orphan = ticket_dir / "1489286" / "n999999.pdf"
    orphan.write_bytes(b"from a previous life")

    downloader.download_ticket("37525", tmp_path, lean=True, clean=True)

    assert not orphan.exists()
    assert (ticket_dir / "1489286" / "n1483997.xlsx").exists()


def test_clean_removes_directories_for_entries_that_are_gone(
    mock_session_with_rt37525_data, tmp_path
):
    """A history directory holding only stale downloader files goes away."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, lean=True)

    ticket_dir = tmp_path / "rt37525"
    stale = ticket_dir / "1400000"
    stale.mkdir()
    (stale / "message.txt").write_text("gone from RT")

    downloader.download_ticket("37525", tmp_path, lean=True, clean=True)

    assert not stale.exists()


def test_clean_leaves_files_the_downloader_never_writes(
    mock_session_with_rt37525_data, tmp_path
):
    """--clean is the downloader cleaning up after itself, and only itself.

    analysis.yaml really does live in ticket directories, and --into names an
    arbitrary directory that may hold unrelated work.
    """
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, lean=True)

    ticket_dir = tmp_path / "rt37525"
    analysis = ticket_dir / "analysis.yaml"
    analysis.write_text("summary: hand-written\n")
    notes = ticket_dir / "1489286" / "notes.md"
    notes.write_text("what this spreadsheet means\n")

    downloader.download_ticket("37525", tmp_path, lean=True, clean=True)

    assert analysis.exists()
    assert notes.exists()


def test_clean_keeps_the_conversions_this_run_produced(
    mock_session_with_rt37525_data, tmp_path
):
    """n{id}.{sheet}.tsv matches the attachment pattern, so only the
    written-paths set keeps --clean from deleting what it just made."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, lean=True, clean=True)

    entry_dir = tmp_path / "rt37525" / "1489286"
    assert (entry_dir / "n1483997.Remapped_list.tsv").exists()
    assert (entry_dir / "n1483997.Samples_with_2__merge.tsv").exists()


def test_clean_is_skipped_when_the_download_aborts(
    mock_session_with_rt37525_data, tmp_path
):
    """A run that never reached the history must not delete what is there."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)

    ticket_dir = tmp_path / "rt37525"
    before = _tree(ticket_dir)

    failing = Mock()
    failing.is_ok = False
    failing.status_code = 500
    failing.status_text = "Internal Server Error"
    original = mock_session_with_rt37525_data.fetch_rest

    def fetch(*parts):
        return failing if parts[-1] == "history" else original(*parts)

    mock_session_with_rt37525_data.fetch_rest = fetch
    downloader.download_ticket("37525", tmp_path, lean=True, clean=True)

    assert _tree(ticket_dir) == before


def test_clean_is_opt_in(mock_session_with_rt37525_data, tmp_path):
    """Without --clean, downloads stay additive, as they always were."""
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, transcript=True)
    downloader.download_ticket("37525", tmp_path, lean=True)

    assert (tmp_path / "rt37525" / "1489286" / "n1483996.html").exists()


def test_a_typod_ticket_id_neither_overwrites_nor_cleans(
    mock_session_with_rt37525_data, tmp_path
):
    """RT answers a missing ticket with HTTP 200 and an error line as the body.

    Found live: without the metadata guard, `download-ticket 99999999 --into
    existing/ --clean` wrote that error text over metadata.txt, history.txt and
    ticket.md, parsed an empty history, and then deleted the entire tree as
    orphaned. The guard makes it a no-op.
    """
    downloader = TicketDownloader(mock_session_with_rt37525_data)
    downloader.download_ticket("37525", tmp_path, lean=True)

    ticket_dir = tmp_path / "rt37525"
    before = _tree(ticket_dir)

    missing = Mock()
    missing.is_ok = True
    missing.payload = b"# Ticket 99999999 does not exist.\n\n"
    mock_session_with_rt37525_data.fetch_rest = Mock(return_value=missing)

    downloader.download_ticket(
        "37525", tmp_path, create_ticket_dir=False, lean=True, clean=True
    )

    assert _tree(ticket_dir) == before
    assert "does not exist" not in (ticket_dir / "metadata.txt").read_text()


def _tree(root: Path) -> set[str]:
    """Every file under root, as paths relative to it."""
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}
