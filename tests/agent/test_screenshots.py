import pytest
from unittest.mock import patch, MagicMock
from PIL import Image
import numpy as np


def _make_image(width=800, height=600):
    return Image.fromarray(
        np.zeros((height, width, 3), dtype=np.uint8), mode="RGB"
    )


def test_capture_returns_pil_image():
    from agent.screenshots.capture import capture_emr_window

    mock_sct = MagicMock()
    mock_sct.__enter__ = lambda s: s
    mock_sct.__exit__ = MagicMock(return_value=False)
    mock_sct.grab.return_value = MagicMock(
        __array_interface__={
            "shape": (600, 800, 4),
            "typestr": "|u1",
            "data": bytes(600 * 800 * 4),
            "version": 3,
        }
    )

    with patch("agent.screenshots.capture.win32gui") as mock_win32:
        mock_win32.GetWindowRect.return_value = (100, 100, 900, 700)
        with patch("agent.screenshots.capture.mss.mss", return_value=mock_sct):
            img = capture_emr_window(hwnd=12345)

    assert isinstance(img, Image.Image)


def test_blur_text_regions_returns_pil_image():
    from agent.screenshots.redactor import blur_text_regions

    img = _make_image()
    fake_df = {
        "level": [5, 5],
        "left": [10, 200],
        "top": [20, 100],
        "width": [80, 120],
        "height": [20, 25],
        "text": ["John Smith", "M5V 3A8"],
        "conf": [90, 85],
    }

    with patch("agent.screenshots.redactor.pytesseract.image_to_data") as mock_ocr:
        import pandas as pd
        mock_ocr.return_value = pd.DataFrame(fake_df)
        result = blur_text_regions(img)

    assert isinstance(result, Image.Image)
    assert result.size == img.size


def test_blur_no_text_returns_original_dimensions():
    from agent.screenshots.redactor import blur_text_regions

    img = _make_image()
    with patch("agent.screenshots.redactor.pytesseract.image_to_data") as mock_ocr:
        import pandas as pd
        mock_ocr.return_value = pd.DataFrame({
            "level": [], "left": [], "top": [],
            "width": [], "height": [], "text": [], "conf": [],
        })
        result = blur_text_regions(img)

    assert result.size == img.size
