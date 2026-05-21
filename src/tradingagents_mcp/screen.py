import logging
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger("mcp_server.screen")


def screen_stocks_online(
    conditions: List[Dict[str, Any]],
    market: str,
    order_by: Optional[List[Dict[str, str]]],
    limit: int,
) -> List[Dict[str, Any]]:
    if market == "CN":
        return _screen_cn(conditions, order_by, limit)
    elif market == "HK":
        return _screen_hk(conditions, order_by, limit)
    elif market == "US":
        return _screen_us(conditions, order_by, limit)
    return []


def _screen_cn(
    conditions: List[Dict[str, Any]],
    order_by: Optional[List[Dict[str, str]]],
    limit: int,
) -> List[Dict[str, Any]]:
    try:
        import akshare as ak
    except ImportError:
        logger.warning("AKShare 不可用，无法筛选A股")
        return []

    try:
        df = ak.stock_zh_a_spot_em()
    except Exception as e:
        logger.error(f"AKShare 获取A股数据失败: {e}")
        return []

    col_map = {
        "代码": "code",
        "名称": "name",
        "最新价": "close",
        "涨跌幅": "pct_chg",
        "市盈率-动态": "pe",
        "市净率": "pb",
        "总市值": "total_mv",
        "流通市值": "circ_mv",
        "成交额": "amount",
        "换手率": "turnover_rate",
        "量比": "volume_ratio",
        "60日中文名称": "industry",
    }
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})

    for mv_col in ["total_mv", "circ_mv"]:
        if mv_col in df.columns:
            try:
                df[mv_col] = pd.to_numeric(df[mv_col], errors="coerce") / 1e8
            except Exception:
                pass

    for col in df.columns:
        if col not in ("code", "name", "industry"):
            try:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            except Exception:
                pass

    df = _apply_conditions(df, conditions)

    if order_by:
        for order in reversed(order_by):
            sort_field = order.get("field")
            ascending = order.get("direction", "desc").lower() != "desc"
            if sort_field in df.columns:
                df = df.sort_values(by=sort_field, ascending=ascending, na_position="last")

    result_cols = [
        "code", "name", "industry", "close", "pct_chg", "pe", "pb",
        "total_mv", "circ_mv", "turnover_rate", "volume_ratio", "amount",
    ]
    available_cols = [c for c in result_cols if c in df.columns]
    df = df[available_cols].head(limit)

    items = df.to_dict(orient="records")
    for item in items:
        for k, v in item.items():
            if pd.isna(v):
                item[k] = None
            elif hasattr(v, "item"):
                item[k] = v.item()
    return items


def _screen_hk(
    conditions: List[Dict[str, Any]],
    order_by: Optional[List[Dict[str, str]]],
    limit: int,
) -> List[Dict[str, Any]]:
    try:
        import akshare as ak
    except ImportError:
        return []

    try:
        df = ak.stock_hk_spot_em()
        col_map = {
            "代码": "code", "名称": "name", "最新价": "close",
            "涨跌幅": "pct_chg", "成交额": "amount",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        df = _apply_conditions(df, conditions)

        result_cols = [c for c in ["code", "name", "close", "pct_chg", "amount"] if c in df.columns]
        df = df[result_cols].head(limit)
        items = df.to_dict(orient="records")
        for item in items:
            for k, v in item.items():
                if pd.isna(v):
                    item[k] = None
                elif hasattr(v, "item"):
                    item[k] = v.item()
        return items
    except Exception as e:
        logger.error(f"港股筛选失败: {e}")
        return []


def _screen_us(
    conditions: List[Dict[str, Any]],
    order_by: Optional[List[Dict[str, str]]],
    limit: int,
) -> List[Dict[str, Any]]:
    logger.warning("美股在线筛选能力有限，建议使用具体股票代码分析")
    return []


def _apply_conditions(df: pd.DataFrame, conditions: List[Dict[str, Any]]) -> pd.DataFrame:
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
        elif operator in ("==", "eq"):
            df = df[df[field] == value]
        elif operator == "!=":
            df = df[df[field] != value]
        elif operator == "between" and isinstance(value, list) and len(value) == 2:
            df = df[(df[field] >= value[0]) & (df[field] <= value[1])]
        elif operator == "in" and isinstance(value, list):
            df = df[df[field].astype(str).isin([str(v) for v in value])]
        elif operator == "not_in" and isinstance(value, list):
            df = df[~df[field].astype(str).isin([str(v) for v in value])]
        elif operator == "contains":
            df = df[df[field].astype(str).str.contains(str(value), na=False)]

    return df


def format_screening_items(items: List[Dict[str, Any]], max_items: int = 30) -> str:
    lines = []
    for i, item in enumerate(items[:max_items]):
        code = item.get("code", "")
        name = item.get("name", "")
        pe = item.get("pe")
        pb = item.get("pb")
        pct = item.get("pct_chg")
        industry = item.get("industry", "")
        parts = [f"{i + 1}. {code} {name}"]
        if industry:
            parts.append(f"行业:{industry}")
        if pe is not None:
            parts.append(f"PE:{pe}")
        if pb is not None:
            parts.append(f"PB:{pb}")
        if pct is not None:
            parts.append(f"涨跌:{pct}%")
        lines.append(" | ".join(parts))
    return "\n".join(lines)
