"""Tiny symbolic-execution machine built on :mod:`symbolic_exec.engine`.

It models a straight-line / branching program over fixed-width bit-vector
variables. Every branch forks the path, each path keeps its own accumulated
path condition, and feasibility is queried through the cached
:class:`~symbolic_exec.engine.SolverEngine` so shared prefixes are never
solved twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import z3

from symbolic_exec.engine import SolveResult, SolverEngine


@dataclass
class Path:
    """One explored execution path."""

    name: str
    constraints: list[z3.BoolRef] = field(default_factory=list)
    result: Optional[SolveResult] = None


class SymbolicMachine:
    """Symbolic state for a single program entry point."""

    def __init__(self, engine: SolverEngine, bit_width: int = 32) -> None:
        self.engine = engine
        self.bit_width = bit_width
        self.variables: dict[str, z3.BitVecRef] = {}
        self.paths: list[Path] = [Path("path-0")]

    def var(self, name: str, width: Optional[int] = None) -> z3.BitVecRef:
        """Declare (or reuse) a symbolic bit-vector variable."""

        if name not in self.variables:
            self.variables[name] = z3.BitVec(name, width or self.bit_width)
        return self.variables[name]

    @staticmethod
    def const(value: int, width: int = 32) -> z3.BitVecRef:
        return z3.BitVecVal(value, width)

    def _fork(self, condition: z3.BoolRef) -> list[Path]:
        """Split every live path on ``condition`` and prune infeasible arms."""

        live: list[Path] = []
        for path in self.paths:
            for label, guard in (("t", condition), ("f", z3.Not(condition))):
                child = Path(
                    name=f"{path.name}/{label}",
                    constraints=[*path.constraints, guard],
                )
                child.result = self.engine.check(child.constraints)
                if child.result.sat:
                    live.append(child)
        self.paths = live
        return live

    def branch_if(
        self, condition: z3.BoolRef, then_body=None, else_body=None
    ) -> None:
        """Symbolic ``if``: both arms are explored, infeasible ones pruned."""

        forked = self._fork(condition)
        for index, path in enumerate(forked):
            body = then_body if path.name.endswith("/t") else else_body
            if body is not None:
                body(path, index)

    def feasible_paths(self) -> list[Path]:
        """Return every path whose accumulated condition is satisfiable."""

        for path in self.paths:
            if path.result is None:
                path.result = self.engine.check(path.constraints)
        return [path for path in self.paths if path.result and path.result.sat]

    def add_assumption(self, constraint: z3.BoolRef) -> None:
        """Add a global assumption (e.g. an input precondition) to all paths."""

        for path in self.paths:
            path.constraints.append(constraint)
