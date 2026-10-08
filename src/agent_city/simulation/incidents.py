from dataclasses import dataclass, field
from enum import Enum


class IncidentType(str, Enum):
    FIRE = "FIRE"
    THEFT = "THEFT"
    FLOOD = "FLOOD"          # natural calamity


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"

    def escalate(self) -> "Severity":
        return {"LOW": Severity.MEDIUM, "MEDIUM": Severity.HIGH, "HIGH": Severity.HIGH}[self.value]


class IncidentStatus(str, Enum):
    ACTIVE = "ACTIVE"          # reported, nobody on the way
    RESPONDING = "RESPONDING"  # at least one unit assigned
    RESOLVED = "RESOLVED"


# which depot answers which kind of incident
SERVICE_FOR = {IncidentType.FIRE: "fire", IncidentType.THEFT: "police", IncidentType.FLOOD: "rescue"}
SERVICE_NAME = {"fire": "Fire Team", "police": "Police", "rescue": "Rescue Team"}
# seconds one unit needs to clear a full-intensity incident (more units work faster)
WORK_TIME = {IncidentType.FIRE: 16.0, IncidentType.THEFT: 11.0, IncidentType.FLOOD: 18.0}
START_INTENSITY = {Severity.LOW: 0.45, Severity.MEDIUM: 0.7, Severity.HIGH: 1.0}
UNITS_NEEDED = {Severity.LOW: 1, Severity.MEDIUM: 1, Severity.HIGH: 2}
ESCALATE_AFTER = 45.0      # an unattended incident gets one level worse after this long


@dataclass
class Incident:
    id: str
    type: IncidentType
    severity: Severity
    building_id: str
    site_name: str
    pos: tuple[float, float]         # centre of the affected site
    status: IncidentStatus = IncidentStatus.ACTIVE
    intensity: float = 1.0           # 1 = at its worst, 0 = cleared
    created_at: float = 0.0
    dispatched_at: float | None = None
    arrived_at: float | None = None
    resolved_at: float | None = None
    escalated_at: float | None = None
    stand_hint: tuple[float, float] = (0.0, 0.0)   # road node serving the building
    mission_ids: list[str] = field(default_factory=list)
    waiting_reason: str = ""

    @property
    def is_open(self) -> bool:
        return self.status != IncidentStatus.RESOLVED

    @property
    def service(self) -> str:
        return SERVICE_FOR[self.type]

    @property
    def units_needed(self) -> int:
        return UNITS_NEEDED[self.severity]

    @property
    def work_time(self) -> float:
        return WORK_TIME[self.type]

    @property
    def label(self) -> str:
        name = self.site_name.upper()
        return {IncidentType.FIRE: f"{name} FIRE", IncidentType.THEFT: f"THEFT · {name}",
                IncidentType.FLOOD: f"FLOOD · {name}"}[self.type]
