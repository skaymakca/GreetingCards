"""Tests for app.core.constants module."""

from datetime import datetime

from app.core.constants import default_year


class TestDefaultYear:
    """Tests for default_year()."""

    def test_returns_previous_year(self) -> None:
        """default_year() returns the previous calendar year as a string."""
        current_year = datetime.now().year
        assert default_year() == str(current_year - 1)

    def test_returns_string(self) -> None:
        """default_year() returns a string, not an int."""
        result = default_year()
        assert isinstance(result, str)
        assert result.isdigit()
        assert len(result) == 4
