"""The 'Agent Info' screen: who the agent is, what it sees, which tools it has, and what it has done."""

import textwrap

from rich.text import Text
from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Static

from simulation.agent_planner import SYSTEM_PROMPT, describe_tools

ACCENT, DIM, OK, ALERT, AMBER, AGENT = "#4cc9f0", "#8a9bb5", "#5ad17a", "#ff6b4a", "#f4b942", "#c792ea"

WHEN_IT_RUNS = [
    "Only while at least one incident is open - an empty city never calls the model.",
    "Only when an incident still needs units AND a unit of the right service is free.",
    "New incidents that arrive together (within ~0.8 s) are decided in one call.",
    "Runs in a background thread, so the city keeps moving while it thinks.",
]
WHAT_IT_SEES = [
    "Every open incident: id, type, severity, location, intensity, how long it has waited.",
    "Units needed / assigned / still needed per incident, and which service answers it.",
    "Per service (fire, police, rescue): which units are available and which are deployed.",
    "Active missions. It does NOT see the map, roads, coordinates or vehicle positions.",
]
GUARDRAILS = [
    "Cannot send a unit of the wrong service (e.g. an engine to a theft) - the order is refused.",
    "Cannot send more units than an incident needs, or units that are not available.",
    "Cannot create or cancel incidents, drive vehicles, or change severity - only dispatch.",
    "Refusals are returned to the model as the tool result, so it can correct itself.",
    "If it fails 3 times in a row, or ignores a situation, the rule planner takes over.",
]


def _section(t: Text, title: str):
    t.append(f"\n{title}\n", style=f"bold {ACCENT}")
    t.append("─" * 78 + "\n", style="#1f3a52")


WIDTH = 86


def _wrapped(t: Text, first: str, rest: str, text: str, style="white", first_style=None):
    """Word-wrap `text` with a hanging indent."""
    lines = textwrap.wrap(text, WIDTH - len(first)) or [""]
    for n, line in enumerate(lines):
        t.append(first if n == 0 else rest, style=first_style or style)
        t.append(line + "\n", style=style)


def _bullets(t: Text, items, style="white"):
    for i in items:
        _wrapped(t, "  • ", "    ", i, style, first_style=ACCENT)


def render_agent_info(app) -> Text:
    t = Text()
    agent = app.agent
    active = app.city.planner is agent and agent is not None
    t.append("AGENT  ", style=f"bold {AGENT}")
    t.append("Emergency Operations Controller\n", style="bold white")

    if agent is None:
        t.append("\nNo Strands agent is running.\n", style=f"bold {AMBER}")
        t.append("The deterministic rule planner is in charge. Start Ollama (and `ollama signin` for the cloud\n"
                 "model) and restart without --rules to let the Strands agent decide.\n", style=DIM)
        _section(t, "RULE PLANNER (current)")
        _bullets(t, ["Ranks open incidents by a priority score: severity, then fire > flood > theft, then waiting time.",
                     "Serves them in that order with whatever units are free. No LLM, no tools."])
        return t

    _section(t, "STATUS")
    rows = [
        ("Framework", "Strands Agents SDK (persistent agent; remembers its earlier decisions)"),
        ("Model", f"{agent.model_id}  via Ollama @ {agent.host_url}"),
        ("In control", "YES - dispatching" if active else "NO - standby (rule planner in charge, press p to hand over)"),
        ("State", agent.status),
        ("Calls / errors", f"{agent.calls} / {agent.errors}"),
        ("Avg response", f"{agent.avg_latency:.1f} s" if agent.avg_latency else "-"),
    ]
    for k, v in rows:
        t.append(f"  {k:<15}", style=DIM)
        col = OK if (k == "In control" and active) else AMBER if k == "In control" else "white"
        t.append(v + "\n", style=col)

    _section(t, "WHEN IT RUNS")
    _bullets(t, WHEN_IT_RUNS)
    _section(t, "WHAT IT SEES (JSON city state in every request)")
    _bullets(t, WHAT_IT_SEES)

    _section(t, "TOOLS IT CAN CALL")
    for tool in describe_tools(app.city):
        args = ", ".join(f"{p['name']}: {p['type']}" for p in tool["params"])
        t.append(f"  {tool['name']}", style=f"bold {AGENT}")
        t.append(f"({args})\n", style=DIM)
        _wrapped(t, "      ", "      ", tool["description"], "white")
        for p in tool["params"]:
            if p["description"]:
                _wrapped(t, f"      {p['name']}: ", "          ", p["description"], DIM)
    _section(t, "WHAT IT CANNOT DO (guardrails in the dispatcher)")
    _bullets(t, GUARDRAILS)

    _section(t, "RECENT TOOL CALLS")
    if not agent.tool_log:
        t.append("  none yet - create an incident (n) or a crisis (x)\n", style=DIM)
    for clock, name, summary, ok in reversed(agent.tool_log):
        t.append(f"  {clock}  ", style=DIM)
        t.append(f"{name:<20}", style=AGENT)
        t.append(summary + "\n", style=OK if ok else ALERT)
    if agent.last_request:
        _section(t, "LAST REQUEST SENT TO THE MODEL (city state, raw JSON)")
        raw = agent.last_request
        t.append(raw[:1800] + ("\n  ... (truncated)" if len(raw) > 1800 else "") + "\n", style=DIM)
    if agent.last_tool_call:
        _section(t, "LAST TOOL CALL RETURNED BY THE MODEL (raw JSON)")
        t.append(agent.last_tool_call[:1500] + "\n", style=DIM)
    if agent.last_text:
        _section(t, "LAST THING IT SAID")
        _wrapped(t, "  ", "  ", agent.last_text[:300], "white")

    _section(t, "ITS INSTRUCTIONS (system prompt, verbatim)")
    paras: list[str] = []
    for line in SYSTEM_PROMPT.splitlines():      # re-join the hard-wrapped source lines into paragraphs
        if not line.strip():
            continue
        if line.startswith(" ") and paras:
            paras[-1] += " " + line.strip()
        else:
            paras.append(line.strip())
    for para in paras:
        numbered = para[:2].rstrip(".").isdigit() or para.startswith("- ")
        _wrapped(t, "  ", "      " if numbered else "  ", para, DIM)
    return t


class AgentInfo(ModalScreen):
    BINDINGS = [("escape", "close", "Close"), ("i", "close", "Close")]
    CSS = """
    AgentInfo { align: center middle; }
    #info_box { width: 96; height: 90%; border: heavy #c792ea; background: #0b1322; padding: 0 2; }
    #info_hint { dock: bottom; height: 1; color: #8a9bb5; background: #0b1322; padding: 0 2; }
    """

    def __init__(self, app_ref):
        super().__init__()
        self.app_ref = app_ref

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="info_box"):
            yield Static(id="info_text")
        yield Static("↑/↓ scroll · Esc or i to close", id="info_hint")

    def on_mount(self) -> None:
        self.refresh_text()
        self.set_interval(0.5, self.refresh_text)

    def refresh_text(self) -> None:
        self.query_one("#info_text", Static).update(render_agent_info(self.app_ref))

    def action_close(self) -> None:
        self.dismiss(None)
