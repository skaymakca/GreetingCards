"""User interaction layer for release configuration.

Provides a Protocol-based abstraction so tests can inject mock input
without touching stdin.
"""

from __future__ import annotations

from typing import Protocol


class UserInput(Protocol):
    """Protocol for user input — mockable in tests."""

    def choose(self, prompt: str, options: list[str], default: int | None = None) -> int:
        """Present numbered options and return the selected index (0-based)."""
        ...

    def ask(self, prompt: str, default: str = "") -> str:
        """Ask for a free-text value, returning default if empty."""
        ...

    def confirm(self, prompt: str, default: bool = True) -> bool:
        """Ask a yes/no question, returning a boolean."""
        ...


class InteractiveInput:
    """Real stdin-based implementation of UserInput."""

    def choose(self, prompt: str, options: list[str], default: int | None = None) -> int:
        """Present numbered options and return the selected index (0-based)."""
        print(f"\n{prompt}")
        for i, option in enumerate(options):
            marker = " *" if i == default else ""
            print(f"  {i + 1}) {option}{marker}")

        while True:
            hint = f" [{default + 1}]" if default is not None else ""
            raw = input(f"Choose{hint}: ").strip()

            if raw == "" and default is not None:
                return default

            try:
                choice = int(raw)
            except ValueError:
                print("  Please enter a number.")
                continue

            if 1 <= choice <= len(options):
                return choice - 1
            print(f"  Please enter a number between 1 and {len(options)}.")

    def ask(self, prompt: str, default: str = "") -> str:
        """Ask for a free-text value, returning default if empty."""
        hint = f" [{default}]" if default else ""
        raw = input(f"{prompt}{hint}: ").strip()
        return raw if raw else default

    def confirm(self, prompt: str, default: bool = True) -> bool:
        """Ask a yes/no question, returning a boolean."""
        hint = "Y/n" if default else "y/N"
        raw = input(f"{prompt} [{hint}]: ").strip().lower()
        if raw == "":
            return default
        return raw in ("y", "yes")
