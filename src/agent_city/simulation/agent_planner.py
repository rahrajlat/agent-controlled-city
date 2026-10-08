"""The Strands agent that runs Emergency Operations.

One persistent Strands Agent (keeps the conversation, so it remembers its earlier decisions) is given the
city state whenever the situation changes and decides which units to send where, by calling tools. The
tools are thin wrappers over the Dispatcher; they are the only way the agent can affect the city.

The LLM call runs in a background thread so the simulation keeps moving while the model thinks.
"""

import json
import os
import threading
import time
import urllib.request
from collections import deque

from simulation.planner import Planner, RulePlanner

DEFAULT_HOST = "http://localhost:11434"
CLOUD_MODEL = "gpt-oss:120b-cloud"      # 120B model served by Ollama cloud (needs `ollama signin`)
LOCAL_FALLBACKS = ("qwen3:8b", "qwen3:4b", "llama3.1:latest", "qwen3.5:27b")

SYSTEM_PROMPT = """You are the Emergency Operations Controller of Agent City.
You decide which emergency units to send to which incidents, using the dispatch tools.

SERVICES (units are scarce and each unit can serve only one incident at a time):
- fire    : fire engines   -> FIRE incidents
- police  : patrol cars    -> THEFT incidents
- rescue  : rescue trucks  -> FLOOD incidents (natural calamity)

RULES
1. Each incident shows units_needed, units_assigned and units_still_needed. HIGH severity needs 2 units,
   MEDIUM and LOW need 1. Never send more than units_still_needed. The service is chosen from the incident type.
2. Rank the incidents of each service: severity first (HIGH > MEDIUM > LOW); on a tie fire > flood > theft;
   on a further tie the incident that has waited longest (unattended incidents get worse after ~45 s).
3. Serve strictly in rank order: give the top-ranked incident ALL its units_still_needed before the next one gets
   any. If the units run out, the lower-ranked incidents simply wait; they are served as units return.
   Never send a unit to a low-ranked incident while a higher-ranked incident of the same service still needs units.
4. Services are independent: a fire engine shortage does not stop you sending police or rescue units.
5. Use dispatch_plan: ONE call with all your orders, listed in rank order. Each order is
   {"incident_id": "...", "units": N, "reason": "<max 15 words>"}. Only include orders for units that are available.
   (dispatch_fire_team / dispatch_police / dispatch_rescue_team send a single unit if you ever need that.)
6. The current state is in the user message; do not call get_city_state unless you need a fresh view.
7. After the tool call reply with ONE short plain sentence saying what you decided and who is waiting. No JSON."""


def list_models(host: str = DEFAULT_HOST, timeout: float = 2.0) -> list[str]:
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=timeout) as r:
            return [m["name"] for m in json.load(r)["models"]]
    except Exception:
        return []


def pick_model(host: str = DEFAULT_HOST) -> str | None:
    """AGENT_CITY_MODEL wins; else the 120B cloud model when Ollama is up; else a local model."""
    forced = os.environ.get("AGENT_CITY_MODEL")
    if forced:
        return forced
    have = list_models(host)
    if not have:
        return None
    for m in LOCAL_FALLBACKS if os.environ.get("AGENT_CITY_LOCAL") else ():
        if m in have:
            return m
    return CLOUD_MODEL


def build_tools(city, on_call=None):
    """The agent's tools. Imported lazily so the rest of the project works without strands installed.
    `on_call(name, args, result)` is told about every call (used by the Agent Info screen)."""
    from strands import tool

    d = city.dispatcher
    rec = on_call or (lambda *a: None)

    @tool
    def get_city_state() -> dict:
        """Get the current city state: open incidents (with units needed/assigned), the available and deployed
        units of each service (fire, police, rescue), and active missions."""
        with city.lock:
            snap = city.snapshot()
        rec("get_city_state", {}, snap)
        return snap

    @tool
    def dispatch_fire_team(incident_id: str, reason: str) -> dict:
        """Send ONE fire engine and crew to a FIRE incident. Call once per unit.

        Args:
            incident_id: id of an open FIRE incident, e.g. "incident_3".
            reason: short justification (max 15 words) for sending this unit now.
        """
        res = d.dispatch_fire_team(incident_id, reason, log=False)
        rec("dispatch_fire_team", {"incident_id": incident_id, "reason": reason}, res)
        return res

    @tool
    def dispatch_police(incident_id: str, reason: str) -> dict:
        """Send ONE police patrol car and officers to a THEFT incident. Call once per unit.

        Args:
            incident_id: id of an open THEFT incident, e.g. "incident_2".
            reason: short justification (max 15 words) for sending this unit now.
        """
        res = d.dispatch_police(incident_id, reason, log=False)
        rec("dispatch_police", {"incident_id": incident_id, "reason": reason}, res)
        return res

    @tool
    def dispatch_rescue_team(incident_id: str, reason: str) -> dict:
        """Send ONE rescue truck and crew to a FLOOD incident. Call once per unit.

        Args:
            incident_id: id of an open FLOOD incident, e.g. "incident_5".
            reason: short justification (max 15 words) for sending this unit now.
        """
        res = d.dispatch_rescue_team(incident_id, reason, log=False)
        rec("dispatch_rescue_team", {"incident_id": incident_id, "reason": reason}, res)
        return res

    @tool
    def dispatch_plan(orders: list[dict]) -> dict:
        """Send units for several incidents in ONE call. Orders are executed in the order given, so list them
        by priority (most urgent first).

        Args:
            orders: list of orders, each {"incident_id": "incident_3", "units": 1 or 2, "reason": "short why"}.
        """
        res = d.dispatch_plan(orders, log=False)
        rec("dispatch_plan", {"orders": orders}, res)
        return res

    return [get_city_state, dispatch_plan, dispatch_fire_team, dispatch_police, dispatch_rescue_team]


def describe_tools(city) -> list[dict]:
    """The tools exactly as the model sees them: name, description, parameters."""
    out = []
    for t in build_tools(city):
        spec = t.tool_spec
        schema = spec["inputSchema"]["json"]
        required = set(schema.get("required", []))
        params = [{"name": n, "type": p.get("type", "any"), "description": p.get("description", ""),
                   "required": n in required} for n, p in schema.get("properties", {}).items()]
        out.append({"name": spec["name"], "description": " ".join(spec["description"].split()), "params": params})
    return out


class StrandsPlanner(Planner):
    name = "AGENT"

    def __init__(self, city, model_id: str | None = None, host: str = DEFAULT_HOST, debounce: float = 0.8,
                 max_attempts: int = 2):
        super().__init__(city)
        self.host = host
        self.model_id = model_id or pick_model(host)
        if not self.model_id:
            raise RuntimeError(f"no Ollama model found at {host} (is Ollama running?)")
        self.debounce = debounce
        self.max_attempts = max_attempts
        self.fallback = RulePlanner(city)
        self.status = "starting"
        self.last_text = ""
        self.calls = 0
        self.errors = 0               # total
        self._consecutive_errors = 0
        self._clock = 0.0
        self._busy = False
        self._seen = None            # signature of the situation the agent last looked at
        self._seen_since = 0.0
        self._attempts: dict = {}
        self._agent = None
        self._lock = threading.Lock()
        self.host_url = host
        self.tool_log = deque(maxlen=12)       # (clock, tool, summary, ok)
        self.latencies = deque(maxlen=20)
        self.last_request = ""                 # raw JSON state sent to the model
        self.last_tool_call = ""               # raw JSON of the model's most recent tool call

    # ---- agent construction (lazy: first call) ----------------------------------
    def _make_agent(self):
        from strands import Agent
        from strands.agent.conversation_manager import SlidingWindowConversationManager
        from strands.models.ollama import OllamaModel

        model = OllamaModel(self.host, model_id=self.model_id, temperature=0.0)
        return Agent(model=model, tools=build_tools(self.city, self._record), system_prompt=SYSTEM_PROMPT,
                     callback_handler=None, conversation_manager=SlidingWindowConversationManager(window_size=16))

    def _record(self, name: str, args: dict, result: dict):
        if name == "dispatch_plan":
            sent = sum(1 for r in result.get("results", []) if r.get("ok"))
            summary, ok = f"{len(args.get('orders', []))} orders -> {sent} unit(s) sent", sent > 0
        elif name == "get_city_state":
            summary, ok = "read city state", True
        else:
            ok = bool(result.get("ok"))
            summary = f"{args.get('incident_id')} -> " + ("unit sent" if ok else str(result.get("error", "refused"))[:50])
        self.tool_log.append((self.city.world.clock(), name, summary, ok))
        if name != "get_city_state":
            self.last_tool_call = json.dumps({"tool": name, "arguments": args}, indent=1, default=str)
            self._log_orders(name, args, result)

    def _log_orders(self, name: str, args: dict, result: dict):
        """One activity-feed entry per tool call: what the model ordered, with its reasons and the outcome."""
        w = self.city.world
        orders = args.get("orders") if name == "dispatch_plan" else [{"incident_id": args.get("incident_id"),
                                                                    "units": 1, "reason": args.get("reason", "")}]
        results = result.get("results") if name == "dispatch_plan" else [dict(result, incident_id=args.get("incident_id"))]
        lines, ids = [], []
        for o in orders or []:
            iid = str(o.get("incident_id"))
            inc = w.incidents.get(iid)
            sent = sum(1 for r in results or [] if r.get("incident_id") == iid and r.get("ok"))
            asked = o.get("units", 1) if isinstance(o.get("units", 1), int) else 1
            where = f"{inc.site_name} {inc.type.value.lower()}" if inc else iid
            why = " ".join(str(o.get("reason", "")).split())
            lines.append(f"{where}: {sent}/{asked} unit(s)" + (f" - {why}" if why else ""))
            if inc:
                ids.append(iid)
        refused = [r.get("error") for r in results or [] if not r.get("ok") and r.get("error")]
        if refused:
            lines.append("refused: " + "; ".join(sorted(set(str(e)[:60] for e in refused))))
        w.add_log(f"◀ Model ordered ({name})", "\n".join(lines) or "nothing", "model_out", tuple(ids))

    @staticmethod
    def _describe_state(snap: dict) -> str:
        free = " · ".join(f"{svc} {len(r['available'])} free" for svc, r in snap["resources"].items())
        lines = [free]
        for i in snap["incidents"]:
            need = i["units_still_needed"]
            lines.append(f"#{i['id'].split('_')[1]} {i['type']} {i['severity']} {i['location']} - "
                         + (f"needs {need} more" if need else "fully staffed"))
        return "\n".join(lines)

    @property
    def avg_latency(self) -> float | None:
        return sum(self.latencies) / len(self.latencies) if self.latencies else None

    # ---- what needs a decision -------------------------------------------------------
    def _decision_needed(self):
        """Signature of the (needs, free units) situation, or None when there is nothing to decide."""
        c = self.city
        with c.lock:
            snap = c.snapshot()
        needy = [i for i in snap["incidents"] if i["units_still_needed"] > 0
                 and snap["resources"][i["required_service"]]["available"]]
        if not needy:
            return None, snap
        sig = (tuple(sorted((i["id"], i["units_still_needed"]) for i in needy)),
               tuple(sorted(u for r in snap["resources"].values() for u in r["available"])))
        return sig, snap

    def update(self, dt: float):
        self._clock += dt
        if self._clock < 0.25:
            return
        step, self._clock = self._clock, 0.0
        if self._busy:
            return
        if not self.city.open_incidents():          # no incidents -> never touch the model
            self._seen, self._seen_since = None, 0.0
            if not self.status.startswith("error"):
                self.status = "idle"
            return
        sig, snap = self._decision_needed()
        if sig is None:
            self._seen, self._seen_since = None, 0.0
            if not self.status.startswith("error"):
                self.status = "idle"
            return
        if sig != self._seen:                       # situation changed: wait a moment to batch new incidents
            self._seen, self._seen_since = sig, 0.0
        self._seen_since += step
        if self._seen_since < self.debounce:
            return
        self._attempts[sig] = self._attempts.get(sig, 0) + 1
        if self._attempts[sig] > self.max_attempts:   # the agent did not act on this situation: do not stall
            self.city.world.add_log("Fallback", "Agent did not resolve this situation - rule planner stepped in", "agent")
            self.fallback.step()
            self._attempts[sig] = 0
            return
        self._busy = True
        self.status = "thinking…"
        threading.Thread(target=self._run, args=(snap,), daemon=True).start()

    # ---- the LLM call (background thread) --------------------------------------------
    def _run(self, snap: dict):
        try:
            if self._agent is None:
                self._agent = self._make_agent()
            self.last_request = json.dumps(snap, indent=1)
            ids = tuple(i["id"] for i in snap["incidents"])
            self.city.world.add_log("▶ To model", self._describe_state(snap), "model_in", ids)
            prompt = ("The situation changed. Decide which units to dispatch now.\n"
                      f"CITY STATE:\n{json.dumps(snap)}")
            if self.model_id.startswith("qwen3"):
                prompt += "\n/no_think"
            t0 = time.time()
            result = self._agent(prompt)
            self.latencies.append(time.time() - t0)
            text = str(result).strip().replace("\n", " ")
            self.last_text = text
            self.calls += 1
            self._consecutive_errors = 0
            if text and not text.startswith(("{", "[")):
                self.city.world.add_log("◀ Model said", text[:160], "model_out", ids)
            self.status = "idle"
        except Exception as exc:          # model down, bad tool call, ...
            self.errors += 1
            self._consecutive_errors += 1
            self.status = f"error: {type(exc).__name__}"
            self.city.world.add_log("Agent error", f"{type(exc).__name__}: {str(exc)[:100]}", "alert")
            if self._consecutive_errors >= 3:
                self.name = "RULES*"          # model keeps failing: hand over to the rule planner
                self.update = self.fallback.update
        finally:
            self._busy = False
