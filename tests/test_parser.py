from pytest import fixture

from rt_tools.parser import (
    Attachment,
    AttachmentMeta,
    HistoryItemMeta,
    HistoryMessage,
    parse_attachment_list,
    parse_history_list,
    parse_history_message,
)

EXPECTED_CONTENT = """Hi All,

We would like to request data submission through MFTS to Person Three's
group for 69 ILWGS sample(s).

Please see the excel for the paths and transfer all files in the /alignment
folders, there should be 2 files per sample.

Please send the data files to the recipient, and include MD5 checksums with the
excel itself.

Person Four
user004@example.com

Previous submission for this group can be found at RT# 36164

Please let me know if you need any additional information, thanks!

Sincerely,
Person One
"""


@fixture(scope="module")
def sample_attachment_list_data(fixtures_dir) -> str:
    attachment_list_path = fixtures_dir / "rt37525_sanitized" / "attachments.txt"
    attachment_list_data = attachment_list_path.read_text()
    return attachment_list_data


@fixture(scope="module")
def sample_history_list_data(fixtures_dir) -> str:
    history_list_path = fixtures_dir / "rt37525_sanitized" / "history.txt"
    history_list_data = history_list_path.read_text()
    return history_list_data


def test_parse_attachment_list_basic(sample_attachment_list_data):
    attachment_index = parse_attachment_list(sample_attachment_list_data)
    assert len(attachment_index) == 37
    assert attachment_index["1483996"] == AttachmentMeta(
        "(Unnamed)",
        "text/html",
        "610b",
    )
    assert attachment_index["1483997"] == AttachmentMeta(
        "Example Workbook.xlsx",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "21.2k",
    )


def test_parse_history_list_basic(sample_history_list_data):
    history_items = list(parse_history_list(sample_history_list_data))

    # Should filter out outgoing emails and only return non-outgoing items
    assert len(history_items) > 0

    # Check first item (should be the initial ticket creation)
    first_item = history_items[0]
    assert isinstance(first_item, HistoryItemMeta)
    assert first_item.history_id == "1489286"
    assert first_item.history_event == "Ticket created by user001"

    # Verify that outgoing emails are filtered out
    for item in history_items:
        assert item.history_event != "Outgoing email recorded by RT_System"

    # Check that we have specific expected non-outgoing items
    history_ids = [item.history_id for item in history_items]
    assert "1489286" in history_ids  # Ticket created
    assert "1489289" in history_ids  # Given to user
    assert "1489291" in history_ids  # Owner set
    assert "1489982" in history_ids  # Correspondence added


def test_parse_history_list_filtering():
    # Test the filtering behavior more specifically
    test_data = """# 5/5 (/total)

1001: Ticket created by user1
1002: Outgoing email recorded by RT_System
1003: Correspondence added by user2
1004: Outgoing email recorded by RT_System
1005: Status changed from new to open by user1"""

    history_items = list(parse_history_list(test_data))

    # Should have 3 non-outgoing items
    assert len(history_items) == 3

    expected_items = [
        ("1001", "Ticket created by user1"),
        ("1003", "Correspondence added by user2"),
        ("1005", "Status changed from new to open by user1"),
    ]

    for i, (expected_id, expected_event) in enumerate(expected_items):
        assert history_items[i].history_id == expected_id
        assert history_items[i].history_event == expected_event


@fixture(scope="module")
def sample_history_data(fixtures_dir) -> str:
    hist_item_path = fixtures_dir / "rt37525_sanitized" / "1489286" / "message.txt"
    hist_item_data = hist_item_path.read_text()
    return hist_item_data


def test_parse_message_basic(sample_history_data):
    msg = parse_history_message(sample_history_data)

    assert isinstance(msg, HistoryMessage)
    assert msg.id == "1489286"
    assert msg.ticket == "37525"
    assert msg.time_taken == "0"
    assert msg.type == "Create"
    assert msg.field is None
    assert msg.old_value is None
    assert msg.new_value is None
    assert msg.data is None
    assert msg.description == "Ticket created by user001"
    assert msg.content.startswith("Hi All")
    assert msg.creator == "user001"
    assert msg.created == "2025-07-30 17:23:55"
    assert len(msg.attachments) == 3


def test_parse_message_content(sample_history_data):
    msg = parse_history_message(sample_history_data)
    assert msg.content == EXPECTED_CONTENT


def test_parse_message_attachments(sample_history_data):
    msg = parse_history_message(sample_history_data)
    assert msg.attachments[0] == Attachment(id="1483995", name="untitled", size="0b")
    assert msg.attachments[2].name == "Example Workbook.xlsx"


def test_parse_attachment_list_edge_cases():
    # Test with empty input
    empty_result = parse_attachment_list("")
    assert len(empty_result) == 0

    # Test with only header, no attachments
    header_only = "id: ticket/123/attachments\n\nAttachments:"
    header_result = parse_attachment_list(header_only)
    assert len(header_result) == 0

    # Test with single attachment
    single_attachment = """id: ticket/123/attachments

Attachments: 456: test.txt (text/plain / 1.2k)"""
    single_result = parse_attachment_list(single_attachment)
    assert len(single_result) == 1
    assert "456" in single_result
    assert single_result["456"].name == "test.txt"
    assert single_result["456"].mime_type == "text/plain"
    assert single_result["456"].size_str == "1.2k"


def test_parse_history_list_edge_cases():
    # Test with empty input
    empty_items = list(parse_history_list(""))
    assert len(empty_items) == 0

    # Test with only header
    header_only = "# 0/0 (/total)\n\n"
    header_items = list(parse_history_list(header_only))
    assert len(header_items) == 0

    # Test with only outgoing emails (should return empty)
    only_outgoing = """# 2/2 (/total)

1001: Outgoing email recorded by RT_System
1002: Outgoing email recorded by RT_System"""
    outgoing_items = list(parse_history_list(only_outgoing))
    assert len(outgoing_items) == 0


def test_parse_history_message_no_content():
    # Test history message without content section
    no_content_data = """# 1/1 (id/123/total)

id: 123
Ticket: 456
TimeTaken: 0
Type: Status
Field: Status
OldValue: new
NewValue: open
Data:
Description: Status changed from 'new' to 'open' by user1
Creator: user1
Created: 2025-01-01 12:00:00
Attachments:"""

    msg = parse_history_message(no_content_data)
    assert msg.id == "123"
    assert msg.ticket == "456"
    assert msg.type == "Status"
    assert msg.field == "Status"
    assert msg.old_value == "new"
    assert msg.new_value == "open"
    assert msg.content is None  # No content section
    assert len(msg.attachments) == 0


def test_parse_history_message_no_attachments():
    # Test history message without attachments
    no_attachments_data = """# 1/1 (id/789/total)

id: 789
Ticket: 123
TimeTaken: 5
Type: Comment
Field:
OldValue:
NewValue:
Data:
Description: Comments added by user2
Content: This is a simple comment without any attachments.

Creator: user2
Created: 2025-01-01 15:30:00
Attachments:"""

    msg = parse_history_message(no_attachments_data)
    assert msg.id == "789"
    assert msg.type == "Comment"
    assert msg.content.strip() == "This is a simple comment without any attachments."
    assert len(msg.attachments) == 0


def test_attachment_meta_dataclass():
    # Test AttachmentMeta dataclass construction
    meta = AttachmentMeta("test.pdf", "application/pdf", "150kb")
    assert meta.name == "test.pdf"
    assert meta.mime_type == "application/pdf"
    assert meta.size_str == "150kb"


def test_history_item_meta_dataclass():
    # Test HistoryItemMeta dataclass construction
    meta = HistoryItemMeta("12345", "Ticket created by testuser")
    assert meta.history_id == "12345"
    assert meta.history_event == "Ticket created by testuser"


def test_attachment_dataclass():
    # Test Attachment dataclass construction
    attachment = Attachment("999", "document.docx", "2.5MB")
    assert attachment.id == "999"
    assert attachment.name == "document.docx"
    assert attachment.size == "2.5MB"


def test_history_message_dataclass():
    # Test HistoryMessage dataclass construction with minimal data
    msg = HistoryMessage(
        id="111",
        ticket="222",
        time_taken="0",
        type="Create",
        field=None,
        old_value=None,
        new_value=None,
        data=None,
        description="Test description",
        content="Test content",
        creator="testuser",
        created="2025-01-01 10:00:00",
    )
    assert msg.id == "111"
    assert msg.ticket == "222"
    assert msg.type == "Create"
    assert len(msg.attachments) == 0  # Default empty list
