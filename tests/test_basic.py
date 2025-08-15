"""Basic tests to ensure CI pipeline works."""


def test_basic_import():
    """Test that basic imports work."""
    # This test ensures the basic Python environment is working
    assert True


def test_python_version():
    """Test that we're running on the expected Python version."""
    import sys

    assert sys.version_info >= (3, 11)


def test_uv_environment():
    """Test that uv environment is properly set up."""
    # This test will fail if dependencies aren't installed
    try:
        import pytest  # noqa: F401

        assert True
    except ImportError as e:
        pytest.fail(f"Missing dependency: {e}")


class TestExample:
    """Example test class to demonstrate pytest features."""

    def test_example_method(self):
        """Example test method."""
        result = 2 + 2
        assert result == 4

    def test_example_with_fixture(self, tmp_path):
        """Example test using pytest fixture."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello, World!")
        assert test_file.read_text() == "Hello, World!"
