# MCP Server 性能优化方案

> 基于对 Skill + `trading_agent` 完整执行流程、缓存机制、输出结构的深度分析，
> 梳理现有问题并按重要程度排序，给出优化方案及实施顺序。

---

## 一、问题总览

| # | 问题 | 影响 | 优先级 |
|---|------|------|--------|
| P0-1 | `trading_agent` 每次调用重建 `TradingAgentsGraph` | 每次多耗 2-5s，LLM/Toolkit/Graph 重复创建 | **P0** |
| P0-2 | 两套独立 LLM 创建逻辑（TradingAgentsGraph vs AnalystRunner） | 560行 vs 84行，重复且不一致 | **P0** |
| P1-1 | `set_config()` 全局状态污染 | 多实例配置互相覆盖，并发不安全 | **P1** |
| P1-2 | 数据缓存无自动清理 | 文件只增不减，磁盘无限增长 | **P1** |
| P1-3 | `_log_state()` 写入 eval_results/ 不可控 | MCP 场景下无意义的磁盘 I/O | **P1** |
| P1-4 | compare_stocks / period_compare 冗余创建 TradingAgentsGraph | 仅需 LLM 却创建完整 Graph | **P1** |
| P2-1 | `extract_reports()` 截断逻辑名存实亡 | SKILL.md 声明 ≤2000 字符但实际不截断 | **P2** |
| P2-2 | `build_config()` 每次调用重建 | 配置不变时无意义重复 copy + 环境变量读取 | **P2** |
| P2-3 | `propagate` 三段重复的 stream 循环 | ~200 行重复代码，仅差进度回调逻辑 | **P2** |
| P3-1 | 交易日历缓存无年度更新机制 | 新年度交易日数据可能缺失 | **P3** |

---

## 二、问题详细分析

### P0-1: `trading_agent` 每次调用重建 TradingAgentsGraph

**现状**：

`server.py:143-156` 每次调用 `trading_agent`：

```python
ta = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)
```

这一行触发了 `TradingAgentsGraph.__init__` 的完整初始化（~560行）：

1. `set_config()` — 覆盖全局配置
2. `create_llm_by_provider()` × 2 — 创建 deep + quick 两个 LLM 实例（含 HTTP 连接池）
3. `Toolkit(config)` — 注册所有数据工具
4. `ToolNode` × 4 — 按分析师类型分组
5. `GraphSetup` → `LangGraph.compile()` — 构建完整计算图
6. `Propagator` / `Reflector` / `SignalProcessor` 初始化

在配置不变、analysts 组合不变的情况下，以上操作完全重复。

**对比**：`AnalystRunner`（`analyst_runner.py`）已实现单例复用 LLM + Toolkit，
但仅用于单分析师路径（`_run_single_analyst`），`trading_agent` 路径完全未利用。

**影响**：每次 `trading_agent` 调用多耗 2-5 秒初始化，且 LLM HTTP 连接池无法复用。

---

### P0-2: 两套独立 LLM 创建逻辑

**现状**：

| 路径 | 文件 | 代码行数 | 创建的 LLM | 配置覆盖 |
|------|------|---------|-----------|---------|
| `TradingAgentsGraph.__init__` | `trading_graph.py` | ~560 行 | deep + quick | 完整（含混合模式） |
| `AnalystRunner.__init__` | `analyst_runner.py` | ~40 行 | 仅 quick | 仅单 provider |

两套逻辑的问题：
- **代码重复**：provider 分支逻辑写了两遍，新增 provider 需改两处
- **行为不一致**：AnalystRunner 不支持混合模式（quick_provider ≠ deep_provider）
- **实例不共享**：同一 MCP 进程内可能存在 3+ 个 LLM 实例（1 个 AnalystRunner + N 个 TradingAgentsGraph）

---

### P1-1: `set_config()` 全局状态污染

**现状**：

`set_config()` 本质是 `config_manager.save_settings(config)`，写入全局单例。
每次创建 `TradingAgentsGraph` 或 `AnalystRunner` 都会调用：

```python
# trading_graph.py:214
set_config(self.config)

# analyst_runner.py:26
set_config(self.config)
```

如果两个调用使用不同 config（虽然当前 MCP 场景不太可能），后者会覆盖前者。
更严重的是，`Toolkit` 内部数据源选择依赖全局 config，若 config 被覆盖，
可能影响正在执行的其他请求。

---

### P1-2: 数据缓存无自动清理

**现状**：

`StockDataCache` 提供了 `clear_old_cache(max_age_days=7)` 方法，但：
- **从未被任何代码调用**
- `get_cache_stats()` 也未暴露给 MCP 用户
- 缓存文件按 `{symbol}_{data_type}_{hash}.txt` 存储，配合 `_meta.json` 元数据
- `find_cached_*` 方法在查找时遍历所有元数据文件，文件多了性能退化

当前缓存文件较少（36K），但 MCP Server 长驻运行，数周后可能累积大量过期文件。

---

### P1-3: `_log_state()` 写入 eval_results/ 不可控

**现状**：

`trading_graph.py:1344-1384`，每次 `propagate()` 调用都会：

```python
directory = Path(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/")
directory.mkdir(parents=True, exist_ok=True)
with open(f"eval_results/{self.ticker}/TradingAgentsStrategy_logs/full_states_log.json", "w") as f:
    json.dump(self.log_states_dict, f, indent=4)
```

问题：
- MCP Server 场景下，用户无法访问服务端文件系统，这些日志无意义
- 同一 ticker 多次运行会不断追加 `log_states_dict`（`self.log_states_dict` 是实例属性，
  但 `TradingAgentsGraph` 每次新建所以实际是覆盖）
- 包含完整的辩论历史、报告文本等，文件可能很大

---

### P1-4: compare_stocks / period_compare 冗余创建 TradingAgentsGraph

**现状**：

`compare_stocks`（非 full 模式）仅需 LLM 生成对比分析，却创建完整 Graph：

```python
# server.py:414-419 — 仅为获取 quick_thinking_llm
ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
comparison_report = await loop.run_in_executor(
    None, lambda: ta.quick_thinking_llm.invoke(comparison_prompt).content
)
```

`period_compare` 更严重，创建了 **两次** TradingAgentsGraph：

```python
# server.py:550 — 第一次：获取行情数据
ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
symbol_data = await loop.run_in_executor(
    None, lambda: ta.toolkit.get_stock_market_data_unified(...)
)

# server.py:609 — 第二次：LLM 生成分析
ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
analysis_report = await loop.run_in_executor(
    None, lambda: ta.quick_thinking_llm.invoke(analysis_prompt).content
)
```

---

### P2-1: `extract_reports()` 截断逻辑名存实亡

**现状**：

```python
# validators.py:240-248
def extract_reports(state: dict) -> dict:
    reports = {}
    for key in ["market_report", "fundamentals_report", "sentiment_report", "news_report"]:
        val = state.get(key, "")
        if isinstance(val, str) and len(val) > 2000:
            reports[key] = val      # ← 超过2000也不截断
        else:
            reports[key] = val      # ← 不到2000也不截断
    return reports
```

SKILL.md 声明报告 `≤2000字符`，但代码中两个分支返回同样的 `val`，实际永远不截断。

---

### P2-2: `build_config()` 每次调用重建

**现状**：

每次调用都执行 `DEFAULT_CONFIG.copy()` + 遍历 8 个环境变量，返回新 dict。
在 MCP 进程生命周期内，环境变量几乎不会变化。

---

### P2-3: propagate 三段重复的 stream 循环

**现状**：

`trading_graph.py:911-1018`，三段几乎相同的 `for chunk in self.graph.stream(...)` 循环：
- debug 模式（~40行）
- 有 progress_callback 的标准模式（~40行）
- 无 progress_callback 的标准模式（~40行）

三者仅差：是否 trace、是否发送进度回调、是否 pretty_print。

---

### P3-1: 交易日历缓存无年度更新机制

**现状**：

`trade_calendar.py` 的 `_is_cache_fresh()` 只检查"今天是否在 date_range 范围内"，
不检查是否应主动更新。如果缓存在年初生成且范围仅覆盖到当年末，
跨年后可能缺少新年度交易日数据（实际当前查询范围是 ±1年，所以短期内不会出问题）。

---

## 三、优化方案

### 方案总览：SharedContext 共享上下文

**核心思路**：MCP Server 启动时初始化一次 LLM + Toolkit，后续所有 Tool 共享复用。

```
MCP Server 启动
    │
    ▼
SharedContext 初始化（一次性）
    ├── build_config()
    ├── set_config(config)
    ├── create_llm_by_provider() × 2  → deep_thinking_llm, quick_thinking_llm
    ├── Toolkit(config)               → toolkit
    └── _graph_cache: {}              → 按需构建，命中则复用
    │
    ├── [请求] trading_agent(analysts=["market","social","news","fundamentals"])
    │   └── shared_ctx.get_graph(analysts)
    │       ├── 首次: 构建 GraphSetup + compile → 缓存
    │       └── 后续: 直接返回已缓存的 Graph
    │
    ├── [请求] market_analyst(symbol, trade_date)
    │   └── create_market_analyst(shared_ctx.quick_thinking_llm, shared_ctx.toolkit)
    │
    ├── [请求] compare_stocks(...)
    │   └── shared_ctx.quick_thinking_llm.invoke(prompt)  ← 直接用，不建 Graph
    │
    └── [请求] period_compare(...)
        ├── shared_ctx.toolkit.get_stock_market_data_unified(...)
        └── shared_ctx.quick_thinking_llm.invoke(prompt)  ← 直接用
```

---

### 优化顺序与详细方案

#### 第 1 步：创建 SharedContext + TradingAgentsGraph 注入支持

**目标**：P0-1 + P0-2

**新增文件** `src/tradingagents_mcp/shared_context.py`：

```python
"""
MCP 进程级共享上下文
启动时初始化 LLM + Toolkit，所有 Tool 共享复用
"""

import logging
import os
from typing import Dict, Optional

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.dataflows.interface import set_config
from tradingagents.agents.utils.agent_utils import Toolkit
from tradingagents.graph.trading_graph import create_llm_by_provider

logger = logging.getLogger(__name__)

_shared_ctx: Optional["SharedContext"] = None


class SharedContext:
    """MCP 进程级共享上下文，启动时初始化一次"""

    def __init__(self, config: dict):
        self.config = config
        set_config(config)

        os.makedirs(
            os.path.join(config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # 深度思考模型
        deep_config = config.get("deep_model_config", {})
        self.deep_thinking_llm = create_llm_by_provider(
            provider=config.get("deep_provider") or config["llm_provider"],
            model=config["deep_think_llm"],
            backend_url=config.get("deep_backend_url") or config.get("backend_url", ""),
            temperature=deep_config.get("temperature", 0.7),
            max_tokens=deep_config.get("max_tokens", 4000),
            timeout=deep_config.get("timeout", 180),
            api_key=config.get("deep_api_key"),
        )

        # 快速思考模型
        quick_config = config.get("quick_model_config", {})
        self.quick_thinking_llm = create_llm_by_provider(
            provider=config.get("quick_provider") or config["llm_provider"],
            model=config["quick_think_llm"],
            backend_url=config.get("quick_backend_url") or config.get("backend_url", ""),
            temperature=quick_config.get("temperature", 0.7),
            max_tokens=quick_config.get("max_tokens", 4000),
            timeout=quick_config.get("timeout", 180),
            api_key=config.get("quick_api_key"),
        )

        self.toolkit = Toolkit(config=config)

        # Graph 缓存: key = tuple(sorted(analysts))
        self._graph_cache: Dict[tuple, object] = {}

        logger.info("SharedContext 初始化完成")

    def get_graph(self, analysts: list[str], config: dict = None):
        """按 analysts 组合获取/缓存 TradingAgentsGraph"""
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        key = tuple(sorted(analysts))
        if key not in self._graph_cache:
            cfg = config or self.config
            self._graph_cache[key] = TradingAgentsGraph(
                selected_analysts=analysts,
                debug=False,
                config=cfg,
                _deep_llm=self.deep_thinking_llm,
                _quick_llm=self.quick_thinking_llm,
                _toolkit=self.toolkit,
            )
        return self._graph_cache[key]

    def invalidate(self):
        """清除所有缓存，下次请求时重建"""
        self._graph_cache.clear()


def get_shared_ctx() -> SharedContext:
    """获取/创建 SharedContext 单例"""
    global _shared_ctx
    if _shared_ctx is None:
        from tradingagents_mcp.validators import build_config
        _shared_ctx = SharedContext(build_config())
    return _shared_ctx


def invalidate_shared_ctx():
    """清除 SharedContext 单例"""
    global _shared_ctx
    _shared_ctx = None
```

**修改** `TradingAgentsGraph.__init__`，支持注入：

```python
def __init__(self, selected_analysts, debug=False, config=None,
             _deep_llm=None, _quick_llm=None, _toolkit=None):

    self.config = config or DEFAULT_CONFIG
    set_config(self.config)  # 保留，确保全局配置一致

    os.makedirs(
        os.path.join(self.config["project_dir"], "dataflows/data_cache"),
        exist_ok=True,
    )

    # ─── 注入 vs 自建 ───
    if _deep_llm and _quick_llm and _toolkit:
        self.deep_thinking_llm = _deep_llm
        self.quick_thinking_llm = _quick_llm
        self.toolkit = _toolkit
    else:
        # 原有完整初始化逻辑（向后兼容）
        ...原有 560 行代码不变...

    # 以下逻辑不论注入还是自建都需执行
    self.tool_nodes = self._create_tool_nodes()
    self.conditional_logic = ConditionalLogic(...)
    self.graph_setup = GraphSetup(...)
    self.propagator = Propagator()
    self.reflector = Reflector(self.quick_thinking_llm)
    self.signal_processor = SignalProcessor(self.quick_thinking_llm)
    self.curr_state = None
    self.ticker = None
    self.log_states_dict = {}
    self.graph = self.graph_setup.setup_graph(selected_analysts)
```

**收益**：
- 同 analysts 组合的 `trading_agent` 调用：2-5s → 0s 初始化
- LLM HTTP 连接池复用，减少 TCP 握手
- 新增 provider 只需改 `create_llm_by_provider()` 一处

---

#### 第 2 步：重构 server.py 各 Tool 使用 SharedContext

**目标**：P0-1 + P1-4

**trading_agent**：

```python
@mcp.tool()
async def trading_agent(symbol, trade_date, analysts=None, ...):
    ...
    ctx = get_shared_ctx()
    # config 中的 max_debate_rounds 等运行时参数需传入
    config = build_config()
    config["max_debate_rounds"] = max_debate_rounds
    config["max_risk_discuss_rounds"] = max_risk_discuss_rounds

    ta = ctx.get_graph(analysts, config=config)
    state, decision = await loop.run_in_executor(
        None, lambda: ta.propagate(symbol, trade_date)
    )
```

**market_analyst / fundamentals_analyst / news_analyst / social_analyst**：

```python
@mcp.tool()
async def market_analyst(symbol, trade_date, ...):
    ...
    ctx = get_shared_ctx()
    node = create_market_analyst(ctx.quick_thinking_llm, ctx.toolkit)
    result_state = await loop.run_in_executor(None, lambda: node(state))
    ...
```

**compare_stocks**（非 full 模式）：

```python
# 替换: ta = TradingAgentsGraph(...) + ta.quick_thinking_llm.invoke(...)
# 改为:
ctx = get_shared_ctx()
comparison_report = await loop.run_in_executor(
    None, lambda: ctx.quick_thinking_llm.invoke(comparison_prompt).content
)
```

**period_compare**：

```python
# 替换两次 TradingAgentsGraph 创建
# 改为:
ctx = get_shared_ctx()
symbol_data = await loop.run_in_executor(
    None, lambda: ctx.toolkit.get_stock_market_data_unified(symbol, start_date, end_date)
)
...
analysis_report = await loop.run_in_executor(
    None, lambda: ctx.quick_thinking_llm.invoke(analysis_prompt).content
)
```

**screen_stocks**：

```python
# 替换: ta = TradingAgentsGraph(...) + ta.quick_thinking_llm.invoke(...)
# 改为:
ctx = get_shared_ctx()
analysis_report = await loop.run_in_executor(
    None, lambda: ctx.quick_thinking_llm.invoke(analysis_prompt).content
)
```

**删除** `analyst_runner.py`，其功能已被 `SharedContext` 完全取代。

**收益**：
- `compare_stocks` / `period_compare` / `screen_stocks` 不再创建无意义的 TradingAgentsGraph
- 统一入口，消除 5 处冗余 Graph 创建
- `period_compare` 从创建 2 次 Graph 降为 0 次

---

#### 第 3 步：修复 `set_config()` 全局污染

**目标**：P1-1

**方案 A（推荐）**：启动时调用一次 `set_config()`，后续不再调用。

`SharedContext.__init__` 中已调用 `set_config(config)`。
`TradingAgentsGraph` 注入路径（`_deep_llm` 非空时）跳过 `set_config()` 调用。

**方案 B（长期）**：将 `config_manager` 改为实例级而非全局单例，
Toolkit 等组件通过构造参数接收 config，而非从全局读取。

```python
# TradingAgentsGraph 注入路径
if _deep_llm and _quick_llm and _toolkit:
    self.deep_thinking_llm = _deep_llm
    self.quick_thinking_llm = _quick_llm
    self.toolkit = _toolkit
    # 不调用 set_config()，避免覆盖全局状态
```

**收益**：消除并发请求间的配置竞争风险。

---

#### 第 4 步：数据缓存自动清理 + 统计暴露

**目标**：P1-2

**4a. MCP Server 启动时清理过期缓存**：

```python
# shared_context.py — SharedContext.__init__ 末尾
from tradingagents.dataflows.cache import get_cache
cache = get_cache()
cache.clear_old_cache(max_age_days=7)
stats = cache.get_cache_stats()
logger.info(f"缓存清理完成: {stats['total_files']} 文件, {stats['total_size_mb']} MB")
```

**4b. agent_status 暴露缓存统计**：

```python
# server.py — agent_status 返回值新增
"cache_stats": get_cache_stats(),  # 由 SharedContext 提供
```

**4c. 可选：新增 MCP Tool `clear_cache`**：

```python
@mcp.tool()
async def clear_cache(max_age_days: int = 7) -> dict:
    """清理过期数据缓存"""
    from tradingagents.dataflows.cache import get_cache
    cache = get_cache()
    before = cache.get_cache_stats()
    cache.clear_old_cache(max_age_days=max_age_days)
    after = cache.get_cache_stats()
    return {
        "success": True,
        "cleared_files": before["total_files"] - after["total_files"],
        "freed_mb": round(before["total_size_mb"] - after["total_size_mb"], 2),
    }
```

**收益**：防止磁盘无限增长，用户可感知和控制缓存。

---

#### 第 5 步：禁用/可配置 `_log_state()`

**目标**：P1-3

**方案**：新增 config 参数 `enable_eval_logging`，默认 False（MCP 场景）。

```python
# trading_graph.py — propagate 末尾
if self.config.get("enable_eval_logging", False):
    self._log_state(trade_date, final_state)
```

**收益**：消除 MCP 场景下无意义的磁盘 I/O，减少文件系统垃圾。

---

#### 第 6 步：修复 `extract_reports()` 截断逻辑

**目标**：P2-1

**方案 A（推荐）**：移除截断声明，SKILL.md 改为"返回完整内容，不做截断"（当前实际行为）。

**方案 B**：真正实现截断，保留前 1800 字符 + 尾部 "…[已截断]" 提示。

```python
def extract_reports(state: dict, max_chars: int = 2000) -> dict:
    reports = {}
    for key in ["market_report", "fundamentals_report", "sentiment_report", "news_report"]:
        val = state.get(key, "")
        if isinstance(val, str) and len(val) > max_chars:
            reports[key] = val[:max_chars] + "\n\n…[报告已截断]"
        else:
            reports[key] = val
    return reports
```

**收益**：代码行为与文档声明一致，消除用户困惑。

---

#### 第 7 步：`build_config()` 缓存

**目标**：P2-2

```python
_config_cache: Optional[dict] = None

def build_config() -> dict:
    global _config_cache
    if _config_cache is not None:
        return _config_cache.copy()  # 返回副本，防止外部修改
    config = DEFAULT_CONFIG.copy()
    for env_key, (config_key, type_fn) in env_map.items():
        val = os.getenv(env_key)
        if val is not None:
            config[config_key] = type_fn(val)
    _config_cache = config
    return config.copy()

def invalidate_config_cache():
    global _config_cache
    _config_cache = None
```

**收益**：微优化，减少每次调用 ~0.1ms 的 dict copy + 环境变量读取。

---

#### 第 8 步：合并 propagate 三段 stream 循环

**目标**：P2-3

```python
def propagate(self, company_name, trade_date, progress_callback=None, task_id=None):
    init_agent_state = self.propagator.create_initial_state(company_name, trade_date)
    use_progress = bool(progress_callback)
    args = self.propagator.get_graph_args(use_progress_callback=use_progress)

    node_timings = {}
    current_node_start = None
    current_node_name = None
    total_start_time = time.time()

    final_state = None
    for chunk in self.graph.stream(init_agent_state, **args):
        # 统一节点计时
        for node_name in chunk.keys():
            if not node_name.startswith('__'):
                if current_node_name and current_node_start:
                    node_timings[current_node_name] = time.time() - current_node_start
                current_node_name = node_name
                current_node_start = time.time()
                break

        # 累积状态
        if final_state is None:
            final_state = init_agent_state.copy()
        if args.get("stream_mode") == "updates":
            for node_name, node_update in chunk.items():
                if not node_name.startswith('__') and isinstance(node_update, dict):
                    final_state.update(node_update)
        else:
            final_state.update(chunk)

        # 可选进度回调
        if progress_callback:
            self._send_progress_update(chunk, progress_callback)

        # 可选调试输出
        if self.debug and not progress_callback:
            if len(chunk.get("messages", [])) > 0:
                chunk["messages"][-1].pretty_print()

    # 收尾计时 + 性能统计（不变）
    ...
```

**收益**：减少 ~200 行重复代码，逻辑更清晰。

---

#### 第 9 步：交易日历缓存年度更新

**目标**：P3-1

**方案**：在 `get_trade_dates()` 中检查缓存年份是否覆盖当前年份。

```python
def get_trade_dates() -> Set[str]:
    global _module_cache
    if _module_cache is not None:
        return _module_cache

    file_cache = _load_cache()
    if file_cache and _is_cache_fresh(file_cache):
        # 新增：检查缓存是否覆盖今年（防止跨年失效）
        current_year = datetime.now().year
        range_end = file_cache["date_range"][1]
        if range_end >= f"{current_year}-12-31":
            _module_cache = set(file_cache["trade_dates"])
            return _module_cache
        else:
            logger.info("交易日历缓存不覆盖当前年度，重新查询")

    # 重新查询...
```

**收益**：确保新年度交易日数据可用。

---

## 四、实施计划

| 阶段 | 步骤 | 涉及文件 | 预计工作量 | 依赖 |
|------|------|---------|-----------|------|
| **阶段 1** | 第 1 步：SharedContext + Graph 注入 | `shared_context.py`(新)、`trading_graph.py` | 2h | 无 |
| **阶段 2** | 第 2 步：重构 server.py 各 Tool | `server.py`、删除 `analyst_runner.py` | 1.5h | 阶段 1 |
| **阶段 3** | 第 3 步：set_config 修复 | `trading_graph.py` | 0.5h | 阶段 1 |
| **阶段 3** | 第 4 步：缓存自动清理 | `shared_context.py`、`server.py` | 0.5h | 阶段 1 |
| **阶段 4** | 第 5 步：禁用 _log_state | `trading_graph.py` | 0.2h | 无 |
| **阶段 4** | 第 6 步：修复截断逻辑 | `validators.py`、`SKILL.md` | 0.3h | 无 |
| **阶段 5** | 第 7-9 步：次要优化 | `validators.py`、`trading_graph.py`、`trade_calendar.py` | 1h | 无 |

**总计约 6h，可分 5 个阶段逐步实施。**

---

## 五、预期收益汇总

| 指标 | 优化前 | 优化后 |
|------|--------|--------|
| 首次 `trading_agent`（需建 Graph） | ~5s 初始化 | ~0.5s（仅 GraphSetup + compile） |
| 重复 `trading_agent`（同 analysts） | ~5s 初始化 | **0s**（缓存命中） |
| 单分析师（market/fundamentals 等） | ~1s 初始化 | **0s**（共享 LLM+Toolkit） |
| compare_stocks 对比 LLM 调用 | 新建完整 Graph | 直接用共享 LLM |
| period_compare | 新建 2 次 Graph | 0 次 |
| screen_stocks | 新建 1 次 Graph | 0 次 |
| eval_results 磁盘写入 | 每次 propagate | 不写入（默认关闭） |
| 数据缓存清理 | 从未清理 | 启动时自动清理 7 天前 |
| LLM 创建代码 | 560 + 40 行（两套） | 统一使用 `create_llm_by_provider` |
| propagate stream 循环 | ~300 行（三段重复） | ~80 行（一段） |
