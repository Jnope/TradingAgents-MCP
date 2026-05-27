# TradingAgents-MCP

TradingAgents-CN 的 MCP (Model Context Protocol) Server 封装，
将多Agent协作分析引擎暴露为 MCP Tools，支持 opencode / Claude Desktop 等 MCP 客户端调用。

## 快速开始

### 安装

```bash
# 方式1:
uv sync
uv build --wheel
uv pip install dist/tradingagents_mcp-1.0.0rc0-py3-none-any.whl

# 方式2：从本地路径安装（开发模式）
pip install -e .
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
      "command": [
        "tradingagents-mcp"
      ],
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

**内部模型示例**（OpenAI 兼容接口）：

```json
{
  "mcp": {
    "tradingagents": {
      "type": "local",
      "command": [
        "tradingagents-mcp"
      ],
      "environment": {
        "MCP_LLM_PROVIDER": "openai",
        "MCP_DEEP_THINK_LLM": "xclaw/glm-5.1",
        "MCP_QUICK_THINK_LLM": "xclaw/glm-5.1",
        "MCP_BACKEND_URL": "https://llmops.transwarp.io/vibecoding/v1",
        "MCP_DEEP_MAX_TOKENS": "8192",
        "MCP_QUICK_MAX_TOKENS": "4096",
        "MCP_QUICK_API_KEY": "your-api-key",
        "MCP_DEEP_API_KEY": "your-api-key"
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

#### 基础配置

| 变量                            | 说明               | 默认值                         |
|-------------------------------|------------------|-----------------------------|
| `MCP_LLM_PROVIDER`            | LLM 供应商，见下方供应商列表 | `openai`                    |
| `MCP_DEEP_THINK_LLM`          | 深度思考模型名称         | `o4-mini`                   |
| `MCP_QUICK_THINK_LLM`         | 快速思考模型名称         | `gpt-4o-mini`               |
| `MCP_BACKEND_URL`             | LLM API 地址（全局默认） | `https://api.openai.com/v1` |
| `MCP_ONLINE_TOOLS`            | 是否启用在线数据工具       | `true`                      |
| `MCP_ONLINE_NEWS`             | 是否启用在线新闻         | `true`                      |
| `MCP_MAX_DEBATE_ROUNDS`       | 默认多空辩论轮次         | `1`                         |
| `MCP_MAX_RISK_DISCUSS_ROUNDS` | 默认风险辩论轮次         | `1`                         |

#### 混合模式配置

快速模型和深度模型使用不同供应商时，需要单独指定各自的 provider/backend_url/api_key：

| 变量                      | 说明            | 默认值                          |
|-------------------------|---------------|------------------------------|
| `MCP_QUICK_PROVIDER`    | 快速模型的供应商      | 继承 `MCP_LLM_PROVIDER`        |
| `MCP_DEEP_PROVIDER`     | 深度模型的供应商      | 继承 `MCP_LLM_PROVIDER`        |
| `MCP_QUICK_BACKEND_URL` | 快速模型的 API 地址  | 继承 `MCP_BACKEND_URL`         |
| `MCP_DEEP_BACKEND_URL`  | 深度模型的 API 地址  | 继承 `MCP_BACKEND_URL`         |
| `MCP_QUICK_API_KEY`     | 快速模型的 API Key | 继承 `MCP_DEEP_API_KEY`（交叉回退）  |
| `MCP_DEEP_API_KEY`      | 深度模型的 API Key | 继承 `MCP_QUICK_API_KEY`（交叉回退） |

#### 模型参数配置

精细控制深度模型和快速模型的推理参数：

| 变量                      | 说明                    | 默认值    |
|-------------------------|-----------------------|--------|
| `MCP_DEEP_MAX_TOKENS`   | 深度模型最大输出 token 数      | `4000` |
| `MCP_QUICK_MAX_TOKENS`  | 快速模型最大输出 token 数      | `4000` |
| `MCP_DEEP_TEMPERATURE`  | 深度模型温度（0.0~2.0，越低越确定） | `0.7`  |
| `MCP_QUICK_TEMPERATURE` | 快速模型温度                | `0.7`  |
| `MCP_DEEP_TIMEOUT`      | 深度模型请求超时（秒）           | `180`  |
| `MCP_QUICK_TIMEOUT`     | 快速模型请求超时（秒）           | `180`  |

#### 服务运行配置

| 变量              | 说明                                                | 默认值       |
|-----------------|---------------------------------------------------|-----------|
| `MCP_TRANSPORT` | 传输协议（`stdio` / `streamable-http`）                 | `stdio`   |
| `MCP_HOST`      | HTTP 模式监听地址                                       | `0.0.0.0` |
| `MCP_PORT`      | HTTP 模式监听端口                                       | `9000`    |
| `MCP_LOG_LEVEL` | 日志级别（`DEBUG`/`INFO`/`WARNING`/`ERROR`/`CRITICAL`） | `WARNING` |

#### API Key 环境变量

根据 `MCP_LLM_PROVIDER` 的选择，需要设置对应的 API Key。
设置方式有两种（优先级从高到低）：

1. **统一 API Key**：通过 `MCP_QUICK_API_KEY` / `MCP_DEEP_API_KEY` 设置（推荐，适用于 MCP 场景）
2. **供应商标准环境变量**：各供应商的标准 API Key 环境变量（适用于 CLI 场景）

| 供应商           | `MCP_LLM_PROVIDER` 值 | 标准环境变量                  | 典型 Backend URL                                            |
|---------------|----------------------|-------------------------|-----------------------------------------------------------|
| OpenAI / 兼容接口 | `openai`             | `OPENAI_API_KEY`        | `https://api.openai.com/v1`                               |
| 阿里云百炼         | `dashscope`          | `DASHSCOPE_API_KEY`     | `https://dashscope.aliyuncs.com/compatible-mode/v1`       |
| DeepSeek      | `deepseek`           | `DEEPSEEK_API_KEY`      | `https://api.deepseek.com/v1`                             |
| Google AI     | `google`             | `GOOGLE_API_KEY`        | `https://generativelanguage.googleapis.com/v1beta/openai` |
| Anthropic     | `anthropic`          | `ANTHROPIC_API_KEY`     | `https://api.anthropic.com/v1`                            |
| SiliconFlow   | `siliconflow`        | `SILICONFLOW_API_KEY`   | —                                                         |
| OpenRouter    | `openrouter`         | `OPENROUTER_API_KEY`    | —                                                         |
| Ollama        | `ollama`             | 无需 API Key              | `http://localhost:11434/v1`                               |
| 智谱 AI         | `zhipu`              | `ZHIPU_API_KEY`         | —                                                         |
| 百度千帆          | `qianfan`            | `QIANFAN_API_KEY`       | —                                                         |
| 自定义 OpenAI    | `custom_openai`      | `CUSTOM_OPENAI_API_KEY` | 需手动设置                                                     |

> **提示**：使用 OpenAI 兼容的内部/私有模型时，设 `MCP_LLM_PROVIDER=openai`，将 `MCP_BACKEND_URL` 指向内部 API 地址即可。

#### A股数据源配置

| 变量                          | 说明                                                 | 默认值                                  |
|-----------------------------|----------------------------------------------------|--------------------------------------|
| `DEFAULT_CHINA_DATA_SOURCE` | A股默认数据源（`internal`/`akshare`/`tushare`/`baostock`） | `internal`                           |
| `JDBC_HTTP_PROXY`           | JDBC HTTP Proxy 地址                                 | `192.168.100.101:9998`               |
| `TM_REAL_CONN`              | Hive JDBC 连接串                                      | `jdbc:hive2://192.168.100.102:10006` |
| `TM_DB_NAME`                | 数据库名称                                              | `meta_data`                          |
| `TM_DB_USER`                | 数据库用户名                                             | `transmatrix_admin`                  |
| `TM_DB_PASSWORD`            | 数据库密码                                              | `Transmatrix123`                     |
| `GUARDIAN_TOKEN`            | Guardian 认证 Token                                  | —                                    |
| `TUSHARE_TOKEN`             | Tushare API Token（使用 tushare 数据源时需要）               | —                                    |

#### API Key 解析优先级

`create_llms_from_config` 的 API Key 解析链（以深度模型为例）：

```
MCP_DEEP_API_KEY → MCP_QUICK_API_KEY（交叉回退）→ 供应商标准环境变量
```

例如 `MCP_LLM_PROVIDER=dashscope`：

1. 优先使用 `MCP_DEEP_API_KEY`
2. 若为空，回退到 `MCP_QUICK_API_KEY`
3. 若仍为空，读取 `DASHSCOPE_API_KEY` 标准环境变量

## 10 个 MCP Tool

| Tool                   | 说明                  | 耗时     |
|------------------------|---------------------|--------|
| `trading_agent`        | 完整全流程（分析师→辩论→风险→决策） | 3-10分钟 |
| `market_analyst`       | 独立技术面分析             | ~30秒   |
| `fundamentals_analyst` | 独立基本面分析             | ~30秒   |
| `news_analyst`         | 独立新闻分析              | ~30秒   |
| `social_analyst`       | 独立情绪分析              | ~30秒   |
| `compare_stocks`       | 多股对比（横向对比+排名）       | 依股数    |
| `batch_analyze`        | 批量独立分析（无对比）         | 依股数    |
| `period_compare`       | 历史区间对比（收益率/回撤/超额）   | ~30秒   |
| `screen_stocks`        | 股票筛选（条件+LLM解读）      | ~15秒   |
| `agent_status`         | 配置状态+健康检查           | <1秒    |

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
