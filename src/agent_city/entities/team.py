from enum import Enum

from simulation.resources import Resource


class TeamState(str, Enum):
    AT_STATION = "AT_STATION"
    BOARDING = "BOARDING"        # running from the station to the vehicle
    IN_VEHICLE = "IN_VEHICLE"
    DEPLOYING = "DEPLOYING"      # climbing out and walking to the scene
    DEPLOYED = "DEPLOYED"        # working at the scene
    STOWING = "STOWING"          # walking back to the vehicle


class Team(Resource):
    """A crew of people. `progress` (0..1) animates the current walking state."""

    def __init__(self, tid: str, role: str, station_id: str, size: int = 4):
        self._init_resource(tid)
        self.role = role
        self.station_id = station_id
        self.size = size
        self.state = TeamState.AT_STATION
        self.progress = 0.0
        self.vehicle_id: str | None = None
        self.scene_positions: list[tuple[float, float]] = []   # where each member works
        self.station_start: tuple[float, float] | None = None  # where boarding starts
