"""Generate Read Me.rtfd for the DMG installer.

Reads content/dmg/readme.md and produces _build/dmg/Read Me.rtfd/ with:
  - 128×128 app icon (centred, via NeXTGraphic)
  - "Greeting Cards" title (bold, 28pt)
  - "Version: X.Y.Z" subtitle (gray, 12pt)
  - Markdown body: ## headings, **bold**, numbered lists, bullet lists, paragraphs

Output is an RTFD package (directory with TXT.rtf + icon.png) because TextEdit
on macOS does not render \\pict\\pngblip images in plain RTF — only NeXTGraphic
references in RTFD packages are displayed.

Exposes generate(version: str) -> Path (returns the .rtfd directory).
"""

import io
import pathlib
import re
import shutil
import sys

from PIL import Image

_ROOT = pathlib.Path(__file__).parent.parent.parent
_README_MD = _ROOT / "content" / "dmg" / "readme.md"
_ICON_PNG = _ROOT / "content" / "images" / "icon.png"
_OUTPUT = _ROOT / "_build" / "dmg" / "Read Me.rtfd"


def _rtf_escape(text: str) -> str:
    """Escape special RTF characters and non-ASCII code points."""
    text = text.replace("\\", "\\\\")
    text = text.replace("{", "\\{")
    text = text.replace("}", "\\}")
    result = []
    for ch in text:
        code = ord(ch)
        if code > 127:
            # RTF Unicode escape: \uN? (? is the fallback for non-Unicode readers)
            result.append(f"\\u{code}?")
        else:
            result.append(ch)
    return "".join(result)


def _inline(text: str) -> str:
    """Render inline Markdown (**bold**) to RTF bold spans."""
    parts = re.split(r"\*\*(.+?)\*\*", text)
    out = []
    for i, part in enumerate(parts):
        if i % 2 == 0:
            out.append(_rtf_escape(part))
        else:
            out.append("{\\b " + _rtf_escape(part) + "}")
    return "".join(out)


def _render_body(md: str) -> str:
    """Convert Markdown body to RTF paragraphs."""
    lines = md.strip().splitlines()
    out: list[str] = []

    for line in lines:
        line = line.rstrip()

        if not line:
            continue

        if line.startswith("## "):
            heading = _rtf_escape(line[3:])
            out.append(f"\\pard\\ql\\sb240\\sa80{{\\f0\\b\\fs30 {heading}}}\\par")

        elif re.match(r"^\d+\.\s", line):
            m = re.match(r"^(\d+)\.\s*(.*)", line)
            if m:
                num = m.group(1)
                content = _inline(m.group(2))
                out.append(f"\\pard\\ql\\li360\\f0\\fs24 {num}. {content}\\par")

        elif line.startswith("- "):
            content = _inline(line[2:])
            out.append(f"\\pard\\ql\\li360\\f0\\fs24 - {content}\\par")

        else:
            content = _inline(line)
            out.append(f"\\pard\\ql\\sa80\\f0\\fs24 {content}\\par")

    return "\n".join(out)


def generate(version: str) -> pathlib.Path:
    """Generate _build/dmg/Read Me.rtfd and return the package path."""
    # RTFD is a directory package — rebuild it fresh each time
    shutil.rmtree(_OUTPUT, ignore_errors=True)
    _OUTPUT.mkdir(parents=True)

    # Resize icon to 128×128 and copy into the package.
    # NeXTGraphic \width/\height are ignored by TextEdit — the image renders at
    # its native pixel size, so we must resize before placing it in the package.
    img = Image.open(_ICON_PNG).convert("RGBA")
    img = img.resize((128, 128), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    (_OUTPUT / "icon.png").write_bytes(buf.getvalue())

    # Double-group structure with Apple attachment attributes and \'ac placeholder —
    # this is the exact format textutil/Cocoa emits; without it TextEdit drops all
    # text following the image.
    # 128px × 20 twips/pt = 2560 twips (correct at 72 DPI); \noorient prevents
    # orientation changes when the document is rotated or reflowed.
    icon_twips = 128 * 20
    icon_block = (
        f"\\pard\\qc\\sb240\\sa120"
        f"{{{{\\NeXTGraphic icon.png \\width{icon_twips} \\height{icon_twips}"
        f" \\noorient \\appleattachmentpadding0 \\appleembedtype0 \\appleaqc\n}}\\'ac}}\\par"
    )
    title_block = "\\pard\\qc\\sb120\\sa60{\\f0\\b\\fs56 Greeting Cards}\\par"
    ver_esc = _rtf_escape(f"Version: {version}")
    version_block = f"\\pard\\qc\\sb60\\sa240{{\\f0\\fs24\\cf1 {ver_esc}\\cf0}}\\par"

    md_text = _README_MD.read_text(encoding="utf-8")
    body = _render_body(md_text)

    rtf = (
        "{\\rtf1\\ansi\\deff0\\readonlydoc1\n"
        "{\\fonttbl{\\f0\\fswiss\\fcharset0 Helvetica;}}\n"
        "{\\colortbl ;\\red128\\green128\\blue128;}\n"
        "\\paperw12240\\paperh15840\n"
        "\\margl1440\\margr1440\\margt1440\\margb1440\n"
        f"{icon_block}\n"
        f"{title_block}\n"
        f"{version_block}\n"
        f"{body}\n"
        "}"
    )

    txt_rtf = _OUTPUT / "TXT.rtf"
    txt_rtf.write_text(rtf, encoding="ascii", errors="replace")
    print(f"Generated {_OUTPUT}")
    return _OUTPUT


if __name__ == "__main__":
    generate(sys.argv[1] if len(sys.argv) > 1 else "0.0.0")
