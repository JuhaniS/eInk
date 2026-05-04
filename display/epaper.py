"""Waveshare 7.5" V2 driver via betterepd7in5.

betterepd7in5 fixes the post-sleep partial-update corruption that the stock
waveshare_epd driver exhibits, and is ~5× faster on Pi Zero 2 W.

Cron-mode caveat: betterepd7in5 keeps the "current displayed image" purely
in-memory (`epd._cur_img`). Our cron runs main.py as a fresh process each
tick, so we persist that image to disk after every refresh and re-inject it
before partial updates. Setting `_cur_img` directly is a private-attr poke,
but it's the only viable path without going daemon-mode.
"""
from pathlib import Path

from PIL import Image

_CUR_IMG_PATH = Path("cache/cur_display.png")


class EPaperDisplay:
    def _epd(self):
        try:
            import betterepd7in5
        except ImportError:
            raise RuntimeError(
                "betterepd7in5 not installed. Run: pip install betterepd7in5"
            )
        return betterepd7in5.EPD(betterepd7in5.RaspberryPi())

    def _save_cur(self, image: Image.Image):
        _CUR_IMG_PATH.parent.mkdir(parents=True, exist_ok=True)
        image.convert("1").save(_CUR_IMG_PATH)

    def _load_cur(self) -> Image.Image | None:
        if _CUR_IMG_PATH.exists():
            return Image.open(_CUR_IMG_PATH).convert("1")
        return None

    def show(self, image, **kwargs):
        """Fast refresh — used for the every-10-min full dashboard update."""
        epd = self._epd()
        with epd.display_bilevel_fast_refresh() as draw:
            draw(image)
        self._save_cur(image)

    def show_full(self, image, **kwargs):
        """Full refresh — slow, but clears ghosting. Run hourly or on demand."""
        epd = self._epd()
        with epd.display_bilevel_full_refresh() as draw:
            draw(image)
        self._save_cur(image)

    def show_partials(self, regions, **_kwargs):
        """Partial-refresh multiple regions in a single EPD session.

        `regions` is a list of `(image, box)` where `box=(x0, y0, x1, y1)`.
        Constraints (asserted): `x0 % 8 == 0`, `(x1 - x0) % 8 == 0`, no two
        boxes overlap. Requires a prior full/fast refresh to have written
        cache/cur_display.png."""
        if not regions:
            return
        for img, box in regions:
            x0, _, x1, _ = box
            assert x0 % 8 == 0,           f"box[0] must be 8-aligned, got {x0}"
            assert (x1 - x0) % 8 == 0,    f"width must be 8-aligned, got {x1-x0}"
        for i, (_, a) in enumerate(regions):
            for _, b in regions[i+1:]:
                assert not (a[0] < b[2] and b[0] < a[2]
                            and a[1] < b[3] and b[1] < a[3]), \
                    f"partial regions overlap: {a} and {b}"

        cur = self._load_cur()
        if cur is None:
            raise RuntimeError(
                f"No baseline at {_CUR_IMG_PATH} — run a full/fast refresh first"
            )
        epd = self._epd()
        epd._cur_img = cur  # see module docstring
        with epd.display_bilevel_partial_refresh() as draw:
            for img, box in regions:
                draw(img.convert("1"), xy=(box[0], box[1]))
        for img, box in regions:
            cur.paste(img.convert("1"), (box[0], box[1]))
        self._save_cur(cur)
