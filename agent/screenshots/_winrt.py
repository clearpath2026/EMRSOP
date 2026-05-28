import io
import asyncio
from PIL import Image


async def _recognize_async(image: Image.Image):
    from winsdk.windows.media.ocr import OcrEngine
    from winsdk.windows.graphics.imaging import (
        BitmapDecoder, SoftwareBitmap,
        BitmapPixelFormat, BitmapAlphaMode,
    )
    from winsdk.windows.storage.streams import InMemoryRandomAccessStream, DataWriter

    buf = io.BytesIO()
    image.save(buf, format="BMP")

    stream = InMemoryRandomAccessStream()
    writer = DataWriter(stream)
    writer.write_bytes(buf.getvalue())
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
        return None

    return await engine.recognize_async(bitmap)


def recognize(image: Image.Image):
    """Run Windows OCR on image, returns OcrResult or None."""
    return asyncio.run(_recognize_async(image))
