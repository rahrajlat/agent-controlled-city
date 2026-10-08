"""The City: owns the world state, road graph, buildings, vehicles and the per-tick update.

Nothing here imports a renderer. A front end (or an agent) only reads/calls this.
"""

import math
import random
import threading

from entities.building import Building
from entities.fire_station import FireStation
from entities.hospital import Hospital
from entities.police_station import PoliceStation
from entities.rescue_centre import RescueCentre
from entities.substation import Substation
from entities.vehicle import Vehicle, Waypoint
from simulation.dispatcher import Dispatcher
from simulation.incidents import (ESCALATE_AFTER, START_INTENSITY, Incident, IncidentStatus, IncidentType,
                                  Severity)
from simulation.missions import Mission, MissionStatus
from simulation.planner import priority_score
from simulation.road_network import RoadGraph, dist
from simulation.world_state import WorldState

LINES = [-21.0, -7.0, 7.0, 21.0]     # road centre lines (both axes)
MIDS = [-14.0, 0.0, 14.0]            # block centres / mid-road access nodes
ROAD_WIDTH = 3.6
BLOCK = 10.4

BLOCK_KINDS = {
    (-14.0, 14.0): "fire_station", (0.0, 14.0): "houses", (14.0, 14.0): "substation",
    (-14.0, 0.0): "park", (0.0, 0.0): "hospital", (14.0, 0.0): "police_station",
    (-14.0, -14.0): "offices", (0.0, -14.0): "rescue_centre", (14.0, -14.0): "warehouse",
}
INCIDENT_SITES = ["warehouse", "north_houses", "west_offices", "park", "substation", "hospital"]

# health lost per second at full intensity / HIGH severity
HEALTH_LOSS = {IncidentType.FIRE: 0.4, IncidentType.FLOOD: 0.3, IncidentType.THEFT: 0.12}
SEVERITY_FACTOR = {Severity.LOW: 0.3, Severity.MEDIUM: 0.6, Severity.HIGH: 1.0}

TRAFFIC_COLORS = ["#e9c46a", "#4ea8de", "#f4f1de", "#9b5de5", "#6a994e", "#ef8354", "#bfc0c0", "#2a9d8f"]


def _site(bid, kind, name, center, rect):
    cx, cz = center
    return Building(bid, kind, name, center, (8.4, 8.4, 3.0), access_node=(cx, cz - 7.0),
                    front_point=(cx, cz - 4.7), rect=rect)


class City:
    def __init__(self, seed: int = 7):
        random.seed(seed)
        self.lock = threading.RLock()          # held while the world changes (agent threads use it too)
        self.world = WorldState()
        self.graph = RoadGraph.grid(LINES, MIDS)
        self.block_kinds = dict(BLOCK_KINDS)
        self.traffic: list[Vehicle] = []

        self.fire_station = FireStation((-14.0, 14.0))
        self.police_station = PoliceStation((14.0, 0.0))
        self.rescue_centre = RescueCentre((0.0, -14.0))
        self.depots = {"fire": self.fire_station, "police": self.police_station, "rescue": self.rescue_centre}

        hospital = Hospital("hospital", "Hospital", (0.0, 0.0))
        hospital.rect = (-3.8, 3.8, -1.7, 3.0)
        substation = Substation("substation", "Substation", (14.0, 14.0))
        substation.rect = (10.0, 18.0, 10.0, 18.0)
        warehouse = Building("warehouse", "warehouse", "Warehouse", (14.0, -14.0), (8.0, 6.0, 3.2), "#b9b3a3",
                             access_node=(14.0, -21.0), front_point=(14.0, -18.7), rect=(10.5, 17.5, -17.6, -11.6))
        self.buildings: dict[str, Building] = {b.id: b for b in (
            self.fire_station, self.police_station, self.rescue_centre, hospital, substation, warehouse,
            _site("north_houses", "houses", "North Houses", (0.0, 14.0), (-3.8, 3.8, 10.2, 17.8)),
            _site("west_offices", "offices", "West Offices", (-14.0, -14.0), (-17.8, -10.2, -17.8, -10.2)),
            _site("park", "park", "Park", (-14.0, 0.0), (-17.8, -10.2, -3.8, 3.8)),
        )}
        self.world.buildings = self.buildings

        self.dispatcher = Dispatcher(self)
        self.planner = None                    # set by the front end: RulePlanner or StrandsPlanner
        self._spawn_traffic(14)

    # ---- access for renderers / agents ---------------------------------------
    @property
    def vehicles(self) -> list[Vehicle]:
        return self.traffic + [v for d in self.depots.values() for v in d.vehicles]

    @property
    def active_missions(self) -> list[Mission]:
        return [m for m in self.world.missions.values() if m.is_active]

    def open_incidents(self) -> list[Incident]:
        return [i for i in self.world.incidents.values() if i.is_open]

    def units_assigned(self, inc: Incident) -> int:
        return sum(1 for m in self.world.missions.values() if m.incident is inc and m.counts_on_incident)

    # ---- incidents -------------------------------------------------------------
    def create_incident(self, itype: IncidentType, building_id: str, severity: Severity = Severity.HIGH) -> Incident:
        b = self.buildings[building_id]
        x0, x1, z0, z1 = b.rect
        inc = Incident(self.world.next_id("incident"), itype, severity, building_id, b.name,
                       ((x0 + x1) / 2, (z0 + z1) / 2), intensity=START_INTENSITY[severity],
                       created_at=self.world.t, stand_hint=b.access_node)
        with self.lock:
            self.world.incidents[inc.id] = inc
            self.world.add_log(inc.label, f"New incident · severity {severity.value}", "alert", (inc.id,))
        return inc

    def next_incident_for(self, service: str, exclude: Incident) -> Incident | None:
        """The most urgent open incident of this service that still needs units, if any."""
        now = self.world.t
        needy = [i for i in self.open_incidents()
                 if i is not exclude and i.service == service and self.units_assigned(i) < i.units_needed]
        return max(needy, key=lambda i: priority_score(i, now), default=None)

    # ---- route planning ------------------------------------------------------
    def plan_departure(self, v, depot, inc: Incident, team, slot: int = 0) -> list[Waypoint]:
        bay = depot.bays[v.bay_index]
        nodes = self.graph.calculate_route(depot.access_node, inc.stand_hint)
        return [Waypoint(bay.x, bay.door_z - 2.0, precise=True)] + self._scene_route(nodes, inc, team, slot)

    def plan_redeploy(self, v, inc: Incident, team, slot: int = 0) -> list[Waypoint]:
        """Route from where the vehicle stands now straight to another incident (no trip via the depot)."""
        nodes = self.graph.calculate_route(tuple(v.pos), inc.stand_hint)
        return self._scene_route(nodes, inc, team, slot)

    def _scene_route(self, nodes, inc: Incident, team, slot: int) -> list[Waypoint]:
        """Road nodes -> line up with the kerb -> park, and set where the crew will stand."""
        b = self.buildings[inc.building_id]
        if len(nodes) > 1:
            u = _unit(nodes[-1][0] - nodes[-2][0], nodes[-1][1] - nodes[-2][1])
        else:
            u = (1.0, 0.0)
        if abs(u[0]) > abs(u[1]):       # perpendicular, towards the building
            side = (0.0, math.copysign(1.0, b.pos[1] - nodes[-1][1]))
        else:
            side = (math.copysign(1.0, b.pos[0] - nodes[-1][0]), 0.0)
        slot = min(slot, 1)
        if slot == 0:        # first unit stops just short of the access point
            park = (nodes[-1][0] - u[0] * 2.8 + side[0] * 1.0, nodes[-1][1] - u[1] * 2.8 + side[1] * 1.0)
            lineup = (park[0] - u[0] * 3.0, park[1] - u[1] * 3.0)
        else:                # second unit stops just past it, so it never has to reverse
            park = (nodes[-1][0] + u[0] * 1.2 + side[0] * 1.0, nodes[-1][1] + u[1] * 1.2 + side[1] * 1.0)
            lineup = (nodes[-1][0] - u[0] * 1.5, nodes[-1][1] - u[1] * 1.5)
        route = [Waypoint(*n) for n in nodes[:-1]]
        route.append(Waypoint(*lineup))                     # line up with the kerb first
        route.append(Waypoint(*park))
        fx, fz = b.front_point
        shift = 4.0 * slot
        team.scene_positions = [(fx + u[0] * ((k - (team.size - 1) / 2) * 1.2 + shift) + 0.4,
                                 fz + u[1] * ((k - (team.size - 1) / 2) * 1.2 + shift))
                                for k in range(team.size)]
        return route

    def plan_return(self, v, depot, inc: Incident) -> list[Waypoint]:
        bay = depot.bays[v.bay_index]
        p = tuple(v.pos)
        u = v.forward
        if abs(u[0]) > abs(u[1]):
            away = (0.0, math.copysign(1.0, p[1] - inc.pos[1]))
        else:
            away = (math.copysign(1.0, p[0] - inc.pos[0]), 0.0)
        route = [Waypoint(p[0] + u[0] * 3.2 + away[0] * 1.2, p[1] + u[1] * 3.2 + away[1] * 1.2),   # swing out, U-turn
                 Waypoint(p[0] + u[0] * 2.0 + away[0] * 2.3, p[1] + u[1] * 2.0 + away[1] * 2.3),
                 Waypoint(p[0] - u[0] * 0.5 + away[0] * 1.6, p[1] - u[1] * 0.5 + away[1] * 1.6)]
        back = (-u[0], -u[1])
        end = route[-1]
        nodes = self.graph.calculate_route(self.graph.nearest_node(p), depot.access_node)
        nodes = [n for n in nodes if (n[0] - end.x) * back[0] + (n[1] - end.z) * back[1] > 1.0] or nodes[-1:]
        if len(nodes) >= 2 and min(nodes[-2][0], nodes[-1][0]) < bay.x < max(nodes[-2][0], nodes[-1][0]):
            nodes = nodes[:-1]                       # the bay is before the access node: skip it
        route += [Waypoint(*n) for n in nodes]
        route.append(Waypoint(bay.x, depot.access_node[1] - 1.7, precise=True))   # swing past the bay, reverse in
        route.append(Waypoint(bay.x, bay.door_z - 0.4, reverse=True))
        route.append(Waypoint(bay.x, bay.park_z, reverse=True, precise=True))
        return route

    # ---- background traffic -----------------------------------------------------
    def _spawn_traffic(self, n: int):
        nodes = [nd for nd in self.graph.nodes if abs(nd[0]) <= 21 and abs(nd[1]) <= 21]
        random.shuffle(nodes)
        taken: list[tuple] = []
        for nd in nodes:
            if len(taken) >= n:
                break
            if any(dist(nd, t) < 9 for t in taken):
                continue
            prev = random.choice(self.graph.neighbors(nd))
            heading = math.degrees(math.atan2(nd[0] - prev[0], nd[1] - prev[1]))
            kind = random.choice(["car", "car", "car", "van", "bus"])
            v = Vehicle(f"car_{len(taken) + 1}", kind, nd, heading, max_speed=random.uniform(3.4, 4.6),
                        color=random.choice(TRAFFIC_COLORS),
                        length={"car": 1.9, "van": 2.2, "bus": 3.4}[kind])
            v.start_wandering(self.graph, nd, prev)
            v.route.clear()
            v._node, v._prev = nd, prev
            v._refill()
            self.traffic.append(v)
            taken.append(nd)

    # ---- tick -------------------------------------------------------------------
    def update(self, dt: float):
        with self.lock:
            w = self.world
            w.t += dt
            for d in self.depots.values():
                d.update(dt)
            everyone = self.vehicles
            for v in everyone:
                v.update(dt, everyone)
            self._work_on_incidents(dt)
            for m in self.active_missions:
                m.update(dt, self)
            self._escalate()
            self._update_city_health(dt)
        if self.planner is not None:
            self.planner.update(dt)

    def _work_on_incidents(self, dt: float):
        """Every unit that is working on site reduces the incident; at zero it is resolved."""
        w = self.world
        for inc in self.open_incidents():
            working = sum(1 for m in w.missions.values()
                          if m.incident is inc and m.status == MissionStatus.RESPONDING)
            if working:
                inc.intensity = max(0.0, inc.intensity - working * dt / inc.work_time)
            if inc.intensity <= 0.0 and working:
                inc.status = IncidentStatus.RESOLVED
                inc.resolved_at = w.t
                w.add_log(f"{inc.label} resolved", "Incident cleared", "ok", (inc.id,))

    def _escalate(self):
        w = self.world
        for inc in self.open_incidents():
            if inc.dispatched_at is not None or inc.severity == Severity.HIGH:
                continue
            since = inc.escalated_at if inc.escalated_at is not None else inc.created_at
            if w.t - since > ESCALATE_AFTER:
                inc.severity = inc.severity.escalate()
                inc.intensity = max(inc.intensity, START_INTENSITY[inc.severity])
                inc.escalated_at = w.t
                w.add_log(f"{inc.label} escalated", f"Unattended - now {inc.severity.value}", "alert", (inc.id,))

    def _update_city_health(self, dt: float):
        w = self.world
        harmful = [i for i in self.open_incidents() if i.intensity > 0]
        for i in harmful:
            f = SEVERITY_FACTOR[i.severity] * i.intensity
            w.city_health = max(0.0, w.city_health - HEALTH_LOSS[i.type] * f * dt)
            if i.type == IncidentType.FIRE:
                b = self.buildings[i.building_id]
                b.damage = min(0.85, b.damage + 0.03 * i.intensity * dt)
        if not harmful:
            w.city_health = min(100.0, w.city_health + 1.0 * dt)
            for b in self.buildings.values():
                b.damage = max(0.0, b.damage - 0.025 * dt)

    # ---- state snapshot (what an agent reads) ---------------------------------------
    def snapshot(self) -> dict:
        w = self.world
        incidents = []
        for i in self.open_incidents():
            assigned = self.units_assigned(i)
            incidents.append({
                "id": i.id, "type": i.type.value, "severity": i.severity.value, "location": i.site_name,
                "status": i.status.value, "intensity": round(i.intensity, 2),
                "waiting_seconds": int(w.t - i.created_at) if i.dispatched_at is None else 0,
                "units_needed": i.units_needed, "units_assigned": assigned,
                "units_still_needed": max(0, i.units_needed - assigned),
                "required_service": i.service,
            })
        resources = {}
        for svc, d in self.depots.items():
            resources[svc] = {"depot": d.name,
                              "available": [v.id for v, c in d.available()],
                              "deployed": [v.id for v in d.vehicles if not v.is_available]}
        return {"time": w.clock(), "city_health": round(w.city_health, 1),
                "incidents": incidents, "resources": resources,
                "missions": [m.to_dict() for m in self.active_missions]}


def _unit(x: float, z: float):
    d = math.hypot(x, z) or 1.0
    return x / d, z / d
