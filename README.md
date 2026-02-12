# Greeting Card Analyzer

Scans holiday/greeting card PDFs, extracts family names via OCR and AI, and batch-renames the files.

## Prerequisites

- Python 3.14
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) (`brew install tesseract`)

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Create a `.env` file with your Anthropic API key (for AI analysis):

```
ANTHROPIC_API_KEY=sk-ant-...
```

## Run

```bash
python main.py
```

## Build .app bundle

Requires `pyinstaller` (`pip install pyinstaller`):

```bash
make app
```

Or manually:

```bash
pyinstaller -y --windowed --name="Greeting Cards" --collect-all tkinterdnd2 main.py
```

The output is at `dist/Greeting Cards.app`.
