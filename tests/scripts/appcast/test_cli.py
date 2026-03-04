"""Tests for scripts/appcast/cli.py — appcast generation."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from unittest.mock import patch

import pytest
from scripts.appcast.cli import AppcastError, generate_appcast_xml, sign_dmg


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
            patch("scripts.appcast.cli._run", return_value=mock_result),
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
            patch("scripts.appcast.cli._run", return_value=mock_result),
            pytest.raises(AppcastError, match="Failed to parse"),
        ):
            sign_dmg(dmg)
