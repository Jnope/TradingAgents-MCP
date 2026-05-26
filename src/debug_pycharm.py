"""
PyCharm 断点调试脚本

用法: 直接在 PyCharm 中右键 Run/Debug，在任意行设断点即可
环境变量在下方 os.environ.setdefault 中修改
"""

import os

os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.setdefault('NO_PROXY', "*")
os.environ.setdefault("MCP_LLM_PROVIDER", "openai")
os.environ.setdefault("MCP_BACKEND_URL", "https://llmops.transwarp.io/vibecoding/v1")
os.environ.setdefault("MCP_DEEP_THINK_LLM", "xclaw/glm-5.1")
os.environ.setdefault("MCP_QUICK_THINK_LLM", "xclaw/glm-5.1")
os.environ.setdefault("MCP_DEEP_API_KEY", "llmops-zhenjiang-368c5e8878cf7b0f55b02401fab49aec")  # TODO: 填入 API Key
os.environ.setdefault("MCP_LOG_LEVEL", "INFO")

import logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

# ============================================================
# 第1步: 构建配置和工具包
# ============================================================
from tradingagents_mcp.validators import build_config
from tradingagents.dataflows.interface import set_config
from tradingagents.agents.utils.agent_utils import Toolkit

config = build_config()
set_config(config)
toolkit = Toolkit(config=config)

# ============================================================
# 第2步: 测试数据获取（不依赖LLM，断点在此区域）
# ============================================================
symbol = "688031"
trade_date = "2025-05-20"

"""
# 2a. 行情数据
market_data = toolkit.get_stock_market_data_unified.invoke({
    "ticker": symbol,
    "start_date": trade_date,
    "end_date": trade_date,
})
print(f"行情数据条数: {len(market_data) if market_data else 0}")
# 👆 在此行设断点，检查 market_data 内容

# 2b. 基本面数据
fundamentals_data = toolkit.get_stock_fundamentals_unified.invoke({"ticker": symbol})
print(f"基本面数据长度: {len(str(fundamentals_data)) if fundamentals_data else 0}")
# 👆 在此行设断点，检查 fundamentals_data 内容

# 2c. 股票信息
from tradingagents.dataflows.interface import get_china_stock_info_unified
stock_info = get_china_stock_info_unified(symbol)
print(f"股票信息: {stock_info[:200] if stock_info else '无'}")
"""

# ============================================================
# 第3步: 测试单分析师（需要LLM）
# ============================================================
from tradingagents_mcp.shared_context import get_shared_ctx
from tradingagents.agents import create_market_analyst
from langchain_core.messages import HumanMessage

ctx = get_shared_ctx()
"""
node = create_market_analyst(ctx.quick_thinking_llm, ctx.toolkit)

state = {
    "messages": [HumanMessage(content=f"请分析股票 {symbol}")],
    "company_of_interest": symbol,
    "trade_date": trade_date,
    "market_tool_call_count": 0,
}

result = node(state)
# 👆 在此行设断点，检查 result["market_report"]

report = result.get("market_report", "")
print(f"市场分析报告长度: {len(report)}")
print(report[:500])
"""

# ============================================================
# 第4步: 测试完整全流程（耗时3-10分钟）
# ============================================================
# 取消下方注释即可运行
# "social", "news",
ta = ctx.get_graph(["market", "fundamentals"])
final_state, decision = ta.propagate(symbol, trade_date)
# 👆 在此行设断点，检查 decision 和 final_state
print(f"state: {final_state}\n决策: {decision}")
