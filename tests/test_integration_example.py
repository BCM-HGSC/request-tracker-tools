"""Example integration tests for RT Tools.

These tests require real RT server connection and are only run with --integration flag.
"""

import pytest


@pytest.mark.integration
def test_example_integration():
    """Example integration test that only runs with --integration flag."""
    # This would be a real integration test that connects to RT server
    # For now, just demonstrate that the marker works
    assert True


def test_regular_unit_test():
    """Regular unit test that always runs."""
    assert True


@pytest.mark.integration
def test_another_integration():
    """Another integration test."""
    # This would also require real RT server
    assert True
