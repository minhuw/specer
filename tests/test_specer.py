"""Tests for the specer package."""

from specer import hello


def test_hello() -> None:
    """Test the hello function."""
    result = hello()
    assert result == "Hello from specer!"
    assert isinstance(result, str)


def test_hello_not_empty() -> None:
    """Test that hello doesn't return empty string."""
    result = hello()
    assert result != ""
    assert len(result) > 0


class TestSpecerPackage:
    """Test class for specer package functionality."""

    def test_package_importable(self) -> None:
        """Test that the package can be imported successfully."""
        import specer  # noqa: F401

    def test_hello_function_exists(self) -> None:
        """Test that hello function exists and is callable."""
        from specer import hello

        assert callable(hello)
