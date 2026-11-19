"""Z3-backed solver engine for symbolic execution.

The engine wraps the raw z3py solver with four practical accelerations:

* tactic chains: named preprocessing + solver pipelines instead of the bare
  default solver, selected per constraint kind;
* result cache: path constraints reachable from multiple branches are checked
  only once, keyed by a canonical representation of the asserted formulas;
* timeouts: every stage gets a bounded budget so a single hard query cannot
  stall the whole exploration;
* staged degradation: on timeout / unknown the engine falls back through
  cheaper-to-stronger tactic chains and finally the generic SMT solver.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Optional, Sequence

import z3


class Status(str, Enum):
    SAT = "sat"
    UNSAT = "unsat"
    UNKNOWN = "unknown"


@dataclass
class SolveResult:
    """Outcome of one :meth:`SolverEngine.check` call."""

    status: Status
    model: Optional[dict[str, object]] = None
    elapsed_ms: float = 0.0
    source: str = "solver"  # "cache" or the stage that produced the result
    timed_out: bool = False
    stages_tried: list[str] = field(default_factory=list)

    @property
    def sat(self) -> bool:
        return self.status is Status.SAT


@dataclass
class EngineStats:
    """Aggregate counters useful when tuning exploration parameters."""

    queries: int = 0
    cache_hits: int = 0
    timeouts: int = 0
    fallback_steps: int = 0
    solve_time_ms: float = 0.0

    @property
    def cache_hit_rate(self) -> float:
        return self.cache_hits / self.queries if self.queries else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "queries": self.queries,
            "cache_hits": self.cache_hits,
            "cache_hit_rate": round(self.cache_hit_rate, 4),
            "timeouts": self.timeouts,
            "fallback_steps": self.fallback_steps,
            "solve_time_ms": round(self.solve_time_ms, 3),
        }


def _build_tactic(steps: Sequence[str]) -> z3.Tactic:
    """Build a tactic chain from a list of z3 tactic names.

    Unknown tactic names are skipped instead of aborting engine construction,
    so the same configuration works across Z3 builds with different tactic
    availability.
    """

    valid: list[z3.Tactic] = []
    for name in steps:
        try:
            valid.append(z3.Tactic(name))
        except z3.Z3Exception:
            continue
    if not valid:
        return z3.Tactic("default")
    if len(valid) == 1:
        return valid[0]
    return z3.Then(*valid)


# Ordered cheapest-first so the degradation ladder walks light to heavy.
DEFAULT_PRESETS: dict[str, list[str]] = {
    "qfbv-light": [
        "simplify",
        "solve-eqs",
        "bit-blast",
        "sat",
    ],
    "qfbv": [
        "simplify",
        "ctx-simplify",
        "solve-eqs",
        "max-bv-sharing",
        "bit-blast",
        "sat",
    ],
    "arith": [
        "simplify",
        "solve-eqs",
        "lia",
    ],
    "smt": [
        "default",
    ],
}


@dataclass
class EngineConfig:
    """Knobs for :class:`SolverEngine`.

    ``tactics`` lists the degradation ladder: each entry is a preset name in
    :data:`DEFAULT_PRESETS` (or a custom name registered through
    ``extra_presets``). Stages are tried in order until one returns sat/unsat
    or the budgets run out.
    """

    tactics: Sequence[str] = ("qfbv-light", "qfbv", "smt")
    timeout_ms: int = 1000
    cache_size: int = 4096
    use_cache: bool = True
    extra_presets: dict[str, list[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_ms <= 0:
            raise ValueError("timeout_ms must be positive")
        if self.cache_size <= 0:
            raise ValueError("cache_size must be positive")
        if not self.tactics:
            raise ValueError("at least one tactic stage is required")


class SolverEngine:
    """Cached, timeout-bounded, tactic-aware symbolic-execution solver."""

    def __init__(self, config: Optional[EngineConfig] = None) -> None:
        self.config = config or EngineConfig()
        presets = {**DEFAULT_PRESETS, **self.config.extra_presets}
        missing = [name for name in self.config.tactics if name not in presets]
        if missing:
            raise KeyError(f"unknown tactic presets: {', '.join(missing)}")
        self._stages: list[tuple[str, z3.Tactic]] = [
            (name, _build_tactic(presets[name])) for name in self.config.tactics
        ]
        self._cache: OrderedDict[str, tuple[Status, Optional[dict[str, object]]]] = OrderedDict()
        self.stats = EngineStats()
        self._lock = threading.Lock()

    @staticmethod
    def constraint_key(constraints: Iterable[z3.BoolRef]) -> str:
        """Canonical cache key for a multiset of path constraints."""

        return "\x00".join(sorted(c.sexpr() for c in constraints))

    @staticmethod
    def _model_to_dict(solver: z3.Solver) -> dict[str, object]:
        model = solver.model()
        values: dict[str, object] = {}
        for decl in model.decls():
            values[decl.name()] = model[decl]
        return values

    def cache_info(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._cache), "capacity": self.config.cache_size}

    def clear_cache(self) -> None:
        with self._lock:
            self._cache.clear()

    def _store(
        self, key: str, status: Status, model: Optional[dict[str, object]]
    ) -> None:
        self._cache[key] = (status, model)
        self._cache.move_to_end(key)
        while len(self._cache) > self.config.cache_size:
            self._cache.popitem(last=False)

    def check(
        self, constraints: Sequence[z3.BoolRef]
    ) -> SolveResult:
        """Check satisfiability of ``constraints`` with cache and fallback."""

        start = time.perf_counter()
        key = self.constraint_key(constraints)
        with self._lock:
            self.stats.queries += 1
            if self.config.use_cache and key in self._cache:
                cached_status, cached_model = self._cache[key]
                self._cache.move_to_end(key)
                self.stats.cache_hits += 1
                self.stats.solve_time_ms += (time.perf_counter() - start) * 1000.0
                return SolveResult(
                    status=cached_status,
                    model=cached_model,
                    elapsed_ms=(time.perf_counter() - start) * 1000.0,
                    source="cache",
                )

        stages_tried: list[str] = []
        timed_out = False
        last_solver: Optional[z3.Solver] = None

        for index, (name, tactic) in enumerate(self._stages):
            # Each later stage receives the remaining budget; the final stage
            # owns whatever is left so the overall call cannot overrun by more
            # than one stage's check() granularity.
            remaining = max(1, self.config.timeout_ms - int((time.perf_counter() - start) * 1000))
            if index < len(self._stages) - 1:
                stage_budget = max(1, remaining // (len(self._stages) - index))
            else:
                stage_budget = remaining

            solver = tactic.solver()
            solver.set(timeout=stage_budget)
            solver.add(*constraints)
            stages_tried.append(name)
            z3_status = solver.check()
            last_solver = solver

            if z3_status == z3.sat:
                model = self._model_to_dict(solver)
                result = SolveResult(
                    Status.SAT,
                    model=model,
                    elapsed_ms=(time.perf_counter() - start) * 1000.0,
                    source=name,
                    stages_tried=stages_tried,
                )
                with self._lock:
                    self._store(key, Status.SAT, model)
                    self.stats.solve_time_ms += result.elapsed_ms
                return result

            if z3_status == z3.unsat:
                result = SolveResult(
                    Status.UNSAT,
                    model=None,
                    elapsed_ms=(time.perf_counter() - start) * 1000.0,
                    source=name,
                    stages_tried=stages_tried,
                )
                with self._lock:
                    self._store(key, Status.UNSAT, None)
                    self.stats.solve_time_ms += result.elapsed_ms
                return result

            # unknown: typically a timeout/cancel, degrade to the next stage.
            reason = str(solver.reason_unknown())
            timed_out = "timeout" in reason or "cancel" in reason
            with self._lock:
                self.stats.timeouts += int(timed_out)
                self.stats.fallback_steps += 1

        assert last_solver is not None
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        with self._lock:
            self.stats.solve_time_ms += elapsed_ms
            # unknown is never cached: a later call with a larger budget may
            # still decide the formula.
        return SolveResult(
            Status.UNKNOWN,
            model=None,
            elapsed_ms=elapsed_ms,
            source=stages_tried[-1],
            timed_out=timed_out,
            stages_tried=stages_tried,
        )


def solve(
    constraints: Sequence[z3.BoolRef], config: Optional[EngineConfig] = None
) -> SolveResult:
    """Convenience one-shot wrapper around :class:`SolverEngine`."""

    return SolverEngine(config).check(constraints)
