
import json
import logging
import pathlib
import random
import string

from PIL import Image, ImageDraw, ImageFont
from typing import Dict, List

from ..server.sensors import Sensors


logger = logging.getLogger(__name__)


class Theme:
    def __init__(self, _config_path: pathlib.Path, _default_width: int, _default_height: int):
        # use json for not recommended to edit manually
        self._config_file = "config.json"
        self._config_path: pathlib.Path = _config_path

        self._default_width = _default_width
        self._default_height = _default_height

        self.background = self._config_path / "demo.jpg"
        self.mask = self._config_path / "mask.png"
        self.mask_img = None
        self.widgets: List[Dict] = [
            {
                "text": "CPU",
                "color": (255, 0, 0, 255),
                "xy": (100, 100),
                "size": 50,
            },
            {
                "widget": "CpuFreqMax",
                "color": (0, 0, 255, 255),
                "xy": (100, 200),
                "size": 50,
                "unit": True,
                "cels": True,
            }
        ]

        self.read_config()

    def read_config(self):
        fp = self._config_path / self._config_file
        try:
            with open(fp, "r+") as f:
                c = json.load(f)
                self.background = pathlib.Path(c["background"])
                self.mask = pathlib.Path(c["mask"])
                self.widgets = c["widgets"]
        except FileNotFoundError:
            logger.warning(f"Theme config {fp} not found")
            self._init_theme()
        except PermissionError:
            logger.warning(f"Theme config {fp} permission denied")
            self._config_file = "config-".join(random.choice(string.ascii_letters) for _ in range(12)) + ".json"
            logger.warning(f"Use temporary config file {self._config_path / self._config_file}")
            logger.warning("Please remove temporary config file yourself and correct permission of theme config files")
            self._init_theme()
        except Exception as e:
            logger.error(f"Theme config load error")
            logger.error(e)
            if fp.exists():
                logger.warning(f"Theme config {fp} could be corrupt")
                ofp = str(fp.absolute())+".old"
                logger.warning(f"Old theme config rename to {ofp}")
                fp.rename(ofp)
            self._init_theme()

        self.mask_img = Image.open(self.mask).convert("RGBA")

    def _init_theme(self):
        self._init_ebu_background(self._default_width, self._default_height)
        self._init_fade_mask(self._default_width, self._default_height)
        self.save_config()

    def _init_ebu_background(self, _width: int, _height: int):
        bars = [
            ("white",   (255, 255, 255)),
            ("yellow",  (191, 191,   0)),
            ("cyan",    (  0, 191, 191)),
            ("green",   (  0, 191,   0)),
            ("magenta", (191,   0, 191)),
            ("red",     (191,   0,   0)),
            ("blue",    (  0,   0, 191)),
            ("black",   (  0,   0,   0)),
        ]
        img = Image.new("RGB", (_width, _height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        bar_w = _width // len(bars)
        for i, (_, c) in enumerate(bars):
            x0 = i * bar_w
            x1 = (i + 1) * bar_w if i < len(bars) - 1 else _width
            draw.rectangle([x0, 0, x1, _height], fill=c)

        draw.text((10, _height - 100), "BG", (0, 0, 0))

        img.save(self.background, format="JPEG", quality=100, progressive=True, optimize=True)

    def _init_fade_mask(self, _width: int, _height: int):
        img = Image.new("RGBA", (_width, _height), (255, 255, 255, 255))
        p = img.load()

        #     y=   0 -> height-1
        # alpha= 255 -> 0 (100% -> 0%)
        for y in range(_height):
            # linear interpolation
            alpha = int(round(255 * (1 - y / (_height - 1)))) if _height > 1 else 255
            for x in range(_width):
                p[x, y] = (255, 255, 255, alpha)

        draw = ImageDraw.Draw(img)
        draw.text((10, 100), "MASK", (0, 0, 0, 255))

        img.save(self.mask, format="PNG")

    def blend(self, _background: Image, _sensor: Sensors) -> Image:
        base = _background.convert("RGBA")

        if self.mask_img.size != base.size:
            self.mask_img = self.mask_img.resize(base.size, Image.BILINEAR)
        img = Image.alpha_composite(base, self.mask_img)

        # widgets
        draw = ImageDraw.Draw(img)
        for w in self.widgets:
            if "text" in w.keys():
                text = w["text"]
            else:
                unit = w.get("unit", True)
                cels = w.get("cels", True)
                text = _sensor.format(w["widget"], unit, cels)[0]
            xy = tuple(w.get("xy", (50, 50)))
            color = tuple(w.get("color", (0, 0, 0, 255)))
            size = w.get("size", 10)
            font = ImageFont.load_default(size)
            draw.text(xy, text, color, font)

        return img

    def save_config(self):
        fp = self._config_path / self._config_file
        d = {
            "background": str(self.background.absolute()),
            "mask": str(self.mask.absolute()),
            "widgets": self.widgets,
        }
        with open(fp, "w+") as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=4))
