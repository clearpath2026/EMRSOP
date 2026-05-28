from PIL import Image


def get_text(image: Image.Image) -> str:
    """Extract all text from image. Tries Windows OCR first, falls back to Tesseract."""
    try:
        from agent.screenshots._winrt import recognize
        result = recognize(image)
        if result is not None:
            return " ".join(line.text for line in result.lines)
    except Exception:
        pass

    try:
        import pytesseract
        return pytesseract.image_to_string(image)
    except Exception:
        return ""
