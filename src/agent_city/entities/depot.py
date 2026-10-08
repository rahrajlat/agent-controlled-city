"""A depot is a building that houses a service's vehicles and crews (fire station, police station, ...)."""

from dataclasses import dataclass

from entities.building import Building
from entities.emergency_vehicle import EmergencyVehicle
from entities.team import Team

DOOR_TIME = 1.4
BAY_SPACING = 2.8


@dataclass
class Bay:
    index: int
    x: float
    park_z: float
    door_z: float
    door_open_target: bool = False
    door_progress: float = 0.0     # 0 closed .. 1 open


class Depot(Building):
    """Faces -z (towards the road). Vehicles park nose-out in bays behind a roll-up door."""

    def __init__(self, bid: str, kind: str, name: str, block_center, *, service: str, n_units: int,
                 vehicle_kind: str, vehicle_prefix: str, crew_prefix: str, crew_role: str,
                 crew_size: int = 4, color: str = "#c8c3b8"):
        cx, cz = block_center
        super().__init__(bid, kind, name, block_center, (8.4, 8.4, 2.6), color)
        self.service = service
        self.access_node = (cx, cz - 7.0)
        door_z = cz - 3.8
        self.front_point = (cx, door_z - 0.6)
        self.rect = (cx - 4.2, cx + 4.2, door_z, cz + 4.2)
        self.bays: list[Bay] = []
        self.vehicles: list[EmergencyVehicle] = []
        self.crews: list[Team] = []
        for i in range(n_units):
            bx = cx + (i - (n_units - 1) / 2) * BAY_SPACING
            bay = Bay(i, bx, door_z + 2.5, door_z)
            self.bays.append(bay)
            self.vehicles.append(EmergencyVehicle(f"{vehicle_prefix}_{i + 1}", vehicle_kind, (bx, bay.park_z),
                                                  180.0, bid, i, service))
            crew = Team(f"{crew_prefix}_{i + 1}", crew_role, bid, size=crew_size)
            crew.station_start = (bx + 1.3, bay.park_z + 2.2)
            self.crews.append(crew)

    def update(self, dt: float):
        for b in self.bays:
            target = 1.0 if b.door_open_target else 0.0
            step = dt / DOOR_TIME
            b.door_progress += max(-step, min(step, target - b.door_progress))

    def open_door(self, bay: int):
        self.bays[bay].door_open_target = True

    def close_door(self, bay: int):
        self.bays[bay].door_open_target = False

    def available(self):
        """(vehicle, crew) pairs that are both free."""
        return [(v, c) for v, c in zip(self.vehicles, self.crews) if v.is_available and c.is_available]
