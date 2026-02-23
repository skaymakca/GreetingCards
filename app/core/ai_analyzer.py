import base64
import io
import logging
import re
from dataclasses import dataclass, field

from PIL import Image

from app.core.config import get_api_key, get_ai_model

logger = logging.getLogger(__name__)

_MAX_TOKENS = 256
_MAX_LINE_LENGTH = 50


@dataclass
class AIResult:
    """Result from AI analysis of a greeting card."""
    best_name: str = ""
    alternates: list[str] = field(default_factory=list)


def _strip_plural(name: str) -> str:
    """Strip plural 's' or 'es' from family names in obvious cases only.

    Conservative approach to avoid breaking names that naturally end in 's'.

    Examples:
        "Walshes" -> "Walsh"   (strip 'es' after 'sh')
        "Smiths" -> "Smith"     (strip 's' after 'th')
        "Browns" -> "Brown"     (strip 's' after 'wn')
        "Jones" -> "Jones"      (keep - natural name ending)
        "Williams" -> "Williams" (keep - natural name ending)
    """
    if not name or len(name) < 3:
        return name

    # Strip "es" after sibilants (very safe plurals)
    if name.endswith("shes") and len(name) > 4:
        return name[:-2]  # "Walshes" -> "Walsh"
    if name.endswith("ches") and len(name) > 4:
        return name[:-2]  # "Marches" -> "March"
    if name.endswith("xes") and len(name) > 3:
        return name[:-2]  # "Foxes" -> "Fox"

    # Strip single 's' after specific consonant patterns (safe plurals)
    if len(name) >= 4 and name.endswith("s") and not name.endswith("ss"):
        if name[-3:-1] in {"th", "wn", "ck", "rd", "rt", "nd", "nt"}:
            return name[:-1]

    return name


def clean_family_name(name: str) -> str:
    """Clean up a family name by removing common unwanted patterns and quotes.

    This is the unified cleaning function applied AFTER loading from DB.
    """
    if not name:
        return ""

    name = name.strip()

    # Remove common prefixes/suffixes
    name = name.split(":", 1)[-1].strip()  # Remove "Page 1:" etc
    name = name.replace("The ", "").replace(" Family", "")
    name = name.replace("From: ", "").replace("Sent by: ", "")

    # Remove ALL double quote variants (straight, curly, low-9, high-reversed-9)
    # Covers: " (U+0022), \u201c (U+201C), \u201d (U+201D), \u201e (U+201E), \u201f (U+201F)
    name = re.sub(r'["""\"\u201C\u201D\u201E\u201F]', '', name).strip()

    # Remove single quotes only at the start/end (not in middle like O'Brien)
    # Handles both straight and curly quotes: ' (U+0027), \u2018 (U+2018), \u2019 (U+2019)
    name = re.sub(r"^[''\u2018\u2019]+", "", name).strip()  # Leading single quotes
    name = re.sub(r"[''\u2018\u2019]+$", "", name).strip()  # Trailing single quotes

    # Final aggressive strip of any remaining punctuation at the ends
    name = name.strip('.,!;:-\u2014\u2013"\'"\u2018\u2019\u201c\u201d')

    # Strip plural 's' or 'es' in obvious cases
    name = _strip_plural(name)

    return name


def format_ai_error(error: Exception) -> str:
    """Format an AI API error into a clean user-facing message."""
    import anthropic

    match error:
        case anthropic.AuthenticationError():
            return "Invalid API key"
        case anthropic.RateLimitError():
            return "Rate limit exceeded — try again later"
        case anthropic.APITimeoutError():
            return "Request timed out"
        case anthropic.APIConnectionError():
            return "Network connection error"
        case anthropic.APIStatusError(status_code=code):
            return f"API error (HTTP {code})"
        case _:
            return str(error)


def _image_to_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


_SKIP_WORDS = {"shows", "appears", "page", "card", "signed", "written", "seems"}

_PROMPT_TEMPLATE = (
    "This is a holiday/greeting card with {count} {page_word}. "
    "Look at ALL pages to find who sent this card. Extract the family name.\n\n"
    "CRITICAL: Return ONLY family last names, one per line. No explanations, "
    "no 'Page 1:', no 'The [Name] Family', no extra text.\n\n"
    "Format:\n"
    "- First line: most likely family name (e.g., 'Smith')\n"
    "- Additional lines (if any): alternate possible names\n"
    "- If uncertain, respond with just: UNKNOWN\n\n"
    "Examples of CORRECT output:\n"
    "Smith\nJones\n\n"
    "Examples of INCORRECT output (DO NOT DO THIS):\n"
    "Page 1: Shows the Smith family\n"
    "The Smith Family\n"
    "From: The Smiths"
)


def _parse_response(response_text: str) -> AIResult:
    """Parse raw AI response text into an AIResult."""
    if response_text.strip().upper() == "UNKNOWN":
        return AIResult()

    # Basic filtering to catch obvious non-name responses
    # NOTE: Comprehensive cleaning is applied AFTER loading from DB, not here
    lines = [
        line for line in (raw.strip() for raw in response_text.split("\n"))
        if line and len(line) <= _MAX_LINE_LENGTH
        and not any(w in line.lower() for w in _SKIP_WORDS)
    ]

    return AIResult(
        best_name=lines[0] if lines else "",
        alternates=lines[1:] if len(lines) > 1 else [],
    )


def _build_content_blocks(images: list[Image.Image]) -> list[dict]:
    """Build the content blocks for the Claude API request."""
    content: list[dict] = []
    for image in images:
        img_b64 = _image_to_b64(image)
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": img_b64,
            },
        })

    page_word = "page" if len(images) == 1 else "pages"
    content.append({
        "type": "text",
        "text": _PROMPT_TEMPLATE.format(count=len(images), page_word=page_word),
    })
    return content


def _normalize_images(images: list[Image.Image] | Image.Image) -> list[Image.Image]:
    """Normalize a single image or list of images to a list."""
    if isinstance(images, Image.Image):
        return [images]
    return images


def _get_validated_api_key() -> str:
    """Get and validate the API key, raising ValueError if not configured."""
    api_key = get_api_key()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured.")
    return api_key


async def analyze_card_with_ai_async(images: list[Image.Image] | Image.Image) -> AIResult:
    """Analyze greeting card images with Claude AI and extract the family name."""
    import anthropic

    images = _normalize_images(images)
    api_key = _get_validated_api_key()
    client = anthropic.AsyncAnthropic(api_key=api_key)
    content = _build_content_blocks(images)

    message = await client.messages.create(
        model=get_ai_model(),
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],  # pyright: ignore[reportArgumentType]  # dict matches MessageParam
    )

    block = message.content[0]
    response_text = block.text.strip() if hasattr(block, "text") else ""  # pyright: ignore[reportAttributeAccessIssue]
    return _parse_response(response_text)


