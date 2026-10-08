"""A Mission is one response: one vehicle + one crew sent to an incident.

Its state machine is advanced by `update()` each tick; renderers only read the result.
Several missions can serve one incident (high severity needs two units).
"""

from enum import Enum

from entities.team import TeamState
from simulation.incidents import IncidentStatus, IncidentType, SERVICE_NAME
from simulation.road_network import RoadGraph, dist

BOARD_TIME = 2.2        # crew runs to the vehicle
DEPLOY_TIME = 2.6       # crew climbs out and walks to the site
STOW_TIME = 2.6         # crew packs up and boards again

TEXT = {   # (deploying, working, resolved)
    IncidentType.FIRE: ("Firefighters deploying", "Hoses on the fire", "Fire out"),
    IncidentType.THEFT: ("Officers on scene", "Securing the scene", "Suspect detained"),
    IncidentType.FLOOD: ("Rescuers deploying", "Pumping and evacuating", "Flood contained"),
}


class MissionStatus(str, Enum):
    CREATED = "CREATED"
    DISPATCHED = "DISPATCHED"
    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"
    RESPONDING = "RESPONDING"
    RESOLVED = "RESOLVED"
    RETURNING = "RETURNING"
    COMPLETE = "COMPLETE"


ACTIVE_ON_INCIDENT = (MissionStatus.CREATED, MissionStatus.DISPATCHED, MissionStatus.EN_ROUTE,
                      MissionStatus.ARRIVED, MissionStatus.RESPONDING)


class Mission:
    def __init__(self, mid: str, incident, depot, vehicle, team, created_at: float):
        self.id = mid
        self.incident = incident
        self.depot = depot
        self.vehicle = vehicle
        self.team = team
        self.status = MissionStatus.CREATED
        self.created_at = created_at
        self._timer = 0.0
        self._door_closed = False

    # -- helpers ----------------------------------------------------------
    @property
    def bay(self):
        return self.depot.bays[self.vehicle.bay_index]

    @property
    def vehicle_name(self) -> str:
        return self.vehicle.name

    @property
    def counts_on_incident(self) -> bool:
        return self.status in ACTIVE_ON_INCIDENT

    def _go(self, status: MissionStatus):
        self.status = status
        self._timer = 0.0

    def estimated_resolution(self, city) -> float | None:
        """Real seconds until the incident is expected to be cleared."""
        s, inc = self.status, self.incident
        if inc.status == IncidentStatus.RESOLVED or s in (MissionStatus.RESOLVED, MissionStatus.RETURNING,
                                                           MissionStatus.COMPLETE):
            return 0.0
        working = max(1, city.units_assigned(inc))
        work = inc.work_time * max(inc.intensity, 0.0) / working
        if s == MissionStatus.RESPONDING:
            return work
        t = work + DEPLOY_TIME
        if s in (MissionStatus.CREATED, MissionStatus.DISPATCHED):
            t += max(0.0, BOARD_TIME - self._timer) + 2.0
            t += RoadGraph.route_length([tuple(self.vehicle.pos), inc.stand_hint]) * 1.3 / (self.vehicle.max_speed * 0.8)
        elif s == MissionStatus.EN_ROUTE:
            pts = [tuple(self.vehicle.pos)] + [(w.x, w.z) for w in self.vehicle.route]
            t += RoadGraph.route_length(pts) / (self.vehicle.max_speed * 0.8)
        elif s == MissionStatus.ARRIVED:
            t -= self._timer
        return t

    # -- lifecycle ------------------------------------------------------------
    def dispatch(self, world, reason: str = ""):
        """Reserve resources, open the bay door, send the crew to the vehicle."""
        self.vehicle.reserve(self.id)
        self.team.reserve(self.id)
        self.team.vehicle_id = self.vehicle.id
        self.team.state = TeamState.BOARDING
        self.team.progress = 0.0
        self.depot.open_door(self.bay.index)
        inc = self.incident
        inc.status = IncidentStatus.RESPONDING
        inc.waiting_reason = ""
        if inc.dispatched_at is None:
            inc.dispatched_at = world.t
        inc.mission_ids.append(self.id)
        self._go(MissionStatus.DISPATCHED)
        world.add_log(f"{self.vehicle_name} dispatched", f"{SERVICE_NAME[inc.service]} to {inc.site_name}", "alert", (inc.id,))

    def update(self, dt: float, city):
        world, v, team, inc = city.world, self.vehicle, self.team, self.incident
        self._timer += dt
        s = self.status
        deploying, working, done = TEXT[inc.type]

        if s == MissionStatus.DISPATCHED:
            team.progress = min(1.0, self._timer / BOARD_TIME)
            if self._timer >= BOARD_TIME and self.bay.door_progress >= 1.0:
                team.state, team.progress = TeamState.IN_VEHICLE, 0.0
                slot = inc.mission_ids.index(self.id)
                v.set_route(city.plan_departure(v, self.depot, inc, team, slot))
                v.lights_on = True
                self._go(MissionStatus.EN_ROUTE)
                world.add_log(f"{self.vehicle_name} en route", f"to {inc.site_name}", "info", (inc.id,))

        elif s == MissionStatus.EN_ROUTE:
            if not self._door_closed and v.pos[1] < self.bay.door_z - 2.0:
                self.depot.close_door(self.bay.index)
                self._door_closed = True
            if v.arrived:
                if inc.arrived_at is None:
                    inc.arrived_at = world.t
                team.state, team.progress = TeamState.DEPLOYING, 0.0
                self._go(MissionStatus.ARRIVED)
                world.add_log(f"{self.vehicle_name} arrived", deploying, "info", (inc.id,))

        elif s == MissionStatus.ARRIVED:
            team.progress = min(1.0, self._timer / DEPLOY_TIME)
            if self._timer >= DEPLOY_TIME:
                team.state, team.progress = TeamState.DEPLOYED, 1.0
                self._go(MissionStatus.RESPONDING)
                world.add_log(f"{self.vehicle_name} working", working, "info", (inc.id,))

        elif s == MissionStatus.RESPONDING:
            # the City reduces incident.intensity for every unit working; we just wait for it to clear
            if inc.status == IncidentStatus.RESOLVED:
                self._go(MissionStatus.RESOLVED)
                team.state, team.progress = TeamState.STOWING, 0.0

        elif s == MissionStatus.RESOLVED:
            team.progress = min(1.0, self._timer / STOW_TIME)
            if self._timer >= STOW_TIME:
                team.state, team.progress = TeamState.IN_VEHICLE, 0.0
                # nothing free at the depot and another incident is waiting: go straight there, skip the base
                nxt = None if self.depot.available() else city.next_incident_for(inc.service, exclude=inc)
                if nxt is not None:
                    self._redirect(nxt, city)
                    return
                v.set_route(city.plan_return(v, self.depot, inc))
                v.lights_on = False
                self._go(MissionStatus.RETURNING)
                world.add_log(f"{self.vehicle_name} returning", "heading back to base", "info", (inc.id,))

        elif s == MissionStatus.RETURNING:
            if dist(tuple(v.pos), self.depot.access_node) < 12 and not self.bay.door_open_target:
                self.depot.open_door(self.bay.index)
            if v.arrived and self.bay.door_progress >= 1.0:
                self.depot.close_door(self.bay.index)
                v.pos[:] = [self.bay.x, self.bay.park_z]
                v.heading, v.speed = v.home_heading, 0.0
                team.state, team.progress, team.vehicle_id = TeamState.AT_STATION, 0.0, None
                v.release()
                team.release()
                self._go(MissionStatus.COMPLETE)
                world.add_log(f"{self.vehicle_name} back at base", "available again", "ok", (inc.id,))

    def _redirect(self, nxt, city):
        """Hand this vehicle and crew straight to another incident as a new mission (no return to base)."""
        world, v, team, old = city.world, self.vehicle, self.team, self.incident
        m = Mission(world.next_id("mission"), nxt, self.depot, v, team, world.t)
        v.mission_id = team.mission_id = m.id          # the reservation moves over; the unit never becomes free
        world.missions[m.id] = m
        nxt.status = IncidentStatus.RESPONDING
        nxt.waiting_reason = ""
        if nxt.dispatched_at is None:
            nxt.dispatched_at = world.t
        nxt.mission_ids.append(m.id)
        m._door_closed = True                          # not leaving a bay, so no door to manage
        v.set_route(city.plan_redeploy(v, nxt, team, slot=nxt.mission_ids.index(m.id)))
        m._go(MissionStatus.EN_ROUTE)
        self._go(MissionStatus.COMPLETE)
        world.add_log(f"{self.vehicle_name} redirected", f"{old.site_name} -> {nxt.site_name}, skipping base", "alert", (nxt.id,))
        world.add_log("Decision", f"{nxt.site_name}: nearest free unit is already out; sent directly", "agent", (nxt.id,))

    @property
    def is_active(self) -> bool:
        return self.status != MissionStatus.COMPLETE

    def to_dict(self) -> dict:
        return {"id": self.id, "incident": self.incident.id, "vehicle": self.vehicle.id,
                "team": self.team.resource_id, "status": self.status.value}
