"""Tests for scripts/appcast/cli.py — appcast generation."""

from __future__ import annotations

import subprocess
import xml.etree.ElementTree as ET
from unittest.mock import MagicMock, patch

import pytest
from scripts.appcast.cli import (
    AppcastError,
    _get_release_notes,
    _load_existing_appcast,
    cmd_generate,
    cmd_push,
    generate_appcast_xml,
    sign_dmg,
)


class TestGenerateAppcastXml:
    """generate_appcast_xml() produces valid Sparkle appcast XML."""

    def test_generates_valid_xml(self) -> None:
        """Output is well-formed XML with Sparkle namespace."""
        xml_str = generate_appcast_xml(
            version="1.2.3",
            build_number="1700000000",
            signature="test_sig_abc",
            length=12345678,
            dmg_filename="Greeting-Cards-1.2.3.dmg",
        )
        root = ET.fromstring(xml_str)
        assert root.tag == "rss"
        assert root.attrib["version"] == "2.0"

    def test_version_fields(self) -> None:
        """Correct shortVersionString and version in the item."""
        xml_str = generate_appcast_xml(
            version="0.13.0",
            build_number="1700000001",
            signature="sig123",
            length=5000000,
            dmg_filename="Greeting-Cards-0.13.0.dmg",
        )
        root = ET.fromstring(xml_str)
        ns = {"sparkle": "http://www.andymatuschak.org/xml-namespaces/sparkle"}

        item = root.find(".//item")
        assert item is not None

        short_ver = item.find("sparkle:shortVersionString", ns)
        assert short_ver is not None
        assert short_ver.text == "0.13.0"

        ver = item.find("sparkle:version", ns)
        assert ver is not None
        assert ver.text == "1700000001"

    def test_enclosure_url(self) -> None:
        """Enclosure URL points to GitHub Releases."""
        xml_str = generate_appcast_xml(
            version="2.0.0",
            build_number="1700000002",
            signature="sig456",
            length=8000000,
            dmg_filename="Greeting-Cards-2.0.0.dmg",
        )
        root = ET.fromstring(xml_str)

        enclosure = root.find(".//enclosure")
        assert enclosure is not None
        url = enclosure.attrib["url"]
        assert "github.com/skaymakca/GreetingCards/releases/download/v2.0.0/" in url
        assert url.endswith("Greeting-Cards-2.0.0.dmg")

    def test_enclosure_signature(self) -> None:
        """Enclosure has edSignature and length attributes."""
        xml_str = generate_appcast_xml(
            version="1.0.0",
            build_number="1700000003",
            signature="my_ed_signature",
            length=9999999,
            dmg_filename="Greeting-Cards-1.0.0.dmg",
        )
        root = ET.fromstring(xml_str)

        enclosure = root.find(".//enclosure")
        assert enclosure is not None
        ns = "http://www.andymatuschak.org/xml-namespaces/sparkle"
        assert enclosure.attrib[f"{{{ns}}}edSignature"] == "my_ed_signature"
        assert enclosure.attrib["length"] == "9999999"

    def test_channel_title(self) -> None:
        """Channel has 'Greeting Cards' title."""
        xml_str = generate_appcast_xml(
            version="1.0.0",
            build_number="1700000004",
            signature="sig",
            length=1000,
            dmg_filename="test.dmg",
        )
        root = ET.fromstring(xml_str)
        title = root.find(".//channel/title")
        assert title is not None
        assert title.text == "Greeting Cards"

    def test_minimum_system_version(self) -> None:
        """Item specifies minimumSystemVersion 13.0."""
        xml_str = generate_appcast_xml(
            version="1.0.0",
            build_number="1700000005",
            signature="sig",
            length=1000,
            dmg_filename="test.dmg",
        )
        root = ET.fromstring(xml_str)
        ns = {"sparkle": "http://www.andymatuschak.org/xml-namespaces/sparkle"}
        min_ver = root.find(".//item/sparkle:minimumSystemVersion", ns)
        assert min_ver is not None
        assert min_ver.text == "13.0"

    def test_no_existing_appcast_creates_new_root(self) -> None:
        """When _load_existing_appcast returns None, a new RSS root is created."""
        with patch("scripts.appcast.cli._load_existing_appcast", return_value=None):
            xml_str = generate_appcast_xml("1.0.0", "100", "sig", 1000, "t.dmg")
        root = ET.fromstring(xml_str)
        assert root.tag == "rss"
        assert root.find(".//channel/title") is not None

    def test_existing_appcast_no_channel(self) -> None:
        """When existing root has no <channel>, one is created."""
        bare_root = ET.Element("rss", {"version": "2.0"})
        with patch("scripts.appcast.cli._load_existing_appcast", return_value=bare_root):
            xml_str = generate_appcast_xml("1.0.0", "100", "sig", 1000, "t.dmg")
        root = ET.fromstring(xml_str)
        channel = root.find("channel")
        assert channel is not None
        assert channel.find("title") is not None

    def test_channel_without_title(self) -> None:
        """When channel has no <title>, item is inserted at index 0."""
        ns = "http://www.andymatuschak.org/xml-namespaces/sparkle"
        ET.register_namespace("sparkle", ns)
        root_el = ET.Element("rss", {"version": "2.0"})
        channel = ET.SubElement(root_el, "channel")
        # Add an existing item but no title
        old_item = ET.SubElement(channel, "item")
        old_title = ET.SubElement(old_item, "title")
        old_title.text = "Version 0.9.0"

        with patch("scripts.appcast.cli._load_existing_appcast", return_value=root_el):
            xml_str = generate_appcast_xml("1.0.0", "100", "sig", 1000, "t.dmg")

        result = ET.fromstring(xml_str)
        items = result.findall(".//item")
        # New item should be first (idx 0 since no title element)
        assert items[0].find("title") is not None
        assert items[0].find("title").text == "Version 1.0.0"

    def test_release_notes_included(self) -> None:
        """When release notes are available, description element is added."""
        with (
            patch("scripts.appcast.cli._load_existing_appcast", return_value=None),
            patch("scripts.appcast.cli._get_release_notes", return_value="Bug fixes and improvements."),
        ):
            xml_str = generate_appcast_xml("1.0.0", "100", "sig", 1000, "t.dmg")

        root = ET.fromstring(xml_str)
        desc = root.find(".//item/description")
        assert desc is not None
        assert desc.text == "Bug fixes and improvements."

    def test_no_release_notes_no_description(self) -> None:
        """When release notes are empty, no description element is added."""
        with (
            patch("scripts.appcast.cli._load_existing_appcast", return_value=None),
            patch("scripts.appcast.cli._get_release_notes", return_value=""),
        ):
            xml_str = generate_appcast_xml("1.0.0", "100", "sig", 1000, "t.dmg")

        root = ET.fromstring(xml_str)
        desc = root.find(".//item/description")
        assert desc is None


class TestSignDmg:
    """sign_dmg() calls sign_update and parses output."""

    def test_sign_update_calls_subprocess(self, tmp_path) -> None:
        """sign_dmg() invokes sign_update and parses the signature."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake dmg content")

        sign_tool = tmp_path / "sign_update"
        sign_tool.write_text("#!/bin/bash\necho 'test'")
        sign_tool.chmod(0o755)

        mock_result = type(
            "R",
            (),
            {
                "stdout": 'sparkle:edSignature="abc123def" length="12345"',
                "stderr": "",
                "returncode": 0,
            },
        )()

        with (
            patch("scripts.appcast.cli._SPARKLE_BIN", tmp_path),
            patch("scripts.appcast.cli.run_command", return_value=mock_result),
        ):
            sig, length = sign_dmg(dmg)

        assert sig == "abc123def"
        assert length == 12345

    def test_dry_run(self, tmp_path) -> None:
        """sign_dmg() with dry_run returns placeholder values."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake")

        sign_tool = tmp_path / "sign_update"
        sign_tool.write_text("#!/bin/bash\necho 'test'")
        sign_tool.chmod(0o755)

        with patch("scripts.appcast.cli._SPARKLE_BIN", tmp_path):
            sig, length = sign_dmg(dmg, dry_run=True)

        assert sig == "DRY_RUN_SIGNATURE"
        assert length == 0

    def test_sign_tool_not_found(self, tmp_path) -> None:
        """sign_dmg() raises FileNotFoundError when sign_update is missing."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake")

        with (
            patch("scripts.appcast.cli._SPARKLE_BIN", tmp_path / "nonexistent"),
            pytest.raises(FileNotFoundError, match="sign_update not found"),
        ):
            sign_dmg(dmg)

    def test_parse_failure_raises_error(self, tmp_path) -> None:
        """sign_dmg() raises AppcastError when output can't be parsed."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake")

        sign_tool = tmp_path / "sign_update"
        sign_tool.write_text("#!/bin/bash\necho 'test'")
        sign_tool.chmod(0o755)

        mock_result = type("R", (), {"stdout": "unexpected output", "stderr": "", "returncode": 0})()

        with (
            patch("scripts.appcast.cli._SPARKLE_BIN", tmp_path),
            patch("scripts.appcast.cli.run_command", return_value=mock_result),
            pytest.raises(AppcastError, match="Failed to parse"),
        ):
            sign_dmg(dmg)


class TestLoadExistingAppcast:
    """_load_existing_appcast() loads XML from gh-pages branch."""

    @patch("scripts.appcast.cli.subprocess.run")
    def test_valid_xml_returns_element(self, mock_run: MagicMock) -> None:
        xml_content = '<rss version="2.0"><channel><title>Greeting Cards</title></channel></rss>'
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout=xml_content, stderr="")
        result = _load_existing_appcast()
        assert result is not None
        assert result.tag == "rss"

    @patch("scripts.appcast.cli.subprocess.run")
    def test_subprocess_failure_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 128, stdout="", stderr="fatal")
        result = _load_existing_appcast()
        assert result is None

    @patch("scripts.appcast.cli.subprocess.run")
    def test_subprocess_raises_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.side_effect = OSError("git not found")
        result = _load_existing_appcast()
        assert result is None

    @patch("scripts.appcast.cli.subprocess.run")
    def test_malformed_xml_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="not valid xml <><>", stderr="")
        result = _load_existing_appcast()
        assert result is None

    @patch("scripts.appcast.cli.subprocess.run")
    def test_empty_stdout_returns_none(self, mock_run: MagicMock) -> None:
        mock_run.return_value = subprocess.CompletedProcess([], 0, stdout="", stderr="")
        result = _load_existing_appcast()
        assert result is None


class TestGetReleaseNotes:
    """_get_release_notes() reads release notes from file."""

    def test_returns_content_when_file_exists(self, tmp_path) -> None:
        notes = tmp_path / "dist" / "release-notes.md"
        notes.parent.mkdir(parents=True)
        notes.write_text("  Bug fixes and improvements.  \n", encoding="utf-8")
        with patch("scripts.appcast.cli.PROJECT_ROOT", tmp_path):
            result = _get_release_notes()
        assert result == "Bug fixes and improvements."

    def test_returns_empty_string_when_file_missing(self, tmp_path) -> None:
        with patch("scripts.appcast.cli.PROJECT_ROOT", tmp_path):
            result = _get_release_notes()
        assert result == ""


class TestCmdGenerate:
    """cmd_generate() signs DMG and generates appcast XML."""

    def test_missing_dmg_raises(self, tmp_path) -> None:
        with (
            patch("scripts.appcast.cli.dmg_path", return_value=tmp_path / "nonexistent.dmg"),
            pytest.raises(FileNotFoundError, match="DMG not found"),
        ):
            cmd_generate("1.0.0")

    def test_dry_run_prints_preview(self, tmp_path) -> None:
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake dmg")

        with (
            patch("scripts.appcast.cli.dmg_path", return_value=dmg),
            patch("scripts.appcast.cli.sign_dmg", return_value=("DRY_RUN_SIG", 0)),
            patch("scripts.appcast.cli.read_build_number", return_value="1700000000"),
            patch("scripts.appcast.cli.generate_appcast_xml", return_value='<?xml version="1.0" ?>\n<rss/>\n'),
        ):
            cmd_generate("1.0.0", dry_run=True)  # should not raise

    def test_dry_run_long_xml_shows_ellipsis(self, tmp_path, capsys) -> None:
        """Dry-run with >10 lines of XML prints '...' truncation."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake dmg")

        long_xml = "\n".join(f"<line{i}/>" for i in range(15)) + "\n"
        with (
            patch("scripts.appcast.cli.dmg_path", return_value=dmg),
            patch("scripts.appcast.cli.sign_dmg", return_value=("DRY_RUN_SIG", 0)),
            patch("scripts.appcast.cli.read_build_number", return_value="1700000000"),
            patch("scripts.appcast.cli.generate_appcast_xml", return_value=long_xml),
        ):
            cmd_generate("1.0.0", dry_run=True)

        captured = capsys.readouterr()
        assert "..." in captured.out

    def test_length_zero_fallback_to_stat(self, tmp_path) -> None:
        """When sign_dmg returns length==0 and not dry_run, uses file stat."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"x" * 42)

        with (
            patch("scripts.appcast.cli.dmg_path", return_value=dmg),
            patch("scripts.appcast.cli.sign_dmg", return_value=("sig123", 0)),
            patch("scripts.appcast.cli.read_build_number", return_value="1700000000"),
            patch("scripts.appcast.cli.generate_appcast_xml", return_value="<rss/>\n") as mock_gen,
            patch("scripts.appcast.cli._APPCAST_OUT", tmp_path / "appcast.xml"),
        ):
            cmd_generate("1.0.0")

        # generate_appcast_xml should have been called with length=42 (file size)
        assert mock_gen.call_args[0][3] == 42

    def test_writes_appcast_file(self, tmp_path) -> None:
        """Non-dry-run writes appcast.xml to disk."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake dmg")
        out = tmp_path / "dist" / "appcast.xml"

        with (
            patch("scripts.appcast.cli.dmg_path", return_value=dmg),
            patch("scripts.appcast.cli.sign_dmg", return_value=("sig", 1000)),
            patch("scripts.appcast.cli.read_build_number", return_value="1700000000"),
            patch("scripts.appcast.cli.generate_appcast_xml", return_value="<rss/>\n"),
            patch("scripts.appcast.cli._APPCAST_OUT", out),
        ):
            cmd_generate("1.0.0")

        assert out.exists()
        assert out.read_text(encoding="utf-8") == "<rss/>\n"

    def test_uses_build_number_from_app_bundle(self, tmp_path) -> None:
        """cmd_generate passes read_build_number() value to generate_appcast_xml."""
        dmg = tmp_path / "test.dmg"
        dmg.write_bytes(b"fake dmg")
        out = tmp_path / "dist" / "appcast.xml"

        with (
            patch("scripts.appcast.cli.dmg_path", return_value=dmg),
            patch("scripts.appcast.cli.sign_dmg", return_value=("sig", 5000)),
            patch("scripts.appcast.cli.read_build_number", return_value="1709876543"),
            patch("scripts.appcast.cli.generate_appcast_xml", return_value="<rss/>\n") as mock_gen,
            patch("scripts.appcast.cli._APPCAST_OUT", out),
        ):
            cmd_generate("2.0.0")

        mock_gen.assert_called_once_with("2.0.0", "1709876543", "sig", 5000, dmg.name)


class TestCmdPush:
    """cmd_push() pushes appcast.xml to gh-pages."""

    def test_missing_appcast_raises(self, tmp_path) -> None:
        with (
            patch("scripts.appcast.cli._APPCAST_OUT", tmp_path / "nonexistent.xml"),
            pytest.raises(FileNotFoundError, match="Appcast not found"),
        ):
            cmd_push()

    def test_dry_run_prints_message(self, tmp_path) -> None:
        appcast = tmp_path / "appcast.xml"
        appcast.write_text("<rss/>", encoding="utf-8")

        with patch("scripts.appcast.cli._APPCAST_OUT", appcast):
            cmd_push(dry_run=True)  # should not raise

    @patch("scripts.appcast.cli.subprocess.run")
    def test_push_with_existing_gh_pages(self, mock_run: MagicMock, tmp_path) -> None:
        """Non-dry-run push when gh-pages branch exists remotely."""
        appcast = tmp_path / "appcast.xml"
        appcast.write_text("<rss/>", encoding="utf-8")
        deploy_dir = tmp_path / "_build" / "gh-pages-deploy"
        # Pre-create deploy dir to exercise the shutil.rmtree cleanup path
        deploy_dir.mkdir(parents=True)

        def run_side_effect(cmd, **_kwargs):
            if "ls-remote" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="abc\trefs/heads/gh-pages\n", stderr="")
            if "add" in cmd and "appcast.xml" in cmd:
                return subprocess.CompletedProcess(cmd, 0)
            if "diff" in cmd and "--cached" in cmd:
                return subprocess.CompletedProcess(cmd, 1)  # has changes
            if "commit" in cmd:
                return subprocess.CompletedProcess(cmd, 0)
            return subprocess.CompletedProcess(cmd, 0)

        mock_run.side_effect = run_side_effect

        def internal_run_side_effect(cmd, **_kw):
            # Simulate git worktree add creating the directory
            if "worktree" in cmd and "add" in cmd:
                deploy_dir.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0)

        with (
            patch("scripts.appcast.cli._APPCAST_OUT", appcast),
            patch("scripts.appcast.cli.PROJECT_ROOT", tmp_path),
            patch("scripts.appcast.cli.run_command", side_effect=internal_run_side_effect),
        ):
            cmd_push()

    @patch("scripts.appcast.cli.subprocess.run")
    def test_push_without_gh_pages(self, mock_run: MagicMock, tmp_path) -> None:
        """Non-dry-run push when gh-pages branch does not exist remotely."""
        appcast = tmp_path / "appcast.xml"
        appcast.write_text("<rss/>", encoding="utf-8")
        deploy_dir = tmp_path / "_build" / "gh-pages-deploy"

        def run_side_effect(cmd, **_kw):
            if "ls-remote" in cmd:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")  # no gh-pages
            if "add" in cmd and "appcast.xml" in cmd:
                return subprocess.CompletedProcess(cmd, 0)
            if "diff" in cmd and "--cached" in cmd:
                return subprocess.CompletedProcess(cmd, 0)  # no changes
            return subprocess.CompletedProcess(cmd, 0)

        mock_run.side_effect = run_side_effect

        def internal_run_side_effect(cmd, **_kw):
            if "worktree" in cmd and "add" in cmd:
                deploy_dir.mkdir(parents=True, exist_ok=True)
            return subprocess.CompletedProcess(cmd, 0)

        with (
            patch("scripts.appcast.cli._APPCAST_OUT", appcast),
            patch("scripts.appcast.cli.PROJECT_ROOT", tmp_path),
            patch("scripts.appcast.cli.run_command", side_effect=internal_run_side_effect),
        ):
            cmd_push()


class TestMain:
    """main() parses args and dispatches to subcommands."""

    def test_generate_subcommand(self) -> None:
        with (
            patch("sys.argv", ["appcast", "generate"]),
            patch("scripts.appcast.cli.read_version", return_value="1.0.0"),
            patch("scripts.appcast.cli.cmd_generate") as mock_gen,
        ):
            from scripts.appcast.cli import main

            main()

        mock_gen.assert_called_once_with("1.0.0", dry_run=False)

    def test_push_subcommand(self) -> None:
        with (
            patch("sys.argv", ["appcast", "push"]),
            patch("scripts.appcast.cli.read_version", return_value="1.0.0"),
            patch("scripts.appcast.cli.cmd_push") as mock_push,
        ):
            from scripts.appcast.cli import main

            main()

        mock_push.assert_called_once_with(dry_run=False)

    def test_dry_run_flag(self) -> None:
        with (
            patch("sys.argv", ["appcast", "--dry-run", "generate"]),
            patch("scripts.appcast.cli.read_version", return_value="1.0.0"),
            patch("scripts.appcast.cli.cmd_generate") as mock_gen,
        ):
            from scripts.appcast.cli import main

            main()

        mock_gen.assert_called_once_with("1.0.0", dry_run=True)

    def test_push_dry_run(self) -> None:
        with (
            patch("sys.argv", ["appcast", "--dry-run", "push"]),
            patch("scripts.appcast.cli.read_version", return_value="1.0.0"),
            patch("scripts.appcast.cli.cmd_push") as mock_push,
        ):
            from scripts.appcast.cli import main

            main()

        mock_push.assert_called_once_with(dry_run=True)

    def test_no_subcommand_errors(self) -> None:
        with (
            patch("sys.argv", ["appcast"]),
            pytest.raises(SystemExit, match="2"),
        ):
            from scripts.appcast.cli import main

            main()
