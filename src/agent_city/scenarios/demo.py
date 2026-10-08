"""Ready-made situations for the user: random incidents and a multi-incident crisis."""

import random

from simulation.city import INCIDENT_SITES
from simulation.incidents import IncidentType, Severity


def random_incident(city, rng=random):
    itype = rng.choice(list(IncidentType))
    sev = rng.choices(list(Severity), weights=[3, 4, 3])[0]
    return city.create_incident(itype, rng.choice(INCIDENT_SITES), sev)


def crisis(city):
    """More demand than units: two HIGH fires (need 4 engines, 3 exist), a HIGH flood, a theft, a minor fire."""
    return [
        city.create_incident(IncidentType.FIRE, "warehouse", Severity.HIGH),
        city.create_incident(IncidentType.THEFT, "west_offices", Severity.MEDIUM),
        city.create_incident(IncidentType.FLOOD, "park", Severity.HIGH),
        city.create_incident(IncidentType.FIRE, "north_houses", Severity.HIGH),
        city.create_incident(IncidentType.FIRE, "substation", Severity.LOW),
    ]
