import base64
import io
import logging
from dataclasses import dataclass, field
from typing import Any

from PIL import Image

from app.core.config import get_ai_model, get_api_key

logger = logging.getLogger(__name__)

# Generous for up to 5 name lines in the response
_MAX_TOKENS = 256
# SDK-level retries with exponential backoff + jitter + retry-after header parsing
_MAX_RETRIES = 4
# Lines longer than this are likely OCR garbage, not family names
_MAX_LINE_LENGTH = 50


@dataclass
class AIResult:
    """Result from AI analysis of a greeting card."""

    best_name: str = ""
    alternates: list[str] = field(default_factory=list)


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


def parse_retry_after(exc: Exception) -> float:
    """Extract retry-after delay from a rate limit exception. Falls back to 10s."""
    headers = getattr(getattr(exc, "response", None), "headers", {})
    for key, divisor in [("retry-after-ms", 1000), ("retry-after", 1)]:
        val = headers.get(key)
        if val:
            try:
                return float(val) / divisor
            except ValueError:
                pass
    return 10.0


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
        line
        for line in (raw.strip() for raw in response_text.split("\n"))
        if line and len(line) <= _MAX_LINE_LENGTH and not any(w in line.lower() for w in _SKIP_WORDS)
    ]

    return AIResult(
        best_name=lines[0] if lines else "",
        alternates=lines[1:] if len(lines) > 1 else [],
    )


def _build_content_blocks(images: list[Image.Image]) -> list[dict[str, Any]]:
    """Build the content blocks for the Claude API request."""
    content: list[dict[str, Any]] = []
    for image in images:
        img_b64 = _image_to_b64(image)
        content.append(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": img_b64,
                },
            }
        )

    page_word = "page" if len(images) == 1 else "pages"
    content.append(
        {
            "type": "text",
            "text": _PROMPT_TEMPLATE.format(count=len(images), page_word=page_word),
        }
    )
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
    client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=_MAX_RETRIES)
    content = _build_content_blocks(images)

    message = await client.messages.create(
        model=get_ai_model(),
        max_tokens=_MAX_TOKENS,
        messages=[{"role": "user", "content": content}],  # type: ignore[typeddict-item]  # pyright: ignore[reportArgumentType]  # dict matches MessageParam
    )

    if not message.content:
        return _parse_response("")
    block = message.content[0]
    response_text = block.text.strip() if hasattr(block, "text") else ""  # pyright: ignore[reportAttributeAccessIssue]
    return _parse_response(response_text)
