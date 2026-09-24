"""Tests for --version on every rt-tools console script."""

import pytest

from rt_tools import __version__, cli

ENTRY_POINTS = [
    ("download-ticket", cli.download_ticket_cli),
    ("dump-ticket", cli.dump_ticket),
    ("dump-rest", cli.dump_rest),
    ("dump-url", cli.dump_url),
    ("open-ticket", cli.open_ticket),
]


@pytest.mark.parametrize("prog, entry_point", ENTRY_POINTS)
def test_version_flag_exits_cleanly(monkeypatch, capsys, prog, entry_point):
    monkeypatch.setattr("sys.argv", [prog, "--version"])

    with pytest.raises(SystemExit) as exc_info:
        entry_point()

    assert exc_info.value.code == 0
    assert capsys.readouterr().out.strip() == f"{prog} {__version__}"
