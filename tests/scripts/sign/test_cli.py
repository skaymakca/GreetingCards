"""Tests for scripts/sign/cli.py."""

from __future__ import annotations

import pathlib
from unittest.mock import MagicMock, patch

import pytest
from scripts.sign.cli import _classify_tier, find_binaries, is_macho, sign_app, sign_binary


class TestIsMacho:
    """Test Mach-O magic number detection."""

    def test_macho_64_le(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "binary"
        f.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 100)
        assert is_macho(f) is True

    def test_macho_64_be(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "binary"
        f.write_bytes(b"\xfe\xed\xfa\xcf" + b"\x00" * 100)
        assert is_macho(f) is True

    def test_macho_32_le(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "binary"
        f.write_bytes(b"\xce\xfa\xed\xfe" + b"\x00" * 100)
        assert is_macho(f) is True

    def test_macho_32_be(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "binary"
        f.write_bytes(b"\xfe\xed\xfa\xce" + b"\x00" * 100)
        assert is_macho(f) is True

    def test_fat_binary(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "binary"
        f.write_bytes(b"\xca\xfe\xba\xbe" + b"\x00" * 100)
        assert is_macho(f) is True

    def test_fat_binary_reversed(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "binary"
        f.write_bytes(b"\xbe\xba\xfe\xca" + b"\x00" * 100)
        assert is_macho(f) is True

    def test_not_macho(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "textfile"
        f.write_text("hello world", encoding="utf-8")
        assert is_macho(f) is False

    def test_empty_file(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "empty"
        f.write_bytes(b"")
        assert is_macho(f) is False

    def test_short_file(self, tmp_path: pathlib.Path) -> None:
        f = tmp_path / "short"
        f.write_bytes(b"\xcf\xfa")
        assert is_macho(f) is False

    def test_directory_returns_false(self, tmp_path: pathlib.Path) -> None:
        d = tmp_path / "subdir"
        d.mkdir()
        assert is_macho(d) is False

    def test_nonexistent_returns_false(self, tmp_path: pathlib.Path) -> None:
        assert is_macho(tmp_path / "nope") is False


class TestClassifyTier:
    """Test signing tier classification."""

    def test_so_file_tier_0(self, tmp_path: pathlib.Path) -> None:
        assert _classify_tier(tmp_path / "lib.so") == 0

    def test_dylib_file_tier_0(self, tmp_path: pathlib.Path) -> None:
        assert _classify_tier(tmp_path / "lib.dylib") == 0

    def test_framework_binary_tier_1(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "Foo.framework" / "Versions" / "A" / "Foo"
        assert _classify_tier(p) == 1

    def test_main_executable_tier_2(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "Contents" / "MacOS" / "MyApp"
        assert _classify_tier(p) == 2

    def test_generic_binary_tier_2(self, tmp_path: pathlib.Path) -> None:
        p = tmp_path / "some_binary"
        assert _classify_tier(p) == 2


class TestFindBinaries:
    """Test binary discovery and sorting."""

    def _make_macho(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"\xcf\xfa\xed\xfe" + b"\x00" * 100)

    def _make_text(self, path: pathlib.Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not a binary", encoding="utf-8")

    def test_finds_macho_files(self, tmp_path: pathlib.Path) -> None:
        app = tmp_path / "Test.app"
        self._make_macho(app / "Contents" / "MacOS" / "Test")
        self._make_macho(app / "Contents" / "Frameworks" / "lib.dylib")
        self._make_text(app / "Contents" / "Resources" / "data.txt")

        binaries = find_binaries(app)
        assert len(binaries) == 2

    def test_sorts_by_tier(self, tmp_path: pathlib.Path) -> None:
        app = tmp_path / "Test.app"
        self._make_macho(app / "Contents" / "MacOS" / "Test")
        self._make_macho(app / "Contents" / "Frameworks" / "lib.so")
        self._make_macho(app / "Contents" / "Frameworks" / "Foo.framework" / "Foo")

        binaries = find_binaries(app)
        tiers = [_classify_tier(b) for b in binaries]
        assert tiers == sorted(tiers)

    def test_empty_app(self, tmp_path: pathlib.Path) -> None:
        app = tmp_path / "Empty.app"
        app.mkdir(parents=True)
        assert find_binaries(app) == []


class TestSignBinary:
    """Test individual binary signing."""

    @patch("scripts.sign.cli.subprocess.run")
    def test_calls_codesign(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        binary = tmp_path / "lib.so"
        entitlements = tmp_path / "entitlements.plist"

        sign_binary(binary, "Developer ID Application: Test", entitlements)

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert cmd[0] == "codesign"
        assert "--force" in cmd
        assert "--options" in cmd
        assert "runtime" in cmd
        assert "--timestamp" in cmd
        assert "--entitlements" in cmd
        assert str(entitlements) in cmd
        assert "Developer ID Application: Test" in cmd
        assert str(binary) in cmd

    @patch("scripts.sign.cli.subprocess.run")
    def test_dry_run_skips_execution(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        binary = tmp_path / "lib.so"
        entitlements = tmp_path / "entitlements.plist"

        sign_binary(binary, "Test", entitlements, dry_run=True)

        mock_run.assert_not_called()


class TestSignApp:
    """Test full app signing orchestration."""

    def _make_app(self, tmp_path: pathlib.Path) -> pathlib.Path:
        app = tmp_path / "Test.app"
        macho_data = b"\xcf\xfa\xed\xfe" + b"\x00" * 100
        exe = app / "Contents" / "MacOS" / "Test"
        exe.parent.mkdir(parents=True)
        exe.write_bytes(macho_data)
        lib = app / "Contents" / "Frameworks" / "lib.so"
        lib.parent.mkdir(parents=True)
        lib.write_bytes(macho_data)
        return app

    @patch("scripts.sign.cli.subprocess.run")
    def test_signs_all_binaries_plus_bundle(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        app = self._make_app(tmp_path)
        entitlements = tmp_path / "entitlements.plist"
        entitlements.write_text("<plist/>", encoding="utf-8")

        sign_app(app, "Test", entitlements)

        # 2 binaries + 1 bundle sign + 1 verify = 4 subprocess calls
        assert mock_run.call_count == 4

    @patch("scripts.sign.cli.subprocess.run")
    def test_dry_run_no_subprocess(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        app = self._make_app(tmp_path)
        entitlements = tmp_path / "entitlements.plist"
        entitlements.write_text("<plist/>", encoding="utf-8")

        sign_app(app, "Test", entitlements, dry_run=True)

        mock_run.assert_not_called()

    @patch("scripts.sign.cli.subprocess.run")
    def test_verify_called_last(self, mock_run: MagicMock, tmp_path: pathlib.Path) -> None:
        app = self._make_app(tmp_path)
        entitlements = tmp_path / "entitlements.plist"
        entitlements.write_text("<plist/>", encoding="utf-8")

        sign_app(app, "Test", entitlements)

        last_cmd = mock_run.call_args_list[-1][0][0]
        assert last_cmd[0] == "codesign"
        assert "--verify" in last_cmd


class TestMainArgParsing:
    """Test CLI argument parsing and validation."""

    def test_identity_from_env(self, tmp_path: pathlib.Path) -> None:
        app = tmp_path / "Test.app"
        app.mkdir()
        ent = tmp_path / "entitlements.plist"
        ent.write_text("<plist/>", encoding="utf-8")

        with (
            patch("sys.argv", ["sign", "--dry-run"]),
            patch.dict("os.environ", {"CODESIGN_IDENTITY": "Test ID"}),
            patch("scripts.sign.cli._APP_PATH", app),
            patch("scripts.sign.cli._ENTITLEMENTS", ent),
            patch("scripts.sign.cli.sign_app") as mock_sign,
        ):
            from scripts.sign.cli import main

            main()

        mock_sign.assert_called_once()
        assert mock_sign.call_args[0][1] == "Test ID"

    def test_no_identity_errors(self) -> None:
        with (
            patch("sys.argv", ["sign"]),
            patch.dict("os.environ", {}, clear=True),
            pytest.raises(SystemExit),
        ):
            from scripts.sign.cli import main

            main()
