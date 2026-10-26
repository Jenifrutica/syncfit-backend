"""Directed graph of reproductive phases (menstrual cycle and gestation)."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass


@dataclass(frozen=True)
class PhaseNode:
    phase: str
    start: int  # first day (cycle) or week (gestation) of the phase
    length: int
    training_kind: str  # STRENGTH | LOW_IMPACT | REST

    @property
    def end(self) -> int:
        return self.start + self.length - 1

    def contains(self, position: int) -> bool:
        return self.start <= position <= self.end


@dataclass(frozen=True)
class PhaseTransition:
    target: str
    restarts_cycle: bool = False


class PhaseGraph:
    """Phases are nodes; each phase leads to exactly one next phase.

    `unit` is "day" for the menstrual cycle and "week" for gestation. The last
    phase of a cycle points back to the first one with `restarts_cycle=True`;
    gestation ends in its last trimester.
    """

    def __init__(self, unit: str) -> None:
        self.unit = unit
        self.first: str | None = None
        self._nodes: dict[str, PhaseNode] = {}
        self._edges: dict[str, PhaseTransition] = {}

    def add_phase(self, node: PhaseNode) -> None:
        if node.phase in self._nodes:
            raise ValueError(f"phase {node.phase} already registered")
        self._nodes[node.phase] = node
        if self.first is None:
            self.first = node.phase

    def node(self, phase: str) -> PhaseNode:
        if phase not in self._nodes:
            raise ValueError(f"phase {phase} does not exist")
        return self._nodes[phase]

    def connect(self, source: str, target: str, restarts_cycle: bool = False) -> None:
        for phase in (source, target):
            if phase not in self._nodes:
                raise ValueError(f"phase {phase} does not exist")
        if source in self._edges:
            raise ValueError(f"phase {source} already has a next phase")
        self._edges[source] = PhaseTransition(target, restarts_cycle)

    def next_phase(self, phase: str) -> PhaseTransition | None:
        return self._edges.get(phase)

    def walk(self, start: str | None = None) -> Iterator[str]:
        """Follow the edges from `start` until the chain ends or comes back to a visited phase."""
        current = start or self.first
        if current is None:
            return
        self.node(current)
        seen: set[str] = set()
        while current is not None and current not in seen:
            seen.add(current)
            yield current
            edge = self._edges.get(current)
            current = edge.target if edge else None

    def phase_for(self, position: int) -> PhaseNode:
        """Phase that holds a day/week. Positions past the end stay in the last phase."""
        if position < 1:
            raise ValueError(f"{self.unit} must be positive")
        last: PhaseNode | None = None
        for phase in self.walk():
            last = self._nodes[phase]
            if last.contains(position):
                return last
        if last is None:
            raise ValueError("graph has no phases")
        return last

    def units_until(self, position: int, target: str) -> int:
        """Days/weeks from `position` until `target` starts.

        Follows the edges, wrapping into the next cycle when the last phase
        restarts it. Raises ValueError when `target` can no longer be reached.
        """
        self.node(target)
        current = self.phase_for(position)
        if current.phase == target:
            return 0
        remaining = current.end - position + 1
        phase = current.phase
        visited = {phase}
        while True:
            edge = self._edges.get(phase)
            if edge is None:
                raise ValueError(f"{target} is not reachable from {current.phase}")
            if edge.target == target:
                return remaining
            if edge.target in visited:
                raise ValueError(f"{target} is not reachable from {current.phase}")
            visited.add(edge.target)
            remaining += self._nodes[edge.target].length
            phase = edge.target


def build_cycle_graph(cycle_length: int = 28) -> PhaseGraph:
    """Menstrual cycle: menstrual 1-5, follicular 6-13, ovulatory 14-16, luteal 17+."""
    graph = PhaseGraph("day")
    luteal_length = max(cycle_length - 16, 1)
    graph.add_phase(PhaseNode("MENSTRUAL", 1, 5, "STRENGTH"))
    graph.add_phase(PhaseNode("FOLLICULAR", 6, 8, "STRENGTH"))
    graph.add_phase(PhaseNode("OVULATORY", 14, 3, "LOW_IMPACT"))
    graph.add_phase(PhaseNode("LUTEAL", 17, luteal_length, "STRENGTH"))
    graph.connect("MENSTRUAL", "FOLLICULAR")
    graph.connect("FOLLICULAR", "OVULATORY")
    graph.connect("OVULATORY", "LUTEAL")
    graph.connect("LUTEAL", "MENSTRUAL", restarts_cycle=True)
    return graph


def build_gestation_graph() -> PhaseGraph:
    """Gestation: trimester 1 weeks 1-13, trimester 2 weeks 14-27, trimester 3 week 28+."""
    graph = PhaseGraph("week")
    graph.add_phase(PhaseNode("TRIMESTER_1", 1, 13, "STRENGTH"))
    graph.add_phase(PhaseNode("TRIMESTER_2", 14, 14, "STRENGTH"))
    graph.add_phase(PhaseNode("TRIMESTER_3", 28, 15, "LOW_IMPACT"))
    graph.connect("TRIMESTER_1", "TRIMESTER_2")
    graph.connect("TRIMESTER_2", "TRIMESTER_3")
    return graph


__all__ = [
    "PhaseGraph",
    "PhaseNode",
    "PhaseTransition",
    "build_cycle_graph",
    "build_gestation_graph",
]
