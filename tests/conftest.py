"""Pytest configuration and fixtures."""

import pytest


@pytest.fixture()
def sample_data() -> dict[str, str]:
    """Sample data for testing."""
    return {"message": "Hello from specer!"}
