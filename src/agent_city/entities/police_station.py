from entities.depot import Depot


class PoliceStation(Depot):
    def __init__(self, block_center, n_cars: int = 2):
        super().__init__("police_station", "police_station", "Police Station", block_center, service="police",
                         n_units=n_cars, vehicle_kind="police_car", vehicle_prefix="police_car",
                         crew_prefix="police_team", crew_role="officers", crew_size=2)
