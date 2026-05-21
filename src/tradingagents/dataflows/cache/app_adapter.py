#!/usr/bin/env python3
"""
App 缓存读取适配器（TradingAgents -> 文件缓存）
已移除 MongoDB 依赖，所有缓存走文件。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd
import logging

_logger = logging.getLogger('dataflows')


def get_basics_from_cache(stock_code: Optional[str] = None) -> Optional[Dict[str, Any] | List[Dict[str, Any]]]:
    """从文件缓存读取基础信息（兼容接口，当前返回 None）。"""
    return None


def get_market_quote_dataframe(symbol: str) -> Optional[pd.DataFrame]:
    """从文件缓存读取行情快照（兼容接口，当前返回 None）。"""
    return None
