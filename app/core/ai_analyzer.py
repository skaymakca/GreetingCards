import base64
import io
import re

from PIL import Image

from app.core.config import get_api_key


def _image_to_b64(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.standard_b64encode(buf.getvalue()).decode("utf-8")


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

    # Parse lines and filter out non-name text
    lines = [line.strip() for line in response_text.split("\n") if line.strip()]

    # Clean up each line - remove common prefixes/patterns
    cleaned_lines = []
    for line in lines:
        # Remove common unwanted patterns
        line = line.split(":", 1)[-1].strip()  # Remove "Page 1:" etc
        line = line.replace("The ", "").replace(" Family", "").replace("The ", "")
        line = line.replace("From: ", "").replace("Sent by: ", "")

        # Remove all double quotes
        line = line.replace('"', '')

        # Remove single quotes only at the start/end (not in middle like O'Brien)
        line = re.sub(r"^'+", "", line)  # Leading single quotes
        line = re.sub(r"'+$", "", line)  # Trailing single quotes
        line = line.strip()

        # Skip lines that are too long (likely explanatory text)
        if len(line) > 30:
            continue

        # Skip lines with common explanation words
        skip_words = ["shows", "appears", "page", "card", "signed", "written"]
        if any(word in line.lower() for word in skip_words):
            continue

        if line:
            cleaned_lines.append(line)

    best = cleaned_lines[0] if cleaned_lines else ""
    alternates = cleaned_lines[1:] if len(cleaned_lines) > 1 else []

    return best, alternates
