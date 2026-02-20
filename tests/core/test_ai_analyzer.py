"""Tests for app.core.ai_analyzer module."""
import base64
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from PIL import Image

from app.core.ai_analyzer import (
    _strip_plural,
    clean_family_name,
    format_ai_error,
    _image_to_b64,
    _parse_response,
    _build_content_blocks,
    _normalize_images,
    _get_validated_api_key,
    AIResult,
    analyze_card_with_ai_async,
)


class TestStripPlural:
    """Tests for _strip_plural()."""

    @pytest.mark.parametrize("input_name,expected", [
        ("Walshes", "Walsh"),
        ("Marches", "March"),
        ("Foxes", "Fox"),
        ("Smiths", "Smith"),
        ("Ross", "Ross"),       # Ends in 'ss' — no strip
        ("Clarks", "Clarks"),   # -rks not in strip set
        ("Richards", "Richard"),  # -rds: name[-3:-1]="rd" is in strip set
        ("Stewarts", "Stewart"), # -rts → strip
        ("", ""),
        ("Ab", "Ab"),           # Too short
    ])
    def test_strip_plural(self, input_name, expected):
        assert _strip_plural(input_name) == expected

    def test_short_names_unchanged(self):
        assert _strip_plural("As") == "As"


class TestCleanFamilyName:
    """Tests for clean_family_name()."""

    def test_removes_the(self):
        assert "The" not in clean_family_name("The Smith")

    def test_removes_family(self):
        assert "Family" not in clean_family_name("Smith Family")

    def test_removes_from_prefix(self):
        assert "From:" not in clean_family_name("From: Smith")

    def test_removes_quotes(self):
        result = clean_family_name('"Smith"')
        assert '"' not in result
        assert result == "Smith"

    def test_removes_smart_quotes(self):
        result = clean_family_name("\u201CSmith\u201D")
        assert result == "Smith"

    def test_strips_punctuation(self):
        result = clean_family_name("Smith.,!")
        assert result == "Smith"

    def test_removes_colon_prefix(self):
        assert clean_family_name("Name: Smith") == "Smith"

    def test_empty_string(self):
        assert clean_family_name("") == ""

    def test_strips_plural(self):
        assert clean_family_name("Smiths") == "Smith"

    def test_sent_by_prefix(self):
        assert "Sent by:" not in clean_family_name("Sent by: Smith")

    def test_full_cleanup(self):
        result = clean_family_name('The "Smiths" Family')
        assert result == "Smith"


class TestFormatAiError:
    """Tests for format_ai_error()."""

    def test_auth_error(self):
        import anthropic
        err = anthropic.AuthenticationError(
            message="invalid key",
            response=MagicMock(status_code=401),
            body=None,
        )
        assert "Invalid API key" in format_ai_error(err)

    def test_rate_limit_error(self):
        import anthropic
        err = anthropic.RateLimitError(
            message="rate limited",
            response=MagicMock(status_code=429),
            body=None,
        )
        assert "Rate limit" in format_ai_error(err)

    def test_timeout_error(self):
        """APITimeoutError should be caught before APIConnectionError."""
        import anthropic
        err = anthropic.APITimeoutError(request=MagicMock())
        assert "timed out" in format_ai_error(err).lower()

    def test_connection_error(self):
        import anthropic
        err = anthropic.APIConnectionError(request=MagicMock())
        assert "connection" in format_ai_error(err).lower()

    def test_status_error(self):
        import anthropic
        err = anthropic.APIStatusError(
            message="server error",
            response=MagicMock(status_code=500),
            body=None,
        )
        result = format_ai_error(err)
        assert "500" in result
        assert "API error" in result

    def test_generic_error(self):
        err = Exception("something broke")
        assert "something broke" in format_ai_error(err)


class TestImageToB64:
    """Tests for _image_to_b64()."""

    def test_returns_valid_base64(self):
        img = Image.new("RGB", (10, 10), "red")
        result = _image_to_b64(img)
        # Should be decodable
        decoded = base64.standard_b64decode(result)
        assert len(decoded) > 0

    def test_result_is_png(self):
        img = Image.new("RGB", (10, 10), "blue")
        result = _image_to_b64(img)
        decoded = base64.standard_b64decode(result)
        # PNG magic bytes
        assert decoded[:4] == b"\x89PNG"


class TestParseResponse:
    """Tests for _parse_response()."""

    def test_unknown_returns_empty(self):
        result = _parse_response("UNKNOWN")
        assert result.best_name == ""
        assert result.alternates == []

    def test_single_name(self):
        result = _parse_response("Smith")
        assert result.best_name == "Smith"
        assert result.alternates == []

    def test_multiple_names(self):
        result = _parse_response("Smith\nJones")
        assert result.best_name == "Smith"
        assert result.alternates == ["Jones"]

    def test_filters_long_lines(self):
        long_text = "Smith\n" + "x" * 51
        result = _parse_response(long_text)
        assert result.best_name == "Smith"
        assert len(result.alternates) == 0

    def test_filters_skip_words(self):
        result = _parse_response("Smith\nThe card shows a family name")
        assert result.best_name == "Smith"
        assert len(result.alternates) == 0

    def test_empty_lines_filtered(self):
        result = _parse_response("Smith\n\n\nJones")
        assert result.best_name == "Smith"
        assert result.alternates == ["Jones"]


class TestAnalyzeCardWithAi:
    """Tests for analyze_card_with_ai_async() (unified async path)."""

    @pytest.mark.asyncio
    @patch("app.core.ai_analyzer.get_api_key", return_value=None)
    async def test_no_api_key_raises(self, mock_key):
        img = Image.new("RGB", (10, 10))
        with pytest.raises(ValueError, match="not configured"):
            await analyze_card_with_ai_async(img)

    @pytest.mark.asyncio
    @patch("app.core.ai_analyzer.get_ai_model", return_value="claude-sonnet-4-6")
    @patch("app.core.ai_analyzer.get_api_key", return_value="sk-test")
    async def test_calls_anthropic(self, mock_key, mock_model):
        import anthropic
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Smith")]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        with patch.object(anthropic, "AsyncAnthropic", return_value=mock_client):
            result = await analyze_card_with_ai_async(Image.new("RGB", (10, 10)))
            assert result.best_name == "Smith"

    @pytest.mark.asyncio
    @patch("app.core.ai_analyzer.get_ai_model", return_value="claude-sonnet-4-6")
    @patch("app.core.ai_analyzer.get_api_key", return_value="sk-test")
    async def test_accepts_single_image(self, mock_key, mock_model):
        import anthropic
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Jones")]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        with patch.object(anthropic, "AsyncAnthropic", return_value=mock_client):
            result = await analyze_card_with_ai_async(Image.new("RGB", (10, 10)))
            assert result.best_name == "Jones"

    @pytest.mark.asyncio
    @patch("app.core.ai_analyzer.get_ai_model", return_value="claude-sonnet-4-6")
    @patch("app.core.ai_analyzer.get_api_key", return_value="sk-test")
    async def test_accepts_image_list(self, mock_key, mock_model):
        import anthropic
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Smith")]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        with patch.object(anthropic, "AsyncAnthropic", return_value=mock_client):
            imgs = [Image.new("RGB", (10, 10)), Image.new("RGB", (10, 10))]
            result = await analyze_card_with_ai_async(imgs)
            assert result.best_name == "Smith"

    @pytest.mark.asyncio
    @patch("app.core.ai_analyzer.get_ai_model", return_value="claude-sonnet-4-6")
    @patch("app.core.ai_analyzer.get_api_key", return_value="sk-test")
    async def test_uses_configured_model(self, mock_key, mock_model):
        """Verifies the configured model is passed to the API."""
        import anthropic
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Smith")]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        with patch.object(anthropic, "AsyncAnthropic", return_value=mock_client):
            await analyze_card_with_ai_async(Image.new("RGB", (10, 10)))
            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs[1]["model"] == "claude-sonnet-4-6"


class TestAnalyzeCardWithAiAsync:
    """Tests for analyze_card_with_ai_async()."""

    @pytest.mark.asyncio
    @patch("app.core.ai_analyzer.get_api_key", return_value=None)
    async def test_no_api_key_raises(self, mock_key):
        img = Image.new("RGB", (10, 10))
        with pytest.raises(ValueError, match="not configured"):
            await analyze_card_with_ai_async(img)

    @pytest.mark.asyncio
    @patch("app.core.ai_analyzer.get_ai_model", return_value="claude-sonnet-4-6")
    @patch("app.core.ai_analyzer.get_api_key", return_value="sk-test")
    async def test_calls_async_anthropic(self, mock_key, mock_model):
        import anthropic
        mock_msg = MagicMock()
        mock_msg.content = [MagicMock(text="Smith")]
        mock_client = MagicMock()
        mock_client.messages.create = AsyncMock(return_value=mock_msg)

        with patch.object(anthropic, "AsyncAnthropic", return_value=mock_client):
            result = await analyze_card_with_ai_async(Image.new("RGB", (10, 10)))
            assert result.best_name == "Smith"


class TestBuildContentBlocks:
    """Tests for _build_content_blocks()."""

    def test_single_image(self):
        """Single image → 1 image block + 1 text block."""
        img = Image.new("RGB", (10, 10))
        blocks = _build_content_blocks([img])
        assert len(blocks) == 2
        assert blocks[0]["type"] == "image"
        assert blocks[1]["type"] == "text"
        assert "1 page" in blocks[1]["text"]

    def test_multiple_images(self):
        """Multiple images → N image blocks + 1 text block with 'pages'."""
        imgs = [Image.new("RGB", (10, 10)) for _ in range(3)]
        blocks = _build_content_blocks(imgs)
        assert len(blocks) == 4  # 3 images + 1 text
        assert blocks[2]["type"] == "image"
        assert "3 pages" in blocks[3]["text"]


class TestNormalizeImages:
    """Tests for _normalize_images()."""

    def test_single_image_to_list(self):
        img = Image.new("RGB", (10, 10))
        result = _normalize_images(img)
        assert isinstance(result, list)
        assert len(result) == 1

    def test_list_passes_through(self):
        imgs = [Image.new("RGB", (10, 10))]
        result = _normalize_images(imgs)
        assert result is imgs


class TestGetValidatedApiKey:
    """Tests for _get_validated_api_key()."""

    @patch("app.core.ai_analyzer.get_api_key", return_value=None)
    def test_no_key_raises(self, mock_key):
        with pytest.raises(ValueError, match="not configured"):
            _get_validated_api_key()

    @patch("app.core.ai_analyzer.get_api_key", return_value="sk-test")
    def test_returns_key(self, mock_key):
        assert _get_validated_api_key() == "sk-test"


class TestParseResponseEdgeCases:
    """Edge case tests for _parse_response()."""

    def test_unknown_case_insensitive(self):
        """'UNKNOWN', 'unknown', 'Unknown' all return empty AIResult."""
        for text in ["UNKNOWN", "unknown", "Unknown", "  UNKNOWN  "]:
            result = _parse_response(text)
            assert result.best_name == ""
            assert result.alternates == []

    def test_empty_response(self):
        """Empty string returns empty AIResult."""
        result = _parse_response("")
        assert result.best_name == ""

    def test_long_lines_filtered(self):
        """Lines over 50 chars are filtered out."""
        long_line = "A" * 51
        result = _parse_response(f"Smith\n{long_line}\nJones")
        assert result.best_name == "Smith"
        assert result.alternates == ["Jones"]

    def test_skip_words_filtered(self):
        """Lines containing skip words are filtered out."""
        result = _parse_response("Smith\nThis page shows a card\nJones")
        assert result.best_name == "Smith"
        assert result.alternates == ["Jones"]

    def test_malformed_multiline(self):
        """Response with blank lines and whitespace is handled."""
        result = _parse_response("  Smith  \n\n  \n  Jones  \n\n")
        assert result.best_name == "Smith"
        assert result.alternates == ["Jones"]
