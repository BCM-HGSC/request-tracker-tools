from pytest import fixture

from rt_tools.parser import (
    Attachment,
    AttachmentMeta,
    HistoryMessage,
    parse_attachment_list,
    parse_history_message,
)

EXPECTED_CONTENT = """Greetings,
Lorem ipsum dolor sit amet, consectetur adipiscing elit.
Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua."""


@fixture(scope="module")
def sample_attachment_list_data(fixture_data_path) -> str:
    attachment_list_path = fixture_data_path / "37525-attachments.txt"
    attachment_list_data = attachment_list_path.read_text()
    return attachment_list_data


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


@fixture(scope="module")
def sample_history_data(fixture_data_path) -> str:
    hist_item_path = fixture_data_path / "37525-history-1489286.bin"
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
    assert msg.description == "Ticket created by user1"
    assert msg.content.startswith("Greetings")
    assert msg.creator == "user1"
    assert msg.created == "2025-07-30 17:23:55"
    assert len(msg.attachments) == 3


def test_parse_message_content(sample_history_data):
    msg = parse_history_message(sample_history_data)
    assert msg.content == EXPECTED_CONTENT


def test_parse_message_attachments(sample_history_data):
    msg = parse_history_message(sample_history_data)
    assert msg.attachments[0] == Attachment(id="1483995", name="untitled", size="0b")
    assert msg.attachments[2].name == "Example Workbook.xlsx"
