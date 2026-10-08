"""Plain-data buildings. The renderer decides how each `kind` looks."""

from dataclasses import dataclass, field


@dataclass
class Building:
    id: str
    kind: str                      # house | office | shop | warehouse | hospital | fire_station | substation | park
    name: str
    pos: tuple[float, float]       # block centre (x, z)
    size: tuple[float, float, float] = (6.0, 5.0, 3.0)   # footprint w (x), d (z), height
    color: str = "#d9d4c7"
    access_node: tuple[float, float] | None = None       # road node serving this building
    front_point: tuple[float, float] | None = None       # where people stand at its door
    rect: tuple[float, float, float, float] | None = None   # footprint (x0, x1, z0, z1) for effects
    facing_z: int = -1              # which way the front door faces (-1 = towards -z)
    damage: float = 0.0            # 0..1, drives charring in the renderer
    props: dict = field(default_factory=dict)
