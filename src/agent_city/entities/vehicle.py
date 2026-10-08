"""Simulated road vehicle. Pure kinematics - no rendering objects.

Heading is in degrees, 0 = +z, 90 = +x (matches Ursina's rotation_y).
Position is on the road centre line; `lane_offset` shifts it sideways for display
(negative = left, we drive on the left).
"""

import math
import random
from collections import deque
from dataclasses import dataclass

LANE = 0.95


@dataclass
class Waypoint:
    x: float
    z: float
    reverse: bool = False
    precise: bool = False   # must be hit closely (parking spots); otherwise corners are cut


def _angle_diff(a: float, b: float) -> float:
    return (a - b + 180.0) % 360.0 - 180.0


class Vehicle:
    def __init__(self, vid: str, kind: str, pos, heading=0.0, max_speed=5.0,
                 lane_offset=-LANE, color="#cc4444", length=1.9, width=0.95):
        self.id = vid
        self.kind = kind
        self.pos = [float(pos[0]), float(pos[1])]
        self.heading = heading
        self.speed = 0.0
        self.max_speed = max_speed
        self.lane_offset = lane_offset
        self.color = color
        self.length = length
        self.width = width
        self.route: deque[Waypoint] = deque()
        self.yields_to_traffic = True
        # wandering (background traffic)
        self.graph = None
        self._prev = None
        self._node = None

    # -- helpers --------------------------------------------------------
    @property
    def forward(self):
        r = math.radians(self.heading)
        return math.sin(r), math.cos(r)

    @property
    def right(self):
        r = math.radians(self.heading)
        return math.cos(r), -math.sin(r)

    @property
    def render_pos(self) -> tuple[float, float]:
        rx, rz = self.right
        return self.pos[0] + rx * self.lane_offset, self.pos[1] + rz * self.lane_offset

    @property
    def arrived(self) -> bool:
        return not self.route

    def set_route(self, waypoints):
        self.route = deque(waypoints)

    def start_wandering(self, graph, node, prev=None):
        self.graph, self._node, self._prev = graph, node, prev
        self._refill()

    def _refill(self):
        while len(self.route) < 2:
            nbrs = [n for n in self.graph.neighbors(self._node) if n != self._prev] or [self._prev]
            if self._prev is not None and len(nbrs) > 1:
                # prefer going straight on
                px, pz = self._prev
                nx, nz = self._node
                straight = (2 * nx - px, 2 * nz - pz)
                if straight in nbrs and random.random() < 0.55:
                    nbrs = [straight]
            nxt = random.choice(nbrs)
            self.route.append(Waypoint(*nxt))
            self._prev, self._node = self._node, nxt

    # -- simulation ----------------------------------------------------------
    def _blocked(self, others) -> bool:
        fx, fz = self.forward
        rx, rz = self.right
        mx, mz = self.render_pos
        for o in others:
            if o is self or not o.yields_to_traffic or not self.yields_to_traffic:
                continue
            ox, oz = o.render_pos
            dx, dz = ox - mx, oz - mz
            ahead = dx * fx + dz * fz
            side = dx * rx + dz * rz
            if 0.0 < ahead < 3.2 and abs(side) < 0.7:
                return True
        return False

    def update(self, dt: float, others=()):
        if self.graph is not None:
            self._refill()
        if not self.route:
            self.speed = max(0.0, self.speed - 12 * dt)
            return
        wp = self.route[0]
        dx, dz = wp.x - self.pos[0], wp.z - self.pos[1]
        d = math.hypot(dx, dz)
        last = len(self.route) == 1
        tol = 0.15 if (last or wp.precise) else 1.7
        if d < tol:
            self.route.popleft()
            return

        if wp.reverse:
            desired = math.degrees(math.atan2(-dx, -dz))
        else:
            desired = math.degrees(math.atan2(dx, dz))
        err = _angle_diff(desired, self.heading)
        rate = 150.0 * min(1.0, 0.35 + self.speed / max(self.max_speed, 0.1))
        self.heading = (self.heading + max(-rate * dt, min(rate * dt, err))) % 360.0

        target = self.max_speed * max(0.3, 1.0 - min(abs(err), 90.0) / 90.0 * 0.7)
        if wp.reverse:
            target = min(target, 2.4)
        if last or wp.precise:
            target = min(target, 0.7 + math.sqrt(2 * 3.0 * d))
        if (last or wp.precise) and abs(err) > 40.0:
            target = min(target, max(0.4, 0.45 * d))     # slow enough that the turning circle fits the target
        if self.yields_to_traffic and self._blocked(others):
            target = 0.0
        accel = 7.0 if target > self.speed else 14.0
        self.speed += max(-accel * dt, min(accel * dt, target - self.speed))

        step = min(self.speed * dt, d)
        sign = -1.0 if wp.reverse else 1.0
        fx, fz = self.forward
        self.pos[0] += fx * step * sign
        self.pos[1] += fz * step * sign
