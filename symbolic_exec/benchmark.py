"""Solve-time comparison across solver configurations.

Four configurations are measured on the same constraint sets:

* baseline: a bare ``z3.Solver`` with no tactic chain or cache (only a guard
  timeout so the benchmark itself cannot hang);
* tactics:  the tactic degradation ladder with per-stage timeouts;
* cached:   the same ladder plus an LRU result cache, exercised with repeated
  identical queries to expose cache-hit savings;
* fallback: a deliberately tight timeout on the cheap stages so the
  degradation ladder and unknown handling are observable.
"""

from __future__ import annotations

import argparse
import csv
import statistics
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import z3

from symbolic_exec.constraints import CASES, ConstraintCase
from symbolic_exec.engine import EngineConfig, SolverEngine, Status


@dataclass
class Row:
    case: str
    mode: str
    run: int
    status: str
    elapsed_ms: float
    source: str
    stages: str


def _baseline_once(constraints: list[z3.BoolRef], timeout_ms: int) -> Row:
    solver = z3.Solver()
    # Guard timeout only: the point of the baseline is to measure the bare
    # default solver; without a bound a single hard case stalls the whole run.
    solver.set(timeout=timeout_ms)
    solver.add(*constraints)
    start = time.perf_counter()
    status = solver.check()
    elapsed = (time.perf_counter() - start) * 1000.0
    return Row(
        "?", "baseline", 0, str(status), elapsed, "z3.Solver(guard-timeout)", "default"
    )


def _engine_once(
    case_name: str, mode: str, run: int, engine: SolverEngine,
    constraints: list[z3.BoolRef],
) -> Row:
    result = engine.check(constraints)
    return Row(
        case=case_name,
        mode=mode,
        run=run,
        status=result.status.value,
        elapsed_ms=result.elapsed_ms,
        source=result.source,
        stages=">".join(result.stages_tried),
    )


def run_benchmark(
    repeats: int = 3,
    timeout_ms: int = 2000,
    fallback_timeout_ms: int = 80,
    baseline_timeout_ms: Optional[int] = None,
    cases: Optional[list[ConstraintCase]] = None,
) -> list[Row]:
    cases = cases or CASES
    rows: list[Row] = []
    cache_stats: dict[str, dict[str, object]] = {}
    baseline_timeout_ms = (
        timeout_ms if baseline_timeout_ms is None else baseline_timeout_ms
    )

    tactic_config = EngineConfig(
        tactics=("qfbv-light", "qfbv", "smt"),
        timeout_ms=timeout_ms,
        use_cache=False,
    )
    cached_config = EngineConfig(
        tactics=("qfbv-light", "qfbv", "smt"),
        timeout_ms=timeout_ms,
        use_cache=True,
    )
    fallback_config = EngineConfig(
        tactics=("qfbv-light", "qfbv", "smt"),
        timeout_ms=fallback_timeout_ms,
        use_cache=False,
    )

    for case in cases:
        # Build once: the cached mode re-queries the identical constraint
        # objects, matching how a symbolic machine re-checks a shared path
        # prefix from several branches.
        shared_constraints = case.build()

        baseline_row = _baseline_once(case.build(), baseline_timeout_ms)
        baseline_row.case = case.name
        rows.append(baseline_row)

        tactic_engine = SolverEngine(tactic_config)
        for run in range(repeats):
            rows.append(
                _engine_once(case.name, "tactics", run, tactic_engine, case.build())
            )

        cached_engine = SolverEngine(cached_config)
        for run in range(repeats):
            rows.append(
                _engine_once(
                    case.name, "cached", run, cached_engine, shared_constraints
                )
            )
        cache_stats[case.name] = cached_engine.stats.as_dict()

        fallback_engine = SolverEngine(fallback_config)
        rows.append(
            _engine_once(
                case.name, "fallback", 0, fallback_engine, case.build()
            )
        )

    return rows, cache_stats


def _aggregate(rows: list[Row]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str], list[Row]] = {}
    for row in rows:
        grouped.setdefault((row.case, row.mode), []).append(row)

    summary: list[dict[str, object]] = []
    for (case_name, mode), bucket in sorted(grouped.items()):
        times = [row.elapsed_ms for row in bucket]
        head = bucket[0]
        summary.append(
            {
                "case": case_name,
                "mode": mode,
                "status": head.status,
                "runs": len(bucket),
                "min_ms": round(min(times), 2),
                "median_ms": round(statistics.median(times), 2),
                "max_ms": round(max(times), 2),
                "source": head.source,
                "stages": head.stages,
            }
        )
    return summary


def _print_table(summary: list[dict[str, object]]) -> None:
    headers = (
        "case", "mode", "status", "runs", "min_ms",
        "median_ms", "max_ms", "source/stages",
    )
    widths = {header: len(header) for header in headers}
    rendered = []
    for item in summary:
        line = {
            **item,
            "source/stages": f"{item['source']} [{item['stages']}]",
        }
        rendered.append(line)
        for header in headers:
            widths[header] = max(widths[header], len(str(line[header])))

    def fmt(line: dict[str, object]) -> str:
        return "  ".join(str(line[header]).ljust(widths[header]) for header in headers)

    print(fmt({header: header for header in headers}))
    print("  ".join("-" * widths[header] for header in headers))
    for line in rendered:
        print(fmt(line))


def _write_csv(rows: list[Row], path: Path) -> None:
    with path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            ["case", "mode", "run", "status", "elapsed_ms", "source", "stages"]
        )
        for row in rows:
            writer.writerow(
                [
                    row.case,
                    row.mode,
                    row.run,
                    row.status,
                    f"{row.elapsed_ms:.4f}",
                    row.source,
                    row.stages,
                ]
            )


def _write_markdown(summary: list[dict[str, object]], path: Path) -> None:
    lines = [
        "# Solve-time comparison",
        "",
        "Times in milliseconds per `check` call; `cached` run 0 is a miss and "
        "later runs are cache hits on identical constraint sets.",
        "",
        "| case | mode | status | runs | min | median | max | source / stages |",
        "|---|---|---|---:|---:|---:|---:|---|",
    ]
    for item in summary:
        lines.append(
            "| {case} | {mode} | {status} | {runs} | {min_ms} | {median_ms} | "
            "{max_ms} | {source} `{stages}` |".format(**item)
        )
    path.write_text("\n".join(lines) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=3)
    parser.add_argument("--timeout-ms", type=int, default=2000)
    parser.add_argument("--fallback-timeout-ms", type=int, default=80)
    parser.add_argument(
        "--baseline-timeout-ms",
        type=int,
        default=None,
        help="guard timeout for the bare z3.Solver baseline (defaults to --timeout-ms)",
    )
    parser.add_argument("--case", action="append", help="run only this case (repeatable)")
    parser.add_argument("--csv", type=Path, help="write per-run raw timings")
    parser.add_argument("--markdown", type=Path, help="write aggregated markdown table")
    args = parser.parse_args()

    selected = (
        [case for case in CASES if case.name in set(args.case)]
        if args.case
        else CASES
    )
    rows, cache_stats = run_benchmark(
        repeats=args.repeats,
        timeout_ms=args.timeout_ms,
        fallback_timeout_ms=args.fallback_timeout_ms,
        baseline_timeout_ms=args.baseline_timeout_ms,
        cases=selected,
    )
    summary = _aggregate(rows)
    _print_table(summary)

    if args.csv:
        _write_csv(rows, args.csv)
        print(f"\nwrote raw rows: {args.csv}")
    if args.markdown:
        _write_markdown(summary, args.markdown)
        print(f"wrote markdown:   {args.markdown}")

    total_hits = sum(item["cache_hits"] for item in cache_stats.values())
    total_queries = sum(item["queries"] for item in cache_stats.values())
    if total_queries:
        print(
            f"\ncached mode: {total_hits}/{total_queries} cache hits "
            f"({total_hits / total_queries:.0%}); per-case stats:"
        )
        for case_name, stats in cache_stats.items():
            print(f"  {case_name:<20s} {stats}")

    timed_out = [row for row in rows if row.status == Status.UNKNOWN.value]
    if timed_out:
        print(
            f"\n{len(timed_out)} call(s) returned unknown (budget exhausted); "
            "see stages column for the degradation ladder."
        )


if __name__ == "__main__":
    main()
