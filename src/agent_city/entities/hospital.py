from entities.building import Building


class Hospital(Building):
    """Placeholder for the ambulance service (not dispatchable yet)."""

    def __init__(self, bid: str, name: str, block_center, color="#eef1f4"):
        super().__init__(bid, "hospital", name, block_center, (8.0, 6.0, 4.6), color)
        cx, cz = block_center
        self.access_node = (cx, cz - 7.0)
        self.front_point = (cx, cz - 3.9)
        self.ambulances = 2
