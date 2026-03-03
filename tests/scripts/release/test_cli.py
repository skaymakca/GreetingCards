"""Tests for scripts/release/cli.py."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from scripts.release.cli import build_draft_command, extract_changelog, generate_checksum

_SAMPLE_CHANGELOG = """\
# Changelog

## 0.12.0 — Scripting & Distribution (2026-03-02)

AppleScript automation and a polished macOS installer.

- AppleScript scripting support
- DMG installer with Applications shortcut

## 0.11.0 — Name Intelligence & Smoother Workflow (2026-02-27)

Better name recognition.

- Non-modal progress strip
- Master family name database
"""


class TestExtractChangelog:
    def test_extracts_version_body(self, tmp_path: pathlib.Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(_SAMPLE_CHANGELOG, encoding="utf-8")

        result = extract_changelog("0.12.0", changelog)

        assert "AppleScript automation" in result
        assert "DMG installer" in result
        assert "## 0.12.0" not in result
        assert "## 0.11.0" not in result

    def test_extracts_last_version(self, tmp_path: pathlib.Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(_SAMPLE_CHANGELOG, encoding="utf-8")

        result = extract_changelog("0.11.0", changelog)

        assert "Non-modal progress strip" in result
        assert "AppleScript" not in result

    def test_version_not_found_raises(self, tmp_path: pathlib.Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(_SAMPLE_CHANGELOG, encoding="utf-8")

        with pytest.raises(ValueError, match=r"99\.0\.0"):
            extract_changelog("99.0.0", changelog)

    def test_returns_stripped_body_with_trailing_newline(self, tmp_path: pathlib.Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(_SAMPLE_CHANGELOG, encoding="utf-8")

        result = extract_changelog("0.12.0", changelog)

        assert not result.startswith("\n")
        assert result.endswith("\n")


class TestGenerateChecksum:
    def test_creates_checksum_file(self, tmp_path: pathlib.Path) -> None:
        dmg = tmp_path / "dist" / "Greeting-Cards-1.0.0.dmg"
        dmg.parent.mkdir(parents=True)
        dmg.write_bytes(b"fake dmg content")

        with (
            patch("scripts.release.cli._ROOT", tmp_path),
        ):
            result = generate_checksum("1.0.0")

        assert result.exists()
        content = result.read_text(encoding="utf-8")
        assert "Greeting-Cards-1.0.0.dmg" in content
        assert len(content.split()[0]) == 64  # SHA256 hex length

    def test_checksum_matches_content(self, tmp_path: pathlib.Path) -> None:
        import hashlib

        data = b"test data for checksum"
        dmg = tmp_path / "dist" / "Greeting-Cards-2.0.0.dmg"
        dmg.parent.mkdir(parents=True)
        dmg.write_bytes(data)

        expected = hashlib.sha256(data).hexdigest()

        with patch("scripts.release.cli._ROOT", tmp_path):
            result = generate_checksum("2.0.0")

        content = result.read_text(encoding="utf-8")
        assert content.startswith(expected)

    def test_missing_dmg_raises(self, tmp_path: pathlib.Path) -> None:
        with (
            patch("scripts.release.cli._ROOT", tmp_path),
            pytest.raises(FileNotFoundError),
        ):
            generate_checksum("1.0.0")


class TestBuildDraftCommand:
    def test_command_structure(self, tmp_path: pathlib.Path) -> None:
        notes = tmp_path / "notes.md"
        dmg = tmp_path / "Greeting-Cards-1.0.0.dmg"
        checksum = tmp_path / "Greeting-Cards-1.0.0.sha256"

        cmd = build_draft_command("1.0.0", notes, dmg, checksum)

        assert cmd[0] == "gh"
        assert "release" in cmd
        assert "create" in cmd
        assert "v1.0.0" in cmd
        assert "--repo" in cmd
        assert "skaymakca/GreetingCards" in cmd
        assert "--draft" in cmd
        assert str(dmg) in cmd
        assert str(checksum) in cmd

    def test_title_includes_version(self, tmp_path: pathlib.Path) -> None:
        cmd = build_draft_command("1.2.3", tmp_path / "n.md", tmp_path / "d.dmg", tmp_path / "c.sha256")

        title_idx = cmd.index("--title")
        assert cmd[title_idx + 1] == "Greeting Cards 1.2.3"


class TestMain:
    def test_changelog_subcommand(self, tmp_path: pathlib.Path) -> None:
        changelog = tmp_path / "CHANGELOG.md"
        changelog.write_text(_SAMPLE_CHANGELOG, encoding="utf-8")
        build_dir = tmp_path / "_build" / "release"

        with (
            patch("sys.argv", ["release", "changelog"]),
            patch("scripts.release.cli._read_version", return_value="0.12.0"),
            patch("scripts.release.cli._CHANGELOG", changelog),
            patch("scripts.release.cli._release_notes_path", return_value=build_dir / "release-notes.md"),
        ):
            build_dir.mkdir(parents=True)

            from scripts.release.cli import main

            main()

        assert (build_dir / "release-notes.md").exists()

    def test_checksum_subcommand(self, tmp_path: pathlib.Path) -> None:
        dmg = tmp_path / "dist" / "Greeting-Cards-1.0.0.dmg"
        dmg.parent.mkdir(parents=True)
        dmg.write_bytes(b"content")

        with (
            patch("sys.argv", ["release", "checksum"]),
            patch("scripts.release.cli._read_version", return_value="1.0.0"),
            patch("scripts.release.cli._ROOT", tmp_path),
        ):
            from scripts.release.cli import main

            main()

        checksum = tmp_path / "dist" / "Greeting-Cards-1.0.0.sha256"
        assert checksum.exists()

    @patch("scripts.release.cli.subprocess.run")
    def test_draft_subcommand(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        dmg = tmp_path / "dist" / "Greeting-Cards-1.0.0.dmg"
        dmg.parent.mkdir(parents=True)
        dmg.write_bytes(b"content")

        checksum = tmp_path / "dist" / "Greeting-Cards-1.0.0.sha256"
        checksum.write_text("abc  Greeting-Cards-1.0.0.dmg\n", encoding="utf-8")

        notes = tmp_path / "_build" / "release" / "release-notes.md"
        notes.parent.mkdir(parents=True)
        notes.write_text("notes", encoding="utf-8")

        with (
            patch("sys.argv", ["release", "draft"]),
            patch("scripts.release.cli._read_version", return_value="1.0.0"),
            patch("scripts.release.cli._ROOT", tmp_path),
            patch("scripts.release.cli._release_notes_path", return_value=notes),
        ):
            from scripts.release.cli import main

            main()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "gh" in cmd
        assert "--draft" in cmd

    @patch("scripts.release.cli.subprocess.run")
    def test_publish_subcommand(self, mock_run: MagicMock) -> None:
        with (
            patch("sys.argv", ["release", "publish"]),
            patch("scripts.release.cli._read_version", return_value="1.0.0"),
        ):
            from scripts.release.cli import main

            main()

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "gh" in cmd
        assert "--draft=false" in cmd
