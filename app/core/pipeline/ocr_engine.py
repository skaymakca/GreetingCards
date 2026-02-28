import tesserocr
from PIL import Image, ImageFilter, ImageOps

from app.core.paths import get_runtime_content_path

_tessdata_path = str(get_runtime_content_path("tessdata/fast"))

# Percent of lightest/darkest pixels to clip during autocontrast.
# Value of 2 clips the top/bottom 2% of the histogram, improving contrast
# on washed-out scans without losing detail on high-contrast originals.
_OCR_CONTRAST_CUTOFF = 2

# Tesseract penalty for non-dictionary words (lower = more lenient on names).
# Greeting cards contain proper names that aren't in dictionaries, so a low
# penalty (0.15 vs default 1.0) prevents Tesseract from "correcting" names
# into dictionary words (e.g. "Walton" → "Watson").
_OCR_DICT_PENALTY = "0.15"


def preprocess_image(image: Image.Image) -> Image.Image:
    """Preprocess image for better OCR results."""
    img = image.copy()
    # Convert to grayscale
    img = ImageOps.grayscale(img)
    # Increase contrast
    img = ImageOps.autocontrast(img, cutoff=_OCR_CONTRAST_CUTOFF)
    # Slight sharpen to help with text edges
    img = img.filter(ImageFilter.SHARPEN)
    return img


def extract_text(image: Image.Image) -> str:
    """Run OCR on an image and return extracted text."""
    processed = preprocess_image(image)
    with tesserocr.PyTessBaseAPI(path=_tessdata_path) as api:
        api.SetPageSegMode(tesserocr.PSM.AUTO)
        api.SetVariable("language_model_penalty_non_dict_word", _OCR_DICT_PENALTY)
        api.SetImage(processed)
        return api.GetUTF8Text().strip()


def extract_text_all_pages(images: list[Image.Image]) -> str:
    """Run OCR on multiple page images and combine results."""
    texts = []
    for img in images:
        text = extract_text(img)
        if text:
            texts.append(text)
    return "\n\n".join(texts)
