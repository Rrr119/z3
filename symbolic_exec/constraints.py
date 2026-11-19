"""Benchmark constraint sets shared by the timing comparison.

Each entry is a deterministic builder returning a fresh list of z3
constraints, so every benchmark mode starts from identical inputs and the
comparison only differs in solver configuration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import z3


@dataclass(frozen=True)
class ConstraintCase:
    name: str
    description: str
    build: Callable[[], list[z3.BoolRef]]


def _linear_bv() -> list[z3.BoolRef]:
    x, y = z3.BitVecs("x y", 32)
    return [x + y == 1000, x - y == 250, z3.UGE(x, 0), z3.UGE(y, 0)]


def _path_guard_chain() -> list[z3.BoolRef]:
    x = z3.BitVec("x", 32)
    constraints = [x > 0]
    value = x
    for step in range(1, 9):
        constraints.append(value > step)
        value = value + step
    constraints.append(value == 60)
    return constraints


def _bitops_mask() -> list[z3.BoolRef]:
    x, y = z3.BitVecs("x y", 32)
    return [
        (x & 0xFF) == 0x7A,
        (y & 0xF0) == 0x30,
        y == (z3.LShR(x, 4) ^ 0x33),
    ]


def _infeasible_path() -> list[z3.BoolRef]:
    x = z3.BitVec("x", 32)
    return [z3.UGT(x, 10), z3.ULT(x, 5)]


def _integer_linear() -> list[z3.BoolRef]:
    x, y, z = z3.Ints("x y z")
    return [
        3 * x + 2 * y - z == 20,
        x + y + z == 10,
        x >= 0,
        y >= 0,
        z >= 0,
    ]


def _nonlinear_bv() -> list[z3.BoolRef]:
    x, y = z3.BitVecs("x y", 32)
    return [x * y == 1000, x + y == 65, x != 0, y != 0]


def _mixed_width() -> list[z3.BoolRef]:
    lo = z3.BitVec("lo", 8)
    mid = z3.BitVec("mid", 16)
    hi = z3.BitVec("hi", 64)
    return [
        z3.ZeroExt(8, lo) + z3.ZeroExt(8, z3.Extract(7, 0, mid)) == 200,
        z3.SignExt(48, mid) + hi == 0xABCDEF,
        z3.UGE(hi, 0),
    ]


def _hard_hash_preimage(rounds: int = 20) -> list[z3.BoolRef]:
    """Nonlinear mixing-function preimage; hard for bit-blasting SAT."""

    x = z3.BitVec("x", 64)
    state = x
    for _ in range(rounds):
        state = state ^ z3.RotateLeft(state, 7)
        state = state * z3.BitVecVal(0x9E3779B97F4A7C15, 64)
    return [state == z3.BitVecVal(0xDEADBEEFCAFEF00D, 64)]


CASES: list[ConstraintCase] = [
    ConstraintCase(
        "linear_bv",
        "two linear 32-bit equations over unsigned inputs",
        _linear_bv,
    ),
    ConstraintCase(
        "path_guard_chain",
        "nine nested path guards from symbolic branching",
        _path_guard_chain,
    ),
    ConstraintCase(
        "bitops_mask",
        "bitwise AND/mask plus shift-xor relation",
        _bitops_mask,
    ),
    ConstraintCase(
        "infeasible_path",
        "contradictory unsigned bounds (unsat path condition)",
        _infeasible_path,
    ),
    ConstraintCase(
        "integer_linear",
        "linear integer arithmetic with non-negativity",
        _integer_linear,
    ),
    ConstraintCase(
        "nonlinear_bv",
        "bit-vector product with a linear sum side condition",
        _nonlinear_bv,
    ),
    ConstraintCase(
        "mixed_width",
        "8/16/64-bit variables joined by extensions",
        _mixed_width,
    ),
    ConstraintCase(
        "hard_hash_preimage",
        "20-round nonlinear 64-bit preimage (stress/timeout case)",
        _hard_hash_preimage,
    ),
]
