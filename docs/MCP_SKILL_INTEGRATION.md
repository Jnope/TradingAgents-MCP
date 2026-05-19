# TradingAgents-CN MCP + Skill 集成方案

> Skill 是 opencode 识别用户意图并正确调用 MCP Tool 的"大脑"，MCP 是执行层。
> 两者必须配合，否则 opencode 会调错工具、传错参数、忽略前置检查。

---

## 一、为什么必须配合 Skill

### 1.1 现有 Skill 的问题

当前 `~/.config/opencode/skills/trading-agents/SKILL.md` 是**上游英文版**的 skill，
与本项目 MCP 完全不匹配：

| 维度 | 现有 Skill | 本项目 MCP | 后果 |
|------|-----------|-----------|------|
| 工具名 | `analyze_stock` | `trading_agent` | 调用 404 |
| 参数名 | `ticker` | `symbol` | 参数无效 |
| 轻量工具 | `get_stock_price` / `get_technical_indicators` 等 7 个 | `market_analyst` / `fundamentals_analyst` 等 4 个 | 不存在的工具 |
| 多股对比 | 无 | `compare_stocks` / `batch_analyze` | 用户意图无法路由 |
| 区间对比 | 无 | `period_compare` | 同上 |
| 股票筛选 | 无 | `screen_stocks` | 同上 |
| 数据源 | yfinance (美股) | AKShare/Tushare/BaoStock (A股为主) | A股数据拿不到 |
| 市场识别 | 无 | 无 | "茅台" 无法解析 |
| 前置检查 | 无 | 无 | 缺 API Key 时等 3 分钟才报错 |

### 1.2 Skill 需要解决的 3 个核心问题

```
┌───────────────────────────────────────────────────────────────┐
│  用户: "帮我看看茅台这半年走势，跑赢沪深300了吗"                │
│                                                               │
│  问题1: 意图路由 — 调哪个 MCP Tool?                           │
│    → period_compare(symbol="600519", compare_with="000300")  │
│                                                               │
│  问题2: 参数预处理 — "茅台" 是什么代码？                       │
│    → 茅台 = 600519 (A股)                                      │
│    → 沪深300 = 000300                                         │
│    → "这半年" = start_date=2024-07-19, end_date=2025-01-19   │
│                                                               │
│  问题3: 前置校验 — 环境是否就绪？                              │
│    → OPENAI_API_KEY 已配？ ✓                                  │
│    → AKShare 可用？ ✓                                         │
│    → 如果不通过，提前告知用户，不等 3 分钟才报错                │
└───────────────────────────────────────────────────────────────┘
```

---

## 二、整体架构

```
┌───────────────────────────────────────────────────────────────┐
│  opencode (LLM)                                               │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  SKILL (SKILL.md)                                       │  │
│  │                                                         │  │
│  │  1. 意图识别 → 匹配用户话术到 MCP Tool                  │  │
│  │  2. 参数预处理 → 中文股票名→代码、自然语言日期→YYYY-MM-DD │  │
│  │  3. 前置校验 → 环境/API/数据源检查                       │  │
│  │  4. 时长预期 → 提前告知用户等待时间                      │  │
│  │  5. 结果解读 → 格式化 MCP 返回的报告                     │  │
│  └──────────────────────┬──────────────────────────────────┘  │
│                         │ 调用 MCP Tool                        │
│                         ▼                                      │
│  ┌─────────────────────────────────────────────────────────┐  │
│  │  MCP Server (FastMCP) — 10 个 Tool                      │  │
│  │                                                         │  │
│  │  分析类:                                                │  │
│  │    trading_agent / market_analyst / fundamentals_analyst │  │
│  │    news_analyst / social_analyst                         │  │
│  │                                                         │  │
│  │  对比类:                                                │  │
│  │    compare_stocks / batch_analyze                        │  │
│  │                                                         │  │
│  │  统计类:                                                │  │
│  │    period_compare / screen_stocks                        │  │
│  │                                                         │  │
│  │  元信息:                                                │  │
│  │    agent_status                                         │  │
│  └─────────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────────┘
```

---

## 三、SKILL.md 完整内容

以下为替换 `~/.config/opencode/skills/trading-agents/SKILL.md` 的完整文件：

```markdown
---
name: trading-agents
description: AI金融交易分析多Agent框架。对股票执行完整的多Agent协作分析(市场/情绪/新闻/基本面→多空辩论→风险讨论→最终决策)，或单独查询技术面/基本面/新闻/情绪，支持多股对比、历史区间分析、条件筛选。触发词：分析股票、交易分析、股票分析、金融分析、对比股票、筛选股票、区间分析、trading analysis
license: MIT
compatibility: opencode
metadata:
  category: finance
  tools: tradingagents
---

## TradingAgents-CN - AI金融交易分析

通过 `tradingagents` MCP 服务器提供金融交易分析能力。

### 前置检查（每次分析前必做）

在调用任何分析工具前，先调用 `agent_status()` 确认环境就绪：
- 如果返回 `error` 或 `online_tools=false`，提示用户检查 `.opencode.json` 中的 env 配置
- A股分析需确保 AKShare 已安装：`pip install akshare`
- 如果用户未提供日期，使用今天日期（格式 YYYY-MM-DD）

### 股票代码规范

**A股**: 6位数字，如 `000001`(平安银行)、`600519`(茅台)、`000858`(五粮液)
**港股**: 4-5位数字+.HK，如 `00700.HK`(腾讯)、`09988.HK`(阿里)
**美股**: 1-5位字母，如 `AAPL`、`NVDA`、`TSLA`

**中文股票名解析规则**:
- 用户说"茅台"→ 600519（A股）
- 用户说"腾讯"→ 00700.HK（港股）
- 用户说"苹果"→ AAPL（美股）
- 无法确定时，先询问用户确认股票代码

**常见中文股票名映射**:
- 茅台/贵州茅台 → 600519
- 平安银行 → 000001
- 招商银行 → 600036
- 五粮液 → 000858
- 宁德时代 → 300750
- 比亚迪 → 002594
- 工商银行 → 601398
- 中国平安 → 601318
- 腾讯/腾讯控股 → 00700.HK
- 阿里/阿里巴巴 → 09988.HK (港股) / BABA (美股)

### 工具 1: `trading_agent` — 完整全流程分析

**耗时**: 3-10 分钟（取决于辩论轮次和 LLM 速度）

**参数**:
- `symbol` (必选): 股票代码
- `trade_date` (必选): 交易日期 YYYY-MM-DD
- `analysts` (可选): 分析师组合，默认 ["market","social","news","fundamentals"]
- `max_debate_rounds` (可选): 多空辩论轮次，默认 1
- `max_risk_discuss_rounds` (可选): 风险辩论轮次，默认 1

**返回**: 完整分析结果，含 decision(BUY/HOLD/SELL) + 各分析师报告 + 辩论记录

**何时使用**: 用户要求"全面分析"、"给我投资建议"、"要不要买入"等需要完整决策的场景

**调用前**: 告知用户"全流程分析需要 3-10 分钟，请耐心等待"

**示例**:
```
trading_agent(symbol="600519", trade_date="2025-01-10")
```

### 工具 2: `market_analyst` — 技术面分析

**耗时**: ~30 秒

**参数**:
- `symbol` (必选): 股票代码
- `trade_date` (必选): 交易日期 YYYY-MM-DD

**返回**: 技术分析报告（MA/MACD/RSI/布林带/成交量/趋势/建议）

**何时使用**: 用户说"看看技术面"、"走势怎么样"、"K线分析"等

**示例**:
```
market_analyst(symbol="000001", trade_date="2025-01-10")
```

### 工具 3: `fundamentals_analyst` — 基本面分析

**耗时**: ~30 秒

**参数**:
- `symbol` (必选): 股票代码
- `trade_date` (必选): 交易日期 YYYY-MM-DD

**返回**: 基本面报告（PE/PB/ROE/估值/盈利能力/财务健康/行业对比）

**何时使用**: 用户说"估值怎么样"、"看看基本面"、"PE高不高"、"贵不贵"等

**示例**:
```
fundamentals_analyst(symbol="AAPL", trade_date="2025-01-10")
```

### 工具 4: `news_analyst` — 新闻分析

**耗时**: ~30 秒

**参数**:
- `symbol` (必选): 股票代码
- `trade_date` (必选): 交易日期 YYYY-MM-DD
- `look_back_days` (可选): 回看天数，默认 7

**返回**: 新闻分析报告（重大事件/政策影响/行业动态/潜在风险）

**何时使用**: 用户说"最近有什么新闻"、"有什么利好利空"等

**示例**:
```
news_analyst(symbol="NVDA", trade_date="2025-01-10", look_back_days=14)
```

### 工具 5: `social_analyst` — 社交媒体情绪分析

**耗时**: ~30 秒

**参数**:
- `symbol` (必选): 股票代码
- `trade_date` (必选): 交易日期 YYYY-MM-DD

**返回**: 情绪分析报告（投资者情绪/讨论热度/多空倾向）

**何时使用**: 用户说"大家怎么看"、"市场情绪"、"散户观点"等

**注意**: A股社交数据源有限，可能返回数据不足

**示例**:
```
social_analyst(symbol="TSLA", trade_date="2025-01-10")
```

### 工具 6: `compare_stocks` — 多股对比分析

**耗时**: 单股时间 × 股数（并行执行取最慢的）

**参数**:
- `symbols` (必选): 股票代码列表，如 ["000001", "600519", "000858"]
- `trade_date` (必选): 交易日期 YYYY-MM-DD
- `analyst` (可选): 对比维度 — "market"(默认)|"fundamentals"|"news"|"social"|"full"
- `max_debate_rounds` (可选): 仅 full 模式使用
- `max_risk_discuss_rounds` (可选): 仅 full 模式使用

**返回**: 各股独立报告 + 横向对比分析 + 排名推荐

**何时使用**: 用户说"这几只哪个好"、"帮我比较"、"XX和YY哪个值得买"等

**示例**:
```
compare_stocks(symbols=["000001", "600036", "601398"], trade_date="2025-01-10", analyst="fundamentals")
```

### 工具 7: `batch_analyze` — 批量独立分析

**耗时**: 同 compare_stocks，但无 LLM 对比环节，稍快

**参数**:
- `symbols` (必选): 股票代码列表
- `trade_date` (必选): 交易日期 YYYY-MM-DD
- `analyst` (可选): 分析师选择，默认 "market"

**返回**: 各股独立报告，无对比逻辑

**何时使用**: 用户说"帮我分析一批股票"、"看看这些股的技术面"等，不需要排名对比

**示例**:
```
batch_analyze(symbols=["NVDA", "AMD", "INTC"], trade_date="2025-01-10", analyst="market")
```

### 工具 8: `period_compare` — 历史区间对比

**耗时**: ~30 秒

**参数**:
- `symbol` (必选): 股票代码
- `start_date` (必选): 起始日期 YYYY-MM-DD
- `end_date` (必选): 结束日期 YYYY-MM-DD
- `metrics` (可选): 对比指标，默认 ["close","volume","pct_chg"]
- `compare_with` (可选): 对比目标代码（股票或指数），如 "000300"(沪深300)

**返回**: 区间统计(收益率/回撤/波动率) + 可选超额收益 + LLM 分析报告

**何时使用**: 
- 用户说"这半年表现怎么样"、"最近一个月走势" → 不带 compare_with
- 用户说"跑赢大盘了吗"、"和沪深300比" → 带 compare_with

**常见指数代码**: 000300(沪深300)、000016(上证50)、000905(中证500)、399006(创业板指)

**示例**:
```
period_compare(symbol="600519", start_date="2024-07-01", end_date="2025-01-01", compare_with="000300")
```

### 工具 9: `screen_stocks` — 股票筛选

**耗时**: ~15 秒

**参数**:
- `conditions` (必选): 筛选条件列表，如 [{"field":"pe","operator":"between","value":[5,30]}]
- `market` (可选): 市场，默认 "CN"
- `order_by` (可选): 排序条件，如 [{"field":"roe","direction":"desc"}]
- `limit` (可选): 返回数量限制，默认 50

**支持的字段**: industry/pe/pb/pe_ttm/roe/total_mv/circ_mv/close/pct_chg/turnover_rate/volume_ratio/amount

**支持的操作符**: > / < / >= / <= / == / != / between / in / not_in / contains

**何时使用**: 用户说"帮我选股"、"筛选低PE"、"找高ROE的银行股"等

**自然语言→条件转换示例**:
- "低估值" → {"field":"pe","operator":"between","value":[5,20]}
- "高ROE" → {"field":"roe","operator":">","value":15}
- "银行股" → {"field":"industry","operator":"in","value":["银行"]}
- "大市值" → {"field":"total_mv","operator":">","value":500}

**示例**:
```
screen_stocks(
  conditions=[
    {"field":"pe","operator":"between","value":[5,15]},
    {"field":"roe","operator":">","value":10},
    {"field":"industry","operator":"in","value":["银行","保险"]}
  ],
  order_by=[{"field":"roe","direction":"desc"}],
  limit=20
)
```

### 工具 10: `agent_status` — 查询配置与能力

**参数**: 无

**何时使用**: 
- 用户问"你能分析什么"、"支持哪些市场"
- 分析前环境自检
- 排查 MCP 连接问题

### 意图路由速查表

| 用户话术 | MCP Tool | 关键参数 |
|---------|----------|---------|
| 全面分析/投资建议/要不要买 | `trading_agent` | symbol, trade_date |
| 技术面/走势/K线/均线 | `market_analyst` | symbol, trade_date |
| 基本面/估值/PE/贵不贵 | `fundamentals_analyst` | symbol, trade_date |
| 新闻/利好利空/消息 | `news_analyst` | symbol, trade_date |
| 情绪/大家怎么看/散户 | `social_analyst` | symbol, trade_date |
| 几只股票哪个好/对比 | `compare_stocks` | symbols, analyst |
| 分析一批/帮我看看这些 | `batch_analyze` | symbols, analyst |
| 这段走势/半年表现 | `period_compare` | symbol, start_date, end_date |
| 跑赢大盘/和XX比 | `period_compare` | + compare_with |
| 选股/筛选/低PE高ROE | `screen_stocks` | conditions |
| 你能做什么/配置/支持什么 | `agent_status` | — |

### 错误恢复指引

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| MCP 连接失败 | tradingagents MCP Server 未启动 | 检查 `.opencode.json` 中 command/args 是否正确 |
| API Key 错误 | OPENAI_API_KEY 等未配 | 在 `.opencode.json` 的 env 中添加 |
| A股数据获取失败 | AKShare 未安装或网络问题 | `pip install akshare`，检查网络 |
| 股票代码无效 | 格式不对 | 确认 A股6位数字/港股.HK/美股字母 |
| 分析超时 | 全流程+多辩论轮次 | 先用 market_analyst 快速验证数据可用 |
| 筛选返回空 | 条件过严 | 放宽条件，如 PE 区间扩大 |
| 社交分析无数据 | A股社交源有限 | 改用 news_analyst 替代 |

### 耗时预期管理

调用耗时较长的工具前，**必须**告知用户预计等待时间：

| 工具 | 预计耗时 | 用户提示 |
|------|---------|---------|
| trading_agent | 3-10 分钟 | "全流程分析需要 3-10 分钟，请耐心等待" |
| 单分析师 (market/fundamentals/news/social) | ~30 秒 | "正在分析，大约需要 30 秒" |
| compare_stocks (3股, market) | ~1 分钟 | "对比分析大约需要 1 分钟" |
| compare_stocks (3股, full) | 5-15 分钟 | "全流程对比需要 5-15 分钟" |
| batch_analyze (N股) | ~30秒×N | "批量分析大约需要 X 分钟" |
| period_compare | ~30 秒 | "区间分析大约需要 30 秒" |
| screen_stocks | ~15 秒 | "正在筛选，大约需要 15 秒" |
| agent_status | <1 秒 | 无需提示 |
```

---

## 四、Skill 层需补充的预处理能力

Skill 本身是 Markdown 指引文件，无法执行代码。但通过在 SKILL.md 中写清楚规则，
让 opencode 的 LLM 在调用 MCP 前执行预处理逻辑。

### 4.1 股票代码规范化

| 用户输入 | 规则 | 规范化结果 |
|---------|------|-----------|
| 茅台 | 查常见映射表 | 600519 |
| 600519 | 6位数字 → A股 | 600519 |
| 0700 / 00700 | 4-5位数字 → 港股 | 00700.HK |
| 0700.HK | 已规范 | 00700.HK |
| AAPL / aapl | 字母 → 美股 | AAPL |
| 腾讯 | 查映射表 | 00700.HK |

**SKILL.md 中已包含常见映射表**（见上文），opencode LLM 会参照解析。

### 4.2 日期规范化

| 用户输入 | 规则 | 规范化结果 |
|---------|------|-----------|
| "今天" | 取当前日期 | 2025-01-19 |
| "昨天" | 当前日期-1（跳周末） | 2025-01-16 |
| "这半年" | 6个月前→今天 | start=2024-07-19, end=2025-01-19 |
| "最近一个月" | 30天前→今天 | start=2024-12-20, end=2025-01-19 |
| "今年以来" | 当年1月1日→今天 | start=2025-01-01, end=2025-01-19 |
| 无日期 | 默认今天 | 2025-01-19 |

### 4.3 自然语言→筛选条件转换

| 用户话术 | 转换规则 | conditions |
|---------|---------|-----------|
| "低估值" | PE 5-20 | [{"field":"pe","operator":"between","value":[5,20]}] |
| "高ROE" | ROE>15 | [{"field":"roe","operator":">","value":15}] |
| "银行股" | industry in 银行 | [{"field":"industry","operator":"in","value":["银行"]}] |
| "大市值蓝筹" | 总市值>500亿 | [{"field":"total_mv","operator":">","value":500}] |
| "低估值高ROE银行股" | 组合以上 | 三个条件 AND |

### 4.4 前置校验清单

SKILL.md 指引 opencode 在分析前执行以下检查：

```
1. 调用 agent_status() → 确认 MCP 可连接
2. 检查返回的 llm_provider / deep_think_llm / quick_think_llm 是否有值
3. 如果 A股分析 → 确认 online_tools=true
4. 如果返回 error → 提示用户检查 .opencode.json 配置
```

---

## 五、opencode 配置

### 5.1 `.opencode.json`

```json
{
  "mcp": {
    "tradingagents": {
      "command": "python",
      "args": ["-m", "tradingagents.mcp_server"],
      "env": {
        "MCP_LLM_PROVIDER": "dashscope",
        "MCP_DEEP_THINK_LLM": "qwen-max",
        "MCP_QUICK_THINK_LLM": "qwen-turbo",
        "MCP_BACKEND_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "MCP_ONLINE_TOOLS": "true",
        "MCP_ONLINE_NEWS": "true",
        "DASHSCOPE_API_KEY": "",
        "OPENAI_API_KEY": ""
      }
    }
  }
}
```

### 5.2 Skill 文件部署

将上文的 SKILL.md 内容写入以下路径之一：

- **项目级**: `.opencode/skills/trading-agents/SKILL.md`（推荐，随项目版本控制）
- **用户级**: `~/.config/opencode/skills/trading-agents/SKILL.md`（全局生效）

---

## 六、MCP Server 侧需配合的改动

Skill 是纯指引，但 MCP Server 侧也需要做一些配合，让 opencode 更容易正确使用：

### 6.1 `agent_status` 增加健康检查

```python
@mcp.tool()
async def agent_status() -> dict:
    config = _build_config()
    
    # 运行时健康检查
    health = {"mcp_server": "ok"}
    
    # 检查 LLM API Key
    llm_provider = config.get("llm_provider", "")
    if llm_provider == "openai" and not os.getenv("OPENAI_API_KEY"):
        health["llm_api_key"] = "missing: OPENAI_API_KEY"
    elif llm_provider == "dashscope" and not os.getenv("DASHSCOPE_API_KEY"):
        health["llm_api_key"] = "missing: DASHSCOPE_API_KEY"
    elif llm_provider == "google" and not os.getenv("GOOGLE_API_KEY"):
        health["llm_api_key"] = "missing: GOOGLE_API_KEY"
    else:
        health["llm_api_key"] = "ok"
    
    # 检查数据源可用性
    try:
        import akshare
        health["akshare"] = "ok"
    except ImportError:
        health["akshare"] = "not_installed"
    
    try:
        import yfinance
        health["yfinance"] = "ok"
    except ImportError:
        health["yfinance"] = "not_installed"
    
    return {
        "version": "1.0.0-preview",
        "health": health,
        "llm_provider": llm_provider,
        "deep_think_llm": config.get("deep_think_llm"),
        "quick_think_llm": config.get("quick_think_llm"),
        "online_tools": config.get("online_tools", False),
        "supported_markets": ["A股", "美股", "港股"],
        "available_tools": { ... },
        "data_sources": { ... },
    }
```

### 6.2 所有 Tool 增加输入校验

在每个 Tool 入口增加股票代码格式校验，复用 `StockUtils`：

```python
from tradingagents.utils.stock_utils import StockUtils

def _validate_symbol(symbol: str) -> tuple[str, str]:
    """校验并规范化股票代码，返回 (normalized_symbol, market)"""
    market_info = StockUtils.get_market_info(symbol)
    if market_info["market"] == "unknown":
        raise ValueError(
            f"无法识别股票代码 '{symbol}'。"
            "A股请用6位数字(如000001)，港股请用数字.HK(如00700.HK)，美股请用字母(如AAPL)"
        )
    
    # 港股规范化
    if market_info["is_hk"]:
        symbol = StockUtils.normalize_hk_ticker(symbol)
    
    market = "A股" if market_info["is_china"] else "港股" if market_info["is_hk"] else "美股"
    return symbol, market
```

### 6.3 日期智能回退

用户传入非交易日（周末/节假日）时，自动回退到最近交易日：

```python
import pandas as pd

def _nearest_trade_date(date_str: str) -> str:
    """如果指定日期非交易日，回退到最近的交易日"""
    dt = pd.Timestamp(date_str)
    if dt.weekday() >= 5:  # 周末
        dt = dt - pd.Timedelta(days=dt.weekday() - 4)  # 回退到周五
    return dt.strftime("%Y-%m-%d")
```

### 6.4 Tool 返回格式统一

所有 Tool 返回 dict 必须包含以下字段，方便 Skill/LLM 解读：

```python
{
    "success": True/False,           # 是否成功
    "error": None/"错误信息",         # 错误描述
    "symbol": "600519",              # 分析的股票代码
    "market": "A股",                  # 市场标识
    "tool": "market_analyst",        # 调用的工具名
    "elapsed_seconds": 28.5,         # 耗时
    # ... 工具特定返回字段
}
```

---

## 七、用户交互流程示例

### 示例 1: 新用户首次使用

```
用户: 你能做什么？

opencode → 调用 agent_status()
opencode: 我是 AI 金融交易分析助手，支持以下能力：
  1. 📊 完整多Agent分析 — 给出买入/持有/卖出决策
  2. 📈 技术面分析 — MA/MACD/RSI/布林带
  3. 📋 基本面分析 — PE/PB/ROE/估值
  4. 📰 新闻分析 — 重大事件/政策影响
  5. 💬 情绪分析 — 社交媒体多空观点
  6. ⚖️ 多股对比 — 横向比较+排名推荐
  7. 📉 区间对比 — 历史走势+超额收益
  8. 🔍 股票筛选 — 按条件选股
  
  支持 A股/美股/港股，请告诉我你想分析哪只股票？
```

### 示例 2: 中文股票名 + 自然语言日期

```
用户: 茅台这半年跑赢沪深300了吗？

opencode 内部推理:
  - 茅台 → 600519 (A股)
  - 这半年 → start_date=2024-07-19, end_date=2025-01-19
  - 跑赢沪深300 → compare_with="000300"
  - 意图 → period_compare

opencode: 我来分析茅台近半年的走势，并与沪深300对比，大约需要30秒。

opencode → 调用 period_compare(
    symbol="600519",
    start_date="2024-07-19",
    end_date="2025-01-19",
    compare_with="000300"
)

opencode: 茅台(600519)近半年表现：
  - 区间收益率: -8.5%
  - 沪深300收益率: +2.1%
  - 超额收益: -10.6%
  - 最大回撤: -15.2%
  
  [LLM 分析报告摘要]
  茅台近半年跑输沪深300约10.6个百分点，主要受...
```

### 示例 3: 自然语言筛选

```
用户: 帮我找低估值高ROE的银行股

opencode 内部推理:
  - 低估值 → PE 4-12
  - 高ROE → ROE > 12
  - 银行股 → industry in ["银行"]
  - 意图 → screen_stocks

opencode → 调用 screen_stocks(
    conditions=[
        {"field":"pe","operator":"between","value":[4,12]},
        {"field":"roe","operator":">","value":12},
        {"field":"industry","operator":"in","value":["银行"]}
    ],
    order_by=[{"field":"roe","direction":"desc"}],
    limit=20
)

opencode: 找到 12 只符合条件的银行股，按 ROE 排序：
  1. 601398 工商银行 | PE:5.2 | ROE:12.3%
  2. 600036 招商银行 | PE:6.8 | ROE:16.5%
  ...
  
  [LLM 筛选解读报告]
```

### 示例 4: 环境异常时

```
用户: 分析一下平安银行

opencode → 先调用 agent_status()
返回: {"health": {"llm_api_key": "missing: DASHSCOPE_API_KEY", ...}}

opencode: ⚠️ 检测到 DASHSCOPE_API_KEY 未配置，无法调用 LLM 进行分析。
  请在 .opencode.json 的 env 中添加：
  "DASHSCOPE_API_KEY": "sk-xxx"
  或改用其他 LLM 供应商（修改 MCP_LLM_PROVIDER）。
  配置完成后重试即可。
```

---

## 八、实现步骤

| 阶段 | 任务 | 产出 | 工作量 |
|------|------|------|--------|
| **Phase 1** | 部署 SKILL.md | `.opencode/skills/trading-agents/SKILL.md` | 0.5 天 |
| **Phase 2** | MCP Server 增加校验 | `agent_status` 健康检查 + `_validate_symbol` + 日期回退 + 统一返回格式 | 1 天 |
| **Phase 3** | 配置 `.opencode.json` | MCP 连接 + env 配置 | 0.5 天 |
| **Phase 4** | 端到端测试 | 覆盖所有 10 个 Tool + 中文股票名 + 日期 + 错误恢复 | 1 天 |

总计 **3 天**。

---

## 九、Skill 与 MCP 的职责边界

```
┌─────────────────────────────────────────────────────────┐
│  SKILL (SKILL.md) — 只读指引，不执行代码                  │
│                                                         │
│  ✓ 意图识别: 用户话术 → MCP Tool 映射                    │
│  ✓ 参数预处理: 中文→代码、自然语言→日期、描述→筛选条件     │
│  ✓ 前置校验: 提醒调用 agent_status()                     │
│  ✓ 时长预期: 告知用户等待时间                             │
│  ✓ 错误恢复: 常见错误 → 解决方案                         │
│  ✓ 结果解读: 格式化 MCP 返回值给用户                     │
│                                                         │
│  ✗ 不执行代码                                           │
│  ✗ 不直接调 API                                         │
│  ✗ 不存储状态                                           │
└─────────────────────────────────────────────────────────┘
                          ↕ 配合
┌─────────────────────────────────────────────────────────┐
│  MCP Server (FastMCP) — 执行层，Python 代码              │
│                                                         │
│  ✓ 10 个 Tool 实现                                      │
│  ✓ 股票代码校验 (_validate_symbol)                      │
│  ✓ 日期规范化 (_nearest_trade_date)                     │
│  ✓ 统一返回格式 (success/error/symbol/elapsed)          │
│  ✓ 健康检查 (agent_status 增强)                         │
│  ✓ 数据获取 + Agent 编排 + LLM 调用                     │
│                                                         │
│  ✗ 不做用户意图识别（由 Skill 负责）                     │
│  ✗ 不做中文股票名解析（由 Skill 指引 LLM 完成）          │
│  ✗ 不做时长预期提示（由 Skill 指引 LLM 完成）            │
└─────────────────────────────────────────────────────────┘
```
