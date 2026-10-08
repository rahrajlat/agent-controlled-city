from entities.depot import Depot


class RescueCentre(Depot):
    """Disaster response: flood rescue trucks and crews."""

    def __init__(self, block_center, n_trucks: int = 2):
        super().__init__("rescue_centre", "rescue_centre", "Rescue Centre", block_center, service="rescue",
                         n_units=n_trucks, vehicle_kind="rescue_truck", vehicle_prefix="rescue_truck",
                         crew_prefix="rescue_team", crew_role="rescuers", crew_size=3)
