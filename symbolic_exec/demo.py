"""End-to-end demo: symbolic branching on top of the cached solver engine."""

from __future__ import annotations

from symbolic_exec.engine import EngineConfig, SolverEngine
from symbolic_exec.machine import SymbolicMachine


def main() -> None:
    engine = SolverEngine(
        EngineConfig(tactics=("qfbv-light", "qfbv", "smt"), timeout_ms=1500)
    )
    machine = SymbolicMachine(engine)

    x = machine.var("x")
    y = machine.var("y")
    machine.add_assumption(x + y == 50)

    machine.branch_if(x > y)
    machine.branch_if(x % 8 == 3)

    feasible = machine.feasible_paths()
    print(f"feasible paths: {len(feasible)}")
    for path in feasible:
        assert path.result is not None
        model = path.result.model or {}
        x_val = model.get("x")
        y_val = model.get("y")
        print(
            f"  {path.name:<14} status={path.result.status.value:<5} "
            f"solved_by={path.result.source:<10} x={x_val} y={y_val}"
        )

    print("\nengine stats:", engine.stats.as_dict())

    shared = feasible[0].constraints
    for _ in range(2):
        engine.check(shared)
    print("after re-checking a shared path condition twice:",
          engine.stats.as_dict())

    tight = SolverEngine(
        EngineConfig(
            tactics=("qfbv-light", "qfbv", "smt"),
            timeout_ms=40,
            use_cache=False,
        )
    )
    from symbolic_exec.constraints import _hard_hash_preimage

    result = tight.check(_hard_hash_preimage())
    print(
        "\nhard preimage with 40ms total budget: "
        f"status={result.status.value} timed_out={result.timed_out} "
        f"stages={result.stages_tried} elapsed={result.elapsed_ms:.1f}ms"
    )


if __name__ == "__main__":
    main()
