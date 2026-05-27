import traceback

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, ToolMessage

from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.utils.logging_init import get_logger
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("default")

_COMPANY_NAME_CACHE = {}


def _get_tool_name(tool) -> str:
    if hasattr(tool, 'name'):
        return tool.name
    if hasattr(tool, '__name__'):
        return tool.__name__
    return str(tool)


def _get_company_name(ticker: str, market_info: dict) -> str:
    cache_key = f"{ticker}:{market_info['market']}"
    if cache_key in _COMPANY_NAME_CACHE:
        return _COMPANY_NAME_CACHE[cache_key]

    try:
        name = _fetch_company_name(ticker, market_info)
    except Exception as e:
        logger.warning(f"获取公司名称失败: {e}")
        name = f"股票{ticker}"

    _COMPANY_NAME_CACHE[cache_key] = name
    return name


def _fetch_company_name(ticker: str, market_info: dict) -> str:
    if market_info['is_china']:
        from tradingagents.dataflows.interface import get_china_stock_info_unified
        stock_info = get_china_stock_info_unified(ticker)
        if stock_info and "股票名称:" in stock_info:
            return stock_info.split("股票名称:")[1].split("\n")[0].strip()
        logger.warning(f"无法从统一接口解析股票名称: {ticker}")
        try:
            from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
            info_dict = get_info_dict(ticker)
            if info_dict and info_dict.get('name'):
                return info_dict['name']
        except Exception as e:
            logger.warning(f"降级获取股票名称也失败: {e}")
        return f"股票代码{ticker}"

    elif market_info['is_hk']:
        try:
            from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
            return get_hk_company_name_improved(ticker)
        except Exception:
            return f"港股{ticker.replace('.HK', '').replace('.hk', '')}"

    elif market_info['is_us']:
        try:
            import yfinance as yf
            tk = yf.Ticker(ticker)
            info = tk.info
            if info and info.get('shortName'):
                return info['shortName']
        except Exception:
            pass
        us_stock_names = {
            'AAPL': '苹果公司', 'TSLA': '特斯拉', 'NVDA': '英伟达',
            'MSFT': '微软', 'GOOGL': '谷歌', 'AMZN': '亚马逊',
            'META': 'Meta', 'NFLX': '奈飞',
        }
        return us_stock_names.get(ticker.upper(), f"美股{ticker}")

    return f"股票{ticker}"


_SYSTEM_PROMPT = (
    "你是一位专业的股票技术分析师。\n"
    "\n"
    "分析对象：{company_name}（{ticker}），{market_name}，{currency_name}（{currency_symbol}），日期：{current_date}\n"
    "\n"
    "工具：{tool_names}\n"
    "工作流程：\n"
    "1. 如消息历史中无工具结果，立即调用 get_stock_market_data_unified（ticker: {ticker}, start_date: {current_date}, end_date: {current_date}）\n"
    "2. 获得工具数据后，立即生成分析报告，不要再调用工具\n"
    "\n"
    "输出格式（必须遵守）：\n"
    "## 基本信息\n"
    "- 公司名称/代码/市场/当前价格/涨跌幅/成交量\n"
    "\n"
    "## 技术指标分析\n"
    "- MA均线系统（MA5/10/20/60）：数值、排列、交叉信号\n"
    "- MACD：DIF/DEA/柱状图、金叉死叉、背离\n"
    "- RSI：数值、超买超卖、背离\n"
    "- 布林带：上中下轨、位置、带宽\n"
    "\n"
    "## 价格趋势分析\n"
    "- 短期（5-10日）/ 中期（20-60日）趋势\n"
    "- 成交量与量价配合\n"
    "\n"
    "## 投资建议\n"
    "- 评级：买入/持有/卖出\n"
    "- 目标价/止损位（{currency_symbol}）\n"
    "- 支撑位/压力位\n"
    "\n"
    "价格使用{currency_name}（{currency_symbol}），中文输出，基于真实数据分析，不少于800字。"
)

_ANALYSIS_PROMPT = (
    "基于上述工具数据，生成完整技术分析报告。\n"
    "对象：{company_name}（{ticker}），{market_name}，{currency_name}（{currency_symbol}）\n"
    "格式：基本信息 → 技术指标（MA/MACD/RSI/BOLL）→ 价格趋势 → 投资建议\n"
    "价格用{currency_symbol}，中文，不少于800字，不要使用emoji。"
)


def create_market_analyst(llm, toolkit, progress_callback=None):

    def market_analyst_node(state):
        logger.debug("市场分析师节点开始")

        tool_call_count = state.get("market_tool_call_count", 0)
        max_tool_calls = 3

        if tool_call_count >= max_tool_calls:
            logger.warning(f"工具调用次数已达上限 {tool_call_count}/{max_tool_calls}，跳过工具调用")
            report = state.get("market_report", "市场分析因工具调用次数超限而中止")
            return {
                "messages": [],
                "market_report": report,
                "market_tool_call_count": tool_call_count,
            }

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        if progress_callback:
            progress_callback("正在获取行情数据...")

        from tradingagents.utils.stock_utils import StockUtils
        market_info = StockUtils.get_market_info(ticker)
        company_name = _get_company_name(ticker, market_info)

        tools = [toolkit.get_stock_market_data_unified]
        tool_names = ", ".join(_get_tool_name(t) for t in tools)

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", _SYSTEM_PROMPT),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(
            tool_names=tool_names, current_date=current_date, ticker=ticker,
            company_name=company_name, market_name=market_info['market_name'],
            currency_name=market_info['currency_name'], currency_symbol=market_info['currency_symbol'],
        )

        logger.info(f"市场分析师: {company_name}({ticker}) @ {current_date}, LLM={llm.__class__.__name__}")

        chain = prompt | llm.bind_tools(tools)
        result = chain.invoke({"messages": state["messages"]})

        if GoogleToolCallHandler.is_google_model(llm):
            if progress_callback:
                progress_callback("行情数据已获取，正在生成技术分析报告...")
            analysis_prompt_template = GoogleToolCallHandler.create_analysis_prompt(
                ticker=ticker, company_name=company_name,
                analyst_type="市场分析",
                specific_requirements="重点关注市场数据、价格走势、交易量变化等市场指标。",
            )
            report, messages = GoogleToolCallHandler.handle_google_tool_calls(
                result=result, llm=llm, tools=tools, state=state,
                analysis_prompt_template=analysis_prompt_template,
                analyst_name="市场分析师",
            )
            return {
                "messages": [result],
                "market_report": report,
                "market_tool_call_count": tool_call_count + 1,
            }

        tool_calls = getattr(result, 'tool_calls', None)

        if not tool_calls:
            report = result.content or ""
            logger.info(f"市场分析师直接回复，长度: {len(report)}")
            return {
                "messages": [result],
                "market_report": report,
                "market_tool_call_count": tool_call_count + 1,
            }

        logger.info(f"市场分析师工具调用: {[_get_tool_name(t) for t in tools]}")

        try:
            tool_messages = _execute_tool_calls(tool_calls, tools)
            if progress_callback:
                progress_callback("行情数据已获取，正在生成技术分析报告...")
            analysis_text = _ANALYSIS_PROMPT.format(
                company_name=company_name, ticker=ticker,
                market_name=market_info['market_name'],
                currency_name=market_info['currency_name'],
                currency_symbol=market_info['currency_symbol'],
            )
            messages = state["messages"] + [result] + tool_messages + [HumanMessage(content=analysis_text)]
            final_result = llm.invoke(messages)
            report = final_result.content

            logger.info(f"市场分析师生成报告，长度: {len(report)}")
            return {
                "messages": [result] + tool_messages + [final_result],
                "market_report": report,
                "market_tool_call_count": tool_call_count + 1,
            }

        except Exception as e:
            logger.error(f"市场分析师工具执行失败: {e}", exc_info=True)
            report = f"市场分析工具调用失败: {e}"
            return {
                "messages": [result],
                "market_report": report,
                "market_tool_call_count": tool_call_count + 1,
            }

    return market_analyst_node


def _execute_tool_calls(tool_calls, tools):
    tool_map = {_get_tool_name(t): t for t in tools}
    tool_messages = []
    for tool_call in tool_calls:
        tool_name = tool_call.get('name')
        tool_args = tool_call.get('args', {})
        tool_id = tool_call.get('id')

        tool_fn = tool_map.get(tool_name)
        if tool_fn is None:
            tool_result = f"未找到工具: {tool_name}"
        else:
            try:
                tool_result = tool_fn.invoke(tool_args)
            except Exception as e:
                logger.error(f"工具 {tool_name} 执行失败: {e}")
                tool_result = f"工具执行失败: {e}"

        tool_messages.append(ToolMessage(content=str(tool_result), tool_call_id=tool_id))
    return tool_messages
