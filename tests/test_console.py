"""Tests for the interactive rules guarding RT writes."""

import io

import pytest

from rt_tools.console import (
    NeedsExplicitYes,
    confirm,
    render_preview,
    resolve_body,
    strip_comments,
)
from rt_tools.writer import (
    ACTION_COMMENT,
    ACTION_CORRESPOND,
    ticket_transaction_request,
)


class FakeStdin(io.StringIO):
    """A stdin whose tty-ness the test decides."""

    def __init__(self, text: str = "", tty: bool = False):
        super().__init__(text)
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


# Consent


def test_non_interactive_without_yes_refuses_rather_than_sends():
    """A piped run that silently mails requestors is the failure to prevent."""
    request = _reply()

    with pytest.raises(NeedsExplicitYes, match="-y/--yes"):
        confirm(request, assume_yes=False, stdin=FakeStdin(tty=False))


def test_non_interactive_with_yes_proceeds():
    assert confirm(_reply(), assume_yes=True, stdin=FakeStdin(tty=False))


def test_interactive_prompt_accepts_y(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: "y")

    assert confirm(_reply(), stdin=FakeStdin(tty=True))
    assert "this sends email" in capsys.readouterr().out


def test_interactive_prompt_treats_anything_else_as_no(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "")

    assert not confirm(_reply(), stdin=FakeStdin(tty=True))


# Preview


def test_preview_shows_the_exact_content_block():
    request = ticket_transaction_request("39943", ACTION_COMMENT, "Line 1\nLine 2")

    preview = render_preview(request)

    assert "POST ticket/39943/comment" in preview
    assert "id: 39943\nAction: comment\nText: Line 1\n Line 2" in preview


def test_preview_warns_only_when_mail_goes_out():
    assert "this sends email" in render_preview(_reply())
    assert "this sends email" not in render_preview(
        ticket_transaction_request("39943", ACTION_COMMENT, "Internal.")
    )


# Body resolution


def test_message_argument_wins():
    assert resolve_body(message="from flag", stdin=FakeStdin("from stdin")) == (
        "from flag"
    )


def test_body_file_dash_reads_stdin():
    assert resolve_body(body_file="-", stdin=FakeStdin("piped body")) == "piped body"


def test_body_file_reads_the_file(tmp_path):
    path = tmp_path / "body.txt"
    path.write_text("body from file\n")

    assert resolve_body(body_file=path, stdin=FakeStdin(tty=True)) == "body from file"


def test_piped_stdin_is_used_when_nothing_else_is_given():
    assert resolve_body(stdin=FakeStdin("piped\nbody", tty=False)) == "piped\nbody"


def test_empty_body_aborts():
    with pytest.raises(ValueError, match="empty message"):
        resolve_body(message="   \n ")


def test_comment_lines_are_dropped_from_an_editor_buffer():
    text = "# a comment\nreal text\n#another\nmore text"

    assert strip_comments(text) == "real text\nmore text"


def _reply():
    return ticket_transaction_request("39943", ACTION_CORRESPOND, "Reply text.")
