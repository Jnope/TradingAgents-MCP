"""
Trade Calendar - 交易日历查询与缓存

优先级：本地缓存文件 → 内部数据库查询 → AKShare在线查询 → LLM智能判断
"""

import json
import logging
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Set

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(os.path.expanduser("~/.tradingagents"))
_CACHE_FILE = _CACHE_DIR / "trade_calendar_cache.json"


def _load_cache() -> Optional[dict]:
    try:
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"读取交易日历缓存失败: {e}")
    return None


def _save_cache(data: dict):
    try:
        _CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(_CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning(f"保存交易日历缓存失败: {e}")


def _is_cache_fresh(cache: dict) -> bool:
    if not cache or "date_range" not in cache or "trade_dates" not in cache:
        return False
    today = datetime.now().strftime("%Y-%m-%d")
    date_range = cache["date_range"]
    if len(date_range) < 2:
        return False
    return date_range[0] <= today <= date_range[1]


def _query_trade_calendar_db() -> Optional[dict]:
    try:
        from tradingagents.dataflows.providers.china.internal_queries import query

        today = datetime.now()
        start = (today - timedelta(days=365)).strftime("%Y-%m-%d")
        end = (today + timedelta(days=365)).strftime("%Y-%m-%d")

        sql = (
            f"SELECT `trade_date`, `is_open` FROM `trade_calendar` "
            f"WHERE `trade_date` >= '{start} 00:00:00' "
            f"AND `trade_date` < '{end} 00:00:00' "
            f"AND `exchange` = 'SSE'"
        )
        df = query(sql, table='trade_calendar')

        if df is None or df.empty:
            return None

        trade_dates = []
        for _, row in df.iterrows():
            date_str = str(row["trade_date"]).split(" ")[0]
            try:
                is_open = float(row["is_open"])
            except (ValueError, TypeError):
                continue
            if is_open == 1.0:
                trade_dates.append(date_str)

        trade_dates = sorted(set(trade_dates))

        if not trade_dates:
            return None

        return {
            "last_updated": today.strftime("%Y-%m-%d %H:%M:%S"),
            "date_range": [start, end],
            "trade_dates": trade_dates,
        }
    except Exception as e:
        logger.warning(f"数据库查询交易日历失败: {e}")
        return None


def _llm_judge_trade_date(date_str: str) -> str:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_openai import ChatOpenAI

        from tradingagents_mcp.validators import build_config

        config = build_config()
        model = config.get("quick_think_llm", "gpt-4o-mini")
        backend_url = config.get("backend_url", "https://api.openai.com/v1")

        provider = config.get("llm_provider", "openai")
        key_map = {
            "openai": "OPENAI_API_KEY",
            "dashscope": "DASHSCOPE_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "google": "GOOGLE_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
        }
        api_key = os.getenv(key_map.get(provider, "OPENAI_API_KEY"))

        if not api_key:
            raise ValueError(f"LLM API Key 未设置")

        llm = ChatOpenAI(
            model=model,
            base_url=backend_url,
            api_key=api_key,
            temperature=0,
            max_tokens=50,
            timeout=15,
        )

        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        weekday = weekday_names[dt.weekday()]

        prompt = (
            f"请判断 {date_str}（{weekday}）是否为中国A股交易日。"
            f"如果不是，请给出该日之前最近的一个交易日，格式为 YYYY-MM-DD。"
            f"只回答一个日期，不要解释。"
        )

        response = llm.invoke([
            SystemMessage(content="你是一个中国A股交易日历专家。"),
            HumanMessage(content=prompt),
        ])

        answer = response.content.strip()
        match = re.search(r'\d{4}-\d{2}-\d{2}', answer)
        if match:
            return match.group(0)

        logger.warning(f"LLM返回格式无法解析: {answer}")
        return date_str
    except Exception as e:
        logger.warning(f"LLM判断交易日失败: {e}")
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        while dt.weekday() >= 5:
            dt -= timedelta(days=1)
        return dt.strftime("%Y-%m-%d")


_module_cache: Optional[Set[str]] = None


def get_trade_dates() -> Set[str]:
    global _module_cache

    if _module_cache is not None:
        return _module_cache

    file_cache = _load_cache()
    if file_cache and _is_cache_fresh(file_cache):
        logger.debug("使用本地缓存的交易日历")
        _module_cache = set(file_cache["trade_dates"])
        return _module_cache

    db_data = _query_trade_calendar_db()
    if db_data:
        _save_cache(db_data)
        _module_cache = set(db_data["trade_dates"])
        return _module_cache

    logger.warning("交易日历数据源不可用，将使用LLM逐次判断")
    return set()


def invalidate_cache():
    global _module_cache
    _module_cache = None
