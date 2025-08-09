"""Global test fixtures for RT Tools."""

from pathlib import Path

from pytest import fixture


@fixture
def fixtures_dir():
    """Return path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"