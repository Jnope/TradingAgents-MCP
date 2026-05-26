import os
import re
from datetime import datetime, timedelta
from typing import Optional, Tuple

import pandas as pd


_CN_STOCK_NAME_MAP = {
    "茅台": "600519", "贵州茅台": "600519",
    "平安银行": "000001",
    "招商银行": "600036",
    "五粮液": "000858",
    "宁德时代": "300750",
    "比亚迪": "002594",
    "工商银行": "601398",
    "中国平安": "601318",
    "美的集团": "000333",
    "格力电器": "000651",
    "中信证券": "600030",
    "海康威视": "002415",
    "隆基绿能": "601012",
    "中国中免": "601888",
    "药明康德": "603259",
    "紫金矿业": "601899",
    "长江电力": "600900",
    "中国移动": "600941",
    "中国石油": "601857",
    "中国神华": "601088",
    "腾讯": "00700.HK", "腾讯控股": "00700.HK",
    "阿里": "09988.HK", "阿里巴巴": "09988.HK",
    "美团": "03690.HK",
    "小米": "01810.HK",
    "苹果": "AAPL",
    "英伟达": "NVDA",
    "特斯拉": "TSLA",
    "微软": "MSFT",
    "亚马逊": "AMZN",
    "谷歌": "GOOGL",
}

_CN_INDEX_MAP = {
    "沪深300": "000300", "沪深300指数": "000300",
    "上证50": "000016",
    "中证500": "000905",
    "创业板指": "399006",
    "上证指数": "000001",
    "深证成指": "399001",
    "科创50": "000688",
}


def resolve_stock_name(name: str) -> Optional[str]:
    if not name:
        return None
    return _CN_STOCK_NAME_MAP.get(name) or _CN_INDEX_MAP.get(name)


def validate_symbol(symbol: str) -> Tuple[str, str]:
    if not symbol or not symbol.strip():
        raise ValueError("股票代码不能为空")

    symbol = symbol.strip()

    resolved = resolve_stock_name(symbol)
    if resolved:
        symbol = resolved

    symbol_upper = symbol.upper()

    if re.match(r'^\d{6}$', symbol):
        market = "A股"
    elif re.match(r'^\d{4,5}\.HK$', symbol_upper):
        market = "港股"
        symbol = symbol_upper
    elif re.match(r'^[A-Z]{1,5}$', symbol_upper):
        market = "美股"
        symbol = symbol_upper
    elif re.match(r'^\d{4,5}$', symbol):
        market = "港股"
        symbol = f"{symbol}.HK"
    else:
        raise ValueError(
            f"无法识别股票代码 '{symbol}'。"
            "A股请用6位数字(如000001)，港股请用数字.HK(如00700.HK)，美股请用字母(如AAPL)"
        )

    return symbol, market


def normalize_date(date_str: str) -> str:
    if not date_str:
        return datetime.now().strftime("%Y-%m-%d")

    date_str = date_str.strip()

    aliases = {
        "今天": datetime.now(),
        "昨天": _prev_trading_day(1),
        "前天": _prev_trading_day(2),
    }
    if date_str in aliases:
        return aliases[date_str].strftime("%Y-%m-%d")

    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%Y-%m-%d")
    except ValueError:
        pass

    raise ValueError(f"日期格式无效 '{date_str}'，请使用 YYYY-MM-DD 格式")


def resolve_date_range(description: str) -> Tuple[str, str]:
    now = datetime.now()
    today = now.strftime("%Y-%m-%d")

    if not description:
        return today, today

    desc = description.strip()

    mappings = {
        "今天": (0,), "今日": (0,),
        "最近一周": (7,), "近一周": (7,), "近1周": (7,),
        "最近两周": (14,), "近两周": (14,),
        "最近一个月": (30,), "近一个月": (30,), "近1个月": (30,), "近一月": (30,),
        "最近三个月": (90,), "近三个月": (90,), "近3个月": (90,),
        "最近半年": (180,), "近半年": (180,), "这半年": (180,),
        "最近一年": (365,), "近一年": (365,), "今年": (None,),
    }

    if desc in mappings:
        days = mappings[desc]
        if days[0] is None:
            start = datetime(now.year, 1, 1).strftime("%Y-%m-%d")
        else:
            start = (now - timedelta(days=days[0])).strftime("%Y-%m-%d")
        return start, today

    if re.match(r'^\d{4}-\d{2}-\d{2}\s*[~至到]\s*\d{4}-\d{2}-\d{2}$', desc):
        parts = re.split(r'\s*[~至到]\s*', desc)
        return parts[0].strip(), parts[1].strip()

    return today, today


def nearest_trade_date(date_str: str) -> str:
    from tradingagents_mcp.trade_calendar import get_trade_dates, _llm_judge_trade_date

    try:
        dt = pd.Timestamp(date_str)
    except Exception:
        return date_str

    trade_dates = get_trade_dates()

    if trade_dates:
        for _ in range(30):
            ds = dt.strftime("%Y-%m-%d")
            if ds in trade_dates:
                return ds
            dt = dt - pd.Timedelta(days=1)
        return date_str

    return _llm_judge_trade_date(date_str)


def build_config() -> dict:
    from tradingagents.default_config import DEFAULT_CONFIG

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
        "MCP_QUICK_PROVIDER": ("quick_provider", str),
        "MCP_DEEP_PROVIDER": ("deep_provider", str),
        "MCP_QUICK_BACKEND_URL": ("quick_backend_url", str),
        "MCP_DEEP_BACKEND_URL": ("deep_backend_url", str),
        "MCP_QUICK_API_KEY": ("quick_api_key", str),
        "MCP_DEEP_API_KEY": ("deep_api_key", str),
        "MCP_PARALLEL_ANALYSTS": ("parallel_analysts", lambda v: v.lower() == "true"),
    }
    for env_key, (config_key, type_fn) in env_map.items():
        val = os.getenv(env_key)
        if val is not None:
            config[config_key] = type_fn(val)

    model_param_map = {
        "MCP_DEEP_MAX_TOKENS": ("deep_model_config", "max_tokens", int),
        "MCP_QUICK_MAX_TOKENS": ("quick_model_config", "max_tokens", int),
        "MCP_DEEP_TEMPERATURE": ("deep_model_config", "temperature", float),
        "MCP_QUICK_TEMPERATURE": ("quick_model_config", "temperature", float),
        "MCP_DEEP_TIMEOUT": ("deep_model_config", "timeout", int),
        "MCP_QUICK_TIMEOUT": ("quick_model_config", "timeout", int),
    }
    for env_key, (config_key, param_key, type_fn) in model_param_map.items():
        val = os.getenv(env_key)
        if val is not None:
            config.setdefault(config_key, {})[param_key] = type_fn(val)

    provider_key_fallback = {
        "openai": ("OPENAI_API_KEY", "openai_api_key"),
        "dashscope": ("DASHSCOPE_API_KEY", "dashscope_api_key"),
        "alibaba": ("DASHSCOPE_API_KEY", "dashscope_api_key"),
        "google": ("GOOGLE_API_KEY", "google_api_key"),
        "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
        "deepseek": ("DEEPSEEK_API_KEY", "deepseek_api_key"),
        "siliconflow": ("SILICONFLOW_API_KEY", "siliconflow_api_key"),
        "openrouter": ("OPENROUTER_API_KEY", "openrouter_api_key"),
        "ollama": (None, None),
        "zhipu": ("ZHIPU_API_KEY", "zhipu_api_key"),
        "qianfan": ("QIANFAN_API_KEY", "qianfan_api_key"),
        "custom_openai": ("CUSTOM_OPENAI_API_KEY", "custom_openai_api_key"),
    }
    provider = config.get("llm_provider", "").lower()
    fallback = provider_key_fallback.get(provider)
    if fallback and fallback[0]:
        env_var, _ = fallback
        quick_key = config.get("quick_api_key")
        deep_key = config.get("deep_api_key")
        if not quick_key and not deep_key:
            env_val = os.getenv(env_var)
            if env_val:
                config.setdefault("quick_api_key", env_val)
                config.setdefault("deep_api_key", env_val)

    return config


def check_health() -> dict:
    config = build_config()
    health = {"mcp_server": "ok"}

    llm_provider = config.get("llm_provider", "").lower()
    key_map = {
        "openai": "OPENAI_API_KEY",
        "dashscope": "DASHSCOPE_API_KEY",
        "alibaba": "DASHSCOPE_API_KEY",
        "google": "GOOGLE_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "deepseek": "DEEPSEEK_API_KEY",
        "siliconflow": "SILICONFLOW_API_KEY",
        "openrouter": "OPENROUTER_API_KEY",
        "zhipu": "ZHIPU_API_KEY",
        "qianfan": "QIANFAN_API_KEY",
        "custom_openai": "CUSTOM_OPENAI_API_KEY",
    }
    has_config_key = bool(config.get("quick_api_key") or config.get("deep_api_key"))
    expected_key = key_map.get(llm_provider)
    if has_config_key:
        expected_key = None
    if expected_key and not os.getenv(expected_key):
        health["llm_api_key"] = f"missing: {expected_key}"
    else:
        health["llm_api_key"] = "ok"

    for pkg in ["akshare", "yfinance", "tushare", "baostock"]:
        try:
            __import__(pkg)
            health[pkg] = "ok"
        except ImportError:
            health[pkg] = "not_installed"

    return health


def _prev_trading_day(n: int = 1) -> datetime:
    from tradingagents_mcp.trade_calendar import get_trade_dates

    trade_dates = get_trade_dates()
    dt = datetime.now()

    if trade_dates:
        count = 0
        while count < n:
            dt = dt - timedelta(days=1)
            if dt.strftime("%Y-%m-%d") in trade_dates:
                count += 1
        return dt

    count = 0
    while count < n:
        dt = dt - timedelta(days=1)
        if dt.weekday() < 5:
            count += 1
    return dt


def extract_reports(state: dict) -> dict:
    reports = {}
    for key in ["market_report", "fundamentals_report", "sentiment_report", "news_report"]:
        val = state.get(key, "")
        if isinstance(val, str) and len(val) > 2000:
            reports[key] = val
        else:
            reports[key] = val
    return reports


def calc_period_stats(data) -> dict:
    if not data or len(data) < 2:
        return {"total_return": None, "max_drawdown": None, "volatility": None}

    closes = []
    for row in data:
        c = row.get("close") or row.get("Close")
        if c is not None:
            try:
                closes.append(float(c))
            except (ValueError, TypeError):
                continue

    if len(closes) < 2:
        return {"total_return": None, "max_drawdown": None, "volatility": None}

    total_return = round((closes[-1] / closes[0] - 1) * 100, 2)

    peak = closes[0]
    max_dd = 0.0
    for c in closes:
        if c > peak:
            peak = c
        dd = (c / peak - 1) * 100
        if dd < max_dd:
            max_dd = dd
    max_drawdown = round(max_dd, 2)

    import statistics
    daily_returns = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
    if len(daily_returns) >= 2:
        vol = round(statistics.stdev(daily_returns) * (252 ** 0.5) * 100, 2)
    else:
        vol = None

    return {"total_return": total_return, "max_drawdown": max_drawdown, "volatility": vol}


def extract_data_points(data, metrics: list, max_points: int = 60) -> list:
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

    if len(rows) > max_points:
        step = len(rows) / max_points
        return [rows[int(i * step)] for i in range(max_points)]
    return rows
