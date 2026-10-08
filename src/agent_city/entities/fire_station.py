from entities.depot import Depot


class FireStation(Depot):
    def __init__(self, block_center, n_engines: int = 3):
        super().__init__("fire_station", "fire_station", "Fire Station", block_center, service="fire",
                         n_units=n_engines, vehicle_kind="fire_engine", vehicle_prefix="engine",
                         crew_prefix="fire_crew", crew_role="firefighters")
