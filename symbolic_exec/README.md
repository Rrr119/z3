# 符号执行的 Z3 加速层

针对符号执行中 SMT 求解过慢的问题，在裸 `z3.Solver` 之上封装了四层
加速机制，并附带一组约束的求解时间对比。

## 结构

| 文件 | 作用 |
|---|---|
| `engine.py` | `SolverEngine`：tactic 组合、LRU 结果缓存、超时与分级降级 |
| `machine.py` | `SymbolicMachine`：位向量符号机，分支 fork 时用引擎做路径可行性裁剪 |
| `constraints.py` | 8 个确定性约束用例（线性/位运算/整数/非线性/硬哈希原像等） |
| `benchmark.py` | baseline / tactics / cached / fallback 四模式计时对比 |
| `demo.py` | 端到端示例：分支探索、缓存命中、超时降级 |
| `results.md` / `results.csv` | 最近一次基准的聚合表与原始逐次数据 |

## 四项加速机制

1. **Tactic 组合**：用 `z3.Then(...)` 把预处理和求解器串成命名预设，
   按从便宜到昂贵排序：
   - `qfbv-light`：`simplify → solve-eqs → bit-blast → sat`
   - `qfbv`：加 `ctx-simplify`、`max-bv-sharing` 等重型预处理
   - `arith`：`simplify → solve-eqs → lia`
   - `smt`：`default` 通用求解器兜底
   不存在的 tactic 名会被跳过，配置可跨 Z3 构建移植。
2. **缓存**：以约束的规范化 SMT 表达式（排序后的 sexpr 拼接）为键，
   `OrderedDict` 实现 LRU（默认 4096 条，线程安全）。只缓存 `sat`/`unsat`；
   `unknown` 不缓存，给后续更大预算的调用留机会。
3. **超时**：每个 tactic 阶段通过 `solver.set(timeout=...)` 获得独立预算，
   剩余预算在后续阶段间分配，整体调用不会明显超过 `timeout_ms`。
4. **降级**：某阶段返回 `unknown`（含 timeout/cancel）后自动落到下一阶段，
   最终由通用 SMT 求解器兜底；全部失败才返回 `unknown`，并在
   `SolveResult.stages_tried` / `timed_out` 中保留轨迹。

## 运行

依赖 `z3-solver`（仓库根目录的 `.venv` 已安装 5.4.1）：

```bash
python3 -m venv .venv
.venv/bin/pip install z3-solver

.venv/bin/python -m symbolic_exec.demo
.venv/bin/python -m symbolic_exec.benchmark \
  --repeats 3 --timeout-ms 1500 --fallback-timeout-ms 80 \
  --csv symbolic_exec/results.csv --markdown symbolic_exec/results.md
```

最小用法：

```python
from symbolic_exec import SolverEngine, EngineConfig
import z3

engine = SolverEngine(EngineConfig(timeout_ms=500))
x, y = z3.BitVecs("x y", 32)
result = engine.check([x + y == 10, x - y == 2])
print(result.status, result.model, result.source, result.stages_tried)
print(engine.stats.as_dict())
```

## 基准结论（本机，单位 ms）

完整数据见 `results.md`，要点：

- **缓存命中极快**：重复查询同一约束时命中路径约 0.03–0.15ms，
  相比首次求解通常快 1–2 个数量级；基准中 cached 模式命中率 58%
  （可判定用例为 100%，仅硬原像因始终 `unknown` 不进缓存）。
- **轻量 tactic 对非线性 BV 有效**：`nonlinear_bv` 从裸求解器的
  ~7–15ms 降到 ~3–4ms。
- **降级保证可控延迟**：硬哈希原像在 80ms 总预算下依次尝试
  `qfbv-light → qfbv → smt` 后返回 `unknown`（~81ms），而裸求解器
  无保护时可阻塞 300 秒以上；1500ms 预算下行为同样可预测。
- **简单查询有固定开销**：亚毫秒级用例上 tactic 链的构建开销可能高于
  裸求解器，此时缓存是主要收益来源；可通过 `EngineConfig.tactics`
  裁剪阶段。

调参建议：路径探索优先调大 `cache_size` 并保持轻量 tactic 在最前；
硬查询调大 `timeout_ms` 或在 `extra_presets` 中注册自定义 tactic 链。
