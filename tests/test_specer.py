"""Tests for the specer package."""

import specer


class TestSpecerPackage:
    """Test class for specer package functionality."""

    def test_package_importable(self) -> None:
        """Test that the package can be imported successfully."""
        import specer  # noqa: F401

    def test_package_has_version(self) -> None:
        """Test that the package has a version attribute."""
        assert hasattr(specer, "__version__")
        assert isinstance(specer.__version__, str)
        assert specer.__version__ == "0.1.0"

    def test_package_metadata(self) -> None:
        """Test that package metadata is available."""
        assert hasattr(specer, "__author__")
        assert hasattr(specer, "__email__")
        assert specer.__author__ == "minhuw"
        assert specer.__email__ == "wangmh15@gmail.com"
