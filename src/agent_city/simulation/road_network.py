"""Road graph + A* routing. Nodes are plain (x, z) points on road centre lines."""

import heapq
import math

Point = tuple[float, float]


def dist(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


class RoadGraph:
    def __init__(self):
        self._adj: dict[Point, set[Point]] = {}

    # -- construction -------------------------------------------------
    def add_road(self, a: Point, b: Point):
        self._adj.setdefault(a, set()).add(b)
        self._adj.setdefault(b, set()).add(a)

    @classmethod
    def grid(cls, lines: list[float], mids: list[float]) -> "RoadGraph":
        """Square grid of roads along `lines` (both axes), with extra nodes at `mids`
        so buildings between intersections get their own access point."""
        g = cls()
        stops = sorted(lines + mids)
        for line in lines:
            for a, b in zip(stops, stops[1:]):
                g.add_road((a, line), (b, line))  # east-west road at z=line
                g.add_road((line, a), (line, b))  # north-south road at x=line
        return g

    # -- queries ------------------------------------------------------
    @property
    def nodes(self) -> list[Point]:
        return list(self._adj)

    @property
    def edges(self) -> list[tuple[Point, Point]]:
        return [(a, b) for a, ns in self._adj.items() for b in ns if a < b]

    def neighbors(self, n: Point) -> list[Point]:
        return sorted(self._adj[n])

    def nearest_node(self, p: Point) -> Point:
        return min(self._adj, key=lambda n: dist(n, p))

    def calculate_route(self, start: Point, destination: Point) -> list[Point]:
        """A* from the nodes nearest to start/destination. Returns waypoints incl. both ends."""
        s, d = self.nearest_node(start), self.nearest_node(destination)
        open_heap = [(dist(s, d), 0.0, s)]
        came: dict[Point, Point] = {}
        best = {s: 0.0}
        while open_heap:
            _, g, cur = heapq.heappop(open_heap)
            if cur == d:
                path = [cur]
                while cur in came:
                    cur = came[cur]
                    path.append(cur)
                return path[::-1]
            if g > best.get(cur, math.inf):
                continue
            for nxt in self.neighbors(cur):
                ng = g + dist(cur, nxt)
                if ng < best.get(nxt, math.inf):
                    best[nxt] = ng
                    came[nxt] = cur
                    heapq.heappush(open_heap, (ng + dist(nxt, d), ng, nxt))
        raise ValueError(f"no route {start} -> {destination}")

    @staticmethod
    def route_length(points: list[Point]) -> float:
        return sum(dist(a, b) for a, b in zip(points, points[1:]))
