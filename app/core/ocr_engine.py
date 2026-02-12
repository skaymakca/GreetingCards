import pytesseract
from PIL import Image, ImageFilter, ImageOps


def preprocess_image(image: Image.Image) -> Image.Image:
    """Preprocess image for better OCR results."""
    img = image.copy()
    # Convert to grayscale
    img = ImageOps.grayscale(img)
    # Increase contrast
    img = ImageOps.autocontrast(img, cutoff=2)
    # Slight sharpen to help with text edges
    img = img.filter(ImageFilter.SHARPEN)
    return img


def extract_text(image: Image.Image) -> str:
    """Run OCR on an image and return extracted text."""
    processed = preprocess_image(image)
    text = pytesseract.image_to_string(processed, config="--psm 6")
    return text.strip()


def extract_text_all_pages(images: list[Image.Image]) -> str:
    """Run OCR on multiple page images and combine results."""
    texts = []
    for img in images:
        text = extract_text(img)
        if text:
            texts.append(text)
    return "\n\n".join(texts)
