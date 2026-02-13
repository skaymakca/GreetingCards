import base64
import io
import re

from PIL import Image

from app.core.config import get_api_key


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

    # Strip single 's' only after specific consonant patterns (safe plurals)
    if name.endswith("s") and not name.endswith("ss") and len(name) >= 4:
        # Very common plural patterns that are safe to strip
        if name.endswith("ths"):
            return name[:-1]  # "Smiths" -> "Smith"
        if name.endswith("wns"):
            return name[:-1]  # "Browns" -> "Brown"
        if name.endswith("cks"):
            return name[:-1]  # "Blacks" -> "Black"
        if name.endswith("rds"):
            return name[:-1]  # "Edwards" -> "Edward"
        if name.endswith("rts"):
            return name[:-1]  # "Roberts" -> "Robert"
        if name.endswith("nds"):
            return name[:-1]  # "Strands" -> "Strand"
        if name.endswith("nts"):
            return name[:-1]  # "Grants" -> "Grant"

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
    # Covers: " (U+0022), " (U+201C), " (U+201D), „ (U+201E), ‟ (U+201F)
    name = re.sub(r'["""\"\u201C\u201D\u201E\u201F]', '', name).strip()

    # Remove single quotes only at the start/end (not in middle like O'Brien)
    # Handles both straight and curly quotes: ' (U+0027), ' (U+2018), ' (U+2019)
    name = re.sub(r"^[''\u2018\u2019]+", "", name).strip()  # Leading single quotes
    name = re.sub(r"[''\u2018\u2019]+$", "", name).strip()  # Trailing single quotes

    # Final aggressive strip of any remaining punctuation at the ends
    name = name.strip('.,!;:-—–"\'"''""')

    # Strip plural 's' or 'es' in obvious cases
    name = _strip_plural(name)

    return name


def format_ai_error(error: Exception) -> str:
    """Format an AI API error into a clean user-facing message."""
    import anthropic

    if isinstance(error, anthropic.AuthenticationError):
        return "Invalid API key"
    if isinstance(error, anthropic.RateLimitError):
        return "Rate limit exceeded — try again later"
    if isinstance(error, anthropic.APIConnectionError):
        return "Network connection error"
    if isinstance(error, anthropic.APITimeoutError):
        return "Request timed out"
    if isinstance(error, anthropic.APIStatusError):
        return f"API error (HTTP {error.status_code})"
    return str(error)


def _image_to_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


async def analyze_card_with_ai_async(images: list[Image.Image] | Image.Image) -> tuple[str, list[str]]:
    """
    Async version for concurrent AI analysis of multiple cards.
    Use Claude's vision to analyze greeting card page images and extract the family name.
    Accepts a single image or a list of page images.
    Returns (best_name, alternates).
    """
    import anthropic

    # Normalize to list
    if isinstance(images, Image.Image):
        images = [images]

    api_key = get_api_key()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured.")

    client = anthropic.AsyncAnthropic(api_key=api_key)

    # Build content blocks — one image per page, then the text prompt
    content = []
    for i, image in enumerate(images):
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
        "text": (
            f"This is a holiday/greeting card with {len(images)} {page_word}. "
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
        ),
    })

    message = await client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=256,
        messages=[{"role": "user", "content": content}],
    )

    response_text = message.content[0].text.strip()

    if response_text.upper() == "UNKNOWN":
        return "", []

    # Parse lines and do basic filtering
    # NOTE: Comprehensive cleaning is applied AFTER loading from DB, not here
    lines = [line.strip() for line in response_text.split("\n") if line.strip()]

    # Basic filtering to catch obvious non-name responses
    filtered_lines = []
    for line in lines:
        # Skip lines that are too long (likely explanatory text)
        if len(line) > 50:
            continue

        # Skip lines with common explanation words
        skip_words = ["shows", "appears", "page", "card", "signed", "written", "seems"]
        if any(word in line.lower() for word in skip_words):
            continue

        if line:
            filtered_lines.append(line)

    # Return RAW results - cleaning happens in database.py when loading
    best = filtered_lines[0] if filtered_lines else ""
    alternates = filtered_lines[1:] if len(filtered_lines) > 1 else []

    return best, alternates


def analyze_card_with_ai(images: list[Image.Image] | Image.Image) -> tuple[str, list[str]]:
    """
    Use Claude's vision to analyze greeting card page images and extract the family name.
    Accepts a single image or a list of page images.
    Returns (best_name, alternates).
    """
    import anthropic

    # Normalize to list
    if isinstance(images, Image.Image):
        images = [images]

    api_key = get_api_key()
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY not configured.")

    client = anthropic.Anthropic(api_key=api_key)

    # Build content blocks — one image per page, then the text prompt
    content = []
    for i, image in enumerate(images):
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
        "text": (
            f"This is a holiday/greeting card with {len(images)} {page_word}. "
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
        ),
    })

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=256,
        messages=[{"role": "user", "content": content}],
    )

    response_text = message.content[0].text.strip()

    if response_text.upper() == "UNKNOWN":
        return "", []

    # Parse lines and do basic filtering
    # NOTE: Comprehensive cleaning is applied AFTER loading from DB, not here
    lines = [line.strip() for line in response_text.split("\n") if line.strip()]

    # Basic filtering to catch obvious non-name responses
    filtered_lines = []
    for line in lines:
        # Skip lines that are too long (likely explanatory text)
        if len(line) > 50:
            continue

        # Skip lines with common explanation words
        skip_words = ["shows", "appears", "page", "card", "signed", "written", "seems"]
        if any(word in line.lower() for word in skip_words):
            continue

        if line:
            filtered_lines.append(line)

    # Return RAW results - cleaning happens in database.py when loading
    best = filtered_lines[0] if filtered_lines else ""
    alternates = filtered_lines[1:] if len(filtered_lines) > 1 else []

    return best, alternates
