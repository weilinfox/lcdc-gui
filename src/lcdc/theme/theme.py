
import json
import logging
import pathlib
import random
import string

from PIL import Image, ImageDraw
from typing import Dict, List


logger = logging.getLogger(__name__)


class Theme:
    def __init__(self, _path: pathlib.Path):
        # use json for not recommended to edit manually
        self._config_file = "config.json"
        self._config_path: pathlib.Path = _path

        self.background = self._config_path / "demo.jpg"
        self.mask = self._config_path / "mask.png"
        self.widgets: List[Dict] = []

        self.read_config()

    def read_config(self):
        fp = self._config_path / self._config_file
        try:
            with open(fp, "rw") as f:
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

    def _init_theme(self):
        self._init_ebu_background(480, 480)
        self._init_fade_mask(480, 480)
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
          # ("black",   (  0,   0,   0)),
        ]
        img = Image.new("RGB", (_width, _height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        bar_w = _width // len(bars)
        for i, (_, c) in enumerate(bars):
            x0 = i * bar_w
            x1 = (i + 1) * bar_w if i < len(bars) - 1 else _width
            draw.rectangle([x0, 0, x1, _height], fill=c)

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

        img.save(self.mask, format="PNG")

    def save_config(self):
        fp = self._config_path / self._config_file
        d = {
            "background": self.background,
            "mask": self.mask,
            "widgets": self.widgets,
        }
        with open(fp, "rw") as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=4))
