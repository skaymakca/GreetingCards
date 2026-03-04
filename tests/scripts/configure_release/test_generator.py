"""Tests for scripts/configure_release/generator.py."""

from __future__ import annotations

import subprocess

from scripts.configure_release.generator import (
    STEPS,
    ExistingConfig,
    ReleaseConfig,
    Scope,
    generate_script,
    parse_existing_script,
)


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
        for step in STEPS:
            assert f"step_{step.number}()" in script

    def test_help_function_lists_steps(self) -> None:
        script = self._generate()
        assert "show_help()" in script
        # Table header
        assert "ID" in script
        assert "Name" in script
        assert "Scope" in script
        # Word IDs in table rows
        for step in STEPS:
            assert step.word_id in script

    def test_scope_values_in_help(self) -> None:
        script = self._generate()
        for step in STEPS:
            assert step.scope.value in script

    def test_step_number_function_present(self) -> None:
        script = self._generate()
        assert "step_number()" in script
        assert 'case "$1" in' in script
        for step in STEPS:
            assert f"{step.word_id}) echo {step.number}" in script

    def test_word_argument_parsing(self) -> None:
        script = self._generate()
        # Single word uses step_number
        assert 'START=$(step_number "$ARG")' in script
        # Range splitting
        assert 'FROM_WORD="${ARG%%-*}"' in script
        assert 'TO_WORD="${ARG##*-}"' in script

    def test_no_args_shows_help(self) -> None:
        script = self._generate()
        assert "show_help" in script
        assert "if [ $# -eq 0 ]" in script

    def test_help_examples_use_words(self) -> None:
        script = self._generate()
        assert "release-local.sh dmg" in script
        assert "release-local.sh build-dmg" in script

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


class TestParseExistingScript:
    """Test parsing config values from an existing release-local.sh."""

    def test_parse_full_config(self) -> None:
        content = (
            "#!/bin/bash\n"
            "set -euo pipefail\n"
            "\n"
            'export CODESIGN_IDENTITY="Developer ID Application: Test (TEAM)"\n'
            'KEYCHAIN_PROFILE="MyProfile"\n'
        )
        result = parse_existing_script(content)
        assert result.signing_identity == "Developer ID Application: Test (TEAM)"
        assert result.keychain_profile == "MyProfile"

    def test_parse_missing_identity(self) -> None:
        content = 'KEYCHAIN_PROFILE="MyProfile"\n'
        result = parse_existing_script(content)
        assert result.signing_identity is None
        assert result.keychain_profile == "MyProfile"

    def test_parse_missing_profile(self) -> None:
        content = 'export CODESIGN_IDENTITY="Test ID"\n'
        result = parse_existing_script(content)
        assert result.signing_identity == "Test ID"
        assert result.keychain_profile is None

    def test_parse_empty_content(self) -> None:
        result = parse_existing_script("")
        assert result.signing_identity is None
        assert result.keychain_profile is None

    def test_parse_special_characters(self) -> None:
        content = """export CODESIGN_IDENTITY="Developer ID Application: O'Brien & Sons (TEAM)"\nKEYCHAIN_PROFILE="My Profile"\n"""
        result = parse_existing_script(content)
        assert result.signing_identity == "Developer ID Application: O'Brien & Sons (TEAM)"
        assert result.keychain_profile == "My Profile"


class TestStepsDataModel:
    """Test the STEPS data model integrity."""

    def test_steps_are_step_instances(self) -> None:
        from scripts.configure_release.generator import Step

        for step in STEPS:
            assert isinstance(step, Step)

    def test_step_numbers_sequential(self) -> None:
        for i, step in enumerate(STEPS, start=1):
            assert step.number == i

    def test_word_ids_unique(self) -> None:
        ids = [s.word_id for s in STEPS]
        assert len(ids) == len(set(ids))

    def test_word_ids_lowercase_alpha(self) -> None:
        import re

        for step in STEPS:
            assert re.fullmatch(r"[a-z]+", step.word_id), f"Bad word ID: {step.word_id}"

    def test_all_scopes_are_scope_enum(self) -> None:
        for step in STEPS:
            assert isinstance(step.scope, Scope)

    def test_existing_config_defaults_to_none(self) -> None:
        config = ExistingConfig()
        assert config.signing_identity is None
        assert config.keychain_profile is None
