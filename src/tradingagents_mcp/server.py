"""
TradingAgents-CN MCP Agent Server

将多Agent协作分析引擎封装为 MCP Tools，
支持完整全流程和单分析师独立调用。

启动方式:
  stdio:    tradingagents-mcp          (或 python -m tradingagents_mcp)
  http:     MCP_TRANSPORT=streamable-http tradingagents-mcp
  check:    tradingagents-mcp check    (环境自检)
"""

import asyncio
import logging
import time
from typing import Optional

from mcp.server.fastmcp import FastMCP, Context
from mcp.server.session import ServerSession

from tradingagents_mcp.validators import (
    validate_symbol,
    normalize_date,
    nearest_trade_date,
    build_config,
    check_health,
    extract_reports,
    calc_period_stats,
    extract_data_points,
)
from tradingagents_mcp.screen import (
    screen_stocks_online,
    format_screening_items,
)

logger = logging.getLogger("mcp_server")

mcp = FastMCP(
    "TradingAgents-CN",
    instructions="AI金融交易分析Agent — 支持完整多Agent协作分析和单分析师独立调用",
)


async def _run_single_analyst(
    analyst_type: str,
    symbol: str,
    trade_date: str,
    ctx: Context = None,
    extra_state: dict = None,
) -> dict:
    from tradingagents.graph.trading_graph import TradingAgentsGraph

    config = build_config()
    config["online_tools"] = config.get("online_tools", True)
    config["online_news"] = config.get("online_news", True)

    ta = TradingAgentsGraph(selected_analysts=[analyst_type], debug=False, config=config)

    from langchain_core.messages import HumanMessage

    state = {
        "messages": [HumanMessage(content=f"请分析股票 {symbol}")],
        "company_of_interest": symbol,
        "trade_date": trade_date,
        f"{analyst_type}_tool_call_count": 0,
    }
    if extra_state:
        state.update(extra_state)

    analyst_map = {
        "market": ("create_market_analyst", "market_report"),
        "fundamentals": ("create_fundamentals_analyst", "fundamentals_report"),
        "news": ("create_news_analyst", "news_report"),
        "social": ("create_social_media_analyst", "sentiment_report"),
    }

    _, report_key = analyst_map[analyst_type]

    from tradingagents.agents import (
        create_market_analyst,
        create_fundamentals_analyst,
        create_news_analyst,
        create_social_media_analyst,
    )

    create_fn = {
        "market": create_market_analyst,
        "fundamentals": create_fundamentals_analyst,
        "news": create_news_analyst,
        "social": create_social_media_analyst,
    }[analyst_type]

    node = create_fn(ta.quick_thinking_llm, ta.toolkit)

    loop = asyncio.get_event_loop()
    result_state = await loop.run_in_executor(None, lambda: node(state))

    report = result_state.get(report_key, "")

    return {
        "success": True,
        "symbol": symbol,
        "trade_date": trade_date,
        "analyst": analyst_type,
        "report": report,
    }


# ============================================================
# Tool 1: trading_agent
# ============================================================
@mcp.tool()
async def trading_agent(
    symbol: str,
    trade_date: str,
    analysts: Optional[list[str]] = None,
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """AI金融交易分析Agent（完整流程）：执行多Agent协作分析，
包含数据获取→多空辩论→风险评估→交易决策。

支持A股(如000001)、美股(如AAPL)、港股(如00700.HK)。

Args:
    symbol: 股票代码
    trade_date: 交易日期 YYYY-MM-DD
    analysts: 分析师组合，默认 ["market","social","news","fundamentals"]
    max_debate_rounds: 多空辩论轮次
    max_risk_discuss_rounds: 风险辩论轮次
"""
    t0 = time.time()
    if analysts is None:
        analysts = ["market", "social", "news", "fundamentals"]

    try:
        symbol, market = validate_symbol(symbol)
        trade_date = nearest_trade_date(normalize_date(trade_date))
    except ValueError as e:
        return {"success": False, "error": str(e)}

    if ctx:
        await ctx.info(f"TradingAgent 开始分析: {symbol}({market}) @ {trade_date}")

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        config = build_config()
        config["max_debate_rounds"] = max_debate_rounds
        config["max_risk_discuss_rounds"] = max_risk_discuss_rounds
        config["online_tools"] = config.get("online_tools", True)
        config["online_news"] = config.get("online_news", True)

        ta = TradingAgentsGraph(selected_analysts=analysts, debug=False, config=config)

        loop = asyncio.get_event_loop()
        state, decision = await loop.run_in_executor(
            None, lambda: ta.propagate(symbol, trade_date)
        )

        elapsed = round(time.time() - t0, 1)
        result = {
            "success": True,
            "symbol": symbol,
            "market": market,
            "trade_date": trade_date,
            "tool": "trading_agent",
            "decision": decision,
            "analysts_used": analysts,
            "elapsed_seconds": elapsed,
            **extract_reports(state),
        }

        perf = state.get("performance_metrics", {})
        if perf:
            result["total_time_minutes"] = perf.get("total_time_minutes")

        return result

    except Exception as e:
        logger.error(f"trading_agent 分析失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbol": symbol, "elapsed_seconds": round(time.time() - t0, 1)}


# ============================================================
# Tool 2-5: 单分析师
# ============================================================
@mcp.tool()
async def market_analyst(
    symbol: str, trade_date: str, ctx: Context[ServerSession, None] = None,
) -> dict:
    """市场分析师Agent（独立运行）：获取行情数据并生成技术分析报告。

分析内容：移动平均线、MACD、RSI、布林带、价格趋势、成交量。
支持A股(AKShare/Tushare/BaoStock)、美股(YFinance)、港股(AKShare)，自动识别。
适合只需看技术面的场景，速度快（~30秒 vs 全流程3-5分钟）。

Args:
    symbol: 股票代码
    trade_date: 交易日期 YYYY-MM-DD
"""
    try:
        symbol, market = validate_symbol(symbol)
        trade_date = nearest_trade_date(normalize_date(trade_date))
    except ValueError as e:
        return {"success": False, "error": str(e)}

    t0 = time.time()
    if ctx:
        await ctx.info(f"市场分析师: {symbol}({market}) @ {trade_date}")
    try:
        result = await _run_single_analyst("market", symbol, trade_date, ctx)
        result["market"] = market
        result["elapsed_seconds"] = round(time.time() - t0, 1)
        return result
    except Exception as e:
        logger.error(f"market_analyst 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbol": symbol, "elapsed_seconds": round(time.time() - t0, 1)}


@mcp.tool()
async def fundamentals_analyst(
    symbol: str, trade_date: str, ctx: Context[ServerSession, None] = None,
) -> dict:
    """基本面分析师Agent（独立运行）：获取PE/PB/ROE等财务数据并生成基本面报告。

分析内容：估值指标、盈利能力、财务健康、行业对比。

Args:
    symbol: 股票代码
    trade_date: 交易日期 YYYY-MM-DD
"""
    try:
        symbol, market = validate_symbol(symbol)
        trade_date = nearest_trade_date(normalize_date(trade_date))
    except ValueError as e:
        return {"success": False, "error": str(e)}

    t0 = time.time()
    if ctx:
        await ctx.info(f"基本面分析师: {symbol}({market}) @ {trade_date}")
    try:
        result = await _run_single_analyst("fundamentals", symbol, trade_date, ctx)
        result["market"] = market
        result["elapsed_seconds"] = round(time.time() - t0, 1)
        return result
    except Exception as e:
        logger.error(f"fundamentals_analyst 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbol": symbol, "elapsed_seconds": round(time.time() - t0, 1)}


@mcp.tool()
async def news_analyst(
    symbol: str, trade_date: str, look_back_days: int = 7,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """新闻分析师Agent（独立运行）：获取股票相关新闻并生成分析报告。

分析内容：重大新闻事件、政策影响、行业动态、潜在风险。

Args:
    symbol: 股票代码
    trade_date: 交易日期 YYYY-MM-DD
    look_back_days: 回看天数，默认7
"""
    try:
        symbol, market = validate_symbol(symbol)
        trade_date = nearest_trade_date(normalize_date(trade_date))
    except ValueError as e:
        return {"success": False, "error": str(e)}

    t0 = time.time()
    if ctx:
        await ctx.info(f"新闻分析师: {symbol}({market}) @ {trade_date}")
    try:
        result = await _run_single_analyst(
            "news", symbol, trade_date, ctx,
            extra_state={"news_tool_call_count": 0},
        )
        result["market"] = market
        result["look_back_days"] = look_back_days
        result["elapsed_seconds"] = round(time.time() - t0, 1)
        return result
    except Exception as e:
        logger.error(f"news_analyst 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbol": symbol, "elapsed_seconds": round(time.time() - t0, 1)}


@mcp.tool()
async def social_analyst(
    symbol: str, trade_date: str, ctx: Context[ServerSession, None] = None,
) -> dict:
    """社交媒体分析师Agent（独立运行）：获取社交平台情绪并生成分析报告。

分析内容：投资者情绪、讨论热度、关键观点、多空倾向。
A股社交数据源有限，可能返回数据不足。

Args:
    symbol: 股票代码
    trade_date: 交易日期 YYYY-MM-DD
"""
    try:
        symbol, market = validate_symbol(symbol)
        trade_date = nearest_trade_date(normalize_date(trade_date))
    except ValueError as e:
        return {"success": False, "error": str(e)}

    t0 = time.time()
    if ctx:
        await ctx.info(f"社交分析师: {symbol}({market}) @ {trade_date}")
    try:
        result = await _run_single_analyst("social", symbol, trade_date, ctx)
        result["market"] = market
        result["elapsed_seconds"] = round(time.time() - t0, 1)
        return result
    except Exception as e:
        logger.error(f"social_analyst 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbol": symbol, "elapsed_seconds": round(time.time() - t0, 1)}


# ============================================================
# Tool 6: compare_stocks
# ============================================================
@mcp.tool()
async def compare_stocks(
    symbols: list[str],
    trade_date: str,
    analyst: str = "market",
    max_debate_rounds: int = 1,
    max_risk_discuss_rounds: int = 1,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """多股对比分析Agent：对多只股票并行分析并生成对比报告。

对比维度(analyst参数): market(技术)|fundamentals(估值)|news(新闻)|social(情绪)|full(全流程)

Args:
    symbols: 股票代码列表，如 ["000001", "600519"]
    trade_date: 交易日期 YYYY-MM-DD
    analyst: 对比维度 "market"|"fundamentals"|"news"|"social"|"full"
    max_debate_rounds: 仅 full 模式
    max_risk_discuss_rounds: 仅 full 模式
"""
    t0 = time.time()

    validated = []
    for s in symbols:
        try:
            s_val, mkt = validate_symbol(s)
            validated.append(s_val)
        except ValueError as e:
            return {"success": False, "error": str(e)}
    symbols = validated

    try:
        trade_date = nearest_trade_date(normalize_date(trade_date))
    except ValueError as e:
        return {"success": False, "error": str(e)}

    if ctx:
        await ctx.info(f"多股对比分析: {symbols} @ {trade_date}, 维度={analyst}")

    try:
        individual_results = {}

        if analyst == "full":
            from tradingagents.graph.trading_graph import TradingAgentsGraph

            config = build_config()
            config["max_debate_rounds"] = max_debate_rounds
            config["max_risk_discuss_rounds"] = max_risk_discuss_rounds

            async def _run_full(sym):
                ta = TradingAgentsGraph(
                    selected_analysts=["market", "social", "news", "fundamentals"],
                    debug=False, config=config,
                )
                loop = asyncio.get_event_loop()
                state, decision = await loop.run_in_executor(
                    None, lambda: ta.propagate(sym, trade_date)
                )
                return {"decision": decision, **extract_reports(state)}

            tasks = [_run_full(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, res in zip(symbols, results):
                individual_results[sym] = res if not isinstance(res, Exception) else {"error": str(res)}
        else:
            async def _run_one(sym):
                return await _run_single_analyst(analyst, sym, trade_date, ctx)

            tasks = [_run_one(sym) for sym in symbols]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for sym, res in zip(symbols, results):
                individual_results[sym] = res if not isinstance(res, Exception) else {"error": str(res)}

        comparison_prompt = (
            f"你是一位专业的投资顾问。请对比以下 {len(symbols)} 只股票的分析报告，"
            f"交易日为 {trade_date}，对比维度为 {analyst}。\n\n"
        )
        for sym, res in individual_results.items():
            if isinstance(res, dict) and "error" not in res:
                report = res.get("report", res.get("market_report", ""))
                comparison_prompt += f"## {sym}\n{report}\n\n"
            elif isinstance(res, dict) and "decision" in res:
                comparison_prompt += f"## {sym}\n决策: {res['decision']}\n\n"

        comparison_prompt += (
            "\n请给出：\n"
            "1. 横向对比分析（各股优劣势）\n"
            "2. 推荐排名（从高到低）\n"
            "3. 每只股票的评分（0-100）和推荐理由\n"
        )

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        config = build_config()
        ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
        loop = asyncio.get_event_loop()
        comparison_report = await loop.run_in_executor(
            None, lambda: ta.quick_thinking_llm.invoke(comparison_prompt).content
        )

        return {
            "success": True,
            "symbols": symbols,
            "trade_date": trade_date,
            "analyst": analyst,
            "individual_reports": {
                sym: res.get("report", res.get("decision", ""))
                for sym, res in individual_results.items()
                if isinstance(res, dict) and "error" not in res
            },
            "comparison": comparison_report,
            "elapsed_seconds": round(time.time() - t0, 1),
        }

    except Exception as e:
        logger.error(f"compare_stocks 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbols": symbols, "elapsed_seconds": round(time.time() - t0, 1)}


# ============================================================
# Tool 7: batch_analyze
# ============================================================
@mcp.tool()
async def batch_analyze(
    symbols: list[str],
    trade_date: str,
    analyst: str = "market",
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """批量独立分析：对多只股票并行运行同一分析师，各股独立返回报告，无对比逻辑。

与 compare_stocks 的区别：batch_analyze 无横向对比和排名，适合快速获取多股同维度报告。

Args:
    symbols: 股票代码列表
    trade_date: 交易日期 YYYY-MM-DD
    analyst: 分析师选择，默认 "market"
"""
    t0 = time.time()

    validated = []
    for s in symbols:
        try:
            s_val, _ = validate_symbol(s)
            validated.append(s_val)
        except ValueError as e:
            return {"success": False, "error": str(e)}
    symbols = validated

    try:
        trade_date = nearest_trade_date(normalize_date(trade_date))
    except ValueError as e:
        return {"success": False, "error": str(e)}

    if ctx:
        await ctx.info(f"批量分析: {len(symbols)} 只股票, 维度={analyst}")

    try:
        tasks = [_run_single_analyst(analyst, sym, trade_date, ctx) for sym in symbols]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        individual_results = {}
        for sym, res in zip(symbols, results):
            individual_results[sym] = res if not isinstance(res, Exception) else {"error": str(res)}

        return {
            "success": True,
            "symbols": symbols,
            "trade_date": trade_date,
            "analyst": analyst,
            "results": individual_results,
            "elapsed_seconds": round(time.time() - t0, 1),
        }

    except Exception as e:
        logger.error(f"batch_analyze 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbols": symbols, "elapsed_seconds": round(time.time() - t0, 1)}


# ============================================================
# Tool 8: period_compare
# ============================================================
@mcp.tool()
async def period_compare(
    symbol: str,
    start_date: str,
    end_date: str,
    metrics: Optional[list[str]] = None,
    compare_with: Optional[str] = None,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """历史区间对比Agent：对比一只股票在指定时间区间内的走势变化，
或与另一只股票/指数的同期走势对比。

返回区间收益率、最大回撤、波动率，可选超额收益(与基准对比)。
常见指数代码: 000300(沪深300) 000016(上证50) 399006(创业板指)

Args:
    symbol: 股票代码
    start_date: 起始日期 YYYY-MM-DD
    end_date: 结束日期 YYYY-MM-DD
    metrics: 对比指标，默认 ["close","volume","pct_chg"]
    compare_with: 对比目标（股票代码或指数代码），可选
"""
    t0 = time.time()
    if metrics is None:
        metrics = ["close", "volume", "pct_chg"]

    try:
        symbol, market = validate_symbol(symbol)
        start_date = normalize_date(start_date)
        end_date = normalize_date(end_date)
        if compare_with:
            compare_with, _ = validate_symbol(compare_with)
    except ValueError as e:
        return {"success": False, "error": str(e)}

    if ctx:
        await ctx.info(f"历史区间对比: {symbol}({market}) {start_date}~{end_date}" + (f" vs {compare_with}" if compare_with else ""))

    try:
        from tradingagents.graph.trading_graph import TradingAgentsGraph

        loop = asyncio.get_event_loop()

        config = build_config()
        config["online_tools"] = config.get("online_tools", True)
        config["online_news"] = config.get("online_news", True)
        ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)

        symbol_data = await loop.run_in_executor(
            None, lambda: ta.toolkit.get_stock_market_data_unified(symbol, start_date, end_date)
        )

        if not symbol_data:
            return {"success": False, "error": f"未获取到 {symbol} 的数据", "symbol": symbol}

        symbol_stats = calc_period_stats(symbol_data)

        compare_data = None
        compare_stats = None
        if compare_with:
            compare_data = await loop.run_in_executor(
                None, lambda: ta.toolkit.get_stock_market_data_unified(compare_with, start_date, end_date)
            )
            if compare_data:
                compare_stats = calc_period_stats(compare_data)

        symbol_points = extract_data_points(symbol_data, metrics, max_points=60)
        compare_points = extract_data_points(compare_data, metrics, max_points=60) if compare_data else None

        summary = {
            "symbol_return": symbol_stats.get("total_return"),
            "max_drawdown": symbol_stats.get("max_drawdown"),
            "volatility": symbol_stats.get("volatility"),
        }
        if compare_stats:
            summary["benchmark_return"] = compare_stats.get("total_return")
            summary["excess_return"] = round(
                (symbol_stats.get("total_return", 0) or 0) - (compare_stats.get("total_return", 0) or 0), 2
            )
            summary["benchmark_max_drawdown"] = compare_stats.get("max_drawdown")

        analysis_prompt = (
            f"你是一位专业的量化分析师。请分析以下股票在 {start_date} 至 {end_date} 期间的表现：\n\n"
            f"## {symbol}({market}) 区间统计\n"
            f"- 区间收益率: {summary.get('symbol_return')}%\n"
            f"- 最大回撤: {summary.get('max_drawdown')}%\n"
            f"- 波动率: {summary.get('volatility')}%\n"
        )
        if compare_stats:
            analysis_prompt += (
                f"\n## {compare_with} (基准) 区间统计\n"
                f"- 区间收益率: {summary.get('benchmark_return')}%\n"
                f"- 最大回撤: {summary.get('benchmark_max_drawdown')}%\n"
                f"- 超额收益: {summary.get('excess_return')}%\n"
            )
        analysis_prompt += (
            "\n请给出：\n"
            "1. 区间走势分析（趋势、关键转折点）\n"
            "2. 风险评估（回撤、波动）\n"
            "3. 与基准的对比结论（如有）\n"
            "4. 后市展望建议\n"
        )

        from tradingagents.graph.trading_graph import TradingAgentsGraph
        config = build_config()
        ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
        analysis_report = await loop.run_in_executor(
            None, lambda: ta.quick_thinking_llm.invoke(analysis_prompt).content
        )

        return {
            "success": True,
            "symbol": symbol,
            "market": market,
            "period": {"start_date": start_date, "end_date": end_date},
            "compare_with": compare_with,
            "summary": summary,
            "data_points": {"symbol": symbol_points, "compare_with": compare_points},
            "analysis": analysis_report,
            "elapsed_seconds": round(time.time() - t0, 1),
        }

    except Exception as e:
        logger.error(f"period_compare 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "symbol": symbol, "elapsed_seconds": round(time.time() - t0, 1)}


# ============================================================
# Tool 9: screen_stocks
# ============================================================
@mcp.tool()
async def screen_stocks(
    conditions: list[dict],
    market: str = "CN",
    order_by: Optional[list[dict]] = None,
    limit: int = 50,
    ctx: Context[ServerSession, None] = None,
) -> dict:
    """股票筛选Agent：根据条件筛选符合要求的股票，并生成筛选解读报告。

支持字段: industry/pe/pb/pe_ttm/roe/total_mv/circ_mv/close/pct_chg/turnover_rate/volume_ratio/amount
操作符: > / < / >= / <= / == / != / between / in / not_in / contains

Args:
    conditions: 筛选条件列表
    market: 市场 CN/HK/US
    order_by: 排序条件
    limit: 返回数量限制
"""
    t0 = time.time()

    if ctx:
        await ctx.info(f"股票筛选: {len(conditions)} 个条件, 市场={market}")

    try:
        loop = asyncio.get_event_loop()

        items = await loop.run_in_executor(
            None, lambda: screen_stocks_online(conditions, market, order_by, limit)
        )

        if items:
            items_summary = format_screening_items(items, max_items=30)
            analysis_prompt = (
                f"你是一位专业的投资顾问。以下是通过筛选条件的 {market} 市场股票（共 {len(items)} 只）：\n\n"
                f"筛选条件: {conditions}\n\n"
                f"{items_summary}\n\n"
                "请给出：\n"
                "1. 筛选结果的整体特征分析\n"
                "2. 值得关注的前5只股票及理由\n"
                "3. 潜在风险提示\n"
            )

            from tradingagents.graph.trading_graph import TradingAgentsGraph
            config = build_config()
            ta = TradingAgentsGraph(selected_analysts=["market"], debug=False, config=config)
            analysis_report = await loop.run_in_executor(
                None, lambda: ta.quick_thinking_llm.invoke(analysis_prompt).content
            )
        else:
            analysis_report = "未找到符合筛选条件的股票。建议放宽条件重试。"

        return {
            "success": True,
            "market": market,
            "conditions": conditions,
            "total": len(items),
            "items": items[:limit],
            "analysis": analysis_report,
            "elapsed_seconds": round(time.time() - t0, 1),
        }

    except Exception as e:
        logger.error(f"screen_stocks 失败: {e}", exc_info=True)
        return {"success": False, "error": str(e), "conditions": conditions, "elapsed_seconds": round(time.time() - t0, 1)}


# ============================================================
# Tool 10: agent_status
# ============================================================
@mcp.tool()
async def agent_status() -> dict:
    """查询当前Agent的配置状态、健康检查和支持的能力。
    适合在分析前检查环境是否就绪，或排查MCP连接问题。"""
    config = build_config()
    health = check_health()

    return {
        "success": True,
        "version": "1.0.0-preview",
        "health": health,
        "llm_provider": config.get("llm_provider"),
        "deep_think_llm": config.get("deep_think_llm"),
        "quick_think_llm": config.get("quick_think_llm"),
        "online_tools": config.get("online_tools", False),
        "supported_markets": ["A股", "美股", "港股"],
        "available_tools": {
            "trading_agent": "完整全流程分析（分析师→辩论→风险→决策，3-10分钟）",
            "market_analyst": "独立市场/技术分析（~30秒）",
            "fundamentals_analyst": "独立基本面分析（~30秒）",
            "news_analyst": "独立新闻分析（~30秒）",
            "social_analyst": "独立社交媒体情绪分析（~30秒）",
            "compare_stocks": "多股对比分析（并行+横向对比+排名推荐）",
            "batch_analyze": "批量独立分析（并行，无对比）",
            "period_compare": "历史区间对比（区间统计+超额收益+走势分析，~30秒）",
            "screen_stocks": "股票筛选（条件筛选+LLM解读，~15秒）",
        },
        "data_sources": {
            "A股": ["AKShare", "Tushare", "BaoStock"],
            "美股": ["YFinance", "Finnhub", "Alpha Vantage"],
            "港股": ["AKShare"],
            "新闻": ["Google News", "Finnhub", "中文财经"],
            "情绪": ["Reddit", "雪球/东财股吧/新浪财经"],
        },
    }


from tradingagents_mcp.prompts import register_prompts
register_prompts(mcp)
