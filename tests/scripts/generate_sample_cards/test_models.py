"""Tests for scripts/generate_sample_cards/models.py."""

from __future__ import annotations

from scripts.generate_sample_cards.models import CardJob, CardSpec, FamilyMember


class TestFamilyMember:
    def test_creation_with_age(self) -> None:
        m = FamilyMember(first_name="Alice", role="parent", age=35)
        assert m.first_name == "Alice"
        assert m.role == "parent"
        assert m.age == 35

    def test_creation_without_age(self) -> None:
        m = FamilyMember(first_name="Fido", role="pet")
        assert m.first_name == "Fido"
        assert m.role == "pet"
        assert m.age is None

    def test_creation_with_none_age(self) -> None:
        m = FamilyMember(first_name="Bob", role="child", age=None)
        assert m.age is None


class TestCardSpecFromDict:
    def _full_dict(self) -> dict:
        return {
            "family_name": "Smith",
            "family_members": [
                {"first_name": "Alice", "role": "parent", "age": 40},
                {"first_name": "Bob", "role": "child", "age": 10},
            ],
            "name_format": "The Smith Family",
            "holiday": "Christmas",
            "greeting_text": "Merry Christmas!",
            "backstory_blurb": "What a year!",
            "visual_style": "minimalist",
            "color_scheme": ["#ff0000", "#00ff00"],
            "page_count": 2,
            "back_page_type": "blurb",
            "filename": "smith_christmas_2024.pdf",
            "image_prompt": "A family in the snow",
            "back_greeting": "Warm wishes!",
            "back_photo_mode": "single",
            "back_image_prompt": "Cozy interior shot",
        }

    def test_full_roundtrip(self) -> None:
        d = self._full_dict()
        spec = CardSpec.from_dict(d)
        assert spec.family_name == "Smith"
        assert spec.holiday == "Christmas"
        assert spec.greeting_text == "Merry Christmas!"
        assert spec.backstory_blurb == "What a year!"
        assert spec.visual_style == "minimalist"
        assert spec.color_scheme == ["#ff0000", "#00ff00"]
        assert spec.page_count == 2
        assert spec.back_page_type == "blurb"
        assert spec.filename == "smith_christmas_2024.pdf"
        assert spec.image_prompt == "A family in the snow"
        assert spec.back_greeting == "Warm wishes!"
        assert spec.back_photo_mode == "single"
        assert spec.back_image_prompt == "Cozy interior shot"

    def test_family_members_converted(self) -> None:
        d = self._full_dict()
        spec = CardSpec.from_dict(d)
        assert len(spec.family_members) == 2
        assert spec.family_members[0].first_name == "Alice"
        assert spec.family_members[0].role == "parent"
        assert spec.family_members[0].age == 40
        assert spec.family_members[1].first_name == "Bob"
        assert spec.family_members[1].age == 10

    def test_missing_optional_fields_use_defaults(self) -> None:
        d = {
            "family_name": "Jones",
            "family_members": [],
            "name_format": "The Jones Family",
            "holiday": "Easter",
            "greeting_text": "Happy Easter!",
            "visual_style": "playful",
            "color_scheme": ["#ff0000"],
            "page_count": 1,
            "filename": "jones.pdf",
            "image_prompt": "A spring garden",
        }
        spec = CardSpec.from_dict(d)
        assert spec.backstory_blurb == ""
        assert spec.back_page_type is None
        assert spec.back_greeting == ""
        assert spec.back_photo_mode == ""
        assert spec.back_image_prompt == ""

    def test_type_coercion_page_count(self) -> None:
        d = self._full_dict()
        d["page_count"] = "2"  # type: ignore[assignment]
        spec = CardSpec.from_dict(d)
        assert spec.page_count == 2
        assert isinstance(spec.page_count, int)

    def test_family_member_age_none_when_missing(self) -> None:
        d = self._full_dict()
        d["family_members"] = [{"first_name": "X", "role": "parent"}]  # no age key
        spec = CardSpec.from_dict(d)
        assert spec.family_members[0].age is None

    def test_family_member_age_coerced_to_int(self) -> None:
        d = self._full_dict()
        d["family_members"] = [{"first_name": "X", "role": "parent", "age": "35"}]  # type: ignore[assignment]
        spec = CardSpec.from_dict(d)
        assert spec.family_members[0].age == 35


class TestCardJob:
    def test_default_status(self) -> None:
        job = CardJob(index=1, family_name="Smith", holiday="Christmas", style="minimalist", back_page="none")
        assert job.status == "waiting"
        assert job.detail == ""

    def test_set_updates_status_and_detail(self) -> None:
        job = CardJob(index=1, family_name="Smith", holiday="Christmas", style="minimalist", back_page="none")
        job.set("gen_front", "5s")
        assert job.status == "gen_front"
        assert job.detail == "5s"

    def test_set_without_detail_clears_detail(self) -> None:
        job = CardJob(index=1, family_name="Smith", holiday="Christmas", style="minimalist", back_page="none")
        job.set("gen_front", "5s")
        job.set("done")
        assert job.status == "done"
        assert job.detail == ""

    def test_index_preserved(self) -> None:
        job = CardJob(index=42, family_name="X", holiday="Y", style="Z", back_page="none")
        assert job.index == 42
