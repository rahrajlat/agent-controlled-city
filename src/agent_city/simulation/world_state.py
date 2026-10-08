"""Mutable world state: clock, health, incidents, missions and the activity log."""

from dataclasses import dataclass

TIME_SCALE = 12.0               # sim seconds per real second
CLOCK_START = 19 * 3600 + 30 * 60


@dataclass
class LogEntry:
    clock: str
    title: str
    detail: str
    kind: str = "info"          # info | alert | ok | agent | model_in | model_out
    incidents: tuple = ()       # ids of the incidents this entry is about (cleared from the feed when all are over)
    t: float = 0.0              # simulation time it was logged


def fmt_duration(real_seconds: float) -> str:
    """Duration shown in in-game minutes/seconds."""
    s = int(max(0.0, real_seconds) * TIME_SCALE)
    return f"{s // 60}m {s % 60:02d}s"


class WorldState:
    def __init__(self):
        self.t = 0.0                      # real seconds of simulated time
        self.city_health = 100.0
        self.incidents: dict = {}
        self.missions: dict = {}
        self.log: list[LogEntry] = []
        self.buildings: dict = {}
        self._seq = 0

    def next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}_{self._seq}"

    def clock(self, t: float | None = None) -> str:
        s = int(CLOCK_START + (self.t if t is None else t) * TIME_SCALE)
        return f"{(s // 3600) % 24:02d}:{(s // 60) % 60:02d}"

    @property
    def active_incidents(self) -> int:
        return sum(1 for i in self.incidents.values() if i.is_open)

    def add_log(self, title: str, detail: str, kind: str = "info", incidents: tuple = ()):
        self.log.append(LogEntry(self.clock(), title, detail, kind, tuple(incidents), self.t))
