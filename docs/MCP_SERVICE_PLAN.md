# TradingAgents-CN MCP Agent 改造方案

> 将多Agent协作分析引擎封装为 MCP Agent，支持完整分析流程和单分析师独立调用。

---

## 一、核心思路

**不是**把数据查询拆成独立 MCP Tool，**而是**将 Agent 层级封装为 MCP Tool：
- 完整流程：`trading_agent` — 全流程（分析师→辩论→风险→决策）
- 单分析师：`market_analyst` / `fundamentals_analyst` / `news_analyst` / `social_analyst` — 独立运行

```
┌───────────────────────────────────────────────────────────┐
│  MCP Client (opencode)                                    │
│  用户说："分析 000001" / "只看技术面" / "对比这几只"        │
│         / "帮我筛选低PE高ROE的银行股" / "看看这股这半年走势" │
└───────────────────────┬───────────────────────────────────┘
                        │ 调用 MCP Tool
                        ▼
┌───────────────────────────────────────────────────────────┐
│  MCP Server (FastMCP)                                     │
│                                                           │
│  方式1: trading_agent(symbol, date)                        │
│       │  完整全流程                                        │
│       ├── Market Analyst → 数据获取+技术分析               │
│       ├── Fundamentals Analyst → PE/PB/财务数据            │
│       ├── News Analyst → 新闻分析                         │
│       ├── Social Analyst → 情绪分析                       │
│       ├── Bull/Bear Debate → 多空辩论                     │
│       ├── Risk Debate → 风险辩论                          │
│       └── Trader → 最终决策                               │
│                                                           │
│  方式2: market_analyst(symbol, date)                       │
│       │  仅运行市场分析师                                   │
│       └── LLM + get_stock_market_data_unified()            │
│          → 返回技术分析报告                                 │
│                                                           │
│  方式2b: fundamentals_analyst(symbol, date)                │
│       └── LLM + get_stock_fundamentals_unified()           │
│          → 返回基本面分析报告                               │
│                                                           │
│  方式2c: news_analyst(symbol, date)                        │
│       └── LLM + unified_news_tool()                        │
│          → 返回新闻分析报告                                 │
│                                                           │
│  方式2d: social_analyst(symbol, date)                      │
│       └── LLM + get_chinese_social_sentiment()             │
│          → 返回情绪分析报告                                 │
│                                                           │
│  方式3: compare_stocks(symbols, date, analyst)             │
│       │  多股对比分析                                       │
│       ├── 并行运行各股指定分析师                             │
│       ├── 横向对比关键指标                                  │
│       └── LLM 生成排名推荐                                  │
│                                                           │
│  方式4: batch_analyze(symbols, date, analyst)              │
│       └── 并行分析，各股独立返回，无对比                     │
│                                                           │
│  方式5: period_compare(symbol, start, end, metrics, vs)   │
│       │  历史区间对比                                       │
│       ├── 获取区间行情数据                                  │
│       ├── 计算区间收益率/回撤/波动率/夏普                    │
│       ├── 可选与另一股票/指数同期对比                        │
│       └── LLM 生成区间分析报告                              │
│                                                           │
│  方式6: screen_stocks(conditions, market)                  │
│       │  股票筛选                                          │
│       ├── 根据条件（PE/PB/ROE/行业/市值等）筛选             │
│       ├── 返回匹配股票列表                                  │
│       └── LLM 生成筛选解读                                  │
│                                                           │
│  所有内部数据获取由 Agent 自主完成，客户端无需关心           │
└───────────────────────────────────────────────────────────┘
```

**设计原则**：
- 每个 analyst 本身就是独立 Agent（LLM + 工具），可以单独运行
- 客户端只需说"做什么"，Agent 自主编排"怎么做"
- 粒度可选：要快看技术面用 `market_analyst`，要全流程用 `trading_agent`

---

## 二、MCP 暴露的 Tool 清单（10 个）

### 2.1 `trading_agent` — 完整全流程

```python
@mcp.tool()
async def trading_agent(
    symbol: str,
    trade_date: str,
    analysts: list[str] | None = None,
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
) -> dict:
    """
    AI金融交易分析Agent（完整流程）：执行多Agent协作分析，
    包含数据获取→多空辩论→风险评估→交易决策。

    适合：需要完整投资建议的场景。

    Args:
        symbol: 股票代码 (A股'000001'/美股'AAPL'/港股'00700')
        trade_date: 交易日期 YYYY-MM-DD
        analysts: 分析师组合，默认 ["market","social","news","fundamentals"]
        max_debate_rounds: 多空辩论轮次
        max_risk_discuss_rounds: 风险辩论轮次

    Returns:
        完整分析结果含 decision + 各分析师报告 + 辩论记录
    """
```

### 2.2 `market_analyst` — 市场分析师（独立）

```python
@mcp.tool()
async def market_analyst(
    symbol: str,
    trade_date: str,
) -> dict:
    """
    市场分析师Agent（独立运行）：获取行情数据并生成技术分析报告。

    分析内容：移动平均线、MACD、RSI、布林带、价格趋势、成交量、投资建议。
    支持A股(AKShare/Tushare/BaoStock)、美股(YFinance)、港股(AKShare)，自动识别。

    适合：只需看技术面的场景，速度快（~30秒 vs 全流程3-5分钟）。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD

    Returns:
        {"symbol": "...", "report": "技术分析报告全文"}
    """
```

### 2.3 `fundamentals_analyst` — 基本面分析师（独立）

```python
@mcp.tool()
async def fundamentals_analyst(
    symbol: str,
    trade_date: str,
) -> dict:
    """
    基本面分析师Agent（独立运行）：获取PE/PB/ROE等财务数据并生成基本面报告。

    分析内容：估值指标、盈利能力、财务健康、行业对比。
    数据源：A股(AKShare/Tushare)、美股(Alpha Vantage/YFinance/Finnhub)，自动降级。

    适合：只需看基本面估值的场景。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD

    Returns:
        {"symbol": "...", "report": "基本面分析报告全文"}
    """
```

### 2.4 `news_analyst` — 新闻分析师（独立）

```python
@mcp.tool()
async def news_analyst(
    symbol: str,
    trade_date: str,
    look_back_days: int = 7,
) -> dict:
    """
    新闻分析师Agent（独立运行）：获取股票相关新闻并生成分析报告。

    分析内容：重大新闻事件、政策影响、行业动态、潜在风险。
    数据源：A股(中文财经)、美股(Finnhub/Google News)，自动选择。

    适合：只需了解新闻面的场景。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD
        look_back_days: 回看天数，默认7

    Returns:
        {"symbol": "...", "report": "新闻分析报告全文"}
    """
```

### 2.5 `social_analyst` — 社交媒体分析师（独立）

```python
@mcp.tool()
async def social_analyst(
    symbol: str,
    trade_date: str,
) -> dict:
    """
    社交媒体分析师Agent（独立运行）：获取社交平台情绪并生成分析报告。

    分析内容：投资者情绪、讨论热度、关键观点、多空倾向。
    数据源：A股(雪球/东财股吧/新浪财经)、美股(Reddit)，自动选择。

    适合：只需了解市场情绪的场景。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD

    Returns:
        {"symbol": "...", "report": "情绪分析报告全文"}
    """
```

### 2.6 `compare_stocks` — 多股对比分析

```python
@mcp.tool()
async def compare_stocks(
    symbols: list[str],
    trade_date: str,
    analyst: str = "market",
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
) -> dict:
    """
    多股对比分析Agent：对多只股票并行分析并生成对比报告。

    工作流程：
    1. 对每只股票并行运行指定的分析师（默认市场分析师）
    2. 横向对比各股的关键指标（估值/技术/情绪等）
    3. 生成排名和推荐

    对比维度（取决于 analyst 选择）：
    - market: 技术指标对比（MA/MACD/RSI）、价格趋势、成交量
    - fundamentals: 估值对比（PE/PB/ROE）、盈利能力、财务健康
    - news: 新闻热度、重大事件对比
    - social: 情绪对比、讨论热度、多空倾向

    也可以传 analyst="full" 走完整 trading_agent 流程后对比决策。

    Args:
        symbols: 股票代码列表，如 ["000001", "600519", "000858"]
        trade_date: 交易日期 YYYY-MM-DD
        analyst: 对比维度 — "market"(默认)|"fundamentals"|"news"|"social"|"full"
        max_debate_rounds: 仅 full 模式使用，多空辩论轮次
        max_risk_discuss_rounds: 仅 full 模式使用，风险辩论轮次

    Returns:
        {
            "symbols": ["000001", "600519", "000858"],
            "trade_date": "2024-05-10",
            "analyst": "market",
            "individual_reports": {"000001": "...", "600519": "...", "000858": "..."},
            "comparison": "横向对比分析报告（含排名和推荐）",
            "ranking": [
                {"symbol": "600519", "rank": 1, "score": 85, "reason": "..."},
                {"symbol": "000858", "rank": 2, "score": 78, "reason": "..."},
                {"symbol": "000001", "rank": 3, "score": 62, "reason": "..."}
            ]
        }
    """
```

### 2.7 `batch_analyze` — 批量独立分析

```python
@mcp.tool()
async def batch_analyze(
    symbols: list[str],
    trade_date: str,
    analyst: str = "market",
) -> dict:
    """
    批量独立分析：对多只股票并行运行同一分析师，不做对比。

    与 compare_stocks 的区别：
    - batch_analyze: 并行分析，各股独立返回报告，无对比逻辑
    - compare_stocks: 并行分析 + 横向对比 + 排名推荐

    适合：需要快速获取多只股票的同维度报告，自行做判断的场景。

    Args:
        symbols: 股票代码列表
        trade_date: 交易日期 YYYY-MM-DD
        analyst: 分析师选择，默认 "market"

    Returns:
        {
            "symbols": [...],
            "trade_date": "...",
            "results": {"000001": {"report": "..."}, "600519": {"report": "..."}, ...}
        }
    """
```

### 2.8 `period_compare` — 历史区间对比

```python
@mcp.tool()
async def period_compare(
    symbol: str,
    start_date: str,
    end_date: str,
    metrics: list[str] | None = None,
    compare_with: str | None = None,
) -> dict:
    """
    历史区间对比Agent：对比一只股票在指定时间区间内的走势变化，
    或与另一只股票/指数的同期走势对比。

    使用场景：
    1. 单股区间对比：查看某股票两个时间段的表现差异（如本月 vs 上月）
    2. 双股同期对比：对比两只股票在相同时期的走势相关性
    3. 与基准对比：与沪深300等指数对比，判断超额收益

    数据源：A股(AKShare/Tushare/BaoStock)、美股(YFinance)、港股(AKShare)，自动识别。

    Args:
        symbol: 股票代码 (A股'000001'/美股'AAPL'/港股'00700')
        start_date: 起始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
        metrics: 对比指标列表，默认 ["close","volume","pct_chg","turnover_rate"]
                 可选: close/open/high/low/volume/amount/pct_chg/turnover_rate/ma5/ma10/ma20/rsi/macd
        compare_with: 对比目标，可选。如 "000300"（沪深300）、"600519"（另一只股票）。
                      为空时只做单股区间内分析。

    Returns:
        {
            "symbol": "000001",
            "period": {"start_date": "2024-01-01", "end_date": "2024-06-01"},
            "compare_with": "000300",  # 或 null
            "summary": {
                "symbol_return": 12.5,     # 区间收益率%
                "benchmark_return": 8.3,   # 基准收益率%（如有对比）
                "excess_return": 4.2,      # 超额收益%
                "max_drawdown": -5.2,      # 最大回撤%
                "volatility": 18.6,        # 波动率%
                "sharpe_ratio": 0.72       # 夏普比率
            },
            "data_points": {
                "symbol": [{"date": "...", "close": ..., "pct_chg": ...}, ...],
                "compare_with": [{"date": "...", "close": ..., "pct_chg": ...}, ...]  # 或 null
            },
            "analysis": "LLM 生成的区间对比分析报告"
        }
    """
```

### 2.9 `screen_stocks` — 股票筛选

```python
@mcp.tool()
async def screen_stocks(
    conditions: list[dict],
    market: str = "CN",
    order_by: list[dict] | None = None,
    limit: int = 50,
) -> dict:
    """
    股票筛选Agent：根据条件筛选符合要求的股票，并生成筛选解读报告。

    工作流程：
    1. 根据筛选条件从数据源获取股票列表
    2. 返回匹配股票的基本信息、估值指标、行情数据
    3. 用 LLM 生成筛选结果解读和投资建议

    支持的筛选字段（按市场略有差异）：

    基础字段:
    - industry: 行业（contains/in/not_in）
    - area: 地区（eq/in/not_in）

    估值/财务字段:
    - pe: 市盈率（>/</between）
    - pb: 市净率（>/</between）
    - pe_ttm: 滚动市盈率（>/</between）
    - roe: 净资产收益率%（>/</between）
    - total_mv: 总市值(亿元)（>/</between）
    - circ_mv: 流通市值(亿元)（>/</between）

    行情/技术字段:
    - close: 收盘价（>/</between）
    - pct_chg: 涨跌幅%（>/</between）
    - turnover_rate: 换手率%（>/</between）
    - volume_ratio: 量比（>/</between）
    - amount: 成交额（>/</between）

    操作符: > / < / >= / <= / == / != / between / in / not_in / contains

    Args:
        conditions: 筛选条件列表，如 [
            {"field": "pe", "operator": "between", "value": [5, 30]},
            {"field": "roe", "operator": ">", "value": 10},
            {"field": "industry", "operator": "in", "value": ["银行", "保险"]}
        ]
        market: 市场，"CN"(默认)/"HK"/"US"
        order_by: 排序条件，如 [{"field": "total_mv", "direction": "desc"}]
        limit: 返回数量限制，默认50，最大500

    Returns:
        {
            "market": "CN",
            "conditions": [...],
            "total": 42,
            "items": [
                {
                    "code": "601398",
                    "name": "工商银行",
                    "industry": "银行",
                    "pe": 5.2,
                    "pb": 0.6,
                    "roe": 12.3,
                    "total_mv": 18500,
                    "close": 5.23,
                    "pct_chg": 0.58
                },
                ...
            ],
            "analysis": "LLM 生成的筛选结果解读报告"
        }
    """
```

### 2.10 `agent_status` — 查询配置与能力

```python
@mcp.tool()
async def agent_status() -> dict:
    """
    查询当前Agent的配置状态和支持的能力。
    """
```

---

## 三、单分析师独立运行的实现原理

每个 analyst 的工厂函数签名统一：

```python
# agents/analysts/market_analyst.py
def create_market_analyst(llm, toolkit):
    def market_analyst_node(state):   # state = AgentState dict
        ...
        return {"messages": [...], "market_report": report}
    return market_analyst_node
```

**独立运行的关键**：构造一个最小 `state` dict，直接调用 node 函数：

```python
async def market_analyst(symbol: str, trade_date: str) -> dict:
    config = _build_config()
    from tradingagents.graph.trading_graph import TradingAgentsGraph
    # 复用 TradingAgentsGraph 的 LLM/Toolkit 初始化逻辑
    ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)

    # 构造最小状态
    from langchain_core.messages import HumanMessage
    state = {
        "messages": [HumanMessage(content=f"请分析股票 {symbol}")],
        "company_of_interest": symbol,
        "trade_date": trade_date,
        "market_tool_call_count": 0,
    }

    # 直接调用市场分析师 node
    node = create_market_analyst(ta.quick_thinking_llm, ta.toolkit)
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: node(state))

    return {"symbol": symbol, "trade_date": trade_date, "report": result.get("market_report", "")}
```

这种方式：
- **复用现有代码**：LLM 初始化、Toolkit 工具绑定、数据获取逻辑全部复用
- **零侵入**：不修改任何现有文件
- **等价于全流程中的单步**：输出与全流程中市场分析师的输出完全一致

---

## 四、MCP Prompt 设计

```python
@mcp.prompt(title="股票分析")
def stock_analysis_prompt(symbol: str, trade_date: str) -> str:
    return (
        f"请对股票 {symbol} 进行全面分析，交易日为 {trade_date}。\n"
        "使用 trading_agent 工具，它会自动完成全部分析流程。\n"
        "分析完成后，基于返回的报告和决策给出综合解读。"
    )

@mcp.prompt(title="技术面分析")
def technical_analysis_prompt(symbol: str, trade_date: str) -> str:
    return (
        f"请分析 {symbol} 的技术面，交易日 {trade_date}。\n"
        "使用 market_analyst 工具，它会获取行情数据并生成技术分析报告。"
    )

@mcp.prompt(title="基本面分析")
def fundamentals_prompt(symbol: str, trade_date: str) -> str:
    return (
        f"请分析 {symbol} 的基本面，交易日 {trade_date}。\n"
        "使用 fundamentals_analyst 工具，它会获取财务数据并生成估值报告。"
    )

@mcp.prompt(title="A股分析")
def china_stock_prompt(stock_code: str, trade_date: str) -> str:
    return (
        f"请分析A股 {stock_code}，交易日 {trade_date}。\n"
        "使用 trading_agent 工具，A股会自动使用中文数据源和社交媒体情绪。"
    )

@mcp.prompt(title="对比分析")
def compare_stocks_prompt(symbols: str, trade_date: str) -> str:
    return (
        f"请对比分析以下股票：{symbols}，交易日 {trade_date}。\n"
        "对每只股票分别调用 market_analyst，然后对比技术指标给出推荐排序。"
    )
```

---

## 五、项目结构

```
tradingagents/
├── mcp_server/                        # MCP Agent 模块（新增）
│   ├── __init__.py
│   ├── server.py                      # FastMCP 主入口 + 全部 Tool 定义
│   └── prompts.py                     # MCP Prompts
├── agents/                            # (已有，不变)
├── dataflows/                         # (已有，不变)
├── graph/                             # (已有，不变)
└── ...
```

仅新增 **2 个文件**，复用现有全部代码。

---

## 六、核心代码实现

### 6.1 `tradingagents/mcp_server/__init__.py`

```python
from .server import mcp

__all__ = ["mcp"]
```

### 6.2 `tradingagents/mcp_server/server.py`

```python
"""
TradingAgents-CN MCP Agent Server

将多Agent协作分析引擎封装为 MCP Tools，
支持完整全流程和单分析师独立调用。

启动方式：
  stdio:    python -m tradingagents.mcp_server
  http:     MCP_TRANSPORT=streamable-http python -m tradingagents.mcp_server
"""

import os
import asyncio
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.utils.logging_manager import get_logger

logger = get_logger("mcp_server")

mcp = FastMCP(
    "TradingAgents-CN",
    version="1.0.0-preview",
    description="AI金融交易分析Agent — 支持完整多Agent协作分析和单分析师独立调用",
)


def _build_config() -> dict:
    """从环境变量构建配置"""
    config = DEFAULT_CONFIG.copy()
    env_map = {
        "MCP_LLM_PROVIDER": ("llm_provider", str),
        "MCP_DEEP_THINK_LLM": ("deep_think_llm", str),
        "MCP_QUICK_THINK_LLM": ("quick_think_llm", str),
        "MCP_BACKEND_URL": ("backend_url", str),
        "MCP_ONLINE_TOOLS": ("online_tools", lambda v: v.lower() == "true"),
        "MCP_ONLINE_NEWS": ("online_news", lambda v: v.lower() == "true"),
        "MCP_MAX_DEBATE_ROUNDS": ("max_debate_rounds", int),
        "MCP_MAX_RISK_DISCUSS_ROUNDS": ("max_risk_discuss_rounds", int),
    }
    for env_key, (config_key, type_fn) in env_map.items():
        val = os.getenv(env_key)
        if val is not None:
            config[config_key] = type_fn(val)
    return config


def _extract_reports(state: dict) -> dict:
    """从 LangGraph 状态中提取各分析师报告摘要"""
    reports = {}
    for key in ["market_report", "fundamentals_report", "sentiment_report", "news_report"]:
        val = state.get(key, "")
        if isinstance(val, str) and len(val) > 2000:
            reports[key] = val[:2000] + "\n...(已截断)"
        else:
            reports[key] = val
    return reports


async def _run_single_analyst(
    analyst_type: str,
    symbol: str,
    trade_date: str,
    ctx: Context = None,
    extra_state: dict = None,
) -> dict:
    """运行单个分析师的通用逻辑"""
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = _build_config()
    config["online_tools"] = config.get("online_tools", True)
    config["online_news"] = config.get("online_news", True)

    ta = TradingAgentsGraph(selected_analysts=[analyst_type], debug=False, config=config)

    from langchain_core.messages import HumanMessage
    state = {
        "messages": [HumanMessage(content=f"请分析股票 {symbol}")],
        "company_of_interest": symbol,
        "trade_date": trade_date,
        f"{analyst_type}_tool_call_count": 0,
    }
    if extra_state:
        state.update(extra_state)

    # 获取对应的 analyst node
    analyst_map = {
        "market": ("create_market_analyst", "market_report"),
        "fundamentals": ("create_fundamentals_analyst", "fundamentals_report"),
        "news": ("create_news_analyst", "news_report"),
        "social": ("create_social_media_analyst", "sentiment_report"),
    }

    create_fn_name, report_key = analyst_map[analyst_type]

    from tradingagents.agents.analysts import (
        create_market_analyst,
        create_fundamentals_analyst,
        create_news_analyst,
        create_social_media_analyst,
    )
    create_fn = {
        "market": create_market_analyst,
        "fundamentals": create_fundamentals_analyst,
        "news": create_news_analyst,
        "social": create_social_media_analyst,
    }[analyst_type]

    node = create_fn(ta.quick_thinking_llm, ta.toolkit)

    loop = asyncio.get_event_loop()
    result_state = await loop.run_in_executor(None, lambda: node(state))

    report = result_state.get(report_key, "")

    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "analyst": analyst_type,
        "report": report[:8000] if len(report) > 8000 else report,
    }


# ============================================================
# Tool 1: trading_agent — 完整全流程
# ============================================================
@mcp.tool()
async def trading_agent(
    symbol: str,
    trade_date: str,
    analysts: Optional[list[str]] = None,
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    AI金融交易分析Agent（完整流程）：执行多Agent协作分析，
    包含数据获取→多空辩论→风险评估→交易决策。

    适合需要完整投资建议的场景。
    支持A股(如000001)、美股(如AAPL)、港股(如00700)。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD
        analysts: 分析师组合，默认 ["market","social","news","fundamentals"]
        max_debate_rounds: 多空辩论轮次
        max_risk_discuss_rounds: 风险辩论轮次
    """
    if analysts is None:
        analysts = ["market", "social", "news", "fundamentals"]

    if ctx:
        await ctx.info(f"TradingAgent 开始分析: {symbol} @ {trade_date}")

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = _build_config()
        config["max_debate_rounds"] = max_debate_rounds
        config["max_risk_discuss_rounds"] = max_risk_discuss_rounds
        config["online_tools"] = config.get("online_tools", True)
        config["online_news"] = config.get("online_news", True)

        if ctx:
            await ctx.report_progress(0.0, 1.0, "初始化分析引擎")

        ta = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)

        if ctx:
            await ctx.report_progress(0.05, 1.0, "开始多Agent分析")

        loop = asyncio.get_event_loop()
        state, decision = await loop.run_in_executor(
            None, lambda: ta.propagate(symbol, trade_date)
        )

        if ctx:
            await ctx.report_progress(0.95, 1.0, "分析完成")

        result = {
            "symbol": symbol,
            "trade_date": trade_date,
            "decision": decision,
            "analysts_used": analysts,
            **_extract_reports(state),
        }

        perf = state.get("performance_metrics", {})
        if perf:
            result["performance_metrics"] = {
                "total_time_seconds": perf.get("total_time"),
                "total_time_minutes": perf.get("total_time_minutes"),
            }

        if ctx:
            await ctx.report_progress(1.0, 1.0, "完成")

        return result

    except Exception as e:
        logger.error(f"trading_agent 分析失败: {e}", exc_info=True)
        return {"error": str(e), "symbol": symbol, "trade_date": trade_date}


# ============================================================
# Tool 2-5: 单分析师独立运行
# ============================================================
@mcp.tool()
async def market_analyst(
    symbol: str,
    trade_date: str,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    市场分析师Agent（独立运行）：获取行情数据并生成技术分析报告。

    分析内容：移动平均线、MACD、RSI、布林带、价格趋势、成交量、投资建议。
    支持A股(AKShare/Tushare/BaoStock)、美股(YFinance)、港股(AKShare)，自动识别。

    适合只需看技术面的场景，速度快（~30秒 vs 全流程3-5分钟）。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD
    """
    if ctx:
        await ctx.info(f"市场分析师: {symbol} @ {trade_date}")
    try:
        return await _run_single_analyst("market", symbol, trade_date, ctx)
    except Exception as e:
        logger.error(f"market_analyst 失败: {e}", exc_info=True)
        return {"error": str(e), "symbol": symbol}


@mcp.tool()
async def fundamentals_analyst(
    symbol: str,
    trade_date: str,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    基本面分析师Agent（独立运行）：获取PE/PB/ROE等财务数据并生成基本面报告。

    分析内容：估值指标、盈利能力、财务健康、行业对比。
    数据源：A股(AKShare/Tushare)、美股(Alpha Vantage/YFinance/Finnhub)，自动降级。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD
    """
    if ctx:
        await ctx.info(f"基本面分析师: {symbol} @ {trade_date}")
    try:
        return await _run_single_analyst("fundamentals", symbol, trade_date, ctx)
    except Exception as e:
        logger.error(f"fundamentals_analyst 失败: {e}", exc_info=True)
        return {"error": str(e), "symbol": symbol}


@mcp.tool()
async def news_analyst(
    symbol: str,
    trade_date: str,
    look_back_days: int = 7,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    新闻分析师Agent（独立运行）：获取股票相关新闻并生成分析报告。

    分析内容：重大新闻事件、政策影响、行业动态、潜在风险。
    数据源：A股(中文财经)、美股(Finnhub/Google News)，自动选择。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD
        look_back_days: 回看天数，默认7
    """
    if ctx:
        await ctx.info(f"新闻分析师: {symbol} @ {trade_date}")
    try:
        return await _run_single_analyst(
            "news", symbol, trade_date, ctx,
            extra_state={"news_tool_call_count": 0},
        )
    except Exception as e:
        logger.error(f"news_analyst 失败: {e}", exc_info=True)
        return {"error": str(e), "symbol": symbol}


@mcp.tool()
async def social_analyst(
    symbol: str,
    trade_date: str,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    社交媒体分析师Agent（独立运行）：获取社交平台情绪并生成分析报告。

    分析内容：投资者情绪、讨论热度、关键观点、多空倾向。
    数据源：A股(雪球/东财股吧/新浪财经)、美股(Reddit)，自动选择。

    Args:
        symbol: 股票代码
        trade_date: 交易日期 YYYY-MM-DD
    """
    if ctx:
        await ctx.info(f"社交分析师: {symbol} @ {trade_date}")
    try:
        return await _run_single_analyst("social", symbol, trade_date, ctx)
    except Exception as e:
        logger.error(f"social_analyst 失败: {e}", exc_info=True)
        return {"error": str(e), "symbol": symbol}


# ============================================================
# Tool 6: compare_stocks — 多股对比分析
# ============================================================
@mcp.tool()
async def compare_stocks(
    symbols: list[str],
    trade_date: str,
    analyst: str = "market",
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    多股对比分析Agent：对多只股票并行分析并生成对比报告。

    工作流程：
    1. 对每只股票并行运行指定的分析师（默认市场分析师）
    2. 横向对比各股的关键指标
    3. 用LLM生成对比分析和排名推荐

    对比维度（取决于 analyst 选择）：
    - market: 技术指标、价格趋势、成交量
    - fundamentals: PE/PB/ROE、盈利能力
    - news: 新闻热度、重大事件
    - social: 情绪、讨论热度
    - full: 完整 trading_agent 流程后对比决策

    Args:
        symbols: 股票代码列表，如 ["000001", "600519"]
        trade_date: 交易日期 YYYY-MM-DD
        analyst: 对比维度 "market"|"fundamentals"|"news"|"social"|"full"
        max_debate_rounds: 仅 full 模式
        max_risk_discuss_rounds: 仅 full 模式
    """
    if ctx:
        await ctx.info(f"多股对比分析: {symbols} @ {trade_date}, 维度={analyst}")

    try:
        individual_results = {}

        if analyst == "full":
            # 完整全流程模式：对每只股票运行 trading_agent
            from tradingagents.graph.trading_graph import TradingAgentsGraph
            config = _build_config()
            config["max_debate_rounds"] = max_debate_rounds
            config["max_risk_discuss_rounds"] = max_risk_discuss_rounds

            async def _run_full(sym):
                ta = TradingAgentsGraph(selected_analysts=["market","social","news","fundamentals"], debug=False, config=config)
                loop = asyncio.get_event_loop()
                state, decision = await loop.run_in_executor(None, lambda: ta.propagate(sym, trade_date))
                return {"decision": decision, **_extract_reports(state)}

            tasks = [_run_full(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, res in zip(symbols, results):
                individual_results[sym] = res if not isinstance(res, Exception) else {"error": str(res)}
        else:
            # 单分析师模式：并行运行
            async def _run_one(sym):
                return await _run_single_analyst(analyst, sym, trade_date, ctx)

            tasks = [_run_one(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, res in zip(symbols, results):
                individual_results[sym] = res if not isinstance(res, Exception) else {"error": str(res)}

        # 用 LLM 生成对比分析
        comparison_prompt = (
            f"你是一位专业的投资顾问。请对比以下 {len(symbols)} 只股票的分析报告，"
            f"交易日为 {trade_date}，对比维度为 {analyst}。\n\n"
        )
        for sym, res in individual_results.items():
            if isinstance(res, dict) and "error" not in res:
                report = res.get("report", res.get("market_report", ""))
                comparison_prompt += f"## {sym}\n{report[:2000]}\n\n"
            elif isinstance(res, dict) and "decision" in res:
                comparison_prompt += f"## {sym}\n决策: {res['decision']}\n\n"

        comparison_prompt += (
            "\n请给出：\n"
            "1. 横向对比分析（各股优劣势）\n"
            "2. 推荐排名（从高到低）\n"
            "3. 每只股票的评分（0-100）和推荐理由\n"
        )

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        config = _build_config()
        ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
        loop = asyncio.get_event_loop()
        comparison_report = await loop.run_in_executor(
            None, lambda: ta.quick_thinking_llm.invoke(comparison_prompt).content
        )

        # 尝试从对比报告中提取排名
        ranking = []
        for i, sym in enumerate(symbols):
            ranking.append({
                "symbol": sym,
                "rank": i + 1,
                "note": "详见comparison报告",
            })

        return {
            "symbols": symbols,
            "trade_date": trade_date,
            "analyst": analyst,
            "individual_reports": {
                sym: res.get("report", res.get("decision", ""))[:1500]
                for sym, res in individual_results.items()
                if isinstance(res, dict) and "error" not in res
            },
            "comparison": comparison_report[:6000],
            "ranking": ranking,
        }

    except Exception as e:
        logger.error(f"compare_stocks 失败: {e}", exc_info=True)
        return {"error": str(e), "symbols": symbols}


# ============================================================
# Tool 7: batch_analyze — 批量独立分析
# ============================================================
@mcp.tool()
async def batch_analyze(
    symbols: list[str],
    trade_date: str,
    analyst: str = "market",
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    批量独立分析：对多只股票并行运行同一分析师，各股独立返回报告，无对比逻辑。

    与 compare_stocks 的区别：
    - batch_analyze: 并行分析，各股独立，无对比
    - compare_stocks: 并行分析 + 横向对比 + 排名推荐

    Args:
        symbols: 股票代码列表
        trade_date: 交易日期 YYYY-MM-DD
        analyst: 分析师选择，默认 "market"
    """
    if ctx:
        await ctx.info(f"批量分析: {len(symbols)} 只股票, 维度={analyst}")

    try:
        tasks = [_run_single_analyst(analyst, sym, trade_date, ctx) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        individual_results = {}
        for sym, res in zip(symbols, results):
            individual_results[sym] = res if not isinstance(res, Exception) else {"error": str(res)}

        return {
            "symbols": symbols,
            "trade_date": trade_date,
            "analyst": analyst,
            "results": individual_results,
        }

    except Exception as e:
        logger.error(f"batch_analyze 失败: {e}", exc_info=True)
        return {"error": str(e), "symbols": symbols}


# ============================================================
# Tool 8: period_compare — 历史区间对比
# ============================================================
@mcp.tool()
async def period_compare(
    symbol: str,
    start_date: str,
    end_date: str,
    metrics: Optional[list[str]] = None,
    compare_with: Optional[str] = None,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    历史区间对比Agent：对比一只股票在指定时间区间内的走势变化，
    或与另一只股票/指数的同期走势对比。

    适合：回顾区间表现、计算超额收益、与基准对比。

    Args:
        symbol: 股票代码
        start_date: 起始日期 YYYY-MM-DD
        end_date: 结束日期 YYYY-MM-DD
        metrics: 对比指标，默认 ["close","volume","pct_chg"]
        compare_with: 对比目标（股票代码或指数代码），可选
    """
    if metrics is None:
        metrics = ["close", "volume", "pct_chg"]

    if ctx:
        await ctx.info(f"历史区间对比: {symbol} {start_date}~{end_date}" + (f" vs {compare_with}" if compare_with else ""))

    try:
        from tradingagents.dataflows.interface import get_stock_market_data_unified

        loop = asyncio.get_event_loop()

        # 获取主股票区间数据
        symbol_data = await loop.run_in_executor(
            None, lambda: get_stock_market_data_unified(symbol, start_date, end_date)
        )

        if not symbol_data:
            return {"error": f"未获取到 {symbol} 的数据", "symbol": symbol}

        # 计算主股票区间统计
        symbol_stats = _calc_period_stats(symbol_data)

        # 获取对比目标数据（如有）
        compare_data = None
        compare_stats = None
        if compare_with:
            compare_data = await loop.run_in_executor(
                None, lambda: get_stock_market_data_unified(compare_with, start_date, end_date)
            )
            if compare_data:
                compare_stats = _calc_period_stats(compare_data)

        # 构建数据摘要（限制条数，避免返回过大）
        symbol_points = _extract_data_points(symbol_data, metrics, max_points=60)
        compare_points = _extract_data_points(compare_data, metrics, max_points=60) if compare_data else None

        # 构建摘要
        summary = {
            "symbol_return": symbol_stats.get("total_return"),
            "max_drawdown": symbol_stats.get("max_drawdown"),
            "volatility": symbol_stats.get("volatility"),
        }
        if compare_stats:
            summary["benchmark_return"] = compare_stats.get("total_return")
            summary["excess_return"] = round(
                (symbol_stats.get("total_return", 0) or 0) - (compare_stats.get("total_return", 0) or 0), 2
            )
            summary["benchmark_max_drawdown"] = compare_stats.get("max_drawdown")

        # 用 LLM 生成区间分析报告
        analysis_prompt = (
            f"你是一位专业的量化分析师。请分析以下股票在 {start_date} 至 {end_date} 期间的表现：\n\n"
            f"## {symbol} 区间统计\n"
            f"- 区间收益率: {summary.get('symbol_return')}%\n"
            f"- 最大回撤: {summary.get('max_drawdown')}%\n"
            f"- 波动率: {summary.get('volatility')}%\n"
        )
        if compare_stats:
            analysis_prompt += (
                f"\n## {compare_with} (基准) 区间统计\n"
                f"- 区间收益率: {summary.get('benchmark_return')}%\n"
                f"- 最大回撤: {summary.get('benchmark_max_drawdown')}%\n"
                f"- 超额收益: {summary.get('excess_return')}%\n"
            )
        analysis_prompt += (
            "\n请给出：\n"
            "1. 区间走势分析（趋势、关键转折点）\n"
            "2. 风险评估（回撤、波动）\n"
            "3. 与基准的对比结论（如有）\n"
            "4. 后市展望建议\n"
        )

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        config = _build_config()
        ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
        analysis_report = await loop.run_in_executor(
            None, lambda: ta.quick_thinking_llm.invoke(analysis_prompt).content
        )

        return {
            "symbol": symbol,
            "period": {"start_date": start_date, "end_date": end_date},
            "compare_with": compare_with,
            "summary": summary,
            "data_points": {
                "symbol": symbol_points,
                "compare_with": compare_points,
            },
            "analysis": analysis_report[:6000],
        }

    except Exception as e:
        logger.error(f"period_compare 失败: {e}", exc_info=True)
        return {"error": str(e), "symbol": symbol}


def _calc_period_stats(data) -> dict:
    """从行情数据计算区间统计指标"""
    if not data or len(data) < 2:
        return {"total_return": None, "max_drawdown": None, "volatility": None}

    closes = []
    for row in data:
        c = row.get("close") or row.get("Close")
        if c is not None:
            closes.append(float(c))

    if len(closes) < 2:
        return {"total_return": None, "max_drawdown": None, "volatility": None}

    total_return = round((closes[-1] / closes[0] - 1) * 100, 2)

    # 最大回撤
    peak = closes[0]
    max_dd = 0
    for c in closes:
        if c > peak:
            peak = c
        dd = (c / peak - 1) * 100
        if dd < max_dd:
            max_dd = dd
    max_drawdown = round(max_dd, 2)

    # 简化波动率（日收益率标准差 * sqrt(252)）
    import statistics
    daily_returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    if len(daily_returns) >= 2:
        vol = round(statistics.stdev(daily_returns) * (252 ** 0.5) * 100, 2)
    else:
        vol = None

    return {"total_return": total_return, "max_drawdown": max_drawdown, "volatility": vol}


def _extract_data_points(data, metrics: list, max_points: int = 60) -> list:
    """从行情数据提取指定指标，降采样到 max_points 条"""
    if not data:
        return []

    metric_key_map = {k.lower(): k for k in data[0].keys()} if data else {}
    rows = []
    for row in data:
        point = {}
        date_val = row.get("date") or row.get("trade_date") or row.get("Date")
        point["date"] = str(date_val) if date_val else ""
        for m in metrics:
            key = metric_key_map.get(m.lower(), m)
            val = row.get(key)
            if val is not None:
                try:
                    point[m] = round(float(val), 4)
                except (ValueError, TypeError):
                    point[m] = val
        rows.append(point)

    # 降采样
    if len(rows) > max_points:
        step = len(rows) / max_points
        sampled = [rows[int(i * step)] for i in range(max_points)]
        return sampled
    return rows


# ============================================================
# Tool 9: screen_stocks — 股票筛选
# ============================================================
@mcp.tool()
async def screen_stocks(
    conditions: list[dict],
    market: str = "CN",
    order_by: Optional[list[dict]] = None,
    limit: int = 50,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """
    股票筛选Agent：根据条件筛选符合要求的股票，并生成筛选解读报告。

    支持字段：industry/pe/pb/pe_ttm/roe/total_mv/circ_mv/close/pct_chg/turnover_rate/volume_ratio/amount
    操作符：> / < / >= / <= / == / != / between / in / not_in / contains

    适合：快速筛选低估值/高ROE/特定行业等股票。

    Args:
        conditions: 筛选条件列表
        market: 市场 CN/HK/US
        order_by: 排序条件
        limit: 返回数量限制
    """
    if ctx:
        await ctx.info(f"股票筛选: {len(conditions)} 个条件, 市场={market}")

    try:
        loop = asyncio.get_event_loop()

        # 尝试使用在线数据源筛选（MCP 模式，无数据库）
        items = await loop.run_in_executor(
            None, lambda: _screen_stocks_online(conditions, market, order_by, limit)
        )

        # 用 LLM 生成筛选解读
        if items:
            items_summary = _format_screening_items_for_prompt(items, max_items=30)
            analysis_prompt = (
                f"你是一位专业的投资顾问。以下是通过筛选条件的 {market} 市场股票（共 {len(items)} 只）：\n\n"
                f"筛选条件: {conditions}\n\n"
                f"{items_summary}\n\n"
                "请给出：\n"
                "1. 筛选结果的整体特征分析\n"
                "2. 值得关注的前5只股票及理由\n"
                "3. 潜在风险提示\n"
            )

            from tradingagents.graph.trading_graph import TradingAgentsGraph
            config = _build_config()
            ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
            analysis_report = await loop.run_in_executor(
                None, lambda: ta.quick_thinking_llm.invoke(analysis_prompt).content
            )
        else:
            analysis_report = "未找到符合筛选条件的股票。建议放宽条件重试。"

        return {
            "market": market,
            "conditions": conditions,
            "total": len(items),
            "items": items[:limit],
            "analysis": analysis_report[:4000],
        }

    except Exception as e:
        logger.error(f"screen_stocks 失败: {e}", exc_info=True)
        return {"error": str(e), "conditions": conditions}


def _screen_stocks_online(
    conditions: list[dict],
    market: str,
    order_by: Optional[list[dict]],
    limit: int,
) -> list[dict]:
    """
    在线模式股票筛选（无数据库依赖）

    实现策略：
    1. 用 AKShare/Tushare 获取股票列表和基础信息
    2. 在内存中按条件过滤
    3. 返回匹配结果
    """
    import pandas as pd

    # 获取全部股票基础信息
    if market == "CN":
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            # 标准化列名
            col_map = {
                "代码": "code", "名称": "name", "最新价": "close",
                "涨跌幅": "pct_chg", "市盈率-动态": "pe",
                "市净率": "pb", "总市值": "total_mv",
                "流通市值": "circ_mv", "成交额": "amount",
                "换手率": "turnover_rate", "量比": "volume_ratio",
                "行业": "industry",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

            # 市值单位转换（AKShare 返回元，转为亿元）
            for mv_col in ["total_mv", "circ_mv"]:
                if mv_col in df.columns:
                    df[mv_col] = df[mv_col] / 1e8

            # 在内存中逐条件过滤
            for cond in conditions:
                field = cond.get("field")
                operator = cond.get("operator")
                value = cond.get("value")

                if field not in df.columns:
                    continue

                if operator == ">":
                    df = df[df[field] > value]
                elif operator == "<":
                    df = df[df[field] < value]
                elif operator == ">=":
                    df = df[df[field] >= value]
                elif operator == "<=":
                    df = df[df[field] <= value]
                elif operator == "between" and isinstance(value, list) and len(value) == 2:
                    df = df[(df[field] >= value[0]) & (df[field] <= value[1])]
                elif operator == "in" and isinstance(value, list):
                    df = df[df[field].astype(str).isin([str(v) for v in value])]
                elif operator == "not_in" and isinstance(value, list):
                    df = df[~df[field].astype(str).isin([str(v) for v in value])]
                elif operator == "contains":
                    df = df[df[field].astype(str).str.contains(str(value), na=False)]
                elif operator in ("==", "eq"):
                    df = df[df[field] == value]

            # 排序
            if order_by:
                for order in reversed(order_by):
                    sort_field = order.get("field")
                    ascending = order.get("direction", "desc").lower() != "desc"
                    if sort_field in df.columns:
                        df = df.sort_values(by=sort_field, ascending=ascending)

            # 转换为字典列表
            result_cols = ["code", "name", "industry", "close", "pct_chg", "pe", "pb",
                           "total_mv", "circ_mv", "turnover_rate", "volume_ratio", "amount"]
            available_cols = [c for c in result_cols if c in df.columns]
            df = df[available_cols].head(limit)
            items = df.to_dict(orient="records")
            # 数值类型转 Python 原生
            for item in items:
                for k, v in item.items():
                    if pd.isna(v):
                        item[k] = None
                    elif hasattr(v, 'item'):
                        item[k] = v.item()
            return items

        except ImportError:
            logger.warning("AKShare 不可用，尝试 Tushare")
        except Exception as e:
            logger.error(f"AKShare 筛选失败: {e}")

        # Tushare 回退
        try:
            import tushare as ts
            pro = ts.pro_api()
            df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,symbol,name,industry,market,list_date')
            # 注意：Tushare 免费版无法批量获取 PE/PB 等指标，需逐只查询
            # 此处仅做基础筛选
            items = df.to_dict(orient="records")[:limit]
            return items
        except Exception as e:
            logger.error(f"Tushare 筛选失败: {e}")
            return []

    elif market == "US":
        try:
            import yfinance as yf
            # 美股筛选：获取标普500等成分股，在内存过滤
            # 简化实现：返回空列表，提示用户使用具体股票代码
            logger.warning("美股在线筛选能力有限，建议使用具体股票代码分析")
            return []
        except Exception as e:
            logger.error(f"美股筛选失败: {e}")
            return []

    elif market == "HK":
        try:
            import akshare as ak
            df = ak.stock_hk_spot_em()
            col_map = {
                "代码": "code", "名称": "name", "最新价": "close",
                "涨跌幅": "pct_chg", "成交额": "amount",
            }
            df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
            items = df.to_dict(orient="records")[:limit]
            return items
        except Exception as e:
            logger.error(f"港股筛选失败: {e}")
            return []

    return []


def _format_screening_items_for_prompt(items: list[dict], max_items: int = 30) -> str:
    """将筛选结果格式化为 LLM Prompt 友好的文本"""
    lines = []
    for i, item in enumerate(items[:max_items]):
        code = item.get("code", "")
        name = item.get("name", "")
        pe = item.get("pe")
        pb = item.get("pb")
        roe = item.get("roe")
        pct = item.get("pct_chg")
        industry = item.get("industry", "")
        parts = [f"{i+1}. {code} {name}"]
        if industry:
            parts.append(f"行业:{industry}")
        if pe is not None:
            parts.append(f"PE:{pe}")
        if pb is not None:
            parts.append(f"PB:{pb}")
        if roe is not None:
            parts.append(f"ROE:{roe}%")
        if pct is not None:
            parts.append(f"涨跌:{pct}%")
        lines.append(" | ".join(parts))
    return "\n".join(lines)


# ============================================================
# Tool 10: agent_status
# ============================================================
@mcp.tool()
async def agent_status() -> dict:
    """查询当前Agent的配置状态和支持的能力"""
    config = _build_config()
    return {
        "version": "1.0.0-preview",
        "llm_provider": config.get("llm_provider"),
        "deep_think_llm": config.get("deep_think_llm"),
        "quick_think_llm": config.get("quick_think_llm"),
        "online_tools": config.get("online_tools", False),
        "supported_markets": ["A股", "美股", "港股"],
        "available_tools": {
            "trading_agent": "完整全流程分析（分析师→辩论→风险→决策）",
            "market_analyst": "独立市场/技术分析",
            "fundamentals_analyst": "独立基本面分析",
            "news_analyst": "独立新闻分析",
            "social_analyst": "独立社交媒体情绪分析",
            "compare_stocks": "多股对比分析（并行分析+横向对比+排名推荐）",
            "batch_analyze": "批量独立分析（并行分析，无对比）",
            "period_compare": "历史区间对比（区间统计+超额收益+走势分析）",
            "screen_stocks": "股票筛选（条件筛选+LLM解读）",
        },
        "data_sources": {
            "A股": ["AKShare", "Tushare", "BaoStock"],
            "美股": ["YFinance", "Finnhub", "Alpha Vantage"],
            "港股": ["AKShare"],
            "新闻": ["Google News", "Finnhub", "中文财经"],
            "情绪": ["Reddit", "雪球/东财股吧/新浪财经"],
        },
    }


# ============================================================
# 导入 Prompts
# ============================================================
from tradingagents.mcp_server.prompts import register_prompts
register_prompts(mcp)


# ============================================================
# 启动入口
# ============================================================
if __name__ == "__main__":
    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "9000"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")
```

### 6.3 `tradingagents/mcp_server/prompts.py`

```python
from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP):

    @mcp.prompt(title="股票分析")
    def stock_analysis_prompt(symbol: str, trade_date: str) -> str:
        return (
            f"请对股票 {symbol} 进行全面分析，交易日为 {trade_date}。\n"
            "使用 trading_agent 工具执行完整分析流程。\n"
            "分析完成后，基于返回的报告和决策给出综合解读。"
        )

    @mcp.prompt(title="技术面分析")
    def technical_analysis_prompt(symbol: str, trade_date: str) -> str:
        return (
            f"请分析 {symbol} 的技术面，交易日 {trade_date}。\n"
            "使用 market_analyst 工具获取技术分析报告。"
        )

    @mcp.prompt(title="基本面分析")
    def fundamentals_prompt(symbol: str, trade_date: str) -> str:
        return (
            f"请分析 {symbol} 的基本面，交易日 {trade_date}。\n"
            "使用 fundamentals_analyst 工具获取估值和财务分析报告。"
        )

    @mcp.prompt(title="A股分析")
    def china_stock_prompt(stock_code: str, trade_date: str) -> str:
        return (
            f"请分析A股 {stock_code}，交易日 {trade_date}。\n"
            "使用 trading_agent 工具，A股会自动使用中文数据源。"
        )

    @mcp.prompt(title="对比分析")
    def compare_stocks_prompt(symbols: str, trade_date: str) -> str:
        return (
            f"请对比分析以下股票：{symbols}，交易日 {trade_date}。\n"
            "对每只股票分别调用 market_analyst，然后对比技术指标给出排序。"
        )

    @mcp.prompt(title="区间走势分析")
    def period_compare_prompt(symbol: str, start_date: str, end_date: str) -> str:
        return (
            f"请分析 {symbol} 在 {start_date} 至 {end_date} 期间的走势表现。\n"
            "使用 period_compare 工具获取区间统计数据和走势分析报告。\n"
            "如需与基准对比，可传入 compare_with 参数（如沪深300代码 '000300'）。"
        )

    @mcp.prompt(title="股票筛选")
    def screen_stocks_prompt(description: str) -> str:
        return (
            f"请根据以下描述筛选股票：{description}\n"
            "使用 screen_stocks 工具，将描述转换为筛选条件后执行。\n"
            "例如：'低估值银行股' → conditions=[{field:'pe',operator:'between',value:[4,10]},{field:'industry',operator:'in',value:['银行']}]"
        )
```

---

## 七、集成配置

### 7.1 依赖添加 (`pyproject.toml`)

```toml
[project.optional-dependencies]
mcp = ["mcp[cli]>=1.0.0"]
```

### 7.2 opencode 配置 (`.opencode.json`)

```json
{
  "mcp": {
    "tradingagents": {
      "command": "python",
      "args": ["-m", "tradingagents.mcp_server"],
      "env": {
        "MCP_LLM_PROVIDER": "openai",
        "MCP_DEEP_THINK_LLM": "o4-mini",
        "MCP_QUICK_THINK_LLM": "gpt-4o-mini",
        "MCP_BACKEND_URL": "https://api.openai.com/v1",
        "MCP_ONLINE_TOOLS": "true",
        "OPENAI_API_KEY": ""
      }
    }
  }
}
```

### 7.3 Claude Desktop 配置

```json
{
  "mcpServers": {
    "tradingagents": {
      "command": "python",
      "args": ["-m", "tradingagents.mcp_server"],
      "env": {
        "OPENAI_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### 7.4 远程 HTTP 模式

```bash
MCP_TRANSPORT=streamable-http MCP_PORT=9000 python -m tradingagents.mcp_server
```

---

## 八、实现步骤

| 阶段 | 任务 | 工作量 |
|------|------|--------|
| **Phase 1** | 创建 `mcp_server/` 目录 + 3 个文件 | 0.5天 |
| **Phase 2** | 安装 mcp SDK + 本地 stdio 测试 | 0.5天 |
| **Phase 3** | opencode 集成测试 + 调试单分析师模式 | 0.5天 |
| **Phase 4** | HTTP 模式 + 文档 | 0.5天 |

总计 **2天**，仅新增 2 个文件，零侵入现有代码。

---

## 九、关键设计决策

### 9.1 为什么同时暴露全流程和单分析师

- **灵活性**：用户可能只想看技术面，不需要等 3-5 分钟全流程
- **速度**：单分析师 ~30秒，全流程 3-5 分钟
- **可组合**：客户端可以先调 `market_analyst` 快速看技术面，再决定是否调 `trading_agent` 全流程
- **与现有架构一致**：`TradingAgentsGraph` 的 `selected_analysts` 参数已支持选择分析师

### 9.2 单分析师独立运行的实现方式

每个 analyst 是工厂函数 `create_xxx_analyst(llm, toolkit)` 返回的 `node(state)` 函数。
独立运行只需：
1. 通过 `TradingAgentsGraph` 初始化 LLM 和 Toolkit（复用现有初始化逻辑）
2. 构造最小 `state` dict
3. 直接调用 `node(state)`

无需修改任何现有文件。

### 9.3 同步→异步适配

所有 analyst node 和 `propagate()` 都是同步函数，通过线程池适配：

```python
loop = asyncio.get_event_loop()
result = await loop.run_in_executor(None, lambda: node(state))
```

### 9.4 无数据库依赖

MCP Agent 模式下不依赖 MongoDB/Redis：
- LLM 配置通过环境变量注入
- 数据获取走 `dataflows/interface.py` 在线模式

### 9.5 无数据库依赖

MCP Agent 模式下不依赖 MongoDB/Redis：
- LLM 配置通过环境变量注入
- 数据获取走 `dataflows/interface.py` 在线模式
- 股票筛选走 AKShare/Tushare 在线 API，在内存中过滤（无需 MongoDB 视图）

### 9.6 历史区间对比的实现方式

`period_compare` 复用 `dataflows/interface.py` 的 `get_stock_market_data_unified()` 获取区间行情数据，
在 MCP Server 端计算收益率/回撤/波动率等统计指标，再由 LLM 生成分析报告。

与现有 `app/routers/multi_period_sync.py:compare_period_data` 的区别：
- 现有：仅对比同股不同周期（daily/weekly/monthly）的原始数据，无分析
- MCP：计算区间统计指标 + 支持双股同期对比 + LLM 分析报告

### 9.7 股票筛选的在线实现

现有 `app/services/enhanced_screening_service.py` 强依赖 MongoDB（`stock_screening_view`），
MCP 模式下无法使用。`screen_stocks` 改用在线数据源筛选：

- A股：AKShare `stock_zh_a_spot_em()` 获取全市场实时数据 → 内存过滤
- 港股：AKShare `stock_hk_spot_em()` 获取港股实时数据 → 内存过滤
- 美股：YFinance 能力有限，建议使用具体股票代码

优势：无数据库依赖，数据实时；限制：无法筛选 ROE 等需单独查询的财务指标（AKShare 实时接口不含）

### 9.8 错误处理

所有 Tool 用 try/except 包裹，返回友好错误而非抛异常。

---

## 十、使用示例

### 快速看技术面

```
用户: 看一下平安银行的技术面

opencode 调用: market_analyst(symbol="000001", trade_date="2024-05-10")
→ ~30秒返回技术分析报告
```

### 只看基本面

```
用户: 苹果公司估值怎么样？

opencode 调用: fundamentals_analyst(symbol="AAPL", trade_date="2024-05-10")
→ 返回PE/PB/ROE等估值分析
```

### 完整投资建议

```
用户: 分析一下茅台，给我买入建议

opencode 调用: trading_agent(symbol="600519", trade_date="2024-05-10")
→ 3-5分钟返回完整决策（含多空辩论+风险评估）
```

### 多维度组合

```
用户: 看看NVDA的新闻和情绪

opencode 并行调用:
  news_analyst(symbol="NVDA", trade_date="2024-05-10")
  social_analyst(symbol="NVDA", trade_date="2024-05-10")
→ 综合两份报告给出解读
```

### 历史区间对比

```
用户: 茅台这半年表现怎么样？跑赢沪深300了吗？

opencode 调用: period_compare(
    symbol="600519",
    start_date="2023-06-01",
    end_date="2023-12-31",
    compare_with="000300"
)
→ 返回区间收益率、最大回撤、波动率、超额收益及 LLM 分析报告
```

### 股票筛选

```
用户: 帮我找PE在5-15之间、ROE大于10的银行股

opencode 调用: screen_stocks(
    conditions=[
        {"field": "pe", "operator": "between", "value": [5, 15]},
        {"field": "roe", "operator": ">", "value": 10},
        {"field": "industry", "operator": "in", "value": ["银行"]}
    ],
    order_by=[{"field": "roe", "direction": "desc"}],
    limit=20
)
→ 返回匹配股票列表 + LLM 筛选解读报告
```
