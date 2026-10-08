"""Top-down ASCII/Unicode map of the city. Pure function of simulation state -> rich Text."""

import math
import random

from rich.style import Style
from rich.text import Text

from entities.team import TeamState
from simulation.choreography import person_pose
from simulation.city import LINES
from simulation.incidents import IncidentStatus, IncidentType

HALF = 26.0                       # world half-extent shown (the city slab is +-26)
VOID = "#0e1626"
GRASS_BG, GRASS_FG = "#2a5236", "#3d7a4a"
ROAD_BG, ROAD_MARK = "#2b2d36", "#8a8466"
WALK_BG = "#5b5a62"
LOT = {"houses": "#4f7a45", "park": "#3f7d4a", "offices": "#6d6b70", "substation": "#6c6c66",
       "hospital": "#7d8189", "fire_station": "#5f5c58", "police_station": "#4f5568", "rescue_centre": "#5f5a50",
       "warehouse": "#66645e"}
DEPOT_STYLE = {"fire": ("#b4443a", " FIRE STATION "), "police": ("#2f4f9a", " POLICE "),
               "rescue": ("#d9822b", " RESCUE CENTRE ")}
EMERGENCY_LAMPS = {"fire": ("#ff3b30", "#ffd23f"), "police": ("#ff3b30", "#3d7bff"), "rescue": ("#ffb02e", "#f6f6f6")}
CREW_FG = {"firefighters": "#ffd23f", "officers": "#7fd4ff", "rescuers": "#ffa64d"}
FLAME = ["#ff3b1f", "#ff7a1a", "#ffb02e", "#ffe27a"]
SMOKE = ["#3a3a40", "#55555c", "#74747c", "#9a9aa2"]
WATER = ["#1d4f8f", "#2b6cb0", "#3d8fd0"]
TAG = {IncidentType.FIRE: ("▲", "#ff6b4a", "#f4b942"), IncidentType.THEFT: ("◆", "#4c86ff", "#e8e8f0"),
       IncidentType.FLOOD: ("≈", "#2bb3c0", "#9fe8ef")}
ARROWS = {0: "▲", 1: "▶", 2: "▼", 3: "◀"}

Cell = tuple  # (char, fg, bg, bold)


def _shade(color: str, f: float) -> str:
    """Scale a #rrggbb colour's brightness by f (<1 darker, >1 lighter)."""
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c * f))) for c in (r, g, b))


def _arrow(heading: float) -> str:
    return ARROWS[int(((heading % 360) + 45) // 90) % 4]


class MapView:
    def __init__(self, city):
        self.city = city
        self._static = None
        self._size = None
        self._geo = None
        self._styles: dict = {}
        self.vis: dict = {}               # incident id -> {"k": visual intensity, "smoke": smoke level}
        self.t = 0.0
        self.rng = random.Random(5)

    # ------------------------------------------------------------ geometry
    def _geometry(self, W, H):
        upr = max(2 * 2 * HALF / W, 2 * HALF / H)       # world units per row (cells are ~1:2)
        return upr / 2, upr

    def to_cell(self, x, z):
        upc, upr = self._geo
        W, H = self._size
        return int(W / 2 + x / upc), int(H / 2 - z / upr)

    def _center(self, col, row):
        upc, upr = self._geo
        W, H = self._size
        return (col + 0.5 - W / 2) * upc, (H / 2 - row - 0.5) * upr

    # ------------------------------------------------------------ static layer
    def _build_static(self, W, H):
        self._size, self._geo = (W, H), self._geometry(W, H)
        grid = [[self._ground_cell(*self._center(col, row), col, row) for col in range(W)] for row in range(H)]
        self._static = grid
        self._buildings(grid)

    def _ground_cell(self, x, z, col, row) -> Cell:
        upc, upr = self._geo
        if abs(x) > HALF or abs(z) > HALF:
            return (" ", VOID, VOID, False)
        on_h = any(abs(z - L) < 1.8 for L in LINES) and abs(x) <= 22.8
        on_v = any(abs(x - L) < 1.8 for L in LINES) and abs(z) <= 22.8
        if on_h or on_v:
            ch = " "
            if on_h and not on_v and any(abs(z - L) < upr / 2 for L in LINES) and col % 2 == 0:
                ch = "─"
            elif on_v and not on_h and any(abs(x - L) < upc for L in LINES) and row % 2 == 0:
                ch = "│"
            return (ch, ROAD_MARK, ROAD_BG, False)
        for (bx, bz), kind in self.city.block_kinds.items():
            if abs(x - bx) <= 5.2 and abs(z - bz) <= 5.2:
                if abs(x - bx) <= 4.2 and abs(z - bz) <= 4.2:
                    return (" ", "#ffffff", LOT[kind], False)
                return (" ", "#ffffff", WALK_BG, False)
        ch = "·" if (col * 7 + row * 13) % 5 == 0 else " "
        return (ch, GRASS_FG, GRASS_BG, False)

    def _paint(self, grid, x0, x1, z0, z1, ch, fg, bg, bold=False):
        c0, r1 = self.to_cell(x0, z0)
        c1, r0 = self.to_cell(x1, z1)
        for r in range(max(r0, 0), min(r1, self._size[1] - 1) + 1):
            for c in range(max(c0, 0), min(c1, self._size[0] - 1) + 1):
                old = grid[r][c]
                grid[r][c] = (ch if ch is not None else old[0], fg or old[1], bg or old[2], bold)

    def _sprite(self, grid, x, z, rows, bold=False):
        """Stamp a small hand-drawn sprite (rows of (char, fg, bg) cells) centred on a world position."""
        col, row = self.to_cell(x, z)
        col -= len(rows[0]) // 2
        row -= len(rows) // 2
        for dr, cells in enumerate(rows):
            for dc, (ch, fg, bg) in enumerate(cells):
                r, c = row + dr, col + dc
                if 0 <= r < self._size[1] and 0 <= c < self._size[0]:
                    grid[r][c] = (ch, fg, bg, bold)

    def _label(self, grid, x, z, text, fg, bg, bold=True):
        col, row = self.to_cell(x, z)
        col = max(0, min(self._size[0] - len(text), col - len(text) // 2))
        if not 0 <= row < self._size[1]:
            return
        for i, ch in enumerate(text):
            if 0 <= col + i < self._size[0]:
                grid[row][col + i] = (ch, fg, bg, bold)

    def _buildings(self, grid):
        for depot in self.city.depots.values():
            color, label = DEPOT_STYLE[depot.service]
            cx, cz = depot.pos
            door_z = depot.bays[0].door_z
            self._paint(grid, cx - 4.2, cx + 4.2, cz + 0.2, cz + 4.2, " ", "#ffffff", color)
            self._paint(grid, cx - 4.2, cx + 4.2, door_z, cz + 0.2, " ", "#ffffff", "#4a4d54")
            self._label(grid, cx, cz + 2.4, label, "#ffffff", color)
            roof = _shade(color, 0.7)
            self._paint(grid, cx - 4.2, cx + 4.2, cz + 3.5, cz + 4.2, "▀", _shade(color, 1.25), roof)   # roof edge
            lamp = ("#ff4d4d", "#4d8bff") if depot.service != "rescue" else ("#ffb02e", "#ffb02e")
            self._put(grid, cx - 4.0, cz + 4.0, "●", lamp[0], roof, True)                                    # roof beacons
            self._put(grid, cx + 4.0, cz + 4.0, "●", lamp[1], roof, True)
        hx, hz = self.city.buildings["hospital"].pos
        self._paint(grid, hx - 3.8, hx + 3.8, hz - 1.7, hz + 3.0, " ", "#ffffff", "#eef1f4")
        self._paint(grid, hx - 0.2, hx + 0.2, hz - 0.6, hz + 1.9, "┃", "#d62828", "#eef1f4", True)
        self._label(grid, hx, hz - 0.6, "  HOSPITAL  ", "#1b2a3a", "#eef1f4")
        self._paint(grid, hx - 3.8, hx + 3.8, hz + 2.6, hz + 3.0, "▀", "#b8c0ca", "#eef1f4")             # roof edge
        self._sprite(grid, hx + 2.6, hz + 1.2, [[("(", "#ffd23f", "#3c4a5a"), ("H", "#ffd23f", "#3c4a5a"),
                                                  (")", "#ffd23f", "#3c4a5a")]], True)                   # helipad
        self._sprite(grid, hx - 2.8, hz + 1.2, [[("▪", "#7fb7e6", "#eef1f4"), ("▪", "#7fb7e6", "#eef1f4"),
                                                  ("▪", "#7fb7e6", "#eef1f4")]])                         # windows
        sx, sz = self.city.buildings["substation"].pos
        self._paint(grid, sx - 4.0, sx + 4.0, sz - 4.0, sz + 4.0, None, "#666b73", "#6c6c66")
        for dx in (-2.4, 0, 2.4):
            self._paint(grid, sx + dx - 0.8, sx + dx + 0.8, sz - 0.4, sz + 1.2, "▓", "#5f7a94", "#4d6580")
        self._paint(grid, sx - 3.8, sx + 3.8, sz + 2.2, sz + 2.5, "┄", "#9aa0a8", "#6c6c66")             # fence
        self._paint(grid, sx - 3.8, sx + 3.8, sz - 3.7, sz - 3.4, "┄", "#9aa0a8", "#6c6c66")
        self._paint(grid, sx - 3.8, sx + 3.8, sz + 1.5, sz + 1.9, "═", "#d4a72c", "#6c6c66")             # live wires
        for dx in (-2.4, 0, 2.4):
            self._put(grid, sx + dx, sz + 1.7, "╤", "#d4a72c", "#6c6c66", True)                         # insulators
        self._sprite(grid, sx + 3.0, sz - 1.4, [[("ϟ", "#ffd23f", "#6c6c66")]], True)                    # danger sign
        self._label(grid, sx, sz - 2.6, " SUBSTATION ", "#101820", "#c9c3b4")
        wb = self.city.buildings["warehouse"]
        x0, x1, z0, z1 = wb.rect
        self._paint(grid, x0, x1, z0, z1, " ", "#ffffff", "#8d887a")
        zc = z0
        while zc < z1:                                    # corrugated roof: a ridge line on every other row
            self._paint(grid, x0, x1, zc, zc + 0.2, "═", "#a8a291", "#8d887a")
            zc += 1.6
        dock_w = (x1 - x0) / 5
        for k in range(4):                                # loading docks along the front wall
            dx = x0 + dock_w * (k + 0.6)
            self._paint(grid, dx, dx + dock_w * 0.7, z0, z0 + 0.5, "▮", "#2f5f94", "#6f6a5e", True)
        self._label(grid, wb.pos[0], wb.pos[1] - 0.6, " WAREHOUSE ", "#1b1b1b", "#d9d2bf")
        rng = random.Random(9)
        for (bx, bz), kind in self.city.block_kinds.items():
            for sx_ in (-1, 1):
                for sz_ in (-1, 1):
                    px, pz = bx + sx_ * 2.1, bz + sz_ * 2.1
                    if kind == "houses":                           # pitched roof over a wall with windows and a door
                        wall = rng.choice(["#f2d0a4", "#e8b4b8", "#b8d8d8", "#f4e285", "#cdb4db"])
                        roof = rng.choice(["#a8483a", "#8a5a44", "#5f6f8f", "#7a4f6d"])
                        lot = LOT["houses"]
                        win = "#5a86b3" if rng.random() < 0.6 else "#ffd966"       # some windows are lit
                        self._sprite(grid, px, pz, [
                            [("◢", roof, lot), ("█", roof, roof), ("◣", roof, lot)],
                            [("▪", win, wall), ("▮", "#6b4226", wall), ("▪", win, wall)]], True)
                    elif kind == "offices":                        # tower: roof edge over a grid of windows
                        wall = rng.choice(["#2f3d5a", "#34435f", "#2c3a52"])
                        roof = _shade(wall, 1.6)
                        rows = [[("▄", roof, wall)] * 4]
                        for _ in range(2):
                            rows.append([("▪", "#ffd966" if rng.random() < 0.45 else "#56688a", wall) for _ in range(4)])
                        self._sprite(grid, px, pz, rows)
            if kind == "park":
                self._paint(grid, bx + 0.6, bx + 3.9, bz - 3.0, bz - 0.7, "≈", "#bfe9ff", "#3d8fd0")
                for (dx, dz) in [(-3, -3), (-3, 3), (3, 3), (-1.9, 1.7), (1.9, 3.2), (-3.3, 0.2), (0.2, -3.4), (-2.2, -1.9)]:
                    self._paint(grid, bx + dx - 0.3, bx + dx + 0.3, bz + dz - 0.3, bz + dz + 0.3, "♣", "#1f6a2e", "#3f7d4a", True)
            if kind == "park":
                for (dx, dz), fc in zip([(-3.4, -1.2), (-0.6, -2.4), (1.0, 3.3), (3.4, 1.4), (-1.0, 0.9)],
                                        ["#ff8fab", "#ffd166", "#f4a6ff", "#ff8fab", "#ffd166"]):
                    self._put(grid, bx + dx, bz + dz, "✿", fc, "#3f7d4a", True)
                self._paint(grid, bx - 0.4, bx + 1.4, bz + 1.4, bz + 1.7, "═", "#8a6a43", "#3f7d4a", True)   # bench
            if kind == "offices":
                self._label(grid, bx, bz, " OFFICES ", "#1b2433", "#b0b8c4")
            if kind == "park":
                self._label(grid, bx - 1.5, bz + 3.4, " PARK ", "#10351a", "#8cc47a")
            if kind == "houses":
                self._label(grid, bx, bz - 3.6, " HOUSES ", "#33302b", "#f6efe3")

    # ------------------------------------------------------------ dynamic layer
    def _put(self, grid, x, z, ch, fg, bg=None, bold=False):
        c, r = self.to_cell(x, z)
        if 0 <= r < self._size[1] and 0 <= c < self._size[0]:
            old = grid[r][c]
            grid[r][c] = (ch, fg, bg or old[2], bold)

    def update(self, dt):
        self.t += dt
        live = set()
        for inc in self.city.world.incidents.values():
            live.add(inc.id)
            v = self.vis.setdefault(inc.id, {"k": 0.0, "smoke": 0.0})
            target = inc.intensity if inc.is_open else 0.0
            rate = 1.5 if target > v["k"] else 3.0
            v["k"] += max(-rate * dt, min(rate * dt, target - v["k"]))
            s_rate = 0.8 if target > v["smoke"] else 0.16
            v["smoke"] += max(-s_rate * dt, min(s_rate * dt, target - v["smoke"]))
        for iid in list(self.vis):
            if iid not in live:
                del self.vis[iid]

    def render(self, W, H) -> Text:
        if (W, H) != self._size or self._static is None:
            self._build_static(W, H)
        grid = [row[:] for row in self._static]
        self._draw_depot_doors(grid)
        for inc in self.city.world.incidents.values():
            v = self.vis.get(inc.id)
            if not v:
                continue
            rect = self.city.buildings[inc.building_id].rect
            if inc.type == IncidentType.FIRE:
                self._draw_fire(grid, rect, v)
            elif inc.type == IncidentType.FLOOD:
                self._draw_flood(grid, rect, v)
            else:
                self._draw_theft(grid, rect, v, inc)
        self._draw_vehicles(grid)
        self._draw_crews(grid)
        self._draw_markers(grid)
        return self._to_text(grid)

    def _draw_depot_doors(self, grid):
        for depot in self.city.depots.values():
            for bay in depot.bays:
                ch = "▀" if bay.door_progress < 0.5 else " "
                self._paint(grid, bay.x - 1.1, bay.x + 1.1, bay.door_z - 0.35, bay.door_z + 0.35, ch, "#e8e4da", "#4a4d54", True)

    def _rect_cells(self, rect, grow=0):
        x0, x1, z0, z1 = rect
        c0, r1 = self.to_cell(x0, z0)
        c1, r0 = self.to_cell(x1, z1)
        for r in range(max(r0 - grow, 0), min(r1 + grow, self._size[1] - 1) + 1):
            for c in range(max(c0 - grow, 0), min(c1 + grow, self._size[0] - 1) + 1):
                yield r, c

    def _draw_fire(self, grid, rect, v):
        rng, k = self.rng, v["k"]
        x0, x1, z0, z1 = rect
        if k > 0.03:
            for r, c in self._rect_cells(rect):
                if rng.random() < 0.75 * k:
                    grid[r][c] = (rng.choice("▲^*♦▴"), FLAME[rng.randint(0, 3)], "#3a1410", True)
            for _ in range(int(14 * k)):                       # tongues above the roof
                self._put(grid, rng.uniform(x0, x1), z1 + rng.uniform(0, 3.2 * k), rng.choice("^▲'"),
                          FLAME[rng.randint(0, 2)], None, True)
        if v["smoke"] > 0.03:
            n = int(40 * v["smoke"])
            for i in range(n):
                p = (self.t * 0.35 + i / max(n, 1)) % 1.0
                x = rng.uniform(x0, x1) + p * 7
                z = z1 + 1 + p * 9
                if rng.random() < 0.8 * v["smoke"] + 0.1:
                    self._put(grid, x, z, "░▒"[rng.randint(0, 1)], SMOKE[min(3, int(p * 4))])

    def _draw_flood(self, grid, rect, v):
        rng, k = self.rng, v["k"]
        if k <= 0.03:
            return
        for r, c in self._rect_cells(rect, grow=1 if k > 0.6 else 0):
            if rng.random() < 0.55 + 0.4 * k:
                grid[r][c] = ("≈~"[rng.randint(0, 1)], "#9fd8ff", WATER[rng.randint(0, 2)], False)
        x0, x1, z0, z1 = rect
        for _ in range(int(24 * k)):                           # heavy rain over the site
            self._put(grid, rng.uniform(x0 - 2, x1 + 2), z1 + rng.uniform(0, 4), rng.choice("╲/'"), "#7fb6ff")

    def _draw_theft(self, grid, rect, v, inc):
        k = v["k"]
        if k <= 0.03:
            return
        x0, x1, z0, z1 = rect
        flash = int(self.t * 4) % 2 == 0
        for (x, z) in ((x0, z0), (x1, z0), (x0, z1), (x1, z1)):
            self._put(grid, x, z, "!", "#ffffff", "#d62828" if flash else "#2a6fdb", True)
        if k > 0.25:                                           # the thief paces along the front until caught
            span = (x1 - x0) / 2 - 0.5
            x = (x0 + x1) / 2 + span * math.sin(self.t * 1.3)
            self._put(grid, x, z0 - 0.6, "☻", "#ff4fd8", None, True)

    def _stamp_vehicle(self, grid, x, z, heading, cells):
        """Draw a vehicle as a short strip of cells (listed rear -> front), lengthwise along its heading."""
        c, r = self.to_cell(x, z)
        h = int(((heading % 360) + 45) // 90) % 4          # 0 north, 1 east, 2 south, 3 west
        n = len(cells)
        if h in (1, 3):                                    # moving along a road running east-west
            seq = cells if h == 1 else cells[::-1]
            n_cols = n
            for i, (ch, fg, bg) in enumerate(seq):
                self._set(grid, r, c - n_cols // 2 + i, ch, fg, bg)
        else:                                              # north-south: two rows is about as long as a car
            seq = [cells[0], cells[-1]] if n > 2 else cells
            seq = seq[::-1] if h == 0 else seq              # facing north the front is the top row
            for i, (ch, fg, bg) in enumerate(seq):
                self._set(grid, r - len(seq) // 2 + i, c, ch, fg, bg)

    def _set(self, grid, r, c, ch, fg, bg):
        if 0 <= r < self._size[1] and 0 <= c < self._size[0]:
            grid[r][c] = (ch, fg, bg, True)

    def _civilian_cells(self, v):
        body, glass = v.color, "#cfe8ff"
        if v.kind == "bus":
            return [("▪", glass, body)] * 3 + [("▌", glass, _shade(body, 0.8))]
        if v.kind == "van":
            return [("▬", _shade(body, 0.7), body), (" ", body, body), ("▪", glass, _shade(body, 0.8))]
        return [(" ", body, body), ("▪", glass, _shade(body, 0.8))]

    def _emergency_cells(self, svc, veh, flash):
        lamp = EMERGENCY_LAMPS[svc][0 if flash else 1] if veh.lights_on else "#555566"
        digit = veh.id[-1]
        if svc == "fire":       # long red engine, white ladder along the roof, cab at the front
            body = "#d62828"
            return [(digit, "#ffffff", body), ("═", "#f5f5f5", body), ("═", "#f5f5f5", body),
                    ("╫", "#ffffff", lamp if veh.lights_on else "#8f1d1d")]
        if svc == "police":     # white car with a blue stripe and a roof light bar
            return [(digit, "#2a6fdb", "#f2f4f8"), ("●", lamp, "#f2f4f8"),
                    ("▪", "#5aa0e0", "#2a6fdb" if not veh.lights_on else lamp)]
        body = "#e8892b"        # rescue: orange truck with a white cross on the box
        return [(digit, "#ffffff", body), ("✚", "#ffffff", "#c26a14"),
                ("▪", "#ffffff", lamp if veh.lights_on else "#8f5a1c")]

    def _draw_vehicles(self, grid):
        for v in self.city.traffic:
            x, z = v.render_pos
            self._stamp_vehicle(grid, x, z, v.heading, self._civilian_cells(v))
        flash = int(self.t * 5) % 2 == 0
        for svc, depot in self.city.depots.items():
            for veh in depot.vehicles:
                x, z = veh.render_pos
                self._stamp_vehicle(grid, x, z, veh.heading, self._emergency_cells(svc, veh, flash))

    def _draw_crews(self, grid):
        c = self.city
        for depot in c.depots.values():
            for crew in depot.crews:
                if crew.state not in (TeamState.BOARDING, TeamState.DEPLOYING, TeamState.DEPLOYED, TeamState.STOWING):
                    continue
                veh = next((v for v in depot.vehicles if v.id == crew.vehicle_id), None)
                mission = next((m for m in c.world.missions.values() if m.team is crew and m.is_active), None)
                inc = mission.incident if mission else None
                nozzles = []
                for k in range(crew.size):
                    pose = person_pose(crew, k, veh, inc)
                    if pose is None:
                        continue
                    (x, z), _, hop = pose
                    self._put(grid, x, z, "☻" if hop else "☺", CREW_FG.get(crew.role, "#ffffff"), None, True)
                    if crew.state == TeamState.DEPLOYED and k in (0, 1):
                        nozzles.append((x, z))
                if (crew.state == TeamState.DEPLOYED and inc is not None and inc.intensity > 0
                        and inc.type in (IncidentType.FIRE, IncidentType.FLOOD)):
                    b = c.buildings[inc.building_id]
                    fx, fz = b.front_point
                    tz = b.rect[2] + 0.8
                    for j, (nx, nz) in enumerate(nozzles):
                        tx = nx + (0.3 if j else -0.3)
                        for s in range(1, 9):
                            u = (s / 9 + self.t * 1.6) % 1.0
                            self._put(grid, nx + (tx - nx) * u, nz + (tz - nz) * u, "≈·"[s % 2], "#8fd3ff", None, True)

    def _draw_markers(self, grid):
        w = self.city.world
        hot = int(self.t * 3) % 2 == 0
        for inc in w.incidents.values():
            rect = self.city.buildings[inc.building_id].rect
            glyph, c1, c2 = TAG[inc.type]
            cx = (rect[0] + rect[1]) / 2
            if inc.is_open:
                assigned = self.city.units_assigned(inc)
                units = f"{assigned}/{inc.units_needed}"
                state = "WAITING" if assigned == 0 else units
                text = f" {glyph} {inc.label} · {inc.severity.value} · {state} "
                self._label(grid, cx, rect[3] + 5.0, text, "#101010", c1 if hot else c2)
            elif inc.resolved_at is not None and w.t - inc.resolved_at < 5.0:
                self._label(grid, cx, rect[3] + 4.0, f" ✔ {inc.label} · RESOLVED ", "#0b2410", "#5ad17a")

    # ------------------------------------------------------------ to rich
    def _style(self, fg, bg, bold):
        key = (fg, bg, bold)
        s = self._styles.get(key)
        if s is None:
            s = self._styles[key] = Style(color=fg, bgcolor=bg, bold=bold)
        return s

    def _to_text(self, grid) -> Text:
        out = Text(no_wrap=True, overflow="crop")
        for ri, row in enumerate(grid):
            run, key = [], None
            for ch, fg, bg, bold in row:
                k = (fg, bg, bold)
                if k != key and run:
                    out.append("".join(run), self._style(*key))
                    run = []
                key = k
                run.append(ch)
            if run:
                out.append("".join(run), self._style(*key))
            if ri < len(grid) - 1:
                out.append("\n")
        return out
