"""Shared resource bookkeeping: anything a mission can reserve (engines, crews, ...)."""

from enum import Enum


class ResourceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    DEPLOYED = "DEPLOYED"


class Resource:
    """Mixin for reservable things. Status only changes through reserve()/release()."""

    resource_id: str
    status: ResourceStatus
    mission_id: str | None

    def _init_resource(self, resource_id: str):
        self.resource_id = resource_id
        self.status = ResourceStatus.AVAILABLE
        self.mission_id = None

    @property
    def is_available(self) -> bool:
        return self.status == ResourceStatus.AVAILABLE

    def reserve(self, mission_id: str):
        if not self.is_available:
            raise RuntimeError(f"{self.resource_id} is not available")
        self.status = ResourceStatus.DEPLOYED
        self.mission_id = mission_id

    def release(self):
        self.status = ResourceStatus.AVAILABLE
        self.mission_id = None


def first_available(resources):
    return next((r for r in resources if r.is_available), None)
