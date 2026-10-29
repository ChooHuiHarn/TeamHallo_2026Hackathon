"""A* pathfinding on the warehouse grid (4-connected, unit cost)."""
from __future__ import annotations

import heapq
import itertools
from typing import AbstractSet, Optional

from .warehouse import Cell, Warehouse


def manhattan(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


def astar(
    warehouse: Warehouse,
    start: Cell,
    goal: Cell,
    extra_blocked: Optional[AbstractSet[Cell]] = None,
) -> Optional[list[Cell]]:
    """Return the shortest path from `start` to `goal` (both included) or None.

    Blocked cells are the warehouse obstacles plus `extra_blocked` (for example
    cells currently occupied by other robots). The start and goal cells are
    always allowed, even if listed as blocked. Ties are broken deterministically
    (lowest f, then lowest h, then insertion order), so the same inputs always
    give the same path.
    """
    extra = extra_blocked or frozenset()
    if not warehouse.in_bounds(*start) or not warehouse.in_bounds(*goal):
        return None
    if start == goal:
        return [start]

    def passable(cell: Cell) -> bool:
        if cell == goal or cell == start:
            return True
        return cell not in warehouse.blocked and cell not in extra

    if goal in warehouse.blocked:
        return None

    counter = itertools.count()
    open_heap: list[tuple[int, int, int, Cell]] = []
    h0 = manhattan(start, goal)
    heapq.heappush(open_heap, (h0, h0, next(counter), start))
    came_from: dict[Cell, Cell] = {}
    g_score: dict[Cell, int] = {start: 0}
    closed: set[Cell] = set()

    while open_heap:
        _, _, _, current = heapq.heappop(open_heap)
        if current in closed:
            continue
        if current == goal:
            path = [current]
            while current in came_from:
                current = came_from[current]
                path.append(current)
            path.reverse()
            return path
        closed.add(current)
        for nxt in warehouse.neighbors(current):
            if nxt in closed or not passable(nxt):
                continue
            tentative = g_score[current] + 1
            if tentative < g_score.get(nxt, 1 << 30):
                g_score[nxt] = tentative
                came_from[nxt] = current
                h = manhattan(nxt, goal)
                heapq.heappush(open_heap, (tentative + h, h, next(counter), nxt))
    return None


def path_length(path: Optional[list[Cell]]) -> Optional[int]:
    """Number of moves in a path (cells minus one)."""
    return None if path is None else len(path) - 1
