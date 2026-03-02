"""Tests for scripts/dmg/background.py."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from PIL import Image, ImageDraw
from scripts.dmg.background import _gradient, _render, generate

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
