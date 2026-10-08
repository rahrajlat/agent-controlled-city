"""Where crew members are while a mission runs. Shared by every renderer (3D, terminal, ...)."""

import math

from entities.team import TeamState


def _ease(u: float) -> float:
    return u * u * (3 - 2 * u)


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def person_pose(crew, k: int, engine, incident):
    """-> ((x, z), facing_degrees, hop_amount) for crew member k, or None if not visible."""
    state, p = crew.state, crew.progress
    if state == TeamState.BOARDING and engine is not None:
        sx, sz = crew.station_start
        sx += (k - 1.5) * 0.28
        sz += (k % 2) * 0.35
        ex, ez = engine.render_pos
        u = _ease(_clamp01(p * 1.25 - k * 0.04))
        x, z = _lerp(sx, ex, u), _lerp(sz, ez + 0.4, u)
        return (x, z), math.degrees(math.atan2(ex - sx, ez - sz)), 1.0 if u < 1 else 0.0
    if engine is None or not crew.scene_positions:
        return None
    ex, ez = engine.render_pos
    r = engine.right
    door = (ex + r[0] * 1.0 + engine.forward[0] * 0.8, ez + r[1] * 1.0 + engine.forward[1] * 0.8)
    spot = crew.scene_positions[k]
    if state in (TeamState.DEPLOYING, TeamState.STOWING):
        u = _ease(_clamp01(p * 1.3 - k * 0.08))
        if state == TeamState.STOWING:
            u = 1 - u
        x, z = _lerp(door[0], spot[0], u), _lerp(door[1], spot[1], u)
        tgt = spot if state == TeamState.DEPLOYING else door
        return (x, z), math.degrees(math.atan2(tgt[0] - x, tgt[1] - z)), 1.0 if 0.02 < u < 0.98 else 0.0
    face = 0.0
    if incident is not None:
        face = math.degrees(math.atan2(incident.pos[0] - spot[0], incident.pos[1] - spot[1]))
    return spot, face, 0.0
