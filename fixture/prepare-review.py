"""Create real raster files for the review's extension-alias regression."""

import os
from pathlib import Path

from PIL import Image

directory = Path(os.environ["ASTRBOT_ROOT"]) / "data/plugin_data/preview_fixture/files/aliases"
directory.mkdir(parents=True, exist_ok=True)
for name, format_, color in [
    ("sample.jfif", "JPEG", "#185bba"),
    ("sample.jpe", "JPEG", "#c96f20"),
    ("sample.dib", "DIB", "#258365"),
]:
    Image.new("RGB", (96, 64), color).save(directory / name, format=format_)
Image.new("RGB", (96, 64), "#185bba").save(
    directory / "sample.apng",
    format="PNG",
    save_all=True,
    append_images=[Image.new("RGB", (96, 64), "#c96f20")],
    duration=100,
    loop=0,
)
print("Prepared four synthetic raster aliases.")
