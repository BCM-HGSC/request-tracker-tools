"""Tests for download-ticket argument validation."""

import pytest

from rt_tools.cli import parse_download_ticket_arguments


def parse(monkeypatch, *argv):
    """Run the download-ticket parser over the given argument list."""
    monkeypatch.setattr("sys.argv", ["download-ticket", *argv])
    return parse_download_ticket_arguments()


def test_prune_requires_transcript(monkeypatch, capsys):
    # --prune alone would delete content with nothing replacing it
    with pytest.raises(SystemExit) as exc_info:
        parse(monkeypatch, "37525", "--prune")

    assert exc_info.value.code == 2
    assert "--prune requires --transcript" in capsys.readouterr().err


def test_prune_with_transcript_is_accepted(monkeypatch):
    args = parse(monkeypatch, "37525", "--transcript", "--prune")

    assert args.prune is True
    assert args.transcript is True


def test_flags_default_off(monkeypatch):
    args = parse(monkeypatch, "37525")

    assert args.prune is False
    assert args.transcript is False
    assert args.lean is False
    assert args.clean is False
    assert args.into is None


def test_lean_is_accepted_alone(monkeypatch):
    # --lean implies the other two, so the --prune guard must not fire
    args = parse(monkeypatch, "37525", "--lean")

    assert args.lean is True


def test_lean_has_a_short_form(monkeypatch):
    # This is the everyday mode until 2.0 makes it the default
    assert parse(monkeypatch, "37525", "-l").lean is True


def test_clean_is_independent_of_the_other_modes(monkeypatch):
    # --clean scopes itself to the downloader's own files, so it needs no
    # companion flag and constrains none
    assert parse(monkeypatch, "37525", "--clean").clean is True
    assert parse(monkeypatch, "37525", "-c", "-l").clean is True


def test_into_rejects_multiple_tickets(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse(monkeypatch, "37525", "37526", "--into", "work/ticket")

    assert exc_info.value.code == 2
    assert "--into takes a single ticket ID" in capsys.readouterr().err


def test_into_and_output_dir_are_mutually_exclusive(monkeypatch, capsys):
    with pytest.raises(SystemExit) as exc_info:
        parse(monkeypatch, "37525", "--into", "a", "--output-dir", "b")

    assert exc_info.value.code == 2
    assert "not allowed with argument" in capsys.readouterr().err
