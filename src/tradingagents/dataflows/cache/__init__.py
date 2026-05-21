"""
缓存管理模块

支持文件缓存策略：
- 文件缓存（默认且唯一）- 简单稳定，不依赖外部服务

使用方法：
    from tradingagents.dataflows.cache import get_cache
    cache = get_cache()
"""

from typing import Union

from tradingagents.utils.logging_manager import get_logger
logger = get_logger('agents')

from .file_cache import StockDataCache
from .app_adapter import get_basics_from_cache, get_market_quote_dataframe

_cache_instance = None


def get_cache() -> StockDataCache:
    if _cache_instance is None:
        _cache_instance = StockDataCache()
        logger.info("✅ 使用文件缓存系统")
    return _cache_instance


__all__ = [
    'get_cache',
    'StockDataCache',
    'get_basics_from_cache',
    'get_market_quote_dataframe',
]
