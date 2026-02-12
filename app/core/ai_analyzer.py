import base64
import io
import os

from PIL import Image
from dotenv import load_dotenv

load_dotenv()


def analyze_card_with_ai(image: Image.Image) -> tuple[str, list[str]]:
    """
    Use Claude's vision to analyze a greeting card image and extract the family name.
    Returns (best_name, alternates).
    """
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key or api_key == "your-api-key-here":
        raise ValueError(
            "ANTHROPIC_API_KEY not set. Please add your API key to the .env file."
        )

    client = anthropic.Anthropic(api_key=api_key)

    # Convert image to base64
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    img_b64 = base64.standard_b64encode(buf.getvalue()).decode("utf-8")

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=256,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": img_b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": (
                            "This is a holiday/greeting card. Extract the family name "
                            "that sent this card. Return ONLY the family last name "
                            "(e.g., 'Smith' not 'The Smith Family' or 'The Smiths'). "
                            "If you see multiple possible names, return the most likely "
                            "one on the first line, then each alternate on its own line. "
                            "If you cannot determine a family name, respond with just: UNKNOWN"
                        ),
                    },
                ],
            }
        ],
    )

    response_text = message.content[0].text.strip()

    if response_text.upper() == "UNKNOWN":
        return "", []

    lines = [line.strip() for line in response_text.split("\n") if line.strip()]
    best = lines[0] if lines else ""
    alternates = lines[1:] if len(lines) > 1 else []

    return best, alternates
