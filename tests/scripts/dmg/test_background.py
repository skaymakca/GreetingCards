"""Tests for scripts/dmg/background.py."""

from __future__ import annotations

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image, ImageDraw
from scripts.dmg.background import APP_X, APP_Y, APPS_X, _gradient, _render, _sf_chevron, generate, main

# A small transparent RGBA image standing in for the SF Symbol chevron
_FAKE_CHEVRON = Image.new("RGBA", (40, 60), (155, 170, 190, 255))


class TestGradient:
    def test_left_pixel_color(self) -> None:
        w, h = 100, 50
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        _gradient(draw, w, h)
        # Left edge should be close to (210, 220, 232)
        pixel = img.getpixel((0, h // 2))
        assert isinstance(pixel, tuple)
        assert abs(pixel[0] - 210) <= 2
        assert abs(pixel[1] - 220) <= 2
        assert abs(pixel[2] - 232) <= 2

    def test_right_pixel_color(self) -> None:
        w, h = 100, 50
        img = Image.new("RGB", (w, h))
        draw = ImageDraw.Draw(img)
        _gradient(draw, w, h)
        # Right edge should be close to (246, 248, 251)
        pixel = img.getpixel((w - 1, h // 2))
        assert isinstance(pixel, tuple)
        assert abs(pixel[0] - 246) <= 2
        assert abs(pixel[1] - 248) <= 2
        assert abs(pixel[2] - 251) <= 2


class TestRender:
    def test_scale_1_image_size(self) -> None:
        with patch("scripts.dmg.background._sf_chevron", return_value=_FAKE_CHEVRON):
            img = _render(1)
        assert img.width == 660
        assert img.height == 480

    def test_scale_2_image_size(self) -> None:
        with patch("scripts.dmg.background._sf_chevron", return_value=_FAKE_CHEVRON):
            img = _render(2)
        assert img.width == 1320
        assert img.height == 960

    def test_returns_rgb_image(self) -> None:
        with patch("scripts.dmg.background._sf_chevron", return_value=_FAKE_CHEVRON):
            img = _render(1)
        assert img.mode == "RGB"


class TestGenerate:
    def test_creates_both_outputs(self, tmp_path: Path) -> None:
        output_1x = tmp_path / "background.png"
        output_2x = tmp_path / "background@2x.png"

        with (
            patch("scripts.dmg.background.OUTPUT", output_1x),
            patch("scripts.dmg.background.OUTPUT_2X", output_2x),
            patch("scripts.dmg.background._sf_chevron", return_value=_FAKE_CHEVRON),
        ):
            result = generate()

        assert output_1x.exists()
        assert output_2x.exists()
        assert result == output_1x

    def test_returns_1x_path(self, tmp_path: Path) -> None:
        output_1x = tmp_path / "background.png"
        output_2x = tmp_path / "background@2x.png"

        with (
            patch("scripts.dmg.background.OUTPUT", output_1x),
            patch("scripts.dmg.background.OUTPUT_2X", output_2x),
            patch("scripts.dmg.background._sf_chevron", return_value=_FAKE_CHEVRON),
        ):
            result = generate()

        assert result == output_1x


class TestSfChevron:
    def test_symbol_not_found_raises(self) -> None:
        mock_appkit = MagicMock()
        mock_foundation = MagicMock()
        mock_appkit.NSImage.imageWithSystemSymbolName_accessibilityDescription_.return_value = None

        with (
            patch.dict("sys.modules", {"AppKit": mock_appkit, "Foundation": mock_foundation}),
            pytest.raises(RuntimeError, match=r"SF Symbol.*not found"),
        ):
            _sf_chevron(1)

    def test_render_chevron_paste_position(self) -> None:
        """Verify the chevron is pasted at the midpoint between app and Applications icons."""
        scale = 1
        chevron = _FAKE_CHEVRON

        with patch("scripts.dmg.background._sf_chevron", return_value=chevron):
            img = _render(scale)

        # Expected paste position (from background.py _render logic)
        cx = (APP_X + APPS_X) // 2 * scale
        cy = APP_Y * scale
        expected_paste_x = cx - chevron.width // 2
        expected_paste_y = cy - chevron.height // 2

        # The chevron colour should appear at the paste position
        pixel = img.getpixel((expected_paste_x + chevron.width // 2, expected_paste_y + chevron.height // 2))
        assert isinstance(pixel, tuple)
        # The center pixel of the fake chevron is (155, 170, 190)
        assert pixel == (155, 170, 190)

    def test_successful_rendering(self) -> None:
        """Mock the full AppKit call chain and verify _sf_chevron returns an RGBA PIL Image."""
        # Create fake PNG bytes from a small test image
        fake_img = Image.new("RGBA", (20, 30), (155, 170, 190, 255))
        buf = io.BytesIO()
        fake_img.save(buf, format="PNG")
        fake_png_bytes = buf.getvalue()

        mock_appkit = MagicMock()
        mock_foundation = MagicMock()

        # NSImage.imageWithSystemSymbolName_accessibilityDescription_ returns a non-None image
        mock_ns_image = MagicMock()
        mock_appkit.NSImage.imageWithSystemSymbolName_accessibilityDescription_.return_value = mock_ns_image

        # imageWithSymbolConfiguration_ returns the configured image
        mock_configured_image = MagicMock()
        mock_ns_image.imageWithSymbolConfiguration_.return_value = mock_configured_image

        # size() returns an object with width and height attributes
        mock_size = MagicMock()
        mock_size.width = 20
        mock_size.height = 30
        mock_configured_image.size.return_value = mock_size

        # NSBitmapImageRep.alloc().initWith..._ returns the rep mock
        mock_rep = MagicMock()
        mock_alloc = MagicMock()
        mock_alloc.initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_.return_value = mock_rep
        mock_appkit.NSBitmapImageRep.alloc.return_value = mock_alloc

        # NSGraphicsContext.graphicsContextWithBitmapImageRep_ returns a context
        mock_ctx = MagicMock()
        mock_appkit.NSGraphicsContext.graphicsContextWithBitmapImageRep_.return_value = mock_ctx

        # rep.representationUsingType_properties_ returns the fake PNG bytes
        mock_rep.representationUsingType_properties_.return_value = fake_png_bytes

        with patch.dict("sys.modules", {"AppKit": mock_appkit, "Foundation": mock_foundation}):
            result = _sf_chevron(1)

        assert isinstance(result, Image.Image)
        assert result.mode == "RGBA"
        assert result.size == (20, 30)

        # Verify the key AppKit calls were made
        mock_appkit.NSImage.imageWithSystemSymbolName_accessibilityDescription_.assert_called_once()
        mock_ns_image.imageWithSymbolConfiguration_.assert_called_once()
        mock_appkit.NSGraphicsContext.saveGraphicsState.assert_called_once()
        mock_appkit.NSGraphicsContext.restoreGraphicsState.assert_called_once()
        mock_rep.representationUsingType_properties_.assert_called_once()


class TestMain:
    def test_prints_path(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Verify main() prints the generated path to stdout."""
        fake_path = Path("/tmp/dmg/background.png")
        with patch("scripts.dmg.background.generate", return_value=fake_path):
            main()

        captured = capsys.readouterr()
        assert str(fake_path) in captured.out
        assert captured.out.strip() == f"Generated {fake_path}"
