"""Create deterministic, synthetic acceptance data in an isolated AstrBot root."""

import copy
import json
import os
from pathlib import Path

from PIL import Image, ImageDraw

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.utils.auth_password import hash_dashboard_password

root = Path(os.environ["ASTRBOT_ROOT"])
data = root / "data"
config = copy.deepcopy(DEFAULT_CONFIG)
config["dashboard"].update(
    {
        "host": "127.0.0.1",
        "port": 6187,
        "pbkdf2_password": hash_dashboard_password("PreviewFixture-Only-10595!"),
        "password_storage_upgraded": True,
        "password_change_required": False,
    }
)
(data / "cmd_config.json").write_text(json.dumps(config), encoding="utf-8")
assets = data / "plugin_data" / "preview_fixture" / "files" / "images"
assets.mkdir(parents=True, exist_ok=True)
for name, color, text, size in [
    ("01-blue-landscape.png", "#185bba", "SYNTHETIC BLUE LANDSCAPE", (1200, 700)),
    ("02-orange-portrait.png", "#c96f20", "SYNTHETIC PORTRAIT", (600, 1100)),
    ("03-green-square.webp", "#258365", "SYNTHETIC GREEN SQUARE", (800, 800)),
]:
    image = Image.new("RGB", size, color)
    draw = ImageDraw.Draw(image)
    draw.rectangle((40, 40, size[0] - 40, size[1] - 40), outline="white", width=5)
    draw.text((65, 80), text, fill="white", font_size=30)
    image.save(assets / name)
(assets / "notes.txt").write_text("Synthetic non-image file.\n", encoding="utf-8")
(assets / "invalid.png").write_bytes(b"This is not an image.\n")
(data / "config").mkdir(exist_ok=True)
paths = [f"files/images/{name}" for name in [
    "01-blue-landscape.png",
    "02-orange-portrait.png",
    "03-green-square.webp",
    "notes.txt",
    "invalid.png",
    "missing.png",
]]
(data / "config" / "astrbot_plugin_preview_fixture_config.json").write_text(
    json.dumps({"images": paths, "other_images": []}), encoding="utf-8"
)
print("Prepared synthetic fixture files and a loopback-only dashboard configuration.")
