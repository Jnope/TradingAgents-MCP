"""
轻量级分析师运行器（已委托给 SharedContext）

保留此文件以兼容外部引用（如 from tradingagents_mcp.analyst_runner import get_runner）。
实际逻辑已迁移到 shared_context.py，get_runner() 返回 SharedContext 的适配视图。
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class _AnalystRunnerAdapter:
    """AnalystRunner 兼容适配器，属性委托到 SharedContext"""

    def __init__(self, shared_ctx):
        self._shared_ctx = shared_ctx

    @property
    def config(self):
        return self._shared_ctx.config

    @property
    def quick_thinking_llm(self):
        return self._shared_ctx.quick_thinking_llm

    @property
    def toolkit(self):
        return self._shared_ctx.toolkit


_adapter_cache: Optional[_AnalystRunnerAdapter] = None


def get_runner(config: dict = None) -> _AnalystRunnerAdapter:
    """获取 AnalystRunner 兼容实例

    委托给 SharedContext，确保全局只有一个 LLM + Toolkit 实例。
    """
    global _adapter_cache
    if _adapter_cache is None:
        from tradingagents_mcp.shared_context import get_shared_ctx
        _adapter_cache = _AnalystRunnerAdapter(get_shared_ctx())
    return _adapter_cache


def invalidate_runner():
    global _adapter_cache
    _adapter_cache = None
