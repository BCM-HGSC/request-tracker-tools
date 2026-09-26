"""Tests for chronological ticket transcript rendering."""

import pytest

from rt_tools.parser import TicketMetadata
from rt_tools.transcript import (
    TranscriptAttachment,
    TranscriptEntry,
    render_transcript,
)


@pytest.fixture(scope="module")
def metadata():
    """Ticket metadata mirroring the rt37525 fixture."""
    return TicketMetadata(
        id="37525",
        subject="[SUBMISSION] MFTS Submission for Person Three",
        queue="Submissions",
        status="open",
        owner="user002",
        creator="user001",
        requestors=["user001@example.com"],
        created="Wed Jul 30 12:23:55 2025",
        last_updated="Tue Aug 05 11:45:05 2025",
    )


def test_render_transcript_full(metadata):
    """A two-entry transcript renders frontmatter, bodies, and attachments."""
    entries = [
        TranscriptEntry(
            history_id="1489286",
            creator="user001",
            created="2025-07-30 17:23:55",
            type="Create",
            description="Ticket created by user001",
            content="Please submit the files described in the spreadsheet.",
            attachments=[
                TranscriptAttachment(
                    id="1483997",
                    name="Example_Workbook.xlsx",
                    size="30.1k",
                    path="1489286/n1483997.xlsx",
                    conversions=[("Sheet1", "1489286/n1483997.tsv")],
                )
            ],
        ),
        TranscriptEntry(
            history_id="1489289",
            creator="user002",
            created="2025-07-30 17:31:02",
            type="Status",
            description="Status changed from new to open by user002",
        ),
    ]

    text = render_transcript(metadata, entries)

    assert text == (
        "---\n"
        "id: 37525\n"
        'subject: "[SUBMISSION] MFTS Submission for Person Three"\n'
        'queue: "Submissions"\n'
        'status: "open"\n'
        'owner: "user002"\n'
        'requestors: ["user001@example.com"]\n'
        'created: "Wed Jul 30 12:23:55 2025"\n'
        'last_updated: "Tue Aug 05 11:45:05 2025"\n'
        "---\n"
        "\n"
        "## 1489286 — user001 — 2025-07-30 17:23:55 — Create\n"
        "\n"
        "*Ticket created by user001*\n"
        "\n"
        "Please submit the files described in the spreadsheet.\n"
        "\n"
        "**Attachments**\n"
        "- `1489286/n1483997.xlsx` — Example_Workbook.xlsx (30.1k)\n"
        '  - converted: `1489286/n1483997.tsv` (sheet "Sheet1")\n'
        "\n"
        "## 1489289 — user002 — 2025-07-30 17:31:02 — Status\n"
        "\n"
        "*Status changed from new to open by user002*\n"
    )


def test_render_transcript_preserves_entry_order(metadata):
    """Entries render in the order given, not sorted by id."""
    entries = [
        TranscriptEntry("300", "a", "t1", "Correspond", "third"),
        TranscriptEntry("100", "b", "t2", "Comment", "first"),
        TranscriptEntry("200", "c", "t3", "Correspond", "second"),
    ]

    headings = [
        line
        for line in render_transcript(metadata, entries).split("\n")
        if line.startswith("## ")
    ]

    assert [h.split()[1] for h in headings] == ["300", "100", "200"]


def test_render_transcript_no_entries(metadata):
    """A ticket with no history renders frontmatter alone."""
    text = render_transcript(metadata, [])

    assert text.startswith("---\n")
    assert text.endswith("---\n")
    assert "## " not in text


def test_render_entry_without_content_is_description_only(metadata):
    """A no-content entry costs one heading and one description line."""
    entry = TranscriptEntry(
        history_id="1489291",
        creator="user002",
        created="2025-07-30 17:31:02",
        type="Set",
        description="Owner forcibly changed to user002 by user002",
    )

    text = render_transcript(metadata, [entry])
    section = text.split("---\n\n", 1)[1]

    assert section == (
        "## 1489291 — user002 — 2025-07-30 17:31:02 — Set\n"
        "\n"
        "*Owner forcibly changed to user002 by user002*\n"
    )


def test_render_attachment_without_conversions(metadata):
    """A non-XLSX attachment gets a bullet and no converted sub-bullet."""
    entry = TranscriptEntry(
        history_id="1489982",
        creator="user001",
        created="2025-08-01 16:02:31",
        type="Correspond",
        description="Correspondence added by user001",
        content="See attached.",
        attachments=[
            TranscriptAttachment(
                id="1484010",
                name="report.pdf",
                size="21.2k",
                path="1489982/n1484010.pdf",
            )
        ],
    )

    text = render_transcript(metadata, [entry])

    assert "- `1489982/n1484010.pdf` — report.pdf (21.2k)\n" in text
    assert "converted:" not in text


def test_render_frontmatter_quotes_and_escapes():
    """Subjects with quotes and leading brackets survive YAML parsing."""
    metadata = TicketMetadata(
        id="1",
        subject='[URGENT] "rush" job: today',
        queue="Submissions",
        status="new",
        owner="Nobody",
        creator="user001",
        requestors=[],
        created="",
        last_updated="",
    )

    text = render_transcript(metadata, [])

    assert 'subject: "[URGENT] \\"rush\\" job: today"' in text
    assert "requestors: []" in text


def test_render_frontmatter_multiple_requestors():
    """Multiple requestors render as a quoted YAML flow sequence."""
    metadata = TicketMetadata(
        id="1",
        subject="s",
        queue="q",
        status="open",
        owner="o",
        creator="c",
        requestors=["a@example.com", "b@example.com"],
        created="",
        last_updated="",
    )

    text = render_transcript(metadata, [])

    assert 'requestors: ["a@example.com", "b@example.com"]' in text
