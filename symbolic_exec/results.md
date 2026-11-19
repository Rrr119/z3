# Solve-time comparison

Times in milliseconds per `check` call; `cached` run 0 is a miss and later runs are cache hits on identical constraint sets.

| case | mode | status | runs | min | median | max | source / stages |
|---|---|---|---:|---:|---:|---:|---|
| bitops_mask | baseline | sat | 1 | 0.44 | 0.44 | 0.44 | z3.Solver(guard-timeout) `default` |
| bitops_mask | cached | sat | 3 | 0.03 | 0.06 | 0.67 | qfbv-light `qfbv-light` |
| bitops_mask | fallback | sat | 1 | 0.64 | 0.64 | 0.64 | qfbv-light `qfbv-light` |
| bitops_mask | tactics | sat | 3 | 0.7 | 0.82 | 3.95 | qfbv-light `qfbv-light` |
| hard_hash_preimage | baseline | unknown | 1 | 1595.72 | 1595.72 | 1595.72 | z3.Solver(guard-timeout) `default` |
| hard_hash_preimage | cached | unknown | 3 | 1500.92 | 1501.38 | 1501.87 | smt `qfbv-light>qfbv>smt` |
| hard_hash_preimage | fallback | unknown | 1 | 81.73 | 81.73 | 81.73 | smt `qfbv-light>qfbv>smt` |
| hard_hash_preimage | tactics | unknown | 3 | 1500.75 | 1500.98 | 1501.91 | smt `qfbv-light>qfbv>smt` |
| infeasible_path | baseline | unsat | 1 | 0.36 | 0.36 | 0.36 | z3.Solver(guard-timeout) `default` |
| infeasible_path | cached | unsat | 3 | 0.02 | 0.06 | 0.44 | qfbv-light `qfbv-light` |
| infeasible_path | fallback | unsat | 1 | 0.44 | 0.44 | 0.44 | qfbv-light `qfbv-light` |
| infeasible_path | tactics | unsat | 3 | 0.44 | 0.47 | 0.54 | qfbv-light `qfbv-light` |
| integer_linear | baseline | sat | 1 | 1.75 | 1.75 | 1.75 | z3.Solver(guard-timeout) `default` |
| integer_linear | cached | sat | 3 | 0.05 | 0.11 | 2.79 | smt `qfbv-light>qfbv>smt` |
| integer_linear | fallback | sat | 1 | 2.91 | 2.91 | 2.91 | smt `qfbv-light>qfbv>smt` |
| integer_linear | tactics | sat | 3 | 2.11 | 2.25 | 2.73 | smt `qfbv-light>qfbv>smt` |
| linear_bv | baseline | sat | 1 | 1.55 | 1.55 | 1.55 | z3.Solver(guard-timeout) `default` |
| linear_bv | cached | sat | 3 | 0.03 | 0.15 | 1.41 | qfbv-light `qfbv-light` |
| linear_bv | fallback | sat | 1 | 1.26 | 1.26 | 1.26 | qfbv-light `qfbv-light` |
| linear_bv | tactics | sat | 3 | 3.75 | 4.87 | 5.48 | qfbv-light `qfbv-light` |
| mixed_width | baseline | sat | 1 | 1.42 | 1.42 | 1.42 | z3.Solver(guard-timeout) `default` |
| mixed_width | cached | sat | 3 | 0.06 | 0.12 | 0.93 | qfbv-light `qfbv-light` |
| mixed_width | fallback | sat | 1 | 0.84 | 0.84 | 0.84 | qfbv-light `qfbv-light` |
| mixed_width | tactics | sat | 3 | 0.86 | 0.98 | 0.99 | qfbv-light `qfbv-light` |
| nonlinear_bv | baseline | sat | 1 | 11.21 | 11.21 | 11.21 | z3.Solver(guard-timeout) `default` |
| nonlinear_bv | cached | sat | 3 | 0.03 | 0.08 | 4.27 | qfbv-light `qfbv-light` |
| nonlinear_bv | fallback | sat | 1 | 3.94 | 3.94 | 3.94 | qfbv-light `qfbv-light` |
| nonlinear_bv | tactics | sat | 3 | 4.53 | 4.67 | 5.45 | qfbv-light `qfbv-light` |
| path_guard_chain | baseline | sat | 1 | 0.29 | 0.29 | 0.29 | z3.Solver(guard-timeout) `default` |
| path_guard_chain | cached | sat | 3 | 0.1 | 0.12 | 0.36 | qfbv-light `qfbv-light` |
| path_guard_chain | fallback | sat | 1 | 0.38 | 0.38 | 0.38 | qfbv-light `qfbv-light` |
| path_guard_chain | tactics | sat | 3 | 0.36 | 0.39 | 0.45 | qfbv-light `qfbv-light` |
