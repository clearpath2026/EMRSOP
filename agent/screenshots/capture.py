from PIL import Image
import numpy as np
import mss
import win32gui


def capture_emr_window(hwnd: int) -> Image.Image:
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    region = {"top": top, "left": left, "width": right - left, "height": bottom - top}
    with mss.mss() as sct:
        raw = sct.grab(region)
        img_array = np.array(raw)
        return Image.fromarray(img_array[:, :, :3], mode="RGB")
