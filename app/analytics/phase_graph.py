from __future__ import annotations
from dataclasses import dataclass

# directed graph of reproductive phases

@dataclass(frozen=True)
class PhaseNode:
    phase: str
    start: int
    length: int
    training_kind: str

    @property
    def end(self) ->int:
        return self.start + self.length -1

    def contains(self, day:int) -> bool:
        if self.start <= day <= self.end:
            return True
        return False

@dataclass(frozen=True)
class PhaseTransition:
    target: str
    restarts_cycle: bool


class PhaseGraph:
    def __init__(self, unit:str):
        self.unit = unit
        self._nodes: dict[str, PhaseNode] = {}
        self._edges: dict[str, PhaseTransition] = {}

        self.first = None

    def add_phase(self, node:PhaseNode) -> None:
        if node.phase in self._nodes:
            raise ValueError(f'phase {node.phase} already registered')
        self._nodes[node.phase] = node

    def node(self, phase:str) -> PhaseNode:
        if phase not in self._nodes:
            raise ValueError(f"phase {phase} doesnt exist")
        return self._nodes[phase]

    def next_phase(self, phase:str) -> PhaseTransition | None:
        return self._edges.get(phase)

    def connect(self, source: str, target: str, restarts_cycle: bool = False) -> None:
        # Both ends must exist: no edges towards unknown phases.
        for phase in (source, target):
            if phase not in self._nodes:
                raise ValueError(f"phase {phase} does not exist")
        # Domain rule: every phase leads to exactly one next phase.
        if source in self._edges:
            raise ValueError(f"phase {source} already has a next phase")
        self._edges[source] = PhaseTransition(target, restarts_cycle)