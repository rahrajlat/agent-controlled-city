from entities.vehicle import Vehicle
from simulation.resources import Resource


class EmergencyVehicle(Vehicle, Resource):
    """A reservable vehicle that lives in a depot bay."""

    def __init__(self, vid: str, kind: str, home_pos, home_heading, station_id: str, bay_index: int,
                 service: str, color="#d62828"):
        Vehicle.__init__(self, vid, kind, home_pos, heading=home_heading, max_speed=7.5,
                         lane_offset=0.0, color=color, length=3.0, width=1.5)
        self._init_resource(vid)
        self.home_pos = tuple(home_pos)
        self.home_heading = home_heading
        self.station_id = station_id
        self.bay_index = bay_index
        self.service = service            # "fire" | "police" | "rescue"
        self.lights_on = False
        self.yields_to_traffic = False    # emergency vehicles take the centre line

    @property
    def name(self) -> str:
        return self.id.replace("_", " ").title()
