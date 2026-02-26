---
title: Card List
---

# Card List

## Confidence Indicators

Each card shows a colored dot indicating extraction quality:

- <strong style="color:#34C759">●</strong> **Green** — High confidence match
- <strong style="color:#FF9500">●</strong> **Yellow** — Medium confidence, worth reviewing
- <strong style="color:#FF3B30">●</strong> **Red** — Low confidence, likely needs editing
- <strong style="color:#1E90FF">●</strong> **Blue** — Manually entered name
- <strong style="color:#6E6E73">●</strong> **Gray** — No name extracted yet

## Editing Cards

- Click a row to view the card in the preview panel
- Use <kbd>Shift+Up</kbd> / <kbd>Shift+Down</kbd> or <kbd>Cmd+A</kbd> to select multiple cards
- Edit the family name directly in the text field
- Select from the **Candidates** dropdown for alternate name suggestions
- Click the **AI Analyze** button to analyze a single card with Claude AI
- Remove cards via the **Remove** button, the **Edit** menu (<kbd>Cmd+Delete</kbd>), or right-click context menu (does not delete the file from disk)
- Check **Remove "Family"** to shorten the renamed file (e.g., "Smith.pdf" instead of "Smith Family.pdf")
- Right-click text fields for Cut, Copy, Paste, Title Case, and Clear

## Right-Click Context Menu

Right-click any card row to access these actions:

- **AI Analyze** — Analyze the card with Claude AI to extract the family name
- **Open** — Open the PDF in your default viewer (e.g., Preview.app)
- **Reveal in Finder** — Show the file in a Finder window with the file selected
- **Remove** — Remove the card from the list (non-destructive; does not delete the file)

When multiple cards are selected, context menu actions apply to all selected cards (e.g., "AI Analyze 5 Cards", "Open 3 Cards"). **Reveal in Finder** is only available for single-card selections.

<div class="note">
    <strong>Tip:</strong> Removing a card only removes it from the current session. You can re-add the file by dropping it onto the window again.
</div>

## File Paths Tab

When the same card appears at multiple file locations (identical content), a **File Paths** tab appears showing all locations. Renaming applies to all copies.

## Sidebar Filters

- **All Cards** — Show all cards
- **Manual Entry** — Cards with manually edited names
- **High Confidence** — Cards with reliable name extraction
- **Needs Review** — Medium and low confidence cards
- **Errors** — Cards that failed processing
- **Folders** — Filter by source folder (appears when loading from multiple directories)

<div class="note">
    <strong>Tip:</strong> <kbd>Option</kbd>-click a filter to multi-select. For example, select both "High Confidence" and "Manual Entry" to see all cards that are ready to rename.
</div>
