"""Planners decide *who gets sent where*. They only act through the Dispatcher.

RulePlanner  - deterministic baseline: rank incidents by a priority score, serve in order with what is free.
StrandsPlanner (simulation/agent_planner.py) - the same decision made by an LLM agent through Strands tools.
"""

from simulation.incidents import IncidentType, Severity

SEVERITY_WEIGHT = {Severity.HIGH: 100, Severity.MEDIUM: 60, Severity.LOW: 30}
TYPE_WEIGHT = {IncidentType.FIRE: 15, IncidentType.FLOOD: 10, IncidentType.THEFT: 0}
UNIT_NAME = {"fire": "engine", "police": "patrol car", "rescue": "rescue truck"}


def priority_score(inc, now: float) -> float:
    """Higher = more urgent. Severity dominates; fire and flood outrank theft; waiting and size add up."""
    wait = min(now - inc.created_at, 120.0)
    return SEVERITY_WEIGHT[inc.severity] + TYPE_WEIGHT[inc.type] + 10 * inc.intensity + 0.4 * wait


class Planner:
    name = "planner"
    status = "idle"

    def __init__(self, city):
        self.city = city

    def update(self, dt: float):
        raise NotImplementedError


class RulePlanner(Planner):
    name = "RULES"

    def __init__(self, city, interval: float = 0.5):
        super().__init__(city)
        self.interval = interval
        self._clock = 0.0
        self._queued_logged: set = set()

    def update(self, dt: float):
        self._clock += dt
        if self._clock < self.interval:
            return
        self._clock = 0.0
        self.step()

    def step(self):
        c = self.city
        with c.lock:
            now = c.world.t
            needy = [i for i in c.open_incidents() if c.units_assigned(i) < i.units_needed]
            needy.sort(key=lambda i: priority_score(i, now), reverse=True)
            for rank, inc in enumerate(needy, 1):
                while c.units_assigned(inc) < inc.units_needed:
                    score = priority_score(inc, now)
                    reason = (f"priority #{rank} ({score:.0f}): {inc.severity.value} {inc.type.value.lower()}, "
                              f"{c.units_assigned(inc) + 1}/{inc.units_needed} {UNIT_NAME[inc.service]}")
                    res = c.dispatcher.dispatch_for(inc.id, reason)
                    if not res["ok"]:
                        key = (inc.id, inc.waiting_reason)
                        if inc.waiting_reason and key not in self._queued_logged:
                            self._queued_logged.add(key)
                            c.world.add_log("Queued", f"{inc.site_name}: {inc.waiting_reason} (priority {score:.0f})", "agent", (inc.id,))
                        break
            self.status = "idle" if not needy else f"{len(needy)} waiting"
