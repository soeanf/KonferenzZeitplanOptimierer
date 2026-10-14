"""Erzeugt die Programm-Icons (icon.ico, icon.png) fuer GUI und EXE.

Aufruf: python tools/make_icon.py
Design: dunkle Kachel, links eine Zeitachse mit Punkten (Slots), rechts die Konferenzen;
parallele Konferenzen liegen nebeneinander. Die Vektorvorlage steht in tools/icon.svg.
"""
from pathlib import Path

from PIL import Image, ImageDraw

SS = 4  # Supersampling
N = 512
NAVY, AXIS, WHITE = "#1a2a44", "#6b7f9e", "#ffffff"
ORANGE, BLUE, GREEN = "#d9631e", "#2b6cb0", "#2f855a"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]

AXIS_X, DOT_Y = 96, (118, 256, 394)
ROWS = [
    (70, [(140, 310, ORANGE), (326, 450, BLUE)]),
    (208, [(140, 450, GREEN)]),
    (346, [(140, 262, BLUE), (278, 450, ORANGE)]),
]


def _rounded(d: ImageDraw.ImageDraw, x0, y0, x1, y1, r, fill) -> None:
    d.rounded_rectangle((x0 * SS, y0 * SS, x1 * SS, y1 * SS), radius=r * SS, fill=fill)


def _dot(d: ImageDraw.ImageDraw, cx, cy, r, fill) -> None:
    d.ellipse(((cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS), fill=fill)


def render() -> Image.Image:
    img = Image.new("RGBA", (N * SS, N * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    _rounded(d, 0, 0, N - 1, N - 1, 100, NAVY)
    _rounded(d, AXIS_X - 4, 70, AXIS_X + 4, 442, 4, AXIS)
    for cy in DOT_Y:
        _dot(d, AXIS_X, cy, 20, WHITE)
        _dot(d, AXIS_X, cy, 9, NAVY)
    for y, blocks in ROWS:
        for x0, x1, color in blocks:
            _rounded(d, x0, y, x1, y + 96, 24, color)
    return img.resize((N, N), Image.LANCZOS)


def main() -> None:
    out = Path(__file__).resolve().parent.parent / "konferenz_optimizer" / "gui" / "assets"
    out.mkdir(parents=True, exist_ok=True)
    img = render()
    img.resize((256, 256), Image.LANCZOS).save(out / "icon.png")
    img.save(out / "icon.ico", format="ICO", sizes=[(s, s) for s in SIZES])
    print("geschrieben:", out)


if __name__ == "__main__":
    main()
