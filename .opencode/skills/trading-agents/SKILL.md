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

### 统一返回值结构

所有工具均返回 JSON dict，包含以下通用字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| `success` | bool | 是否成功。**始终检查此字段**判断调用结果 |
| `error` | str | 仅失败时存在，错误描述 |
| `elapsed_seconds` | float | 调用耗时（秒） |

**成功时**: `success=true` + 工具专属字段（见各工具文档）
**失败时**: `success=false` + `error` 描述 + 可能的 `symbol`/`conditions` 等上下文字段

**报告截断规则**: 所有报告均返回完整内容，不做截断。

### 自动规范化行为

调用工具时，以下参数会自动规范化，无需用户手动处理：

| 输入 | 自动转换 | 示例 |
|------|---------|------|
| 中文股票名 | → 标准代码 | "茅台" → "600519", "腾讯" → "00700.HK" |
| 中文指数名 | → 指数代码 | "沪深300" → "000300", "创业板指" → "399006" |
| 港股纯数字 | → 补 .HK | "700" → "00700.HK", "9988" → "09988.HK" |
| 代码大小写 | → 统一大写 | "aapl" → "AAPL" |
| 中文日期别名 | → 标准日期 | "今天" → 当天, "昨天" → 前一交易日(跳周末) |
| 周末/假日日期 | → 回退到最近交易日 | "2025-01-05"(周日) → "2025-01-03"(周五) |

### 前置确认流程（严格遵守顺序，每步必须获得用户确认后才能进入下一步）

在调用任何分析工具前，**必须严格按以下顺序逐项确认**。每一步都必须获得用户明确回复后才可进入下一步，**严禁跳过任何步骤**：

```
Step 1: 确认股票代码 ← 必须获得用户确认
    │
    ▼ 用户确认代码后
Step 2: 确认分析日期 ← 必须获得用户确认
    │
    ▼ 用户确认日期后
Step 3: 确认分析类型 ← 必须获得用户确认
    │
    ▼ 用户确认类型后
Step 4: 调用工具（此时才可调用 MCP Tool）
```

**禁止行为**：
- ❌ 未确认股票代码就询问分析类型
- ❌ 未确认日期就调用工具
- ❌ 自行假设用户确认（必须等用户明确回复"是"/"确认"/"对"等）
- ❌ 一次询问多个确认项（必须逐项确认）

### Step 1: 股票代码确认（第一个必须完成的确认）

用户提到股票时，**必须**按以下流程确认代码，**确认完成后才能进入 Step 2**：

```
用户提到股票名称/代码
       │
       ▼
  是否为标准代码格式？
  (A股6位数字 / 港股数字.HK / 美股字母)
       │
    是 ─┤─→ 向用户确认："确认分析 代码(公司名) 吗？"
       │        等待用户回复确认
       │
    否 ─┤─→ 可能是公司名称或简称
       │
       ▼
  查常见中文股票名映射表
       │
    命中 ─┤─→ 向用户确认："您说的是 XX(代码) 吗？"
       │        等待用户回复确认后才可继续
       │
    未命中 ─┤─→ 使用 web_search 搜索 "XX 股票代码"
       │
       ▼
  搜索到结果？
       │
    是 ─┤─→ 向用户展示搜索结果并确认：
       │        "搜索到 XX 的股票代码为 YY(ZZ市场)，确认吗？"
       │        如果有多条结果，列出供用户选择
       │        等待用户回复确认后才可继续
       │
    否 ─┤─→ 要求用户手动输入：
             "未找到 'XX' 的股票代码，请提供准确的股票代码
              (A股6位数字/港股数字.HK/美股字母)"
```

**关键规则**:
- **绝不猜测**股票代码，必须经过用户确认
- **即使搜索到了代码，也必须向用户确认后才能使用**
- 同一公司可能有多个上市代码（如阿里港股 09988.HK / 美股 BABA），需确认用户要分析哪个市场
- 用户提供的已是标准代码格式时，仍需向用户确认"确认分析 XX(代码) 吗？"

### 股票代码格式规范

**A股**: 6位数字，如 `000001`(平安银行)、`600519`(茅台)、`000858`(五粮液)
**港股**: 4-5位数字+.HK，如 `00700.HK`(腾讯)、`09988.HK`(阿里)
**美股**: 1-5位字母，如 `AAPL`、`NVDA`、`TSLA`

### Step 2: 日期确认（股票代码确认后，第二个必须完成的确认）

**必须在股票代码确认后、分析类型确认前完成日期确认**：

1. 用户已明确指定日期 → 向用户确认："确认分析日期为 YYYY-MM-DD？"
2. 用户说"今天"/"昨天"等 → 按规则解析后确认（"昨天"自动跳周末）
3. 用户未指定日期 → **必须询问用户**："请问您要分析哪个交易日的数据？默认为今天(YYYY-MM-DD)"
4. 用户确认"默认"/"今天"/"是" → 使用今天日期

**日期解析规则**:
- "今天" → 当天
- "昨天" → 前一个交易日（跳周末）
- "这半年"/"近半年" → 仅用于 period_compare 的 start_date/end_date
- "今年" → 仅用于 period_compare 的 start_date/end_date

### Step 3: 分析类型确认（日期确认后，第三个必须完成的确认）

**必须在日期确认后才可询问分析类型**：

```
日期已确认
        │
        ▼
   用户是否明确指定了分析维度？
   （如"技术面"/"基本面"/"新闻"/"情绪"/"全面"）
        │
     是 ─┤─→ 向用户确认后使用对应工具
        │
     否 ─┤─→ 向用户确认分析类型：
        │
        ▼
   询问用户："请问您需要哪种分析？
     1. 全面分析（trading_agent）— 包含技术面+基本面+新闻+情绪+多空辩论+风险讨论+最终决策，耗时3-10分钟
     2. 仅技术面（market_analyst）— K线/均线/MACD/RSI等，约30秒
     3. 仅基本面（fundamentals_analyst）— PE/PB/ROE/估值等，约30秒
     4. 仅新闻（news_analyst）— 重大事件/政策/行业动态，约30秒
     5. 仅情绪（social_analyst）— 投资者情绪/讨论热度，约30秒"
        │
        ▼
   用户选择后，使用对应工具
```

**关键规则**:
- 用户说"全面分析"/"投资建议"/"要不要买" → 默认 `trading_agent`
- 用户说"看看技术面"/"走势" → `market_analyst`
- 用户说"估值"/"基本面" → `fundamentals_analyst`
- 用户说"有什么新闻" → `news_analyst`
- 用户说"大家怎么看" → `social_analyst`
- **模糊表述时（如"分析一下"）必须询问确认，不得自行假设为全流程分析**

### Step 4: 环境检查（首次使用时执行一次即可）

- 调用 `agent_status()` 确认环境就绪
- 如果返回 `health.llm_api_key` 包含 "missing"，提示用户检查 `.opencode.json` 中的 environment 配置
- A股分析需确保 AKShare 已安装：`pip install akshare`

### 常见中文股票名映射

以下为内置映射表，用户提到这些名称时可直接转换但仍需确认：

**A股**:
- 茅台/贵州茅台 → 600519
- 平安银行 → 000001
- 招商银行 → 600036
- 五粮液 → 000858
- 宁德时代 → 300750
- 比亚迪 → 002594
- 工商银行 → 601398
- 中国平安 → 601318
- 美的集团 → 000333
- 格力电器 → 000651
- 中信证券 → 600030
- 海康威视 → 002415
- 隆基绿能 → 601012
- 中国中免 → 601888
- 药明康德 → 603259
- 紫金矿业 → 601899
- 长江电力 → 600900
- 中国移动 → 600941
- 中国石油 → 601857
- 中国神华 → 601088

**港股**:
- 腾讯/腾讯控股 → 00700.HK
- 阿里/阿里巴巴 → 09988.HK（注意：美股为 BABA）
- 美团 → 03690.HK
- 小米 → 01810.HK

**美股**:
- 苹果 → AAPL
- 英伟达 → NVDA
- 特斯拉 → TSLA
- 微软 → MSFT
- 亚马逊 → AMZN
- 谷歌 → GOOGL

**常见指数代码**: 000300(沪深300) 000016(上证50) 000905(中证500) 399006(创业板指) 000001(上证指数) 399001(深证成指) 000688(科创50)

### 工具 1: `trading_agent` — 完整全流程分析

**耗时**: 3-10 分钟（取决于辩论轮次和 LLM 速度）

**参数**:
- `symbol` (必选): 股票代码
- `trade_date` (必选): 交易日期 YYYY-MM-DD
- `analysts` (可选): 分析师组合，默认 ["market","social","news","fundamentals"]
- `max_debate_rounds` (可选): 多空辩论轮次，默认 1
- `max_risk_discuss_rounds` (可选): 风险辩论轮次，默认 1

**返回值**:
| 字段 | 说明 |
|------|------|
| `decision` | 最终决策: BUY/HOLD/SELL |
| `market` | 市场标识: A股/美股/港股 |
| `analysts_used` | 使用的分析师列表 |
| `market_report` | 市场分析报告(≤2000字符) |
| `fundamentals_report` | 基本面报告(≤2000字符) |
| `sentiment_report` | 情绪分析报告(≤2000字符) |
| `news_report` | 新闻分析报告(≤2000字符) |
| `total_time_minutes` | 总耗时(分钟)，可能为空 |

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `report` | 技术分析报告文本(≤8000字符) |
| `market` | 市场标识: A股/美股/港股 |

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `report` | 基本面报告文本(≤8000字符) |
| `market` | 市场标识: A股/美股/港股 |

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `report` | 新闻分析报告文本(≤8000字符) |
| `market` | 市场标识: A股/美股/港股 |
| `look_back_days` | 实际回看天数 |

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `report` | 情绪分析报告文本(≤8000字符) |
| `market` | 市场标识: A股/美股/港股 |

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `individual_reports` | 各股报告摘要 dict，key=代码, value=报告(≤1500字符) |
| `comparison` | LLM 横向对比分析+排名推荐(≤6000字符) |

**full 模式特别说明**: analyst="full" 时对每只股票运行完整 trading_agent 流程（辩论+风险+决策），每股耗时 3-10 分钟。返回的 individual_reports 中包含 `decision` 字段。**务必提前告知用户耗时**。

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `results` | 各股独立报告 dict，key=代码, value=含 report/analyst/symbol 的 dict |

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `summary` | 区间统计 dict（见下表） |
| `data_points` | 降采样数据点（默认≤60个点），含 symbol 和 compare_with 两组 |
| `analysis` | LLM 走势分析报告(≤6000字符) |

**summary 字段**:
| 字段 | 说明 |
|------|------|
| `symbol_return` | 区间收益率(%) |
| `max_drawdown` | 最大回撤(%)，负数 |
| `volatility` | 年化波动率(%) |
| `benchmark_return` | 基准收益率(%)，仅 compare_with 存在时 |
| `excess_return` | 超额收益(%)，仅 compare_with 存在时 |
| `benchmark_max_drawdown` | 基准最大回撤(%)，仅 compare_with 存在时 |

**何时使用**:
- 用户说"这半年表现怎么样"、"最近一个月走势" → 不带 compare_with
- 用户说"跑赢大盘了吗"、"和沪深300比" → 带 compare_with

**常见指数代码**: 000300(沪深300)、000016(上证50)、000905(中证500)、399006(创业板指)

**日期解析规则**:
- "这半年"/"近半年"/"最近半年" → start_date = 6个月前, end_date = 今天
- "最近一个月"/"近一个月" → start_date = 30天前, end_date = 今天
- "今年以来"/"今年" → start_date = 当年1月1日, end_date = 今天
- "近一周" → start_date = 7天前, end_date = 今天
- "近3个月"/"近一年" → start_date = 90/365天前, end_date = 今天
- "2024-01-01至2025-01-01" → 支持 "至/到/~" 作为分隔符

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

**市场支持**:
- `"CN"` (默认): A股，基于 AKShare 实时数据
- `"HK"`: 港股，基于 AKShare 实时数据
- `"US"`: 美股筛选**暂未实现**，会返回空结果

**自然语言→条件转换示例**:
- "低估值" → {"field":"pe","operator":"between","value":[5,20]}
- "高ROE" → {"field":"roe","operator":">","value":15}
- "银行股" → {"field":"industry","operator":"in","value":["银行"]}
- "大市值" → {"field":"total_mv","operator":">","value":500}
- "低估值高ROE银行股" → 组合以上三个条件 AND

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

**返回值**:
| 字段 | 说明 |
|------|------|
| `total` | 符合条件的股票数量 |
| `items` | 筛选结果列表（最多 limit 条） |
| `analysis` | LLM 解读报告(≤4000字符)，含整体特征/前5推荐/风险提示 |

### 工具 10: `agent_status` — 查询配置与能力

**参数**: 无

**返回值**:
| 字段 | 说明 |
|------|------|
| `version` | MCP Server 版本 |
| `health` | 健康检查 dict: mcp_server/llm_api_key/akshare/yfinance/tushare/baostock |
| `llm_provider` | 当前 LLM 供应商 |
| `deep_think_llm` | 深度思考模型名 |
| `quick_think_llm` | 快速思考模型名 |
| `online_tools` | 是否启用在线数据工具 |
| `supported_markets` | 支持的市场列表 |
| `available_tools` | 所有可用工具及说明 |
| `data_sources` | 各市场数据源 |

**何时使用**:
- 用户问"你能分析什么"、"支持哪些市场"
- 分析前环境自检（首次使用时执行一次即可）
- 排查 MCP 连接问题（health.llm_api_key 含 "missing" 时提示用户检查环境变量）

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
| 环境检查/健康检查 | `agent_status` | — |
| A股分析/沪深股票 | `trading_agent` | symbol(6位数字), trade_date |

### 错误恢复指引

| 错误 | 原因 | 解决方案 |
|------|------|---------|
| MCP 连接失败 | tradingagents MCP Server 未启动 | 检查 `.opencode.json` 中 command/args 是否正确 |
| API Key 错误 | OPENAI_API_KEY 等未配 | 在 `.opencode.json` 的 environment 中添加 |
| A股数据获取失败 | AKShare 未安装或网络问题 | `pip install akshare`，检查网络 |
| 股票代码无效 | 格式不对 | 确认 A股6位数字/港股.HK/美股字母 |
| 分析超时 | 全流程+多辩论轮次 | 先用 market_analyst 快速验证数据可用 |
| 筛选返回空 | 条件过严 | 放宽条件，如 PE 区间扩大 |
| 社交分析无数据 | A股社交源有限 | 改用 news_analyst 替代 |
| 美股筛选无结果 | US 市场筛选未实现 | 使用 market="CN" 或 "HK" |
| health.llm_api_key 含 missing | API Key 环境变量未设置 | 检查对应供应商的 Key 是否配置 |

### LLM 供应商配置

| 供应商 | MCP_LLM_PROVIDER | 需要的 API Key 环境变量 | 典型 Backend URL |
|--------|-------------------|------------------------|-----------------|
| OpenAI | `openai` | `OPENAI_API_KEY` | https://api.openai.com/v1 |
| 阿里云通义 | `dashscope` | `DASHSCOPE_API_KEY` | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | https://api.deepseek.com/v1 |
| Google AI | `google` | `GOOGLE_API_KEY` | https://generativelanguage.googleapis.com/v1beta/openai |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | https://api.anthropic.com/v1 |

环境变量在 `.opencode.json` 的 `environment` 字段中配置。

### MCP Prompts（预置对话模板）

MCP Server 注册了 6 个 Prompt 模板，MCP 客户端可直接调用：

| Prompt 标题 | 参数 | 用途 |
|------------|------|------|
| 股票分析 | symbol, trade_date | 触发 trading_agent 全流程 |
| 技术面分析 | symbol, trade_date | 触发 market_analyst |
| 基本面分析 | symbol, trade_date | 触发 fundamentals_analyst |
| A股分析 | stock_code, trade_date | 触发 trading_agent（强调中文数据源） |
| 对比分析 | symbols, trade_date | 触发 compare_stocks |
| 区间走势分析 | symbol, start_date, end_date | 触发 period_compare |
| 股票筛选 | description | 触发 screen_stocks（自然语言→条件转换） |

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
