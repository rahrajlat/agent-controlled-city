"""Draw the animated Agent City logo (docs/assets/logo.gif) with Pillow.

    uv run python scripts/make_logo.py

A night-time skyline, a fire that breaks out, a fire engine that is dispatched to it, and a patrol car passing by.
"""

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "logo.gif"
W, H, S = 800, 300, 2  # output size, supersampling factor
FRAMES, FRAME_MS = 72, 70
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"

BG_TOP, BG_BOT = (8, 14, 32), (24, 30, 64)
CYAN, WHITE, DIM = (76, 201, 240), (236, 240, 248), (138, 155, 181)
ROAD_Y = 252

rng = random.Random(7)
BUILDINGS = [  # x, width, height, colour
    (20, 52, 84, (30, 41, 74)), (78, 40, 118, (38, 50, 88)), (124, 60, 70, (30, 41, 74)),
    (190, 46, 100, (38, 50, 88)), (560, 50, 96, (30, 41, 74)), (616, 44, 132, (38, 50, 88)),
    (666, 56, 78, (30, 41, 74)), (728, 48, 108, (38, 50, 88)),
]
FIRE_BLDG = (440, 100, 92, (52, 40, 70))  # the one that burns, under the title's right side
WINDOWS = {}
for b in BUILDINGS + [FIRE_BLDG]:
    x, w, h, _ = b
    WINDOWS[x] = [(x + 8 + c * 12, ROAD_Y - h + 10 + r * 16, rng.random() * 6.28) for c in range((w - 8) // 12) for r in range((h - 14) // 16)]
STARS = [(rng.randrange(W), rng.randrange(0, 150), rng.random() * 6.28) for _ in range(45)]


def font(path, size):
    return ImageFont.truetype(path, size * S)


F_TITLE, F_TAG, F_SMALL = font(BOLD, 54), font(REG, 15), font(BOLD, 12)


def sc(*pts):
    return [v * S for v in pts]


def ease(t):
    return t * t * (3 - 2 * t)


def clamp01(v):
    return max(0.0, min(1.0, v))


def flame(d, cx, base, size, t):
    """Flickering flame made of stacked teardrops."""
    if size <= 0.02:
        return
    for k, (col, sw, sh) in enumerate([((255, 90, 40), 1.0, 1.0), ((255, 160, 40), 0.68, 0.78), ((255, 230, 120), 0.36, 0.5)]):
        wob = math.sin(t * 25 + k * 1.7) * 3
        w, h = 22 * sw * size, 46 * sh * size * (1 + 0.12 * math.sin(t * 31 + k))
        pts = [(cx - w, base), (cx - w * 0.9 + wob, base - h * 0.45), (cx + wob * 1.5, base - h),
               (cx + w * 0.9 + wob, base - h * 0.45), (cx + w, base)]
        d.polygon(sc(*[c for p in pts for c in p]), fill=col)
        d.ellipse(sc(cx - w, base - w, cx + w, base + w * 0.6), fill=col)


def vehicle(d, x, kind, t, facing=1):
    """Fire engine or patrol car; x is the centre, drawn pointing right when facing=1."""
    body, stripe = ((214, 52, 44), (250, 250, 250)) if kind == "fire" else ((240, 244, 250), (40, 90, 200))
    wide = 74 if kind == "fire" else 56
    y = ROAD_Y + 4
    x0, x1 = x - wide / 2, x + wide / 2
    d.rounded_rectangle(sc(x0, y - 24, x1, y), radius=4 * S, fill=body)
    cab_x = (x1 - 26, x1 - 2) if facing == 1 else (x0 + 2, x0 + 26)
    d.rectangle(sc(cab_x[0], y - 34, cab_x[1], y - 24), fill=body)
    d.rectangle(sc(cab_x[0] + 4, y - 31, cab_x[1] - 4, y - 25), fill=(120, 200, 240))
    d.rectangle(sc(x0 + 2, y - 11, x1 - 2, y - 8), fill=stripe)
    if kind == "fire":  # ladder
        d.rectangle(sc(x0 + 6, y - 29, x0 + 38, y - 26), fill=(200, 205, 215))
    flash = int(t * 14) % 2 == 0
    lamp = [(255, 60, 60), (70, 130, 255)] if kind == "police" else [(255, 70, 60), (255, 200, 60)]
    lx = (x0 + x1) / 2
    d.rectangle(sc(lx - 8, y - 38, lx - 1, y - 34), fill=lamp[0] if flash else (60, 30, 30))
    d.rectangle(sc(lx + 1, y - 38, lx + 8, y - 34), fill=lamp[1] if not flash else (30, 40, 70))
    col = lamp[0] if flash else lamp[1]  # glow
    for r, a in ((26, 40), (16, 70)):
        glow = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse(sc(lx - r, y - 36 - r, lx + r, y - 36 + r), fill=col + (a,))
        d._image.paste(glow, (0, 0), glow)
    for wx in (x0 + 14, x1 - 14):
        d.ellipse(sc(wx - 7, y - 7, wx + 7, y + 7), fill=(24, 24, 30))
        d.ellipse(sc(wx - 3, y - 3, wx + 3, y + 3), fill=(150, 155, 170))


def frame(i):
    t = i / FRAMES
    img = Image.new("RGB", (W * S, H * S))
    d = ImageDraw.Draw(img)
    for row in range(H * S):  # sky gradient
        k = row / (H * S)
        d.line([(0, row), (W * S, row)], fill=tuple(int(a + (b - a) * k) for a, b in zip(BG_TOP, BG_BOT)))
    for sx, sy, ph in STARS:
        a = 0.5 + 0.5 * math.sin(t * 6.28 * 2 + ph)
        c = int(70 + 150 * a)
        d.ellipse(sc(sx - 1, sy - 1, sx + 1, sy + 1), fill=(c, c, min(255, c + 25)))

    # fire timeline: burning at t=0, put out 0.34-0.62, reignites 0.86-1.0 so the loop is seamless
    fire = 1.0
    if 0.34 <= t < 0.62:
        fire = 1 - ease((t - 0.34) / 0.28)
    elif 0.62 <= t < 0.86:
        fire = 0.0
    elif t >= 0.86:
        fire = ease((t - 0.86) / 0.14)

    for bx, bw, bh, col in BUILDINGS + [FIRE_BLDG]:
        d.rectangle(sc(bx, ROAD_Y - bh, bx + bw, ROAD_Y), fill=col)
        burning = bx == FIRE_BLDG[0]
        for wx, wy, ph in WINDOWS[bx]:
            lit = math.sin(t * 6.28 * 1 + ph * 3) > -0.2
            c = (255, int(120 + 60 * fire), 60) if burning and fire > 0.15 and math.sin(t * 40 + ph * 9) > -0.3 else \
                ((255, 214, 120) if lit else (44, 56, 92))
            d.rectangle(sc(wx, wy, wx + 6, wy + 8), fill=c)

    # ground
    d.rectangle(sc(0, ROAD_Y, W, H), fill=(34, 38, 56))
    d.rectangle(sc(0, ROAD_Y, W, ROAD_Y + 3), fill=(70, 78, 108))
    for k in range(-1, W // 40 + 2):
        dx = (k * 40 - t * 40) % (W + 40) - 20
        d.rectangle(sc(dx, ROAD_Y + 26, dx + 20, ROAD_Y + 29), fill=(120, 126, 150))

    # flames sit on the burning building's roof
    fx, fb = FIRE_BLDG[0] + FIRE_BLDG[1] / 2, ROAD_Y - FIRE_BLDG[2] + 6
    flame(d, fx - 22, fb, fire * 0.9, t)
    flame(d, fx + 8, fb, fire * 1.15, t + 0.3)
    flame(d, fx + 34, fb, fire * 0.7, t + 0.6)
    if 0.0 < fire < 0.4 or 0.34 <= t < 0.7:  # smoke
        for k in range(5):
            r = 6 + k * 3 + (t * 30) % 6
            cy = fb - 24 - k * 16 - (t * 60) % 12
            cxx = fx + 6 + math.sin(t * 8 + k) * 5 + k * 3
            sm = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
            ImageDraw.Draw(sm).ellipse(sc(cxx - r, cy - r, cxx + r, cy + r), fill=(150, 156, 175, max(0, 90 - k * 16)))
            img.paste(sm, (0, 0), sm)

    # fire engine: dispatched at t=0, arrives ~0.28, sprays, leaves ~0.66
    stop = FIRE_BLDG[0] + 28
    if t < 0.28:
        ex = -60 + (stop + 60) * ease(t / 0.28)
    elif t < 0.66:
        ex = stop
    else:
        ex = stop + (W + 80 - stop) * ease((t - 0.66) / 0.34)
    # patrol car crosses the other way
    px = W + 60 - (W + 120) * clamp01((t - 0.05) / 0.9)
    vehicle(d, px, "police", t, facing=-1)
    vehicle(d, ex, "fire", t, facing=1)

    # water arc
    if 0.28 <= t < 0.62:
        a = (ex - 20, ROAD_Y - 30)
        b = (fx + 6, fb - 14)
        for k in range(14):
            u = (k / 14 + t * 6) % 1.0
            xx = a[0] + (b[0] - a[0]) * u
            yy = a[1] + (b[1] - a[1]) * u - math.sin(u * math.pi) * 46
            d.ellipse(sc(xx - 2.5, yy - 2.5, xx + 2.5, yy + 2.5), fill=(120, 190, 255))

    # dispatch chip while the engine is en route
    if 0.02 <= t < 0.3:
        chip = "DISPATCH  Engine 1 -> Substation"
        tw = d.textlength(chip, font=F_SMALL) / S
        cx0 = 40
        d.rounded_rectangle(sc(cx0, 112, cx0 + tw + 20, 136), radius=6 * S, fill=(12, 20, 40), outline=CYAN, width=S)
        d.text(sc(cx0 + 10, 117), chip, font=F_SMALL, fill=CYAN)
    elif 0.3 <= t < 0.62:
        chip = "RESPONDING  ...  fire 1/1"
        tw = d.textlength(chip, font=F_SMALL) / S
        cx0 = 40
        d.rounded_rectangle(sc(cx0, 112, cx0 + tw + 20, 136), radius=6 * S, fill=(12, 20, 40), outline=(255, 180, 60), width=S)
        d.text(sc(cx0 + 10, 117), chip, font=F_SMALL, fill=(255, 180, 60))
    elif 0.62 <= t < 0.84:
        chip = "RESOLVED   city health 100%"
        tw = d.textlength(chip, font=F_SMALL) / S
        cx0 = 40
        d.rounded_rectangle(sc(cx0, 112, cx0 + tw + 20, 136), radius=6 * S, fill=(12, 20, 40), outline=(100, 220, 160), width=S)
        d.text(sc(cx0 + 10, 117), chip, font=F_SMALL, fill=(100, 220, 160))

    # title with a typed-in feel + blinking cursor
    text_a, text_b = "AGENT", "CITY"
    shown = int(clamp01(t / 0.2) * 10)
    full = text_a + " " + text_b
    bob = math.sin(t * 6.28) * 2
    title_w = d.textlength(full, font=F_TITLE) / S
    tx, ty = (W - title_w) / 2 - 8, 12 + bob
    d.text(sc(tx + 3, ty + 3), full[:shown], font=F_TITLE, fill=(0, 0, 0))
    wa = d.textlength(text_a + " ", font=F_TITLE) / S
    d.text(sc(tx, ty), text_a[:shown], font=F_TITLE, fill=WHITE)
    if shown > 6:
        d.text(sc(tx + wa, ty), text_b[: shown - 6], font=F_TITLE, fill=CYAN)
    cw = d.textlength(full[:shown], font=F_TITLE) / S
    if int(t * 6.28 * 2.5) % 2 == 0 or shown < 10:
        d.rectangle(sc(tx + cw + 4, ty + 8, tx + cw + 18, ty + 62), fill=CYAN)
    tag = "an AI dispatcher for a tiny city"
    d.text(sc((W - d.textlength(tag, font=F_TAG) / S) / 2, ty + 74 - bob), tag, font=F_TAG, fill=DIM)

    return img.resize((W, H), Image.LANCZOS)


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [frame(i) for i in range(FRAMES)]
    sample = frames[:: FRAMES // 8]  # one shared palette drawn from the whole animation
    strip = Image.new("RGB", (W, H * len(sample)))
    for k, f in enumerate(sample):
        strip.paste(f, (0, k * H))
    pal = strip.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=FRAME_MS, loop=0, optimize=True, disposal=1)
    print(f"{OUT.name}: {FRAMES} frames, {OUT.stat().st_size / 1e3:.0f} KB")
