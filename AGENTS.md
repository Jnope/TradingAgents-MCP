# TradingAgents-MCP 项目记忆

> AI Agent 记忆文件，已解析项目结构和功能，后续无需重复解析。

## 项目概述

- **名称**: TradingAgents-MCP
- **版本**: 1.0.0-preview
- **定位**: 将 TradingAgents-CN 多Agent协作分析引擎封装为 FastMCP Server，供 opencode/Claude Desktop 等 MCP 客户端调用
- **上游项目**: TradingAgents-CN（中文增强版多智能体股票分析平台）
- **Python**: >=3.10
- **许可证**: Apache-2.0
- **安装方式**: `pipx install -e .`（全局注册 `tradingagents-mcp` 命令）

## 架构总览

```
┌─────────────────────────────────────────────────┐
│  MCP Client (opencode / Claude Desktop)          │
│  .opencode.json 配置 MCP 连接                     │
│  .opencode/skills/trading-agents/SKILL.md 意图路由│
└──────────────────────┬──────────────────────────┘
                       │ MCP Protocol (stdio / streamable-http)
                       ▼
┌─────────────────────────────────────────────────┐
│  FastMCP Server (src/tradingagents_mcp/)          │
│  10 个 MCP Tool                                   │
│  6 个 MCP Prompt                                  │
└──────────────────────┬──────────────────────────┘
                       │ 复用核心引擎
                       ▼
┌─────────────────────────────────────────────────┐
│  tradingagents/ (核心多Agent分析引擎)              │
│  LangGraph + LangChain 多Agent协作                │
│  Analysts → Researchers → Risk → Trader           │
└─────────────────────────────────────────────────┘
```

## 项目结构

```
TradingAgents-MCP/
├── AGENTS.md                    # 本文件 — 项目记忆
├── pyproject.toml               # 项目元数据、依赖、CLI入口点
├── README.md                    # 使用说明
├── .opencode.json               # opencode MCP 配置（含环境变量）
├── docs/                        # 设计文档
│   ├── AGENTS.md                # 上游 TradingAgents-CN 项目解析
│   ├── MCP_MIGRATION_ANALYSIS.md  # FastMCP改造分析（数据源/可移除文件）
│   ├── MCP_SERVICE_PLAN.md      # MCP Tool 设计方案（10个Tool详细设计）
│   └── MCP_SKILL_INTEGRATION.md # Skill+MCP集成方案（意图路由/预处理）
├── .opencode/skills/
│   └── trading-agents/SKILL.md  # opencode Skill 定义（意图识别+参数预处理）
└── src/
    ├── tradingagents_mcp/       # MCP Server 模块（本项目核心）
    │   ├── __init__.py          # 版本号
    │   ├── __main__.py          # CLI 入口 (tradingagents-mcp / python -m)
    │   ├── server.py            # FastMCP Server + 10 个 Tool 定义（~745行）
    │   ├── prompts.py           # 6 个 MCP Prompt 注册
    │   ├── validators.py        # 校验/配置/健康检查/统计工具函数
    │   └── screen.py            # 在线股票筛选（A股/港股/美股）
    ├── tradingagents/           # 核心引擎（来自上游 TradingAgents-CN）
    │   ├── agents/              # 所有Agent定义
    │   │   ├── analysts/        # 分析师: market/fundamentals/news/social_media/china_market
    │   │   ├── researchers/     # 研究员: bull/bear (多空辩论)
    │   │   ├── risk_mgmt/       # 风险管理: aggressive/conservative/neutral (三方辩论)
    │   │   ├── managers/        # 经理: research_manager/risk_manager
    │   │   ├── trader/          # 交易决策: trader (最终决策)
    │   │   └── utils/           # AgentState/Toolkit/Memory
    │   ├── graph/               # LangGraph 工作流编排
    │   │   ├── trading_graph.py # TradingAgentsGraph 主入口
    │   │   ├── setup.py         # GraphSetup 节点/边构建
    │   │   ├── propagation.py   # Propagator 状态初始化与传播
    │   │   ├── reflection.py    # Reflector 反思与记忆
    │   │   ├── signal_processing.py  # SignalProcessor
    │   │   └── conditional_logic.py  # ConditionalLogic 条件路由
    │   ├── dataflows/           # 数据获取层
    │   │   ├── interface.py     # 统一数据接口 (set_config)
    │   │   ├── stock_api.py     # 股票API入口
    │   │   ├── data_source_manager.py  # 数据源管理器（降级链: INTERNAL→AKSHARE→TUSHARE→BAOSTOCK）
    │   │   ├── providers/       # 数据供应商适配器 (A股/美股/港股)
    │   │   │   ├── china/       # A股数据源
    │   │   │   │   ├── internal.py           # TransMatrix 内部数据库 Provider
    │   │   │   │   ├── internal_queries.py   # SQL 查询封装 (DatabaseConn)
    │   │   │   │   ├── internal_code_mapper.py  # 代码格式转换 (000001↔000001.SZ)
    │   │   │   │   ├── akshare.py            # AKShare适配器
    │   │   │   │   ├── tushare.py            # Tushare适配器
    │   │   │   │   ├── baostock.py           # BaoStock适配器
    │   │   │   │   └── fundamentals_snapshot.py  # 基本面快照
    │   │   ├── news/            # 新闻数据源
    │   │   ├── technical/       # 技术指标 (stockstats)
    │   │   └── cache/           # 数据缓存
    │   ├── llm_adapters/        # LLM适配器
    │   │   ├── openai_compatible_base.py  # OpenAI兼容基类
    │   │   ├── dashscope_openai_adapter.py
    │   │   ├── deepseek_adapter.py
    │   │   └── google_openai_adapter.py
    │   ├── config/              # 配置管理
    │   │   ├── config_manager.py   # 配置管理器（MongoDB导入已静默处理）
    │   │   ├── providers_config.py # LLM供应商配置
    │   │   ├── runtime_settings.py # 运行时设置
    │   │   ├── tushare_config.py   # Tushare配置
    │   │   └── env_utils.py        # 环境变量工具
    │   ├── tools/               # 工具集
    │   ├── utils/               # 通用工具
    │   ├── constants/           # 常量
    │   └── default_config.py    # 默认配置
    └── config/                  # 日志配置 (logging.toml)
```

## 10 个 MCP Tool

| Tool | 说明 | 耗时 | 关键参数 |
|------|------|------|---------|
| `trading_agent` | 完整全流程（分析师→辩论→风险→决策） | 3-10分钟 | symbol, trade_date, analysts, max_debate_rounds |
| `market_analyst` | 独立技术面分析 | ~30秒 | symbol, trade_date |
| `fundamentals_analyst` | 独立基本面分析 | ~30秒 | symbol, trade_date |
| `news_analyst` | 独立新闻分析 | ~30秒 | symbol, trade_date, look_back_days |
| `social_analyst` | 独立情绪分析 | ~30秒 | symbol, trade_date |
| `compare_stocks` | 多股对比（横向对比+排名） | 依股数 | symbols, analyst, max_debate_rounds |
| `batch_analyze` | 批量独立分析（无对比） | 依股数 | symbols, analyst |
| `period_compare` | 历史区间对比（收益率/回撤/超额） | ~30秒 | symbol, start_date, end_date, compare_with |
| `screen_stocks` | 股票筛选（条件+LLM解读） | ~15秒 | conditions, market, order_by, limit |
| `agent_status` | 配置状态+健康检查 | <1秒 | 无 |

## 核心工作流程

```
用户输入股票代码 + 日期
        │
        ▼
┌─────────────────── 分析师层 ───────────────────┐
│ Market Analyst     → 技术指标分析报告            │
│ Fundamentals Analyst → PE/PB/财务数据分析报告    │
│ News Analyst       → 新闻分析报告               │
│ Social Media Analyst → 社交媒体情绪报告          │
└───────────────────────────────────────────────┘
        │
        ▼
┌─────────────────── 多空辩论层 ─────────────────┐
│ Bull Researcher (看多)  ←→  Bear Researcher (看空) │
│ Research Manager 主持辩论，轮次: max_debate_rounds  │
└───────────────────────────────────────────────┘
        │
        ▼
┌─────────────────── 风险辩论层 ─────────────────┐
│ Aggressive / Conservative / Neutral Debater       │
│ Risk Manager 主持辩论，轮次: max_risk_discuss_rounds│
└───────────────────────────────────────────────┘
        │
        ▼
┌─────────────────── 决策层 ─────────────────────┐
│ Trader Agent → 最终交易决策（BUY/HOLD/SELL）      │
└───────────────────────────────────────────────┘
```

## 关键源文件说明

### `src/tradingagents_mcp/server.py` (~745行)
- FastMCP 实例创建（名称 "TradingAgents-CN"）
- 10 个 Tool 的完整实现
- `_run_single_analyst()`: 通用单分析师运行逻辑，构造最小 state 调用 analyst node
- `trading_agent`: 初始化 TradingAgentsGraph → propagate() → 提取 decision + reports
- `compare_stocks`: 并行运行各股分析师 → LLM 生成对比分析
- `period_compare`: 获取行情数据 → calc_period_stats → LLM 生成区间分析
- `screen_stocks`: 调用 screen_stocks_online() → LLM 生成筛选解读

### `src/tradingagents_mcp/validators.py` (~308行)
- `validate_symbol()`: 股票代码校验+规范化（A股6位/港股.HK/美股字母）+ 中文股票名解析
- `normalize_date()`: 日期规范化（支持"今天/昨天"等中文别名）
- `resolve_date_range()`: 自然语言日期范围解析（"近半年"→start/end）
- `nearest_trade_date()`: 回退到最近交易日（跳周末/假日）
- `build_config()`: 从环境变量构建配置（MCP_LLM_PROVIDER 等）
- `check_health()`: MCP/LLM API Key/数据源包 可用性检查
- `extract_reports()`: 从 LangGraph state 提取分析师报告摘要
- `calc_period_stats()`: 计算区间统计（收益率/最大回撤/波动率）
- `extract_data_points()`: 从行情数据提取指定指标（支持降采样）

### `src/tradingagents_mcp/screen.py` (~186行)
- `screen_stocks_online()`: 在线股票筛选（无数据库依赖）
- `_screen_cn()`: A股筛选（AKShare stock_zh_a_spot_em + 内存条件过滤）
- `_screen_hk()`: 港股筛选（AKShare stock_hk_spot_em）
- `_screen_us()`: 美股筛选（暂未实现，返回空）
- `_apply_conditions()`: 通用 DataFrame 条件过滤（支持 >/< /between/in/contains 等）
- `format_screening_items()`: 格式化筛选结果为文本摘要

### `src/tradingagents_mcp/prompts.py` (~56行)
- 6 个 MCP Prompt: 股票分析/技术面分析/基本面分析/A股分析/对比分析/区间走势分析/股票筛选

### `src/tradingagents_mcp/__main__.py` (~83行)
- CLI 入口: `tradingagents-mcp` 或 `python -m tradingagents_mcp`
- `check` 子命令: 环境自检
- 默认启动 stdio 模式，MCP_TRANSPORT=streamable-http 切换 HTTP 模式

## 环境变量配置

### MCP Server 配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MCP_LLM_PROVIDER` | LLM 供应商 (openai/dashscope/google/anthropic/deepseek) | openai |
| `MCP_DEEP_THINK_LLM` | 深度思考模型 | o4-mini |
| `MCP_QUICK_THINK_LLM` | 快速思考模型 | gpt-4o-mini |
| `MCP_BACKEND_URL` | LLM API 地址 | https://api.openai.com/v1 |
| `MCP_ONLINE_TOOLS` | 是否启用在线数据工具 (true/false) | true |
| `MCP_ONLINE_NEWS` | 是否启用在线新闻 (true/false) | true |
| `MCP_MAX_DEBATE_ROUNDS` | 默认辩论轮次 | 1 |
| `MCP_MAX_RISK_DISCUSS_ROUNDS` | 默认风险辩论轮次 | 1 |
| `MCP_TRANSPORT` | 传输协议 (stdio/streamable-http) | stdio |
| `MCP_HOST` | HTTP 监听地址 | 0.0.0.0 |
| `MCP_PORT` | HTTP 监听端口 | 9000 |
| `MCP_LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL) | WARNING |

### TransMatrix 内部数据库配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `DEFAULT_CHINA_DATA_SOURCE` | A股默认数据源 (internal/akshare/tushare/baostock) | internal |
| `JDBC_HTTP_PROXY` | JDBC HTTP Proxy 地址 | 192.168.100.101:9998 |
| `TM_REAL_CONN` | Hive JDBC 连接串 | jdbc:hive2://192.168.100.102:10006 |
| `TM_DB_NAME` | 数据库名称 | meta_data |
| `TM_DB_USER` | 数据库用户名 | transmatrix_admin |
| `TM_DB_PASSWORD` | 数据库密码 | Transmatrix123 |
| `GUARDIAN_TOKEN` | Guardian 认证 Token | UgJRRGe7qMAKcirOQ017-TDH |

### LLM 供应商 API Key

根据 `MCP_LLM_PROVIDER` 的选择，需要设置对应的 API Key：

| 供应商 | Provider标识 | API Key 环境变量 | 典型 Backend URL | 适配器 |
|--------|-------------|-----------------|-----------------|--------|
| OpenAI | `openai` | `OPENAI_API_KEY` | https://api.openai.com/v1 | ChatOpenAI (langchain原生) |
| 阿里云通义 | `dashscope` | `DASHSCOPE_API_KEY` | https://dashscope.aliyuncs.com/compatible-mode/v1 | ChatDashScopeOpenAI (自研适配器) |
| DeepSeek | `deepseek` | `DEEPSEEK_API_KEY` | https://api.deepseek.com/v1 | ChatDeepSeek (自研适配器) |
| Google AI | `google` | `GOOGLE_API_KEY` | https://generativelanguage.googleapis.com/v1beta/openai | ChatGoogleOpenAI (自研适配器) |
| Anthropic | `anthropic` | `ANTHROPIC_API_KEY` | https://api.anthropic.com/v1 | ChatAnthropic (langchain原生) |

## 数据源支持

| 市场 | 数据源 | 功能 |
|------|--------|------|
| A股 | TransMatrix 内部数据库 | 行情/K线/基本面/财务/资金流向/股东（最高优先级） |
| A股 | AKShare | 行情/基本面/财务数据（降级） |
| A股 | Tushare | 行情/基本面/财务数据（需Token，降级） |
| A股 | BaoStock | 行情/历史数据（降级） |
| 美股 | YFinance | 行情/基本面 |
| 美股 | Finnhub | 新闻/数据（需API Key） |
| 港股 | AKShare | 行情/基本面 |

## 已知问题和修复记录

1. **FastMCP `version`/`description` 参数移除**: mcp>=1.27.0 不再支持 `version` 和 `description` 参数，已改为 `instructions`
2. **MongoDB 导入报错**: `config_manager.py` 中 MongoDBStorage 导入失败不再输出 ERROR 日志，已静默处理（本项目不使用 MongoDB）
3. **系统级 pip 安装限制**: 使用 `pipx install -e .` 替代 `pip install -e .` 安装到全局
4. **opencode MCP 配置格式**: `.opencode.json` 中 MCP 配置必须使用 `type: "local"`、`command` 为数组格式、环境变量字段名为 `environment`（不是 `env`），否则 opencode schema 验证报 `ConfigInvalidError`。Claude Desktop 仍使用 `env` 和字符串 `command`

## 开发/调试

```bash
# 安装（全局）
pipx install -e .

# 环境检查
tradingagents-mcp check

# stdio 模式启动（opencode 使用）
tradingagents-mcp

# HTTP 模式启动
MCP_TRANSPORT=streamable-http MCP_PORT=9000 tradingagents-mcp

# Python 模块方式
python -m tradingagents_mcp
python -m tradingagents_mcp check
```

## docs/ 文档索引

| 文件 | 内容 |
|------|------|
| `AGENTS.md` | 上游 TradingAgents-CN 完整项目结构解析（agents/dataflows/graph/config 全目录树） |
| `MCP_MIGRATION_ANALYSIS.md` | FastMCP 改造分析：数据源切换方案、可移除文件清单（app/frontend/web 约300文件10M） |
| `MCP_SERVICE_PLAN.md` | 10个 MCP Tool 的完整设计文档（参数/返回值/实现原理/代码） |
| `MCP_SKILL_INTEGRATION.md` | Skill+MCP 集成方案：意图路由、参数预处理、前置校验、SKILL.md 完整内容 |
