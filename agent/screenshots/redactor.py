from PIL import Image, ImageFilter
import pytesseract
import pandas as pd

_CONF_THRESHOLD = 60
_BLUR_RADIUS = 15


def blur_text_regions(image: Image.Image) -> Image.Image:
    data: pd.DataFrame = pytesseract.image_to_data(
        image, output_type=pytesseract.Output.DATAFRAME
    )
    result = image.copy()

    text_rows = data[(data["level"] == 5) & (data["conf"] >= _CONF_THRESHOLD)]
    for _, row in text_rows.iterrows():
        x, y, w, h = int(row["left"]), int(row["top"]), int(row["width"]), int(row["height"])
        if w <= 0 or h <= 0:
            continue
        region = result.crop((x, y, x + w, y + h))
        blurred = region.filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS))
        result.paste(blurred, (x, y))

    return result
