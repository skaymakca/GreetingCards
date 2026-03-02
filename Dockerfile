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

WORKDIR /app

# Layer-cached dependency install: copy only dependency files first
COPY pyproject.toml uv.lock ./

# Install dependencies (without the project itself)
RUN uv sync --no-install-project

# Copy the rest of the source
COPY . .

# Install the project
RUN uv sync

ENV PYTHONDONTWRITEBYTECODE=1

CMD ["uv", "run", "pytest", "tests/core/", "tests/scripts/", \
     "--ignore=tests/core/test_apple_events.py", \
     "-x", "--tb=short"]
