"""Global test fixtures for RT Tools."""

from pathlib import Path

import pytest
from pytest import fixture


def pytest_addoption(parser):
    """Add custom pytest command line options."""
    parser.addoption(
        "--integration",
        action="store_true",
        default=False,
        help="run integration tests",
    )


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test")


def pytest_collection_modifyitems(config, items):
    """Skip integration tests unless --integration option is used."""
    if config.getoption("--integration"):
        # When --integration is used, run all tests including integration tests
        return

    skip_integration = pytest.mark.skip(reason="need --integration option to run")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_integration)


@fixture
def fixtures_dir():
    """Return path to the test fixtures directory."""
    return Path(__file__).parent / "fixtures"


@fixture
def fixture_data_path(fixtures_dir):
    """Return path to test fixture data."""
    return fixtures_dir / "rt_ticket_data"
