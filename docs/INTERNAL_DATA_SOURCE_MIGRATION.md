# 内部数据源接入方案（TransMatrix 数据库）

> 基于 TransMatrix 本地数据库的完整数据能力，设计内部数据源接入方案，全面替代 AKShare/Tushare 等公共数据源。

## 一、TransMatrix 数据库能力 vs 系统需求

### 1.1 数据覆盖全景

| 系统需求 | TransMatrix 表 | 字段完备度 | 可替代 |
|---------|---------------|-----------|--------|
| 股票列表/基本信息 | `stock_code` | code/name/area/industry/market/list_date | ✅ 完全替代 |
| 行业分类 | `sw_industry` | 申万一二三级行业 | ✅ 完全替代 |
| 概念板块 | `concept_code` + `concept_component` | 概念代码/名称/成分股 | ✅ 完全替代 |
| 日 K 线 | `stock_bar_1day` | OHLCV + vwap + factor(复权) | ✅ 完全替代 |
| 分钟 K 线 | `stock_bar_1/5/10/30/60min` | OHLCV + vwap | ✅ 完全替代 |
| 实时快照 | `stock_snapshot` | 价格+十档盘口+涨跌停 | ✅ 完全替代 |
| 资金流向 | `stock_money_flow` | 主力/大单/中单/小单净额净占比 | ✅ 完全替代（增强） |
| 估值指标 | `capital` | PE(TTM)/PE(LYR)/PB/PS/PCF/市值/换手率 | ✅ 完全替代 |
| 财务指标 | `finance_indicator` | EPS/ROE/ROA/毛利率/净利率/同比增长率… | ✅ 完全替代 |
| 资产负债表 | `balance` | 完整三大表（50+字段） | ✅ 完全替代 |
| 利润表 | `income` | 完整（30+字段） | ✅ 完全替代 |
| 现金流表 | `cashflow` | 完整（50+字段） | ✅ 完全替代 |
| 分红配股 | `dividend_allocation` | 完整 | ✅ 完全替代 |
| 十大股东 | `shareholders_top10` | 持股数量/比例/类别/质押 | ✅ 完全替代 |
| 十大流通股东 | `float_shareholders_top10` | 持股数量/比例/类别 | ✅ 完全替代 |
| 股东户数 | `shareholder_num` | A/B/H股股东户数 | ✅ 完全替代 |
| 大股东增减持 | `shareholder_change` | 增减持数量/价格/比例 | ✅ 完全替代 |
| 股份质押 | `pledge_shares` | 质押数量/起止日/解除 | ✅ 完全替代 |
| 股份冻结 | `frozen_shares` | 冻结数量/起止日/解冻 | ✅ 完全替代 |
| 股本变动 | `capital_change` | 总股本/流通股/限售股细分 | ✅ 完全替代 |
| 指数数据 | `index_bar_1day` + `index_code` | 指数K线/权重 | ✅ 完全替代 |
| 宏观数据 | `macro_leverage`/`cpi`/`pmi`/… | 杠杆率/CPI/PMI/M2/贸易… | ✅ 完全替代 |
| 舆情/情绪 | 财联社 Kafka | — | ✅ 新接入 |
| 新闻 | 财联社 Kafka | — | ✅ 新接入 |

**结论：TransMatrix 数据能力远超当前系统需求，可完全替代 AKShare/Tushare/BaoStock，并额外提供资金流向、股东、宏观等数据。**

### 1.2 关键字段映射

#### 股票代码格式

TransMatrix 使用 `000001.SZ` 格式（带交易所后缀），系统内部使用 `000001` 格式（6 位纯数字）。需要双向转换：

```python
def to_internal_code(tm_code: str) -> str:
    """TransMatrix → 系统内部: 000001.SZ → 000001"""
    return tm_code.split(".")[0] if "." in tm_code else tm_code

def to_tm_code(code: str) -> str:
    """系统内部 → TransMatrix: 000001 → 000001.SZ"""
    if "." in code:
        return code
    if code.startswith(("6",)):
        return f"{code}.SH"
    return f"{code}.SZ"
```

#### K 线字段映射

| TransMatrix (`stock_bar_1day`) | 系统标准列 | 说明 |
|------|------|------|
| `code` | `code` | 需去掉后缀 |
| `trade_day` | `date` | 交易日期 |
| `open` | `open` | 开盘价 |
| `high` | `high` | 最高价 |
| `low` | `low` | 最低价 |
| `close` | `close` | 收盘价 |
| `volume` | `vol` | 成交量 |
| `turnover` | `amount` | 成交额 |
| `vwap` | — | 成交均价（额外） |
| `factor` | — | 复权因子（额外） |

#### 估值字段映射

| TransMatrix (`capital`) | 系统使用 | 说明 |
|------|------|------|
| `capitalization` | 总股本 | 万股 |
| `circulating_cap` | 流通股本 | 万股 |
| `market_cap` | 总市值 | 亿元 |
| `circulating_market_cap` | 流通市值 | 亿元 |
| `turnover_ratio` | 换手率 | % |
| `pe_ratio` | PE(TTM) | ✅ |
| `pe_ratio_lyr` | PE(LYR) | ✅ |
| `pb_ratio` | PB | ✅ |
| `ps_ratio` | PS(TTM) | ✅ |
| `pcf_ratio` | PCF(TTM) | ✅ |

---

## 二、架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────┐
│  agents/ (Market/Fundamentals/News/Social)       │
│  通过 interface.py + DataSourceManager 调用      │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  DataSourceManager (降级链管理)                   │
│  INTERNAL → AKSHARE → TUSHARE → BAOSTOCK        │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  InternalProvider (核心 Provider)                 │
│  ├── DB 查询层：SQLAlchemy / pymssql / httpx     │
│  ├── 字段映射 + 标准化                            │
│  ├── 技术指标本地计算（MA/MACD/RSI/BOLL）          │
│  └── 降级 AKShare 兜底                            │
└──────────────────────┬──────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────┐
│  TransMatrix DB + 财联社 Kafka                    │
│  ├── SQL Server / PostgreSQL (行情+财务)          │
│  ├── stock_bar_1day (日K)                        │
│  ├── capital (估值)                               │
│  ├── finance_indicator (财务指标)                  │
│  ├── balance / income / cashflow (三大表)         │
│  ├── stock_snapshot (实时快照)                     │
│  ├── stock_money_flow (资金流向)                   │
│  ├── stock_code / sw_industry (基础)              │
│  └── Kafka Topic: cls-sentiment (舆情+新闻)       │
└─────────────────────────────────────────────────┘
```

### 2.2 连接方式选择

| 方案 | 说明 | 优点 | 缺点 |
|------|------|------|------|
| **A：直接 DB 查询** | InternalProvider 内用 SQLAlchemy 连 TransMatrix DB | 最快、无中间层 | 需暴露 DB 连接串 |
| **B：内部 HTTP API** | 在 DB 前搭一层 HTTP 服务 | 解耦、权限控制 | 多一跳延迟 |
| **C：混合** | 高频数据(行情)直连 DB，低频数据(财务)走 API | 最优性能 | 实现稍复杂 |

**推荐方案 A（直接 DB 查询）**：MCP Server 与 TransMatrix DB 在同一内网，直连性能最优。如果后续需要权限管控，再切换到方案 B。

---

## 三、InternalProvider 实现

### 3.1 文件结构

```
src/tradingagents/dataflows/providers/china/
├── internal.py              # 主 Provider（同步接口）
├── internal_queries.py      # SQL 查询封装
└── internal_code_mapper.py  # 代码格式转换
```

### 3.2 代码格式转换（`internal_code_mapper.py`）

```python
_CODE_SUFFIX_MAP = {
    "6": ".SH",  # 60xxxx 沪市主板
    "9": ".SH",  # 68xxxx 科创板 / 90xxxx
    "0": ".SZ",  # 00xxxx 深市主板
    "3": ".SZ",  # 30xxxx 创业板
    "2": ".SZ",  # 20xxxx 深市B股
}

def to_tm_code(code: str) -> str:
    """6位纯数字 → TransMatrix 格式: 000001 → 000001.SZ"""
    if not code or "." in code:
        return code
    suffix = _CODE_SUFFIX_MAP.get(code[0], ".SZ")
    return f"{code}{suffix}"

def to_internal_code(tm_code: str) -> str:
    """TransMatrix → 6位纯数字: 000001.SZ → 000001"""
    return tm_code.split(".")[0] if "." in tm_code else tm_code

def is_tm_code(code: str) -> bool:
    return "." in code
```

### 3.3 SQL 查询封装（`internal_queries.py`）

```python
import os
from typing import Optional, List
import pandas as pd
from sqlalchemy import create_engine, text

_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        url = os.getenv(
            "TM_DB_URL",
            "mssql+pymssql://user:pass@tm-db:1433/TransMatrix",
        )
        _engine = create_engine(url, pool_size=5, max_overflow=10, pool_pre_ping=True)
    return _engine

def query(sql: str, params: dict = None) -> pd.DataFrame:
    with _get_engine().connect() as conn:
        return pd.read_sql(text(sql), conn, params=params)


# ==================== 股票基本信息 ====================

def get_stock_info(symbol: str) -> Optional[dict]:
    from .internal_code_mapper import to_tm_code
    tm_code = to_tm_code(symbol)
    df = query("SELECT * FROM stock_code WHERE code = :code", {"code": tm_code})
    return df.iloc[0].to_dict() if not df.empty else None

def get_stock_list() -> pd.DataFrame:
    return query("SELECT * FROM stock_code WHERE delist_date IS NULL")

def get_sw_industry(symbol: str) -> Optional[dict]:
    from .internal_code_mapper import to_tm_code
    tm_code = to_tm_code(symbol)
    df = query(
        "SELECT TOP 1 * FROM sw_industry WHERE code = :code ORDER BY datetime DESC",
        {"code": tm_code},
    )
    return df.iloc[0].to_dict() if not df.empty else None


# ==================== K 线数据 ====================

def get_daily_kline(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    tm_code = to_tm_code(symbol)
    return query(
        """SELECT code, trade_day, open, high, low, close, volume, turnover, vwap, factor
           FROM stock_bar_1day
           WHERE code = :code AND trade_day >= :start AND trade_day <= :end
           ORDER BY trade_day""",
        {"code": tm_code, "start": start_date, "end": end_date},
    )


# ==================== 实时快照 ====================

def get_snapshot(symbol: str) -> Optional[dict]:
    from .internal_code_mapper import to_tm_code
    tm_code = to_tm_code(symbol)
    df = query(
        "SELECT TOP 1 * FROM stock_snapshot WHERE code = :code ORDER BY datetime DESC",
        {"code": tm_code},
    )
    return df.iloc[0].to_dict() if not df.empty else None

def get_all_snapshots(trade_day: str) -> pd.DataFrame:
    return query(
        "SELECT * FROM stock_snapshot WHERE trade_day = :day",
        {"day": trade_day},
    )


# ==================== 估值数据 ====================

def get_valuation(symbol: str, trade_day: str = None) -> Optional[dict]:
    from .internal_code_mapper import to_tm_code
    tm_code = to_tm_code(symbol)
    if trade_day:
        df = query(
            """SELECT TOP 1 * FROM capital WHERE code = :code
               AND CONVERT(DATE, datetime) <= :day ORDER BY datetime DESC""",
            {"code": tm_code, "day": trade_day},
        )
    else:
        df = query(
            "SELECT TOP 1 * FROM capital WHERE code = :code ORDER BY datetime DESC",
            {"code": tm_code},
        )
    return df.iloc[0].to_dict() if not df.empty else None


# ==================== 财务指标 ====================

def get_finance_indicator(symbol: str, limit: int = 4) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    tm_code = to_tm_code(symbol)
    return query(
        """SELECT TOP :n * FROM finance_indicator
           WHERE code = :code ORDER BY datetime DESC""",
        {"code": tm_code, "n": limit},
    )


# ==================== 三大财务报表 ====================

def get_balance(symbol: str, limit: int = 4) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    return query(
        "SELECT TOP :n * FROM balance WHERE code = :code ORDER BY datetime DESC",
        {"code": to_tm_code(symbol), "n": limit},
    )

def get_income(symbol: str, limit: int = 4) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    return query(
        "SELECT TOP :n * FROM income WHERE code = :code ORDER BY datetime DESC",
        {"code": to_tm_code(symbol), "n": limit},
    )

def get_cashflow(symbol: str, limit: int = 4) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    return query(
        "SELECT TOP :n * FROM cashflow WHERE code = :code ORDER BY datetime DESC",
        {"code": to_tm_code(symbol), "n": limit},
    )


# ==================== 资金流向 ====================

def get_money_flow(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    return query(
        """SELECT * FROM stock_money_flow
           WHERE code = :code AND trade_day >= :start AND trade_day <= :end
           ORDER BY trade_day""",
        {"code": to_tm_code(symbol), "start": start_date, "end": end_date},
    )


# ==================== 股东数据 ====================

def get_top10_shareholders(symbol: str, limit: int = 2) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    return query(
        "SELECT TOP :n * FROM shareholders_top10 WHERE code = :code ORDER BY datetime DESC",
        {"code": to_tm_code(symbol), "n": limit * 10},
    )

def get_shareholder_num(symbol: str, limit: int = 4) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    return query(
        "SELECT TOP :n * FROM shareholder_num WHERE code = :code ORDER BY datetime DESC",
        {"code": to_tm_code(symbol), "n": limit},
    )


# ==================== 分红配股 ====================

def get_dividend(symbol: str, limit: int = 5) -> pd.DataFrame:
    from .internal_code_mapper import to_tm_code
    return query(
        "SELECT TOP :n * FROM dividend_allocation WHERE code = :code ORDER BY datetime DESC",
        {"code": to_tm_code(symbol), "n": limit},
    )


# ==================== 指数数据 ====================

def get_index_kline(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    return query(
        """SELECT * FROM index_bar_1day
           WHERE code = :code AND trade_day >= :start AND trade_day <= :end
           ORDER BY trade_day""",
        {"code": code, "start": start_date, "end": end_date},
    )


# ==================== 全市场快照（筛选） ====================

def get_market_snapshot() -> pd.DataFrame:
    return query(
        """SELECT s.code, c.name, s.last_price as close, s.pre_close,
                  s.open, s.high, s.low, s.volume, s.turnover,
                  s.limit_up, s.limit_down
           FROM stock_snapshot s
           JOIN stock_code c ON s.code = c.code
           WHERE s.trade_day = (SELECT MAX(trade_day) FROM stock_snapshot)"""
    )


# ==================== 宏观数据 ====================

def get_macro_pmi() -> pd.DataFrame:
    return query("SELECT * FROM official_pmi ORDER BY datetime DESC")

def get_macro_cpi() -> pd.DataFrame:
    return query("SELECT * FROM cpi ORDER BY datetime DESC")

def get_macro_m2() -> pd.DataFrame:
    return query("SELECT * FROM m2_supply ORDER BY datetime DESC")
```

### 3.4 主 Provider（`internal.py`）

```python
"""
TransMatrix 内部数据源 Provider
同步接口，与 AKShareProvider 风格一致
"""
import os
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class InternalProvider:

    def __init__(self):
        self._db_url = os.getenv("TM_DB_URL", "")

    def health_check(self) -> bool:
        try:
            from .internal_queries import _get_engine
            engine = _get_engine()
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return True
        except Exception as e:
            logger.warning(f"TransMatrix DB 连接失败: {e}")
            return False

    # ==================== 股票基本信息 ====================

    def get_stock_info(self, symbol: str) -> dict:
        from .internal_queries import get_stock_info
        info = get_stock_info(symbol)
        if not info:
            return {"code": symbol, "name": f"股票{symbol}", "error": "未找到"}
        from .internal_code_mapper import to_internal_code
        info["code"] = to_internal_code(info.get("code", symbol))
        return info

    def get_stock_list(self) -> List[dict]:
        from .internal_queries import get_stock_list
        df = get_stock_list()
        from .internal_code_mapper import to_internal_code
        df["code"] = df["code"].apply(to_internal_code)
        return df.to_dict("records")

    # ==================== K 线数据 ====================

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        from .internal_queries import get_daily_kline
        df = get_daily_kline(symbol, start_date, end_date)
        if df.empty:
            logger.warning(f"TransMatrix 无 K 线数据: {symbol}，降级 AKShare")
            return self._fallback_akshare_kline(symbol, start_date, end_date)
        return self._standardize_kline(df)

    # ==================== 实时行情 ====================

    def get_stock_quotes(self, symbol: str) -> dict:
        from .internal_queries import get_snapshot
        snap = get_snapshot(symbol)
        if not snap:
            return {}
        from .internal_code_mapper import to_internal_code
        snap["code"] = to_internal_code(snap.get("code", symbol))
        return {
            "code": snap["code"],
            "close": snap.get("last_price"),
            "open": snap.get("open"),
            "high": snap.get("high"),
            "low": snap.get("low"),
            "pre_close": snap.get("pre_close"),
            "volume": snap.get("volume"),
            "amount": snap.get("turnover"),
            "limit_up": snap.get("limit_up"),
            "limit_down": snap.get("limit_down"),
        }

    # ==================== 基本面（估值+财务指标+三大表） ====================

    def get_fundamentals(self, symbol: str) -> str:
        from .internal_code_mapper import to_tm_code
        tm_code = to_tm_code(symbol)

        try:
            from .internal_queries import (
                get_stock_info, get_valuation, get_finance_indicator,
                get_income, get_balance, get_cashflow, get_dividend,
            )

            info = get_stock_info(symbol) or {}
            val = get_valuation(symbol) or {}
            fi = get_finance_indicator(symbol, limit=1)
            fi_row = fi.iloc[0].to_dict() if not fi.empty else {}

            # 基本信息
            report = f"📊 {symbol} 基本面分析（TransMatrix 数据源）\n\n"
            report += f"📈 股票名称: {info.get('name', '未知')}\n"
            report += f"🏢 所属行业: {info.get('industry', '未知')}\n"
            report += f"📍 所属地区: {info.get('area', '未知')}\n"
            report += f"📅 上市日期: {info.get('list_date', '未知')}\n\n"

            # 估值指标（capital 表，日频更新）
            report += "📊 估值指标:\n"
            if val:
                report += f"   总市值: {val.get('market_cap', 'N/A')}亿元\n"
                report += f"   流通市值: {val.get('circulating_market_cap', 'N/A')}亿元\n"
                report += f"   PE(TTM): {val.get('pe_ratio', 'N/A')}\n"
                report += f"   PE(LYR): {val.get('pe_ratio_lyr', 'N/A')}\n"
                report += f"   PB: {val.get('pb_ratio', 'N/A')}\n"
                report += f"   PS(TTM): {val.get('ps_ratio', 'N/A')}\n"
                report += f"   PCF(TTM): {val.get('pcf_ratio', 'N/A')}\n"
                report += f"   换手率: {val.get('turnover_ratio', 'N/A')}%\n"
                report += f"   总股本: {val.get('capitalization', 'N/A')}万股\n"
                report += f"   流通股本: {val.get('circulating_cap', 'N/A')}万股\n"
            report += "\n"

            # 财务指标（finance_indicator 表）
            if fi_row:
                report += "💹 盈利能力:\n"
                report += f"   EPS: {fi_row.get('eps', 'N/A')}\n"
                report += f"   ROE: {fi_row.get('roe', 'N/A')}\n"
                report += f"   ROA: {fi_row.get('roa', 'N/A')}\n"
                report += f"   净利率: {fi_row.get('net_profit_margin', 'N/A')}\n"
                report += f"   毛利率: {fi_row.get('gross_profit_margin', 'N/A')}\n"
                report += "\n📈 成长能力:\n"
                report += f"   营收同比增长: {fi_row.get('inc_revenue_year_on_year', 'N/A')}%\n"
                report += f"   净利润同比增长: {fi_row.get('inc_net_profit_year_on_year', 'N/A')}%\n"
                report += f"   营业利润同比增长: {fi_row.get('inc_operation_profit_year_on_year', 'N/A')}%\n"
                report += "\n"

            # 分红
            div_df = get_dividend(symbol, limit=3)
            if not div_df.empty:
                report += "💰 近期分红:\n"
                for _, row in div_df.iterrows():
                    report += f"   {row.get('report_date', 'N/A')}: {row.get('implementation_bonusnote', 'N/A')}\n"
                report += "\n"

            return report

        except Exception as e:
            logger.error(f"❌ TransMatrix 基本面获取失败: {e}")
            return f"❌ 获取{symbol}基本面数据失败: {e}"

    # ==================== 资金流向（增强数据） ====================

    def get_money_flow(self, symbol: str, start_date: str, end_date: str) -> str:
        from .internal_queries import get_money_flow
        df = get_money_flow(symbol, start_date, end_date)
        if df.empty:
            return ""
        latest = df.iloc[-1]
        report = f"📊 {symbol} 资金流向 ({latest.get('trade_day', '')})\n\n"
        report += f"   涨跌幅: {latest.get('change_pct', 'N/A')}%\n"
        report += f"   主力净额: {latest.get('net_amount_main', 'N/A')}万\n"
        report += f"   主力净占比: {latest.get('net_pct_main', 'N/A')}%\n"
        report += f"   超大单净额: {latest.get('net_amount_xl', 'N/A')}万\n"
        report += f"   大单净额: {latest.get('net_amount_l', 'N/A')}万\n"
        report += f"   中单净额: {latest.get('net_amount_m', 'N/A')}万\n"
        report += f"   小单净额: {latest.get('net_amount_s', 'N/A')}万\n"
        return report

    # ==================== 全市场快照（筛选） ====================

    def get_market_snapshot(self) -> Optional[pd.DataFrame]:
        from .internal_queries import get_market_snapshot
        return get_market_snapshot()

    # ==================== 内部工具方法 ====================

    def _standardize_kline(self, df: pd.DataFrame) -> pd.DataFrame:
        from .internal_code_mapper import to_internal_code
        if df.empty:
            return df
        df = df.copy()
        df["code"] = df["code"].apply(to_internal_code)
        df = df.rename(columns={
            "trade_day": "date",
            "volume": "vol",
            "turnover": "amount",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
        if "pct_change" not in df.columns and "close" in df.columns:
            df["pct_change"] = df["close"].pct_change() * 100.0
        return df

    def _fallback_akshare_kline(self, symbol, start_date, end_date):
        try:
            from .akshare import get_akshare_provider
            provider = get_akshare_provider()
            return provider.get_stock_data(symbol, start_date, end_date)
        except Exception as e:
            logger.warning(f"AKShare K 线降级失败: {e}")
            return pd.DataFrame()


_internal_provider = None

def get_internal_provider() -> InternalProvider:
    global _internal_provider
    if _internal_provider is None:
        _internal_provider = InternalProvider()
    return _internal_provider
```

---

## 四、财联社 Kafka 接入

### 4.1 新增文件

`src/tradingagents/dataflows/news/cls_kafka.py`

与上一版方案相同：后台线程消费 Kafka Topic → 内存缓存 → 供 social_analyst/news_analyst 查询。

Kafka 消息格式需确认，预期字段：

```json
{
    "symbol": "000001.SZ",
    "title": "平安银行发布年报...",
    "content": "详细内容...",
    "sentiment": "positive",
    "source": "财联社",
    "timestamp": "2026-05-20T10:30:00"
}
```

### 4.2 注册路由

在 `interface.py` 中：

- `get_chinese_social_sentiment()` → 优先财联社 Kafka → 降级东方财富
- `get_google_news()` → 优先财联社 Kafka → 降级 Google News

---

## 五、DataSourceManager 注册

文件：`src/tradingagents/dataflows/data_source_manager.py`

### 5.1 修改清单（与上一版相同，此处省略重复代码，仅列要点）

| 位置 | 修改 |
|------|------|
| `ChinaDataSource` 枚举 | 新增 `INTERNAL = "internal"` |
| `DataSourceCode` 常量 | 新增 `INTERNAL = "internal"` |
| `_check_available_sources()` | 新增 InternalProvider 健康检查 |
| `_get_default_source()` | 默认值改为 `internal` |
| `_get_data_source_priority_order()` | 默认顺序: INTERNAL → AKSHARE → TUSHARE → BAOSTOCK |
| `get_stock_data()` | 新增 `INTERNAL` 分支 |
| `get_stock_dataframe()` | 新增 `INTERNAL` 分支 |
| `get_fundamentals_data()` | 新增 `_get_internal_fundamentals()` |
| `get_data_adapter()` | 新增 `_get_internal_adapter()` |
| `_try_fallback_fundamentals()` | 新增 `INTERNAL` 降级分支 |
| `switch_china_data_source()` | 新增 `internal` 映射 |

### 5.2 interface.py 修改清单

| 位置 | 修改 |
|------|------|
| `switch_china_data_source()` :1685 | 新增 `internal` 映射 |
| `get_chinese_social_sentiment()` | 优先财联社 Kafka |
| `get_google_news()` :492 | 优先财联社 Kafka 新闻 |
| `_get_enabled_hk_data_sources()` :55 | 如有港股数据则加入 `internal` |

### 5.3 screen.py 修改清单

`_screen_cn()` :24 → 优先 `InternalProvider.get_market_snapshot()`

---

## 六、新增工具函数（增强能力）

TransMatrix 提供了远超当前系统的数据，可为 Agent 注册新的 `@tool`：

| 新工具 | 数据来源 | 受益 Analyst |
|--------|---------|-------------|
| `get_money_flow` | `stock_money_flow` | market_analyst（资金面） |
| `get_top10_shareholders` | `shareholders_top10` | fundamentals_analyst |
| `get_shareholder_changes` | `shareholder_change` | fundamentals_analyst |
| `get_dividend_info` | `dividend_allocation` | fundamentals_analyst |
| `get_pledge_info` | `pledge_shares` | risk_mgmt（风险） |
| `get_frozen_info` | `frozen_shares` | risk_mgmt（风险） |
| `get_macro_data` | `official_pmi`/`cpi`/`m2_supply` | news_analyst（宏观） |
| `get_index_data` | `index_bar_1day` | market_analyst（基准对比） |

这些增强可在基础接入完成后逐步添加。

---

## 七、环境变量配置

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `TM_DB_URL` | TransMatrix 数据库连接串 | `mssql+pymssql://user:pass@tm-db:1433/TransMatrix` |
| `TM_DB_POOL_SIZE` | 连接池大小 | `5` |
| `DEFAULT_CHINA_DATA_SOURCE` | A 股默认数据源 | `internal` |
| `CLS_KAFKA_BOOTSTRAP` | 财联社 Kafka Broker | `kafka:9092` |
| `CLS_KAFKA_TOPIC` | 财联社 Topic | `cls-sentiment` |
| `CLS_KAFKA_GROUP_ID` | Kafka Group ID | `tradingagents-mcp` |

---

## 八、实施路径

```
Phase 1: TransMatrix DB 接入（1-2 周）
├── 实现 internal_code_mapper.py（代码格式转换）
├── 实现 internal_queries.py（SQL 查询封装）
├── 实现 internal.py（主 Provider）
├── 注册到 DataSourceManager
├── 验证：stock_code / stock_bar_1day / capital / finance_indicator 查询
└── 测试：market_analyst + fundamentals_analyst 全流程

Phase 2: 财联社 Kafka 接入（3-5 天）
├── 实现 cls_kafka.py
├── 确认 Kafka Topic 消息格式
├── 注册到 interface.py 舆情/新闻路由
└── 测试：social_analyst + news_analyst

Phase 3: 增强数据 + 新工具（1 周）
├── 注册资金流向 @tool
├── 注册股东/分红/质押 @tool
├── 注册宏观数据 @tool
├── 替换 screen.py
└── 端到端测试：trading_agent 全流程

Phase 4: 优化（持续）
├── 查询性能优化（缓存热数据）
├── 逐步减少 AKShare 依赖
├── 美股/港股按需扩展（如有数据）
└── 压力测试 + 降级链验证
```

---

## 九、文件修改清单

| 操作 | 文件路径 | 修改内容 |
|------|---------|---------|
| **新增** | `dataflows/providers/china/internal.py` | 主 Provider |
| **新增** | `dataflows/providers/china/internal_queries.py` | SQL 查询封装 |
| **新增** | `dataflows/providers/china/internal_code_mapper.py` | 代码格式转换 |
| **新增** | `dataflows/news/cls_kafka.py` | 财联社 Kafka Consumer |
| 修改 | `constants/` DataSourceCode | 新增 INTERNAL |
| 修改 | `dataflows/data_source_manager.py` | 枚举 + 检查 + 路由 + 降级 |
| 修改 | `dataflows/interface.py` | 切换接口 + 舆情路由 |
| 修改 | `tradingagents_mcp/screen.py` | 筛选函数降级 |
| 修改 | `.opencode.json` | 环境变量配置 |
| **不改** | `agents/` 全部文件 | 通过 interface 间接调用 |
| **不改** | `dataflows/technical/stockstats.py` | 本地计算不受影响 |
| **不改** | `dataflows/providers/china/akshare.py` | 保留作为降级 |


实现总结                                                                                                                                                                               114,329 tokens                       █  
                                                                                                                                                                                            0% used                              █  
     新增文件 (3个)                                                                                                                                                                         $0.00 spent                          █  
                                                                                                                                                                                                                                 █  
     1.  src/tradingagents/dataflows/providers/china/internal_code_mapper.py - 代码格式转换 (000001 ↔ 000001.SZ)，支持沪/深/京三板                                                          ▼ MCP                                █  
                                                                                                                                                                                            • test-mcp-server Connected          ▀  
     2.  src/tradingagents/dataflows/providers/china/internal_queries.py - SQL 查询封装层，通过 transwarp.timelyre.timelyre_public.DatabaseConn 连接 TransMatrix 内部数据库，提供:          • tradingagents Connected               
         - query() - 通用 SQL 查询 (使用 query_as_df)                                                                                                                                       • vibe_trading Connected                
         - health_check() - 健康检查 (使用 query_raw_data)                                                                                                                                                                          
         - 16 个数据查询函数：股票信息、日K/分钟K线、实时快照、估值、财务指标、三大表、资金流向、股东、分红、指数、市场快照、宏观数据 
     3.  src/tradingagents/dataflows/providers/china/internal.py - InternalProvider 主类，提供:                                                                                             Context                              █  
         - get_stock_data() / get_stock_info() / get_stock_quotes() / get_fundamentals() / get_money_flow() / get_market_snapshot()                                                         114,329 tokens                       █  
         - K线数据自动降级到 AKShare                                                                                                                                                        0% used                              █  
         - _standardize_kline() 字段映射 (trade_day→date, volume→vol, turnover→amount)                                                                                                      $0.00 spent                          █  
                                                                                                                                                                                                                                 █  
     修改文件 (5个)                                                                                                                                                                         ▼ MCP                                █  
                                                                                                                                                                                            • test-mcp-server Connected          ▀  
     4.  src/tradingagents/constants/data_sources.py - 添加 INTERNAL = "internal" 枚举值和注册表条目                                                                                        • tradingagents Connected               
                                                                                                                                                                                            • vibe_trading Connected                
     5.  src/tradingagents/dataflows/data_source_manager.py - 全面注册 INTERNAL 数据源:                                                                                                                                             
         - ChinaDataSource 枚举新增 INTERNAL                                                                                                                                                LSP                                     
         - _check_available_sources() - 添加 TransMatrix 健康检查
         - _get_default_source() - 默认数据源改为 internal                                                                                                                                  Context                              █  
         - _get_data_source_priority_order() - 默认顺序: INTERNAL → AKSHARE → TUSHARE → BAOSTOCK                                                                                            114,329 tokens                       █  
         - get_data_adapter() / get_stock_data() / get_stock_dataframe() / get_fundamentals_data() - 添加 INTERNAL 分支                                                                     0% used                              █  
         - 新增 _get_internal_data() / _get_internal_fundamentals() / _get_internal_adapter() 方法                                                                                          $0.00 spent                          █  
         - _try_fallback_sources() / _try_fallback_fundamentals() - 添加 INTERNAL 降级分支                                                                                                                                       █  
                                                                                                                                                                                            ▼ MCP                                █  
     6.  src/tradingagents/dataflows/interface.py - switch_china_data_source() 支持 internal                                                                                                • test-mcp-server Connected          ▀  
                                                                                                                                                                                            • tradingagents Connected               
     7.  .opencode.json - 添加 TransMatrix 环境变量配置                                                                                                                                     • vibe_trading Connected                
                                                                                                                                                                                                                                    
     8.  AGENTS.md - 更新项目结构、环境变量、数据源支持文档
