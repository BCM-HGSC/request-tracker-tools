"""Global test fixtures for RT Tools."""

from pathlib import Path

import pytest
from pytest import fixture


def pytest_addoption(parser):
    """Add custom pytest command line options."""
    parser.addoption(
        "--e2e",
        action="store_true",
        default=False,
        help="run end-to-end tests",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "e2e: mark test as end-to-end test")


def pytest_collection_modifyitems(config, items):
    """Skip end-to-end tests unless --e2e option is used."""
    if config.getoption("--e2e"):
        # When --e2e is used, run all tests including end-to-end tests
        return

    skip_e2e = pytest.mark.skip(reason="need --e2e option to run")
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip_e2e)


@fixture(scope="session")
def fixtures_dir() -> Path:
    """Return path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@fixture(scope="session")
def fixture_data_path(fixtures_dir) -> Path:
    """Return path to test fixture data."""
    return fixtures_dir / "rt_ticket_data"


@fixture(scope="session")
def rt37525_sanitized_data(fixtures_dir):
    """Load sanitized RT ticket 37525 data for testing."""
    fixture_path = fixtures_dir / "rt37525_sanitized"

    # Load all fixture files
    data = {}
    data["metadata"] = (fixture_path / "metadata.txt").read_bytes()
    data["history"] = (fixture_path / "history.txt").read_bytes()
    data["attachments"] = (fixture_path / "attachments.txt").read_bytes()

    # Load individual history messages
    data["history_messages"] = {}
    for history_dir in fixture_path.iterdir():
        if history_dir.is_dir() and history_dir.name.isdigit():
            history_id = history_dir.name
            message_file = history_dir / "message.txt"
            if message_file.exists():
                data["history_messages"][history_id] = message_file.read_bytes()

    # Load attachment content (simulate what would be downloaded)
    data["attachment_content"] = {}
    for history_dir in fixture_path.iterdir():
        if history_dir.is_dir() and history_dir.name.isdigit():
            for attachment_file in history_dir.glob("n*.html"):
                # Extract attachment ID from filename (n1483996.html -> 1483996)
                attachment_id = attachment_file.stem[1:]  # Remove 'n' prefix
                data["attachment_content"][attachment_id] = attachment_file.read_bytes()
            for attachment_file in history_dir.glob("n*.xlsx"):
                attachment_id = attachment_file.stem[1:]
                data["attachment_content"][attachment_id] = attachment_file.read_bytes()
            # Also load TSV files for comparison (though they won't be "downloaded")
            for attachment_file in history_dir.glob("n*.tsv"):
                attachment_id = attachment_file.stem[1:]
                data["attachment_content"][f"{attachment_id}_tsv"] = (
                    attachment_file.read_bytes()
                )

    return data


@fixture(scope="session")
def rt37525_xlsx_fixtures(fixtures_dir):
    """Get XLSX and TSV fixture file paths for RT 37525."""
    return {
        "xlsx": fixtures_dir / "rt37525_sanitized" / "1489286" / "n1483997.xlsx",
        "tsv": fixtures_dir / "rt37525_sanitized" / "1489286" / "n1483997.tsv",
    }
