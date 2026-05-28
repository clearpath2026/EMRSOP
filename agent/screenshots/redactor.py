from PIL import Image, ImageFilter
import io

_BLUR_RADIUS = 15


def _regions_windows_ocr(image: Image.Image) -> list:
    import asyncio

    async def _run():
        from winsdk.windows.media.ocr import OcrEngine
        from winsdk.windows.graphics.imaging import (
            BitmapDecoder, SoftwareBitmap,
            BitmapPixelFormat, BitmapAlphaMode,
        )
        from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

        buf = io.BytesIO()
        image.save(buf, format="BMP")
        data = buf.getvalue()

        stream = InMemoryRandomAccessStream()
        writer = DataWriter(stream)
        writer.write_bytes(data)
        await writer.store_async()
        stream.seek(0)

        decoder = await BitmapDecoder.create_async(stream)
        bitmap = await decoder.get_software_bitmap_async()
        bitmap = SoftwareBitmap.convert(
            bitmap,
            BitmapPixelFormat.BGRA8,
            BitmapAlphaMode.PREMULTIPLIED,
        )

        engine = OcrEngine.try_create_from_user_profile_languages()
        if engine is None:
            return []

        result = await engine.recognize_async(bitmap)
        regions = []
        for line in result.lines:
            for word in line.words:
                r = word.bounding_rect
                regions.append((int(r.x), int(r.y), int(r.width), int(r.height)))
        return regions

    return asyncio.run(_run())


def _regions_tesseract(image: Image.Image) -> list:
    import pytesseract
    import pandas as pd

    _CONF_THRESHOLD = 60
    data: pd.DataFrame = pytesseract.image_to_data(
        image, output_type=pytesseract.Output.DATAFRAME
    )
    regions = []
    for _, row in data[(data["level"] == 5) & (data["conf"] >= _CONF_THRESHOLD)].iterrows():
        x, y, w, h = int(row["left"]), int(row["top"]), int(row["width"]), int(row["height"])
        if w > 0 and h > 0:
            regions.append((x, y, w, h))
    return regions


def blur_text_regions(image: Image.Image) -> Image.Image:
    regions: list = []

    try:
        regions = _regions_windows_ocr(image)
    except Exception:
        pass

    if not regions:
        try:
            regions = _regions_tesseract(image)
        except Exception:
            pass

    result = image.copy()
    for x, y, w, h in regions:
        if w <= 0 or h <= 0:
            continue
        region = result.crop((x, y, x + w, y + h))
        result.paste(region.filter(ImageFilter.GaussianBlur(radius=_BLUR_RADIUS)), (x, y))

    return result
