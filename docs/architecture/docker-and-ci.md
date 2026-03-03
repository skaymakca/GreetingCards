# Docker and CI

This doc covers the Docker-based cross-platform testing setup and the GitHub Actions CI pipeline.

## Docker Setup

### Purpose

The Docker setup runs the test suite on Linux to verify cross-platform compatibility. Since the app targets macOS, this
catches assumptions about platform-specific behavior (path separators, Tesseract integration, system locale) that
macOS-only testing would miss.

### Dockerfile

`Dockerfile` builds a test image based on `python:3.14-slim-bookworm`:

| Layer                      | What it does                                                                       |
|----------------------------|------------------------------------------------------------------------------------|
| System deps                | Installs `build-essential`, `pkg-config`, `libtesseract-dev`, `libleptonica-dev`, `tesseract-ocr-eng`, `git` |
| uv                         | Copies the `uv` binary from the official `ghcr.io/astral-sh/uv` image             |
| Non-root user              | Creates a `tester` user (UID 1000) for realistic filesystem permission behavior    |
| Layer-cached deps          | Copies `pyproject.toml` + `uv.lock` first, runs `uv sync --no-install-project`    |
| Full source + project sync | Copies remaining source, runs `uv sync` to install the project itself              |

The default `CMD` runs `pytest tests/core/ tests/scripts/ --ignore=tests/core/test_apple_events.py -x --tb=short`.

### docker-compose.yml

`docker-compose.yml` defines a single `test-linux` service:

- **Volume mount:** `.:/app` — mounts the project directory so code changes are reflected without rebuilding
- **Anonymous volume:** `/app/.venv` — prevents the macOS `.venv` from leaking into the container; the container uses
  its own virtual environment
- **User:** `1000:1000` — matches the non-root `tester` user in the image
- **Environment:** `PYTHONDONTWRITEBYTECODE=1` — prevents `.pyc` files from polluting the mounted source

### What's excluded

- `tests/gui/` — wxPython requires a display server and macOS frameworks
- `tests/core/test_apple_events.py` — Apple Events are macOS-only
- `tests/integration/` — AppleScript integration tests require a running macOS app

### Make targets

| Target         | Description                                           |
|----------------|-------------------------------------------------------|
| `docker-build` | Builds the `greeting-cards-test` image                |
| `docker-test`  | Runs the default test command via `docker compose run` |
| `docker-shell` | Opens an interactive bash shell in the container       |

## CI Pipeline

### Overview

GitHub Actions CI is defined in `.github/workflows/ci.yml`. It uses a shared composite action for environment setup.

### Composite action: `setup-build-env`

`.github/actions/setup-build-env/action.yml` installs:

1. Python 3.14 + uv (`astral-sh/setup-uv@v6` with `python-version` and `prune-cache: false` — caches the uv dependency
   cache across runs; pruning is disabled because `uv cache prune --ci` removes nearly all cached packages, making
   subsequent cache restores useless)
2. System dependencies: `tesseract`, `leptonica`, `pkg-config`, `lcov` (`gerlero/brew-install@v1` — caches Homebrew
   packages across runs)
3. Project dependencies (`uv sync`)
4. pyright (`uv tool install pyright`)

### Jobs

| Job     | Trigger                           | Runner      | Steps                                                           |
|---------|-----------------------------------|-------------|-----------------------------------------------------------------|
| `check` | Every push (all branches)         | `macos-26`  | Checkout, setup, `make check`, upload `static-checks.log`       |
| `test`  | PRs to `main` only (`if` guard)   | `macos-26`  | Checkout, setup, `make check`, `make app`, `make test T="all --cov"`, upload logs + coverage |

### Artifacts

Both jobs use `actions/upload-artifact@v4` with `if: always()` so artifacts are uploaded even on failure:

- **`check` job** uploads `static-checks` artifact: `static-checks.log`
- **`test` job** uploads `test-job-logs` artifact: `static-checks.log`, `test-results.log`, and `_build/coverage/latest/` (HTML coverage report)

### Triggers

```yaml
on:
  push:           # all branches — runs 'check' job
  pull_request:
    branches: [main]  # PRs to main — runs both 'check' and 'test' jobs
```

The `test` job has an additional `if: github.event_name == 'pull_request'` guard so it only runs on PRs, not on every
push.

## Gotchas

- **Anonymous `.venv` volume:** The `docker-compose.yml` anonymous volume for `/app/.venv` is essential. Without it,
  the macOS `.venv` (with platform-specific wheels) would be mounted into the Linux container and break imports.
- **Non-root user:** The Dockerfile creates a non-root `tester` user so that tests exercise realistic filesystem
  permission behavior. The `user: "1000:1000"` in `docker-compose.yml` must match.
- **`--ignore` for macOS-only tests:** The default `CMD` explicitly ignores `test_apple_events.py`. If new macOS-only
  test files are added, they need to be added to the ignore list or moved under a macOS-specific directory.
- **Layer caching:** The Dockerfile copies `pyproject.toml` and `uv.lock` before the full source to maximize Docker
  layer cache hits. Dependency changes trigger a rebuild; source-only changes reuse the cached dependency layer.
- **`make check` runs on macOS CI, not in Docker:** Static analysis (pyright, mypy, ruff, bandit) runs natively on
  macOS runners because the tools need access to macOS-specific stubs (wx, AppKit, Foundation). Docker is only for
  cross-platform test execution.
