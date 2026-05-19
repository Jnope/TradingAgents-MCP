# FastMCP 改造分析：数据源切换与可移除文件

---

## 一、当前项目数据源切换能力分析

### 1.1 已有能力：支持切换，但依赖数据库

项目**已支持**数据源切换，核心机制在 `tradingagents/dataflows/data_source_manager.py`：

```
数据源优先级读取链路：

1. MongoDB 数据库配置（system_configs 集合）
   └── 用户通过 FastAPI/Vue 前端配置的数据源优先级
   └── 按 priority 字段排序，enabled 字段过滤

2. 环境变量回退
   └── TA_USE_APP_CACHE — 是否启用 MongoDB 缓存

3. 代码默认值
   └── A股: AKShare > Tushare > BaoStock
   └── 美股: YFinance > Alpha Vantage > Finnhub
   └── 港股: AKShare
```

关键代码（`data_source_manager.py:91-171`）：

```python
def _get_data_source_priority_order(self, symbol=None):
    # 1. 尝试从 MongoDB 读取用户配置的优先级
    db = get_mongo_db_sync()
    config_data = config_collection.find_one({"is_active": True}, ...)
    # 2. 按 priority 排序，返回启用的数据源
    # 3. 如果 MongoDB 不可用，回退到默认顺序
    default_order = [ChinaDataSource.AKSHARE, ChinaDataSource.TUSHARE, ChinaDataSource.BAOSTOCK]
```

**问题**：数据源切换**依赖 MongoDB**，MCP 模式下无法使用。

### 1.2 FastMCP 下的数据源切换方案

改用**环境变量 + Tool 参数**控制，无需数据库：

#### 方案 A：环境变量控制（全局配置）

```bash
# .opencode.json 中的 env 字段
"MCP_CHINA_DATA_SOURCE": "tushare",     # akshare | tushare | baostock
"MCP_US_DATA_SOURCE": "yfinance",        # yfinance | alpha_vantage | finnhub
"MCP_HK_DATA_SOURCE": "akshare",         # akshare
```

MCP server 启动时读取，设置数据源优先级：

```python
def _build_config() -> dict:
    config = DEFAULT_CONFIG.copy()
    china_source = os.getenv("MCP_CHINA_DATA_SOURCE", "akshare")
    # 通过环境变量覆盖默认数据源优先级
    config["china_data_source_priority"] = china_source
    return config
```

#### 方案 B：Tool 参数控制（按需切换）

在 Tool 参数中增加 `data_source` 选项：

```python
@mcp.tool()
async def market_analyst(
    symbol: str,
    trade_date: str,
    data_source: str = "auto",  # auto | akshare | tushare | baostock
) -> dict:
    """
    市场分析师Agent。data_source 指定数据源，默认 auto 自动选择。
    """
```

#### 推荐：方案 A + B 结合

- 环境变量设置全局默认数据源（无数据库依赖）
- Tool 参数允许单次调用覆盖（灵活按需切换）

---

## 二、改为 FastMCP 后不再需要的文件/目录

### 2.1 整体可移除的目录

| 目录 | 文件数 | 大小 | 说明 |
|------|--------|------|------|
| `app/` | 153个.py | 2.6M | **整个 FastAPI 后端**，MCP 不需要 |
| `frontend/` | 102个.ts/.vue | 6.5M | **整个 Vue 前端**，MCP 不需要 |
| `web/` | 35个.py | 776K | **Streamlit 旧版 UI**，MCP 不需要 |
| `nginx/` | 少量 | 8K | Nginx 反向代理配置 |
| `docker/` | 少量 | 8K | Docker 构建/部署文件 |
| `docker-compose*.yml` | 3个 | — | 容器编排 |
| `Dockerfile.*` | 2个 | — | 后端/前端镜像构建 |

**总计可移除：~10M，290+ 文件**

### 2.2 `app/` 详细拆解（全部可移除）

```
app/                            # 整个目录可移除
├── main.py                     # FastAPI 入口、路由注册、中间件、APScheduler
├── core/                       # Pydantic Settings、数据库连接、Redis、日志配置
│   ├── config.py               # FastAPI 配置（端口、数据库URL、密钥等）
│   ├── unified_config.py       # 统一配置管理
│   ├── config_bridge.py        # 配置桥接（tradingagents ↔ FastAPI）
│   ├── database.py             # MongoDB 连接管理
│   ├── redis_client.py         # Redis 客户端
│   ├── rate_limiter.py         # API 速率限制
│   └── startup_validator.py    # 启动时数据库/Redis 连接验证
├── routers/                    # 30+ 个 REST API 路由模块
│   ├── analysis.py             # 股票分析 API
│   ├── auth_db.py              # 用户认证 API
│   ├── stocks.py               # 股票列表 API
│   ├── screening.py            # 股票筛选 API
│   ├── favorites.py            # 自选股 API
│   ├── paper.py                # 模拟交易 API
│   ├── config.py               # 配置管理 API
│   ├── sse.py / websocket_notifications.py  # SSE/WebSocket 推送
│   └── ... (27 more)
├── services/                   # 45+ 个业务服务模块
│   ├── analysis_service.py     # 分析服务（调用 tradingagents）
│   ├── auth_service.py         # 认证服务
│   ├── queue_service.py        # 任务队列
│   ├── scheduler_service.py    # 定时调度
│   └── ... (41 more)
├── middleware/                  # 中间件（错误处理、限流、日志）
├── models/                      # Pydantic/MongoDB 数据模型
├── schemas/                     # 请求/响应 Schema
├── worker/                      # 后台同步 Worker
│   ├── tushare_sync_service.py
│   ├── akshare_sync_service.py
│   └── ...
├── constants/
└── utils/
```

**移除原因**：MCP 模式下，opencode 直接调用 `tradingagents/` 核心，不需要 REST API/Web UI/用户认证/任务队列等。

### 2.3 `frontend/` 详细拆解（全部可移除）

```
frontend/                       # 整个目录可移除
├── src/
│   ├── views/                  # 15 个页面视图
│   │   ├── Analysis/           # 股票分析页
│   │   ├── Dashboard/          # 仪表盘
│   │   ├── Screening/          # 股票筛选
│   │   ├── Settings/           # 系统设置
│   │   └── ...
│   ├── components/             # 公共组件
│   ├── stores/                 # Pinia 状态管理
│   ├── api/                    # API 调用层
│   └── router/                 # 路由
├── package.json
└── vite.config.ts
```

### 2.4 `web/` 详细拆解（全部可移除）

```
web/                            # Streamlit 旧版 UI，整个目录可移除
├── app.py
├── components/
├── utils/
└── run_web.py
```

### 2.5 部分可移除的 `tradingagents/` 文件

以下文件**强依赖 `app/`（FastAPI/MongoDB/Redis）**，MCP 模式下无用：

| 文件 | 依赖 | 说明 |
|------|------|------|
| `config/mongodb_storage.py` | MongoDB | 配置存储到 MongoDB |
| `config/database_config.py` | MongoDB | 数据库配置 |
| `config/database_manager.py` | MongoDB | 数据库管理器 |
| `config/usage_models.py` | MongoDB | 用量统计模型 |
| `dataflows/data_source_manager.py` 中的 MongoDB 读取部分 | MongoDB | 需改写为环境变量 |
| `dataflows/interface.py` 中的 `_get_enabled_*_data_sources()` | MongoDB | 需改写为环境变量 |
| `config/runtime_settings.py` 中的动态配置获取 | `app.services` | 已注释禁用，无影响 |

### 2.6 根目录可移除的文件

| 文件 | 说明 |
|------|------|
| `Dockerfile.backend` | FastAPI 后端镜像 |
| `Dockerfile.frontend` | Vue 前端镜像 |
| `docker-compose.yml` | 完整编排 |
| `docker-compose.hub.nginx.yml` | Nginx 版编排 |
| `docker-compose.hub.nginx.arm.yml` | ARM 版编排 |
| `.env.docker` | Docker 环境变量 |
| `.streamlit/` | Streamlit 配置 |
| `install/` | 安装配置 |

---

## 三、改造后的精简项目结构

```
TradingAgents-CN/
├── tradingagents/                  # 核心引擎（保留，小幅修改）
│   ├── agents/                     # 全部保留
│   ├── graph/                      # 全部保留
│   ├── dataflows/                  # 保留，修改数据源切换逻辑
│   │   ├── interface.py            # 移除 MongoDB 读取，改用环境变量
│   │   ├── data_source_manager.py  # 移除 MongoDB 读取，改用环境变量
│   │   ├── providers/              # 全部保留（数据源适配器）
│   │   ├── news/                   # 全部保留
│   │   ├── technical/              # 全部保留
│   │   └── cache/                  # 保留（文件缓存仍可用）
│   ├── llm_adapters/               # 全部保留
│   ├── config/                     # 保留，移除 MongoDB 相关
│   │   ├── config_manager.py       # 保留（已标记 deprecated，日志告警）
│   │   ├── providers_config.py     # 保留
│   │   ├── runtime_settings.py     # 保留（已兼容无 app 场景）
│   │   ├── env_utils.py            # 保留
│   │   ├── tushare_config.py       # 保留
│   │   ├── mongodb_storage.py      # ❌ 可移除
│   │   ├── database_config.py      # ❌ 可移除
│   │   ├── database_manager.py     # ❌ 可移除
│   │   └── usage_models.py         # ❌ 可移除
│   ├── tools/                      # 全部保留
│   ├── utils/                      # 全部保留
│   ├── constants/                  # 全部保留
│   ├── mcp_server/                 # ✨ 新增
│   │   ├── __init__.py
│   │   ├── server.py
│   │   └── prompts.py
│   └── default_config.py           # 保留，新增数据源环境变量
├── config/                         # 保留（logging.toml）
├── cli/                            # 保留（数据源初始化工具）
├── tests/                          # 保留
├── docs/                           # 保留
├── examples/                       # 保留
├── pyproject.toml                  # 保留，移除 FastAPI 相关依赖
├── main.py                         # 保留（CLI 入口）
└── .env.example                    # 保留，更新 MCP 配置说明
```

### 需要修改的文件（最小改动）

| 文件 | 修改内容 |
|------|----------|
| `tradingagents/dataflows/interface.py` | `_get_enabled_hk_data_sources()` / `_get_enabled_us_data_sources()` 改为读环境变量 |
| `tradingagents/dataflows/data_source_manager.py` | `_get_data_source_priority_order()` 增加环境变量回退 |
| `tradingagents/default_config.py` | 新增 `china_data_source` / `us_data_source` 等配置项 |
| `pyproject.toml` | 新增 `mcp[cli]` 依赖，移除 `fastapi`/`uvicorn`/`motor`/`redis` 等依赖（可选） |

---

## 四、数据源切换具体修改方案

### 4.1 `default_config.py` 新增配置

```python
DEFAULT_CONFIG = {
    # ...existing...
    "china_data_source": os.getenv("MCP_CHINA_DATA_SOURCE", "akshare"),
    "us_data_source": os.getenv("MCP_US_DATA_SOURCE", "yfinance"),
    "hk_data_source": os.getenv("MCP_HK_DATA_SOURCE", "akshare"),
}
```

### 4.2 `data_source_manager.py` 修改优先级读取

```python
def _get_data_source_priority_order(self, symbol=None):
    # 1. 尝试环境变量配置（MCP 模式）
    env_priority = self._get_env_data_source_priority(symbol)
    if env_priority:
        return env_priority

    # 2. 尝试 MongoDB（FastAPI 模式，如果可用）
    try:
        from app.core.database import get_mongo_db_sync
        # ...existing MongoDB logic...
    except (ImportError, Exception):
        pass

    # 3. 默认顺序
    return [ChinaDataSource.AKSHARE, ChinaDataSource.TUSHARE, ChinaDataSource.BAOSTOCK]

def _get_env_data_source_priority(self, symbol):
    """从环境变量读取数据源优先级"""
    market = self._identify_market_category(symbol)
    if market == 'a_shares':
        source_str = os.getenv("MCP_CHINA_DATA_SOURCE", "akshare")
        mapping = {"akshare": ChinaDataSource.AKSHARE, "tushare": ChinaDataSource.TUSHARE, "baostock": ChinaDataSource.BAOSTOCK}
    elif market == 'us_stocks':
        source_str = os.getenv("MCP_US_DATA_SOURCE", "yfinance")
        mapping = {"yfinance": USDataSource.YFINANCE, "alpha_vantage": USDataSource.ALPHA_VANTAGE, "finnhub": USDataSource.FINNHUB}
    else:
        return None

    source = mapping.get(source_str.lower())
    if source and source in self.available_sources:
        return [source]
    return None
```

### 4.3 `interface.py` 同步修改

```python
def _get_enabled_hk_data_sources() -> list:
    # 1. 环境变量优先
    env_source = os.getenv("MCP_HK_DATA_SOURCE")
    if env_source:
        return [env_source.lower()]

    # 2. 尝试 MongoDB（兼容 FastAPI 模式）
    try:
        from app.core.database import get_mongo_db_sync
        # ...existing logic...
    except (ImportError, Exception):
        pass

    # 3. 默认
    return ['akshare', 'yfinance']
```

---

## 五、总结

### 数据源切换

| 问题 | 答案 |
|------|------|
| 当前是否支持切换？ | **支持**，但通过 MongoDB 数据库配置，需 FastAPI 前端操作 |
| MCP 下能否切换？ | **能**，改为环境变量 + Tool 参数控制，无需数据库 |
| 改动量 | 3 个文件小幅修改，新增环境变量读取逻辑 |

### 可移除文件

| 类别 | 可移除文件数 | 可移除体积 |
|------|-------------|-----------|
| `app/` 整个目录 | 153 .py | 2.6M |
| `frontend/` 整个目录 | 102 .ts/.vue | 6.5M |
| `web/` 整个目录 | 35 .py | 776K |
| `nginx/` + `docker/` + Docker 文件 | ~10 | ~20K |
| `tradingagents/config/` 中 3 个 MongoDB 文件 | 3 .py | ~30K |
| **合计** | **~300 文件** | **~10M** |

### 保留的核心

`tradingagents/` 核心引擎（2M）+ `mcp_server/` 新增（2文件），总代码量从 ~10M 精简到 ~2M。
