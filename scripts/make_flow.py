"""Draw the animated "how the agent works" diagram (docs/assets/flow.gif) with Pillow.

    uv run python scripts/make_flow.py
"""

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent.parent / "docs" / "assets" / "flow.gif"
W, H, S = 800, 330, 2
FRAMES, FRAME_MS = 84, 70
BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf"
REG = "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf"
BG, PANEL, LINE = (10, 16, 34), (18, 28, 56), (52, 66, 106)
WHITE, DIM, CYAN = (236, 240, 248), (138, 155, 181), (76, 201, 240)

STEPS = [  # label, colour, caption title, caption body
    ("INCIDENT", (255, 120, 70), "1  An incident appears", ["You (or chaos) start a fire, theft or flood", "at one of six sites, with a severity."]),
    ("SENSE", (76, 201, 240), "2  The agent senses", ["A fresh city snapshot: every incident, units needed", "vs assigned, which units are free or busy."]),
    ("THINK", (190, 140, 255), "3  The agent thinks", ["Ranks by severity, then fire > flood > theft, then", "who has waited longest. Serves in that order."]),
    ("ACT", (255, 200, 60), "4  The agent acts", ["One tool call: dispatch_plan(orders), with a short", "reason for every order. It moves nothing itself."]),
    ("GUARD", (100, 220, 160), "5  The dispatcher checks", ["Right kind of unit, never more than an incident", "needs. Bad orders are refused, not executed."]),
    ("ROLL", (255, 120, 120), "6  Units roll", ["A* routes, flashing lights, crews on scene. The", "incident shrinks, units come home, and we go again."]),
]
N = len(STEPS)
NW, NH, GAP = 100, 78, 24
X0 = (W - (N * NW + (N - 1) * GAP)) / 2
NY = 96
CENTERS = [(X0 + i * (NW + GAP) + NW / 2, NY + NH / 2) for i in range(N)]
LOOP_Y = NY + NH + 22


def font(path, size):
    return ImageFont.truetype(path, size * S)


F_LABEL, F_CAP_T, F_CAP, F_TITLE, F_SM = font(BOLD, 13), font(BOLD, 18), font(REG, 14), font(BOLD, 22), font(REG, 11)


def sc(*v):
    return [x * S for x in v]


def path_point(u):
    """Packet position for u in [0, N): node i -> node i+1 along the row; the last segment returns along the loop."""
    i = int(u) % N
    f = u - int(u)
    f = f * f * (3 - 2 * f)
    if i < N - 1:
        (ax, ay), (bx, by) = CENTERS[i], CENTERS[i + 1]
        return ax + (bx - ax) * f, ay + (by - ay) * f
    ax, bx = CENTERS[N - 1][0], CENTERS[0][0]  # return trip: down, left along the loop, up
    pts = [(ax, NY + NH), (ax, LOOP_Y), (bx, LOOP_Y), (bx, NY + NH)]
    seg = [math.dist(pts[k], pts[k + 1]) for k in range(3)]
    d = f * sum(seg)
    for k in range(3):
        if d <= seg[k]:
            r = d / seg[k]
            return pts[k][0] + (pts[k + 1][0] - pts[k][0]) * r, pts[k][1] + (pts[k + 1][1] - pts[k][1]) * r
        d -= seg[k]
    return pts[3]


def icon(d, k, cx, cy, col, t):
    if k == 0:  # flame
        w = 9 + math.sin(t * 30) * 1.2
        d.polygon(sc(cx - w, cy + 10, cx - w * 0.6, cy - 2, cx, cy - 14 - math.sin(t * 25) * 2, cx + w * 0.6, cy - 2, cx + w, cy + 10), fill=col)
        d.ellipse(sc(cx - 4, cy + 1, cx + 4, cy + 10), fill=(255, 230, 120))
    elif k == 1:  # eye
        d.ellipse(sc(cx - 14, cy - 8, cx + 14, cy + 8), outline=col, width=2 * S)
        dx = math.sin(t * 12) * 3
        d.ellipse(sc(cx - 5 + dx, cy - 5, cx + 5 + dx, cy + 5), fill=col)
    elif k == 2:  # spark / brain
        for a in range(8):
            ang = a * math.pi / 4 + t * 3
            r1, r2 = 5, 13 + 3 * math.sin(t * 14 + a)
            d.line(sc(cx + math.cos(ang) * r1, cy + math.sin(ang) * r1, cx + math.cos(ang) * r2, cy + math.sin(ang) * r2), fill=col, width=2 * S)
        d.ellipse(sc(cx - 4, cy - 4, cx + 4, cy + 4), fill=col)
    elif k == 3:  # bolt
        d.polygon(sc(cx + 2, cy - 14, cx - 8, cy + 2, cx, cy + 2, cx - 3, cy + 14, cx + 9, cy - 4, cx + 1, cy - 4), fill=col)
    elif k == 4:  # shield with tick
        d.polygon(sc(cx - 11, cy - 11, cx + 11, cy - 11, cx + 11, cy + 2, cx, cy + 14, cx - 11, cy + 2), outline=col, width=2 * S)
        d.line(sc(cx - 5, cy, cx - 1, cy + 5, cx + 6, cy - 5), fill=col, width=2 * S)
    else:  # car
        d.rounded_rectangle(sc(cx - 14, cy - 3, cx + 14, cy + 8), radius=3 * S, fill=col)
        d.rectangle(sc(cx - 7, cy - 10, cx + 7, cy - 3), fill=col)
        for wx in (cx - 8, cx + 8):
            d.ellipse(sc(wx - 3.5, cy + 5, wx + 3.5, cy + 12), fill=(24, 24, 30))
        if int(t * 14) % 2 == 0:
            d.ellipse(sc(cx - 3, cy - 14, cx + 3, cy - 10), fill=(255, 255, 255))


def dashed(d, p, q, col, phase=0.0):
    length = math.dist(p, q)
    n = int(length // 8)
    for k in range(n):
        a, b = (k + phase) / n, (k + phase + 0.5) / n
        if b > 1:
            continue
        d.line(sc(p[0] + (q[0] - p[0]) * a, p[1] + (q[1] - p[1]) * a, p[0] + (q[0] - p[0]) * b, p[1] + (q[1] - p[1]) * b), fill=col, width=S)


def frame(i):
    t = i / FRAMES
    u = t * N  # which step is "current"
    cur = int(u) % N
    img = Image.new("RGB", (W * S, H * S), BG)
    d = ImageDraw.Draw(img)
    for gx in range(0, W, 24):  # faint grid, like a city map
        d.line(sc(gx, 0, gx, H), fill=(14, 22, 44), width=1)
    for gy in range(0, H, 24):
        d.line(sc(0, gy, W, gy), fill=(14, 22, 44), width=1)

    title = "how the agent runs the city"
    d.text(sc((W - d.textlength(title, font=F_TITLE) / S) / 2, 14), title, font=F_TITLE, fill=WHITE)

    # connectors and the return loop
    for k in range(N - 1):
        a, b = CENTERS[k][0] + NW / 2, CENTERS[k + 1][0] - NW / 2
        d.line(sc(a, NY + NH / 2, b, NY + NH / 2), fill=LINE, width=2 * S)
        d.polygon(sc(b, NY + NH / 2, b - 6, NY + NH / 2 - 4, b - 6, NY + NH / 2 + 4), fill=LINE)
    lx0, lx1 = CENTERS[N - 1][0], CENTERS[0][0]
    d.line(sc(lx0, NY + NH, lx0, LOOP_Y, lx1, LOOP_Y, lx1, NY + NH + 3), fill=LINE, width=2 * S)
    d.polygon(sc(lx1, NY + NH + 2, lx1 - 4, NY + NH + 9, lx1 + 4, NY + NH + 9), fill=LINE)
    lab = "repeat whenever the situation changes"
    d.text(sc((lx0 + lx1) / 2 - d.textlength(lab, font=F_SM) / S / 2, LOOP_Y + 5), lab, font=F_SM, fill=DIM)

    # rule-planner fallback hanging off THINK
    tx, ty = CENTERS[2]
    fb = (tx - 55, 52, tx + 55, 80)
    dashed(d, (tx, NY), (tx, fb[3]), (90, 98, 130), phase=(t * 6) % 1)
    d.rounded_rectangle(sc(*fb), radius=6 * S, outline=(90, 98, 130), width=S, fill=BG)
    ft = "rule planner"
    d.text(sc(tx - d.textlength(ft, font=F_SM) / S / 2, 60), ft, font=F_SM, fill=DIM)
    d.text(sc(tx + 62, 56), "backup if the model fails", font=F_SM, fill=(90, 98, 130))

    # nodes
    for k, (label, col, _, _) in enumerate(STEPS):
        x = CENTERS[k][0] - NW / 2
        dist = min(abs(u - k), abs(u - k - N), abs(u - k + N))
        glow = clamp(1 - dist / 0.9)
        if glow > 0:
            g = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
            ImageDraw.Draw(g).rounded_rectangle(sc(x - 6, NY - 6, x + NW + 6, NY + NH + 6), radius=14 * S, fill=col + (int(70 * glow),))
            img.paste(g, (0, 0), g)
        fill = tuple(int(a + (b - a) * 0.22 * glow) for a, b in zip(PANEL, col))
        d.rounded_rectangle(sc(x, NY, x + NW, NY + NH), radius=10 * S, fill=fill, outline=col if glow > 0.2 else LINE, width=2 * S)
        icon(d, k, CENTERS[k][0], NY + 29, col if glow > 0.2 else DIM, t)
        d.text(sc(CENTERS[k][0] - d.textlength(label, font=F_LABEL) / S / 2, NY + 55), label, font=F_LABEL, fill=WHITE if glow > 0.2 else DIM)

    # travelling packet
    px, py = path_point(u)
    col = STEPS[cur][1]
    for r, a in ((13, 40), (8, 90)):
        g = Image.new("RGBA", (W * S, H * S), (0, 0, 0, 0))
        ImageDraw.Draw(g).ellipse(sc(px - r, py - r, px + r, py + r), fill=col + (a,))
        img.paste(g, (0, 0), g)
    d.ellipse(sc(px - 4, py - 4, px + 4, py + 4), fill=WHITE)

    # caption panel
    _, col, ct, body = STEPS[cur]
    d.rounded_rectangle(sc(60, 252, W - 60, 316), radius=10 * S, fill=PANEL, outline=col, width=2 * S)
    d.rectangle(sc(60, 252, 66, 316), fill=col)
    d.text(sc(82, 259), ct, font=F_CAP_T, fill=col)
    f = u - int(u)
    chars = int(clamp(f / 0.55) * 1000)  # typewriter reveal
    for n, line in enumerate(body):
        shown = line[: max(0, chars)]
        chars -= len(line)
        d.text(sc(82, 283 + n * 17), shown, font=F_CAP, fill=(210, 218, 235))

    return img.resize((W, H), Image.LANCZOS)


def clamp(v):
    return max(0.0, min(1.0, v))


if __name__ == "__main__":
    OUT.parent.mkdir(parents=True, exist_ok=True)
    frames = [frame(i) for i in range(FRAMES)]
    sample = frames[:: FRAMES // 12]
    strip = Image.new("RGB", (W, H * len(sample)))
    for k, f in enumerate(sample):
        strip.paste(f, (0, k * H))
    pal = strip.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE)
    q = [f.quantize(palette=pal, dither=Image.Dither.NONE) for f in frames]
    q[0].save(OUT, save_all=True, append_images=q[1:], duration=FRAME_MS, loop=0, optimize=True, disposal=1)
    print(f"{OUT.name}: {FRAMES} frames, {OUT.stat().st_size / 1e3:.0f} KB")
