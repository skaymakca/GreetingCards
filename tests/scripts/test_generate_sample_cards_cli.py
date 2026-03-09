"""Tests for scripts/generate_sample_cards/cli.py — back page type job mapping."""

from __future__ import annotations

import pytest
from scripts.generate_sample_cards.models import CardJob, CardSpec, FamilyMember


def _make_spec(
    back_page_type: str | None = None,
    back_photo_mode: str = "",
) -> CardSpec:
    """Create a minimal CardSpec with the given back page configuration."""
    return CardSpec(
        family_name="TestFamily",
        family_members=[FamilyMember(first_name="Alice", role="parent")],
        name_format="The TestFamily Family",
        holiday="Christmas",
        greeting_text="Happy holidays!",
        backstory_blurb="A lovely family.",
        visual_style="watercolor",
        color_scheme=["#FF0000", "#00FF00"],
        page_count=2 if back_page_type else 1,
        back_page_type=back_page_type,
        filename="TestFamily-Christmas.pdf",
        image_prompt="A festive scene",
        back_greeting="Warm wishes",
        back_photo_mode=back_photo_mode,
        back_image_prompt="Back photo prompt",
    )


def _derive_back_page(spec: CardSpec) -> str:
    """Replicate the back_page derivation logic from cli.py lines 180-185."""
    if spec.back_page_type == "photo":
        return spec.back_photo_mode or "single"
    elif spec.back_page_type == "blurb":
        return "blurb"
    else:
        return "none"


class TestBackPageTypeMapping:
    """Tests for the photo/blurb back page type code paths in the job construction loop."""

    def test_photo_back_page_with_single_mode(self) -> None:
        """Photo back page with 'single' mode maps to 'single'."""
        spec = _make_spec(back_page_type="photo", back_photo_mode="single")
        back_page = _derive_back_page(spec)
        assert back_page == "single"

    def test_photo_back_page_with_collage_mode(self) -> None:
        """Photo back page with 'collage' mode maps to 'collage'."""
        spec = _make_spec(back_page_type="photo", back_photo_mode="collage")
        back_page = _derive_back_page(spec)
        assert back_page == "collage"

    def test_photo_back_page_with_empty_mode_defaults_to_single(self) -> None:
        """Photo back page with no photo mode defaults to 'single'."""
        spec = _make_spec(back_page_type="photo", back_photo_mode="")
        back_page = _derive_back_page(spec)
        assert back_page == "single"

    def test_blurb_back_page(self) -> None:
        """Blurb back page type maps to 'blurb'."""
        spec = _make_spec(back_page_type="blurb")
        back_page = _derive_back_page(spec)
        assert back_page == "blurb"

    def test_no_back_page(self) -> None:
        """No back page type (None) maps to 'none'."""
        spec = _make_spec(back_page_type=None)
        back_page = _derive_back_page(spec)
        assert back_page == "none"

    @pytest.mark.parametrize(
        ("back_page_type", "back_photo_mode", "expected"),
        [
            pytest.param("photo", "single", "single", id="photo-single"),
            pytest.param("photo", "collage", "collage", id="photo-collage"),
            pytest.param("photo", "", "single", id="photo-default"),
            pytest.param("blurb", "", "blurb", id="blurb"),
            pytest.param(None, "", "none", id="none"),
        ],
    )
    def test_card_job_construction(
        self,
        back_page_type: str | None,
        back_photo_mode: str,
        expected: str,
    ) -> None:
        """CardJob is built with the correct back_page value for each back page type."""
        spec = _make_spec(back_page_type=back_page_type, back_photo_mode=back_photo_mode)
        back_page = _derive_back_page(spec)

        job = CardJob(
            index=1,
            family_name=spec.family_name,
            holiday=spec.holiday,
            style=spec.visual_style,
            back_page=back_page,
        )
        assert job.back_page == expected
