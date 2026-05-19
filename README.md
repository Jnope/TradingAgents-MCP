# TradingAgents-MCP

TradingAgents-CN 的 MCP (Model Context Protocol) Server 封装，
将多Agent协作分析引擎暴露为 MCP Tools，支持 opencode / Claude Desktop 等 MCP 客户端调用。

## 快速开始

### 安装

```bash
# 方式1: 从本地路径安装（开发模式）
cd /home/transwarp/Code/AI金融项目/TradingAgents-MCP
pip install -e .

# 方式2: 确保 tradingagents 核心已安装
pip install -e /home/transwarp/Code/AI金融项目/TradingAgents-CN
```

### 环境检查

```bash
tradingagents-mcp check
# 或
python -m tradingagents_mcp check
```

### 启动 MCP Server

```bash
# stdio 模式（默认，opencode/Claude Desktop 使用）
tradingagents-mcp

# HTTP 模式
MCP_TRANSPORT=streamable-http MCP_PORT=9000 tradingagents-mcp

# Python 模块方式
python -m tradingagents_mcp
```

## 配置

### opencode (`.opencode.json`)

> **注意**: opencode 要求 `type` 为 `"local"`，`command` 为数组格式，环境变量字段名为 `environment`（不是 `env`）。
> 详见 [opencode MCP 文档](https://opencode.ai/docs/mcp-servers/)

```json
{
  "mcp": {
    "tradingagents": {
      "type": "local",
      "command": ["tradingagents-mcp"],
      "environment": {
        "MCP_LLM_PROVIDER": "dashscope",
        "MCP_DEEP_THINK_LLM": "qwen-max",
        "MCP_QUICK_THINK_LLM": "qwen-turbo",
        "MCP_BACKEND_URL": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "MCP_ONLINE_TOOLS": "true",
        "MCP_ONLINE_NEWS": "true",
        "DASHSCOPE_API_KEY": "sk-xxx"
      }
    }
  }
}
```

### Claude Desktop

```json
{
  "mcpServers": {
    "tradingagents": {
      "command": "tradingagents-mcp",
      "env": {
        "MCP_LLM_PROVIDER": "openai",
        "MCP_DEEP_THINK_LLM": "o4-mini",
        "MCP_QUICK_THINK_LLM": "gpt-4o-mini",
        "OPENAI_API_KEY": "sk-xxx"
      }
    }
  }
}
```

> **注意**: Claude Desktop 使用 `env` 字段名（与 opencode 的 `environment` 不同），且 `command` 为字符串而非数组。

### 环境变量

#### MCP Server 配置

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
| `MCP_HOST` | HTTP 模式监听地址 | 0.0.0.0 |
| `MCP_PORT` | HTTP 模式监听端口 | 9000 |
| `MCP_LOG_LEVEL` | 日志级别 (DEBUG/INFO/WARNING/ERROR/CRITICAL) | WARNING |

#### LLM 供应商 API Key

根据 `MCP_LLM_PROVIDER` 的选择，需要设置对应的 API Key 环境变量：

| 供应商 | 需要的环境变量 | 典型 Backend URL |
|--------|---------------|-----------------|
| `openai` | `OPENAI_API_KEY` | https://api.openai.com/v1 |
| `dashscope` | `DASHSCOPE_API_KEY` | https://dashscope.aliyuncs.com/compatible-mode/v1 |
| `deepseek` | `DEEPSEEK_API_KEY` | https://api.deepseek.com/v1 |
| `google` | `GOOGLE_API_KEY` | https://generativelanguage.googleapis.com/v1beta/openai |
| `anthropic` | `ANTHROPIC_API_KEY` | https://api.anthropic.com/v1 |

## 10 个 MCP Tool

| Tool | 说明 | 耗时 |
|------|------|------|
| `trading_agent` | 完整全流程（分析师→辩论→风险→决策） | 3-10分钟 |
| `market_analyst` | 独立技术面分析 | ~30秒 |
| `fundamentals_analyst` | 独立基本面分析 | ~30秒 |
| `news_analyst` | 独立新闻分析 | ~30秒 |
| `social_analyst` | 独立情绪分析 | ~30秒 |
| `compare_stocks` | 多股对比（横向对比+排名） | 依股数 |
| `batch_analyze` | 批量独立分析（无对比） | 依股数 |
| `period_compare` | 历史区间对比（收益率/回撤/超额） | ~30秒 |
| `screen_stocks` | 股票筛选（条件+LLM解读） | ~15秒 |
| `agent_status` | 配置状态+健康检查 | <1秒 |

## 项目结构

```
TradingAgents-MCP/
├── pyproject.toml
├── docs                        # TradingAgents-CN AI解析文档及重构设计文档 
├── .opencode.json              # opencode MCP 配置模板
├── .opencode/skills/
│   └── trading-agents/
│       └── SKILL.md            # opencode Skill 定义
└── src/tradingagents_mcp/
    ├── __init__.py
    ├── __main__.py              # CLI 入口 (tradingagents-mcp / python -m)
    ├── server.py                # FastMCP Server + 10 个 Tool
    ├── prompts.py               # MCP Prompts
    ├── validators.py            # 股票代码校验、日期规范化、健康检查
    └── screen.py                # 在线股票筛选
```
TradingAgents-CN 为当前项目的源项目，docs内为解析TradingAgents-CN 产生的文档，及由TradingAgents-CN重构为当前项目的设计文档
