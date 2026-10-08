from entities.building import Building


class Substation(Building):
    """Placeholder for the power grid (no outage scenario yet)."""

    def __init__(self, bid: str, name: str, block_center, color="#8d9399"):
        super().__init__(bid, "substation", name, block_center, (7.6, 7.0, 2.2), color)
        cx, cz = block_center
        self.access_node = (cx, cz - 7.0)
        self.front_point = (cx, cz - 4.2)
        self.online = True
