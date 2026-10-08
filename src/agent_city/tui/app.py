"""Agent City as a Textual terminal app: the user creates incidents, a planner (the Strands agent) dispatches."""

import math
import time

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from scenarios.demo import crisis, random_incident
from simulation.city import INCIDENT_SITES, City
from simulation.incidents import IncidentStatus, IncidentType, Severity
from simulation.missions import MissionStatus
from simulation.planner import RulePlanner, priority_score
from simulation.world_state import fmt_duration
from tui.agent_info import AgentInfo
from tui.map_view import TAG, MapView

OK, ALERT, AMBER, ACCENT, DIM, AGENT = "#5ad17a", "#ff6b4a", "#f4b942", "#4cc9f0", "#8a9bb5", "#c792ea"
KIND = {"info": ACCENT, "alert": ALERT, "ok": OK, "agent": AGENT, "model_in": ACCENT, "model_out": AGENT}
GRACE = 4.0          # seconds an incident's entries stay visible after it is resolved
SEV_COLOR = {Severity.HIGH: ALERT, Severity.MEDIUM: AMBER, Severity.LOW: "#9fd3a8"}
SERVICE_TITLE = {"fire": "FIRE", "police": "POLICE", "rescue": "RESCUE"}
FPS = 20


def health_color(h):
    return OK if h >= 75 else AMBER if h >= 45 else ALERT


class NewIncident(ModalScreen):
    """Three quick questions: what, where, how bad."""

    BINDINGS = [("escape", "cancel", "Cancel")]
    CSS = """
    NewIncident { align: center middle; }
    #wiz { width: 56; height: auto; max-height: 24; border: heavy #4cc9f0; background: #0b1322; padding: 1 2; }
    #wiz_title { color: #4cc9f0; text-style: bold; margin-bottom: 1; }
    #wiz_hint { color: #8a9bb5; margin-top: 1; }
    OptionList { background: #0b1322; border: none; height: auto; max-height: 12; }
    """

    def __init__(self, city):
        super().__init__()
        self.city = city
        self.step = 0
        self.choice: list = []

    def compose(self) -> ComposeResult:
        with Vertical(id="wiz"):
            yield Static(id="wiz_title")
            yield OptionList(id="wiz_list")
            yield Static("↑/↓ or number · Enter to choose · Esc to cancel", id="wiz_hint")

    def on_mount(self) -> None:
        self._show()

    def _options(self):
        if self.step == 0:
            return "What happened?", [
                (IncidentType.FIRE, "Fire"), (IncidentType.THEFT, "Theft"),
                (IncidentType.FLOOD, "Flood (natural calamity)")]
        if self.step == 1:
            return "Where?", [(sid, self.city.buildings[sid].name) for sid in INCIDENT_SITES]
        return "How severe?", [(Severity.HIGH, "High  (needs 2 units)"), (Severity.MEDIUM, "Medium (1 unit)"),
                               (Severity.LOW, "Low    (1 unit)")]

    def _show(self) -> None:
        title, opts = self._options()
        self.query_one("#wiz_title", Static).update(f"NEW INCIDENT  ·  {self.step + 1}/3  ·  {title}")
        ol = self.query_one("#wiz_list", OptionList)
        ol.clear_options()
        ol.add_options([Option(f"{i + 1}.  {label}", id=str(i)) for i, (_, label) in enumerate(opts)])
        ol.highlighted = 0
        ol.focus()

    def on_key(self, event) -> None:
        if event.key.isdigit():
            _, opts = self._options()
            idx = int(event.key) - 1
            if 0 <= idx < len(opts):
                self.query_one("#wiz_list", OptionList).highlighted = idx
                self._pick(idx)
                event.stop()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self._pick(int(event.option.id))

    def _pick(self, idx: int) -> None:
        _, opts = self._options()
        self.choice.append(opts[idx][0])
        self.step += 1
        if self.step == 3:
            self.dismiss(tuple(self.choice))
        else:
            self._show()

    def action_cancel(self) -> None:
        self.dismiss(None)


class AgentCityApp(App):
    TITLE = "Agent City"
    CSS = """
    Screen { background: #0b1322; }
    #top { height: 3; padding: 1 2 0 2; background: #0b1322; border-bottom: heavy #1f3a52; }
    #body { height: 1fr; }
    #map { width: 1fr; height: 1fr; background: #0e1626; }
    #side { width: 56; height: 1fr; }
    .panel { border: round #1f3a52; padding: 0 1; background: #0b1322; }
    #incidents { height: auto; min-height: 5; max-height: 14; }
    #units { height: auto; }
    #activity { height: 1fr; }
    """
    BINDINGS = [
        ("n", "new_incident", "New incident"),
        ("r", "random", "Random"),
        ("x", "crisis", "Crisis"),
        ("p", "planner", "Planner"),
        ("i", "agent_info", "Agent info"),
        ("space", "pause", "Pause"),
        ("1", "speed(1)", "1x"),
        ("2", "speed(2)", "2x"),
        ("3", "speed(4)", "4x"),
        ("q", "quit", "Quit"),
    ]

    def __init__(self, planner: str = "agent", model: str | None = None):
        super().__init__()
        self.city = City()
        self.view = MapView(self.city)
        self.speed = 1.0
        self.paused = False
        self._last = time.monotonic()
        self.rule = RulePlanner(self.city)
        self.agent = None
        if planner != "rules":
            try:
                from simulation.agent_planner import StrandsPlanner
                self.agent = StrandsPlanner(self.city, model_id=model)
            except Exception as exc:
                self.city.world.add_log("Agent unavailable", f"{str(exc)[:90]} - using rule planner", "alert")
        self.city.planner = self.agent or self.rule
        if self.agent:
            self.city.world.add_log("Strands agent online", f"model {self.agent.model_id}", "agent")

    def compose(self) -> ComposeResult:
        yield Static(id="top")
        with Horizontal(id="body"):
            yield Static(id="map")
            with Vertical(id="side"):
                yield Static(id="incidents", classes="panel")
                yield Static(id="units", classes="panel")
                yield Static(id="activity", classes="panel")
        yield Footer()

    def on_mount(self) -> None:
        for pid, title in (("incidents", "INCIDENTS"), ("units", "UNITS"), ("activity", "ACTIVITY & DECISIONS")):
            self.query_one(f"#{pid}").border_title = title
        self.set_interval(1 / FPS, self.tick)

    # ------------------------------------------------------------ actions
    def action_new_incident(self) -> None:
        def made(result):
            if result:
                itype, site, sev = result
                self.city.create_incident(itype, site, sev)
        self.push_screen(NewIncident(self.city), made)

    def action_random(self) -> None:
        random_incident(self.city)

    def action_crisis(self) -> None:
        crisis(self.city)

    def action_planner(self) -> None:
        if self.agent is None:
            self.city.world.add_log("Planner", "Strands agent is not available", "alert")
            return
        self.city.planner = self.rule if self.city.planner is self.agent else self.agent
        self.city.world.add_log("Planner switched", f"now {self.city.planner.name}", "agent")

    def action_agent_info(self) -> None:
        self.push_screen(AgentInfo(self))

    def action_pause(self) -> None:
        self.paused = not self.paused

    def action_speed(self, s: int) -> None:
        self.speed = float(s)

    # ------------------------------------------------------------ loop
    def tick(self) -> None:
        now = time.monotonic()
        dt = min(now - self._last, 0.1)
        self._last = now
        if not self.paused:
            dt *= self.speed
            self.city.update(dt)
            self.view.update(dt)
        self.step_ui()

    def step_ui(self) -> None:
        mp = self.query_one("#map", Static)
        w, h = mp.size.width, mp.size.height
        if w >= 20 and h >= 8:
            mp.update(self.view.render(w, h))
        self.query_one("#top", Static).update(self._top())
        self.query_one("#incidents", Static).update(self._incidents())
        self.query_one("#units", Static).update(self._units())
        self.query_one("#activity", Static).update(self._activity())

    # ------------------------------------------------------------ panels
    def _top(self) -> Text:
        w = self.city.world
        t = Text()
        t.append("AGENT ", style="bold white")
        t.append("CITY", style=f"bold {ACCENT}")
        t.append("     Health ", style=DIM)
        filled = int(round(w.city_health / 10))
        t.append("█" * filled, style=health_color(w.city_health))
        t.append("░" * (10 - filled), style="#2a3b50")
        t.append(f" {w.city_health:.0f}%", style=f"bold {health_color(w.city_health)}")
        t.append("    Incidents ", style=DIM)
        n = w.active_incidents
        t.append(str(n), style=f"bold {ALERT if n else 'white'}")
        t.append("    ", style=DIM)
        t.append(w.clock(), style="bold white")
        p = self.city.planner
        t.append("    Planner ", style=DIM)
        t.append(p.name, style=f"bold {AGENT}")
        if p.status not in ("idle", "starting"):
            t.append(f" {p.status}", style=AMBER if "think" in p.status else ALERT)
        if self.paused:
            t.append("    ⏸ PAUSED", style=f"bold {AMBER}")
        elif self.speed != 1.0:
            t.append(f"    {self.speed:.0f}x", style=f"bold {AMBER}")
        return t

    def _inc_state(self, inc):
        ms = [m for m in self.city.world.missions.values() if m.incident is inc and m.counts_on_incident]
        if not ms:
            return "WAITING", AMBER
        if any(m.status == MissionStatus.RESPONDING for m in ms):
            return "ON SCENE", OK
        if any(m.status == MissionStatus.ARRIVED for m in ms):
            return "ARRIVING", ACCENT
        return "EN ROUTE", ACCENT

    def _incidents(self) -> Text:
        c = self.city
        w = c.world
        t = Text()
        opn = sorted(c.open_incidents(), key=lambda i: priority_score(i, w.t), reverse=True)
        recent = [i for i in w.incidents.values() if not i.is_open and i.resolved_at and w.t - i.resolved_at < 6]
        if not opn and not recent:
            t.append("No incidents. Press ", style=DIM)
            t.append("n", style=f"bold {ACCENT}")
            t.append(" to create one,\n", style=DIM)
            t.append("x", style=f"bold {ACCENT}")
            t.append(" for a multi-incident crisis.", style=DIM)
            return t
        for inc in opn:
            glyph, tcol, _ = TAG[inc.type]
            state, scol = self._inc_state(inc)
            assigned = c.units_assigned(inc)
            t.append(f"{glyph} ", style=f"bold {tcol}")
            t.append(f"{inc.severity.value[:3]} ", style=f"bold {SEV_COLOR[inc.severity]}")
            t.append(f"{inc.id.split('_')[1]:>2} ", style=DIM)
            t.append(f"{inc.type.value.title():<5} {inc.site_name:<12.12}", style="white")
            t.append(f" {assigned}/{inc.units_needed} ", style="white")
            filled = int(round(inc.intensity * 5))
            t.append("█" * filled + "░" * (5 - filled), style=SEV_COLOR[inc.severity])
            t.append(f" {state}\n", style=scol)
        for inc in recent:
            t.append(f"✔ {inc.label.title()} resolved\n", style=OK)
        t.rstrip()
        return t

    def _units(self) -> Text:
        c = self.city
        t = Text()
        for svc, depot in c.depots.items():
            free = len(depot.available())
            t.append(f"{SERVICE_TITLE[svc]:<7}", style=f"bold {ACCENT}")
            t.append(f"{free}/{len(depot.vehicles)} free\n", style=OK if free else ALERT)
            for veh in depot.vehicles:
                m = next((m for m in c.world.missions.values() if m.vehicle is veh and m.is_active), None)
                t.append(" ● ", style=OK if veh.is_available else ALERT)
                t.append(f"{veh.name:<15}", style="white" if veh.is_available else AMBER)
                if m is None:
                    t.append("AVAILABLE\n", style=OK)
                else:
                    t.append(f"{m.incident.site_name[:11]:<11} {m.status.value.replace('_', ' ')}\n", style=AMBER)
        t.rstrip()
        return t

    def _visible(self, e) -> bool:
        """An entry about incidents stays only while one of them is open (plus a short grace after it is resolved)."""
        w = self.city.world
        if e.incidents:
            for iid in e.incidents:
                inc = w.incidents.get(iid)
                if inc is not None and (inc.is_open or w.t - (inc.resolved_at if inc.resolved_at is not None else w.t) < GRACE):
                    return True
            return False
        return w.t - e.t < 25.0            # general notices fade on their own

    def _activity(self) -> Text:
        panel = self.query_one("#activity")
        budget = max(4, panel.size.height - 2)
        width = max(20, panel.size.width - 8)
        t = Text()
        shown = 0
        for e in reversed(self.city.world.log):
            if not self._visible(e):
                continue
            detail = e.detail.splitlines() or [""]
            need = 1 + sum(max(1, math.ceil(len(d) / width)) for d in detail)
            if shown + need > budget and shown:
                break
            shown += need
            col = KIND.get(e.kind, DIM)
            model = e.kind in ("model_in", "model_out", "agent")
            t.append("▌", style=col)
            t.append(f" {e.clock} ", style=DIM)
            t.append(e.title, style=f"bold {col}" if model else "bold white")
            for d in detail:
                t.append(f"\n   {d}", style=col if model else DIM)
            t.append("\n")
        if not shown:
            t.append("Quiet. City operating normally.", style=DIM)
        t.rstrip()
        return t


def run(planner: str = "agent", model: str | None = None):
    AgentCityApp(planner=planner, model=model).run()
