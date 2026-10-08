"""Render the README animations by driving the real Textual app headlessly.

    uv run python scripts/make_gifs.py

Uses the deterministic rule planner and a fake clock, so the output is reproducible and needs no LLM.
Writes docs/assets/hero.gif (a crisis unfolding) and docs/assets/tour.gif (wizard -> incident -> agent info).
"""

import asyncio
import io
import sys
import types
from pathlib import Path

import cairosvg
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src" / "agent_city"))

from tui import app as app_mod  # noqa: E402

SIZE = (130, 40)
OUT = ROOT / "docs" / "assets"


class Clock:
    t = 1000.0

    def __call__(self) -> float:
        return self.t


async def record(script, name: str, frame_ms: int = 100, scale: float = 0.62) -> None:
    clock = Clock()
    app_mod.time = types.SimpleNamespace(monotonic=clock)  # fake clock for the app only, not asyncio
    app = app_mod.AgentCityApp(planner="rules")
    frames: list[Image.Image] = []
    durations: list[int] = []

    async with app.run_test(size=SIZE) as pilot:
        async def grab(hold_ms: int = frame_ms) -> None:
            await pilot.pause()
            svg = app.export_screenshot()
            png = cairosvg.svg2png(bytestring=svg.encode(), scale=scale)
            frames.append(Image.open(io.BytesIO(png)).convert("RGB"))
            durations.append(hold_ms)

        async def run(sim_seconds: float, every: float = 0.5, speed: int = 4) -> None:
            """Advance the simulation, capturing a frame every `every` sim-seconds."""
            app.speed = float(speed)
            step = 0.1 / speed * speed  # real dt fed per tick (app caps dt at 0.1 then multiplies by speed)
            elapsed = 0.0
            since = 0.0
            while elapsed < sim_seconds:
                clock.t += step
                app.tick()
                elapsed += step * speed
                since += step * speed
                if since >= every:
                    since = 0.0
                    await grab()

        await script(app, pilot, grab, run)

    quant = [f.quantize(colors=48, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE) for f in frames]
    quant[0].save(OUT / name, save_all=True, append_images=quant[1:], duration=durations, loop=0, optimize=True, disposal=1)
    print(f"{name}: {len(frames)} frames, {(OUT / name).stat().st_size / 1e6:.1f} MB, {frames[0].size}")


async def hero(app, pilot, grab, run):
    await run(1.5)
    await pilot.press("x")  # crisis: five incidents at once
    await grab(600)
    await run(60, every=1.0)
    await grab(1500)


async def tour(app, pilot, grab, run):
    await run(1.5)
    await grab(800)
    await pilot.press("n")  # wizard: what / where / how severe
    await grab(900)
    for _ in range(3):
        await pilot.press("1")
        await grab(700)
    await run(25, every=0.6)
    await pilot.press("r")
    await run(10, every=0.6)
    await pilot.press("i")  # agent info screen
    await grab(2500)
    await pilot.press("escape")
    await run(20, every=1.0)
    await grab(1500)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    asyncio.run(record(hero, "hero.gif"))
    asyncio.run(record(tour, "tour.gif"))
