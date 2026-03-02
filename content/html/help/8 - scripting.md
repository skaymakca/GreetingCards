---
title: Scripting
---

# AppleScript Scripting

Greeting Cards supports AppleScript automation. You can control the app from Script Editor, Automator, or the
`osascript` command in Terminal — load folders, trigger AI analysis, rename cards, and query results.

## Requirements

- The installed `.app` bundle (scripting does not work with `uv run python main.py`)
- Script Editor or `osascript` in Terminal
- macOS 12 or later

## Quick Start

```applescript
-- Get current status
tell application "Greeting Cards"
    set statusJSON to get status
end tell

-- Load a folder of PDFs
tell application "Greeting Cards"
    set result to load paths {"/Users/you/Cards"}
end tell

-- Rename a specific card
tell application "Greeting Cards"
    set result to rename card path "/Users/you/Cards/IMG_001.pdf"
end tell
```

## Commands

### Loading & Status

| Command                  | What it does                                                        |
|--------------------------|---------------------------------------------------------------------|
| `load paths {path, ...}` | Load one or more folder or file paths into the app                  |
| `get status`             | Return processing state, loaded card count, current model, and year |
| `reload`                 | Re-scan all currently loaded paths                                  |
| `clear all`              | Unload all cards and reset the app                                  |

### Card Queries

| Command                | What it does                                 |
|------------------------|----------------------------------------------|
| `get card info path p` | Return full details for the card at path `p` |
| `get loaded cards`     | Return a summary list of all loaded cards    |

### Card Mutations

| Command                             | What it does                                           |
|-------------------------------------|--------------------------------------------------------|
| `rename card path p`                | Rename the card at `p` using its current best name     |
| `set card name path p name n`       | Set a manual name for the card at `p`                  |
| `select candidate path p index i`   | Promote candidate `i` (0-based) as the chosen name     |
| `set remove family path p remove r` | Set whether to strip the family name from the filename |

### AI & Models

| Command                | What it does                                     |
|------------------------|--------------------------------------------------|
| `analyze cards`        | Run AI analysis on all loaded cards              |
| `clear AI results`     | Discard cached AI results for all cards          |
| `get models`           | Return the list of available AI models           |
| `set model model_id m` | Switch to model `m` (e.g. `"claude-sonnet-4-6"`) |
| `quit`                 | Quit the application                             |

## JSON Responses

All commands return a JSON string. Parse it with `json.loads()` in Python or a JSON library in your scripting language
of choice.

| Response shape                                                     | Fields                                                                                        | Returned by                                                                                  |
|--------------------------------------------------------------------|-----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------|
| `{success, count, error?}`                                         | `success` (bool), `count` (int), `error` (str, optional)                                      | `load paths`, `analyze cards`, `clear AI results`                                            |
| `{success, error?}`                                                | `success` (bool), `error` (str, optional)                                                     | `reload`, `clear all`, `set card name`, `select candidate`, `set remove family`, `set model` |
| `{success, old_path, new_path, error}`                             | all strings + `success` bool                                                                  | `rename card`                                                                                |
| `{is_processing, is_analyzing, loaded_count, current_model, year}` | see schema                                                                                    | `get status`                                                                                 |
| card info object                                                   | `filename`, `file_hash`, `file_paths`, `family_name`, `confidence`, `method`, `candidates`, … | `get card info`                                                                              |
| array of card summaries                                            | `filename`, `file_hash`, `family_name`, `confidence`                                          | `get loaded cards`                                                                           |
| array of model objects                                             | `model_id`, `label`, `description`, `speed` (1–5), `quality` (1–5)                            | `get models`                                                                                 |

[Full JSON Schema (draft 2020-12)](https://raw.githubusercontent.com/skaymakca/GreetingCards/main/content/schemas/apple-events.schema.json)

## Example Script

This script loads a folder, waits for processing to finish, then renames all cards:

```applescript
-- Load cards from a folder
tell application "Greeting Cards"
    set loadResult to load paths {"/Users/you/Cards"}
end tell

-- Poll until processing and AI analysis are complete
repeat
    tell application "Greeting Cards"
        set statusJSON to get status
    end tell

    -- Parse the JSON string (requires JavaScript or external tool)
    -- Quick check: done when "is_processing":false and "is_analyzing":false
    if statusJSON contains "\"is_processing\":false" and statusJSON contains "\"is_analyzing\":false" then
        exit repeat
    end if
    delay 2
end repeat

-- Rename all loaded cards
tell application "Greeting Cards"
    set cardsJSON to get loaded cards
end tell

-- For each card path, call rename card
-- (iterate with your preferred JSON parser or shell helper)
```

For Python-based automation using `subprocess` and `json`:

```python
import subprocess, json, time


def run(cmd):
    result = subprocess.run(["osascript", "-e", cmd], capture_output=True, text=True)
    return json.loads(result.stdout.strip())


# Load a folder
run('tell application "Greeting Cards" to load paths {"/Users/you/Cards"}')

# Wait for processing
while True:
    status = run('tell application "Greeting Cards" to get status')
    if not status["is_processing"] and not status["is_analyzing"]:
        break
    time.sleep(2)

# Rename all cards
cards = run('tell application "Greeting Cards" to get loaded cards')
for card in cards:
    for path in card.get("file_paths", []):
        result = run(f'tell application "Greeting Cards" to rename card path "{path}"')
        print(result)
```
