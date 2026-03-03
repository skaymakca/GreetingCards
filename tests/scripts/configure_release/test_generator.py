"""Tests for scripts/configure_release/generator.py."""

from __future__ import annotations

import subprocess

from scripts.configure_release.generator import STEPS, ReleaseConfig, generate_script


class TestGenerateScript:
    """Test the generated shell script content."""

    def _generate(
        self,
        identity: str = "Developer ID Application: Test Corp (TEAM123)",
        profile: str = "GreetingCards",
    ) -> str:
        config = ReleaseConfig(signing_identity=identity, keychain_profile=profile)
        return generate_script(config)

    def test_shebang(self) -> None:
        script = self._generate()
        assert script.startswith("#!/bin/bash\n")

    def test_set_euo_pipefail(self) -> None:
        script = self._generate()
        assert "set -euo pipefail" in script

    def test_contains_identity(self) -> None:
        script = self._generate(identity="Developer ID Application: My Corp (XYZ)")
        assert 'export CODESIGN_IDENTITY="Developer ID Application: My Corp (XYZ)"' in script

    def test_contains_profile(self) -> None:
        script = self._generate(profile="MyProfile")
        assert 'KEYCHAIN_PROFILE="MyProfile"' in script

    def test_all_seven_steps_present(self) -> None:
        script = self._generate()
        for number, _label, _cmd in STEPS:
            assert f"step_{number}()" in script

    def test_help_function_lists_steps(self) -> None:
        script = self._generate()
        assert "show_help()" in script
        for number, label, _cmd in STEPS:
            assert f"{number}. {label}" in script

    def test_no_args_shows_help(self) -> None:
        script = self._generate()
        assert "show_help" in script
        assert "if [ $# -eq 0 ]" in script

    def test_special_characters_in_identity(self) -> None:
        identity = "Developer ID Application: O'Brien & Sons (TEAM)"
        script = self._generate(identity=identity)
        assert identity in script

    def test_shellcheck_passes(self, tmp_path: object) -> None:
        import pathlib

        path = pathlib.Path(str(tmp_path)) / "release-local.sh"
        script = self._generate()
        path.write_text(script, encoding="utf-8")

        result = subprocess.run(
            ["shellcheck", str(path)],
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stdout + result.stderr
