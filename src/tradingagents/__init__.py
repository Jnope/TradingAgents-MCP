#!/usr/bin/env python3
"""
TradingAgents-CN 核心模块

这是一个基于多智能体的股票分析系统，支持A股、港股和美股的综合分析。
"""

__version__ = "1.0.0-preview"
__author__ = "TradingAgents-CN Team"
__description__ = "Multi-agent stock analysis system for Chinese markets"

# 导入核心模块
try:
    from .utils import logging_manager
except ImportError:
    pass

__all__ = [
    "__version__",
    "__author__", 
    "__description__"
]