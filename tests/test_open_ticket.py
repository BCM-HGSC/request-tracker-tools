"""Tests for the open-ticket entry point."""

import pytest

from rt_tools import cli


@pytest.fixture
def opened(monkeypatch):
    """Capture the URLs open_ticket hands to the browser."""
    urls = []
    monkeypatch.setattr(cli.webbrowser, "open", urls.append)
    return urls


def test_open_ticket_builds_the_display_url(monkeypatch, opened):
    monkeypatch.setattr("sys.argv", ["open-ticket", "37597"])

    cli.open_ticket()

    assert opened == ["https://rt.hgsc.bcm.edu/Ticket/Display.html?id=37597"]


def test_open_ticket_accepts_several_ids(monkeypatch, opened):
    monkeypatch.setattr("sys.argv", ["open-ticket", "1", "2"])

    cli.open_ticket()

    assert [url.rsplit("=", 1)[1] for url in opened] == ["1", "2"]


def test_open_ticket_requires_an_id(monkeypatch, opened):
    monkeypatch.setattr("sys.argv", ["open-ticket"])

    with pytest.raises(SystemExit):
        cli.open_ticket()

    assert opened == []
