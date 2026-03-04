FROM python:3.14-slim-bookworm

# System dependencies for tesserocr and git
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libtesseract-dev \
    libleptonica-dev \
    tesseract-ocr-eng \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

# Non-root user for realistic filesystem permission behavior
RUN useradd --create-home --uid 1000 tester
USER tester

WORKDIR /app

# Layer-cached dependency install: copy only dependency files first
COPY --chown=tester:tester pyproject.toml uv.lock ./

# Install dependencies (without the project itself)
RUN uv sync --no-install-project

# Copy the rest of the source
COPY --chown=tester:tester . .

# Install the project
RUN uv sync

ENV PYTHONDONTWRITEBYTECODE=1

CMD ["uv", "run", "pytest", "tests/core/", "tests/scripts/", \
     "--ignore=tests/core/test_apple_events.py", \
     "-x", "--tb=short"]
