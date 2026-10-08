"""Dispatch layer = the tool boundary for the Strands agent.

Every `dispatch_*` takes only JSON-friendly arguments and returns a JSON-friendly dict - exactly what a
Strands @tool wants. The planners (rule-based or the Strands agent) are the *deciders*; this is the *actuator*.
"""

from simulation.incidents import SERVICE_FOR, IncidentType
from simulation.missions import Mission


class Dispatcher:
    def __init__(self, city):
        self.city = city

    # ---------------- tool-shaped API ----------------
    def dispatch_fire_team(self, incident_id: str, reason: str = "", log: bool = True) -> dict:
        """Send one fire engine + crew to a FIRE incident."""
        return self._dispatch(incident_id, IncidentType.FIRE, reason, log)

    def dispatch_police(self, incident_id: str, reason: str = "", log: bool = True) -> dict:
        """Send one police car + officers to a THEFT incident."""
        return self._dispatch(incident_id, IncidentType.THEFT, reason, log)

    def dispatch_rescue_team(self, incident_id: str, reason: str = "", log: bool = True) -> dict:
        """Send one rescue truck + crew to a FLOOD incident."""
        return self._dispatch(incident_id, IncidentType.FLOOD, reason, log)

    def dispatch_plan(self, orders: list, log: bool = True) -> dict:
        """Execute several dispatch orders in the given (priority) order. Each order is a dict with
        `incident_id`, optional `units` (default 1) and `reason`. The right service is chosen from the incident type."""
        results = []
        for o in orders or []:
            if not isinstance(o, dict) or "incident_id" not in o:
                results.append({"ok": False, "error": "each order needs an incident_id"})
                continue
            try:
                units = max(1, min(int(o.get("units", 1)), 2))
            except (TypeError, ValueError):
                units = 1
            for n in range(units):
                res = self.dispatch_for(str(o["incident_id"]), str(o.get("reason", "")), log)
                res["incident_id"] = o["incident_id"]
                results.append(res)
                if not res["ok"]:
                    break
        return {"ok": any(r["ok"] for r in results), "results": results}

    def dispatch_for(self, incident_id: str, reason: str = "", log: bool = True) -> dict:
        """Dispatch whichever service the incident type needs (used by the rule planner)."""
        inc = self.city.world.incidents.get(incident_id)
        if inc is None:
            return {"ok": False, "error": f"unknown incident {incident_id}"}
        return self._dispatch(incident_id, inc.type, reason, log)

    # ---------------- internals ----------------
    def _dispatch(self, incident_id: str, expected: IncidentType, reason: str, log: bool = True) -> dict:
        c = self.city
        reason = " ".join(str(reason or "").split())
        with c.lock:
            w = c.world
            inc = w.incidents.get(incident_id)
            if inc is None:
                return {"ok": False, "error": f"unknown incident {incident_id}"}
            if not inc.is_open:
                return {"ok": False, "error": f"{incident_id} is already resolved"}
            if inc.type != expected:
                return {"ok": False, "error": f"{incident_id} is a {inc.type.value} incident; it needs the "
                                              f"{SERVICE_FOR[inc.type]} service, not {SERVICE_FOR[expected]}"}
            assigned = c.units_assigned(inc)
            if assigned >= inc.units_needed:
                return {"ok": False, "error": f"{incident_id} already has {assigned}/{inc.units_needed} units"}
            depot = c.depots[inc.service]
            free = depot.available()
            if not free:
                inc.waiting_reason = f"all {depot.name} units are deployed"
                return {"ok": False, "error": f"no {inc.service} unit available (all deployed)"}
            vehicle, crew = free[0]
            mission = Mission(w.next_id("mission"), inc, depot, vehicle, crew, w.t)
            w.missions[mission.id] = mission
            mission.dispatch(w, reason)
            if reason and log:
                w.add_log("Decision", f"{inc.site_name}: {reason}"[:140], "agent", (inc.id,))
            return {"ok": True, "mission": mission.to_dict(), "units_assigned": assigned + 1,
                    "units_needed": inc.units_needed}
