"""Warehouse layout: a 10 x 8 grid with six zones and blocked cells.

Coordinates are (x, y) with x = column (0..9) and y = row (0..7); y = 0 is the
top row. The default layout:

        0 1 2 3 4 5 6 7 8 9
    y0  R R . S S S S . P P      R Receiving   S Storage   P Picking
    y1  R R . S S S S . P P
    y2  . . . . . . . . . .      # obstacle (blocked cell)
    y3  . . # . . . . # . .
    y4  . . # . . . . # . .      K Packing   H Shipping   C Charging
    y5  . . . . . . . . . .
    y6  C C C . K K . H H H
    y7  C C C . K K . H H H

Zone cells are walkable floor. Corridors (rows 2-5 and columns 2 / 7) keep
robots moving between zones.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from . import config as C

Cell = tuple[int, int]


@dataclass(frozen=True)
class Zone:
    id: str
    name: str
    x: int
    y: int
    w: int
    h: int
    color: str
    dock: Cell
    description: str

    def cells(self) -> list[Cell]:
        return [(cx, cy) for cy in range(self.y, self.y + self.h) for cx in range(self.x, self.x + self.w)]

    def contains(self, x: int, y: int) -> bool:
        return self.x <= x < self.x + self.w and self.y <= y < self.y + self.h

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "x": self.x, "y": self.y, "w": self.w, "h": self.h,
            "color": self.color, "dock": {"x": self.dock[0], "y": self.dock[1]},
            "description": self.description,
        }


DEFAULT_ZONES = [
    Zone("receiving", "Receiving Area", 0, 0, 2, 2, "#b8d4dd", (1, 1), "Incoming packages arrive here."),
    Zone("storage", "Storage Area", 3, 0, 4, 2, "#f1d3b3", (4, 1), "Shelves and inventory are stored here."),
    Zone("picking", "Picking Station", 8, 0, 2, 2, "#d6e4c3", (8, 1), "Items are collected for orders."),
    Zone("packing", "Packing Station", 4, 6, 2, 2, "#e6d0e0", (4, 6), "Packages are packed and prepared."),
    Zone("shipping", "Shipping Area", 7, 6, 3, 2, "#c9d3e8", (8, 6), "Completed packages wait for dispatch."),
    Zone("charging", "Charging Station", 0, 6, 3, 2, "#f3e6a8", (1, 6), "Robots recharge here (6 bays)."),
]

DEFAULT_OBSTACLES: list[Cell] = [(2, 3), (2, 4), (7, 3), (7, 4)]


class Warehouse:
    def __init__(
        self,
        width: int = C.GRID_WIDTH,
        height: int = C.GRID_HEIGHT,
        zones: Optional[Iterable[Zone]] = None,
        obstacles: Optional[Iterable[Cell]] = None,
    ):
        self.width = width
        self.height = height
        self.zones = list(zones if zones is not None else DEFAULT_ZONES)
        self.blocked: set[Cell] = set(obstacles if obstacles is not None else DEFAULT_OBSTACLES)

    # ------------------------------------------------------------------ queries
    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def is_blocked(self, x: int, y: int) -> bool:
        return (x, y) in self.blocked

    def zone_by_id(self, zone_id: str) -> Optional[Zone]:
        for zone in self.zones:
            if zone.id == zone_id:
                return zone
        return None

    def zone_at(self, x: int, y: int) -> Optional[Zone]:
        for zone in self.zones:
            if zone.contains(x, y):
                return zone
        return None

    def neighbors(self, cell: Cell) -> list[Cell]:
        """4-connected neighbours in fixed order (N, E, S, W) for determinism."""
        x, y = cell
        result = []
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
            nx, ny = x + dx, y + dy
            if self.in_bounds(nx, ny):
                result.append((nx, ny))
        return result

    def charging_cells(self) -> list[Cell]:
        zone = self.zone_by_id("charging")
        return zone.cells() if zone else []

    # ------------------------------------------------------------------ mutation
    def set_obstacle(self, x: int, y: int, blocked: bool) -> None:
        if blocked:
            self.blocked.add((x, y))
        else:
            self.blocked.discard((x, y))

    # ------------------------------------------------------------------ serialisation
    def to_dict(self) -> dict:
        return {
            "width": self.width,
            "height": self.height,
            "zones": [z.to_dict() for z in self.zones],
            "obstacles": [{"x": x, "y": y} for (x, y) in sorted(self.blocked)],
        }
