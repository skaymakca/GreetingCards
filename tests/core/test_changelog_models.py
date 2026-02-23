"""Tests for app.core.changelog_models module."""

from app.core.changelog_models import ChangelogVersion, ChangelogGroup


class TestChangelogVersion:
    """Tests for ChangelogVersion dataclass."""

    def test_construction(self):
        v = ChangelogVersion(
            version="0.8.0",
            title="0.8.0 — Native macOS Interface",
            date="2026-02-19",
            body_html="<p>Content</p>",
        )
        assert v.version == "0.8.0"
        assert v.title == "0.8.0 — Native macOS Interface"
        assert v.date == "2026-02-19"
        assert v.body_html == "<p>Content</p>"

    def test_in_progress_date(self):
        v = ChangelogVersion(
            version="1.0.0", title="1.0.0", date="in progress", body_html=""
        )
        assert v.date == "in progress"


class TestChangelogGroup:
    """Tests for ChangelogGroup dataclass."""

    def test_construction(self):
        g = ChangelogGroup(label="0.9.x", slug="0.9")
        assert g.label == "0.9.x"
        assert g.slug == "0.9"
        assert g.versions == []

    def test_versions_default_empty(self):
        g = ChangelogGroup(label="0.8.x", slug="0.8")
        assert g.versions == []

    def test_with_versions(self):
        v1 = ChangelogVersion("0.9.0", "0.9.0", "2026-02-20", "<p>A</p>")
        v2 = ChangelogVersion("0.9.1", "0.9.1", "2026-02-21", "<p>B</p>")
        g = ChangelogGroup(label="0.9.x", slug="0.9", versions=[v1, v2])
        assert len(g.versions) == 2
        assert g.versions[0].version == "0.9.0"
