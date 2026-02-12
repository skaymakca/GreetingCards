import base64
import io

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
            "Look at ALL pages to find who sent this card. Extract the family name "
            "that sent this card. Return ONLY the family last name "
            "(e.g., 'Smith' not 'The Smith Family' or 'The Smiths'). "
            "If you see multiple possible names, return the most likely "
            "one on the first line, then each alternate on its own line. "
            "If you cannot determine a family name, respond with just: UNKNOWN"
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

    lines = [line.strip() for line in response_text.split("\n") if line.strip()]
    best = lines[0] if lines else ""
    alternates = lines[1:] if len(lines) > 1 else []

    return best, alternates
