# TradingAgents/graph/setup.py

from typing import Dict, Any
from concurrent.futures import ThreadPoolExecutor, as_completed
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, ToolMessage
from langgraph.graph import END, StateGraph, START
from langgraph.prebuilt import ToolNode

from tradingagents.agents import *
from tradingagents.agents.utils.agent_states import AgentState
from tradingagents.agents.utils.agent_utils import Toolkit

from .conditional_logic import ConditionalLogic

from tradingagents.utils.logging_init import get_logger
logger = get_logger("default")

_ANALYST_REPORT_KEY = {
    "market": "market_report",
    "fundamentals": "fundamentals_report",
    "news": "news_report",
    "social": "sentiment_report",
    "news_social": "news_report",  # 合并节点: news_social 同时写入 news_report + sentiment_report
}

_ANALYST_TOOL_COUNT_KEY = {
    "market": "market_tool_call_count",
    "fundamentals": "fundamentals_tool_call_count",
    "news": "news_tool_call_count",
    "social": "sentiment_tool_call_count",
    "news_social": "news_tool_call_count",  # 合并节点
}


class GraphSetup:
    """Handles the setup and configuration of the agent graph."""

    def __init__(
        self,
        quick_thinking_llm: ChatOpenAI,
        deep_thinking_llm: ChatOpenAI,
        toolkit: Toolkit,
        tool_nodes: Dict[str, ToolNode],
        bull_memory,
        bear_memory,
        trader_memory,
        invest_judge_memory,
        risk_manager_memory,
        conditional_logic: ConditionalLogic,
        config: Dict[str, Any] = None,
        react_llm = None,
    ):
        self.quick_thinking_llm = quick_thinking_llm
        self.deep_thinking_llm = deep_thinking_llm
        self.toolkit = toolkit
        self.tool_nodes = tool_nodes
        self.bull_memory = bull_memory
        self.bear_memory = bear_memory
        self.trader_memory = trader_memory
        self.invest_judge_memory = invest_judge_memory
        self.risk_manager_memory = risk_manager_memory
        self.conditional_logic = conditional_logic
        self.config = config or {}
        self.react_llm = react_llm

    # ------------------------------------------------------------------
    #  Parallel analysts node
    # ------------------------------------------------------------------

    def _create_analyst_nodes(self, selected_analysts):
        analyst_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm, self.toolkit
            )

        # news + social 合并为一次调用
        if "news" in selected_analysts and "social" in selected_analysts:
            from tradingagents.agents.analysts.news_social_analyst import create_news_social_analyst
            analyst_nodes["news_social"] = create_news_social_analyst(
                self.quick_thinking_llm, self.toolkit
            )
        else:
            if "social" in selected_analysts:
                analyst_nodes["social"] = create_social_media_analyst(
                    self.quick_thinking_llm, self.toolkit
                )
            if "news" in selected_analysts:
                analyst_nodes["news"] = create_news_analyst(
                    self.quick_thinking_llm, self.toolkit
                )

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm, self.toolkit
            )

        return analyst_nodes

    def _make_parallel_analysts_node(self, selected_analysts):
        analyst_nodes = self._create_analyst_nodes(selected_analysts)

        analyst_tools_map = {
            "market": [self.toolkit.get_stock_market_data_unified],
            "fundamentals": [self.toolkit.get_stock_fundamentals_unified],
            "social": [self.toolkit.get_stock_sentiment_unified],
            "news": [self.toolkit.get_stock_news_unified],
            "news_social": [self.toolkit.get_stock_news_unified],
        }

        def _execute_tool_calls(tool_calls, tools):
            tool_map = {}
            for t in tools:
                name = getattr(t, 'name', None) or getattr(t, '__name__', str(t))
                tool_map[name] = t

            tool_messages = []
            for tc in tool_calls:
                tool_name = tc.get('name', '')
                tool_args = tc.get('args', {})
                tool_id = tc.get('id', '')

                tool_fn = tool_map.get(tool_name)
                if tool_fn is None:
                    tool_messages.append(
                        ToolMessage(content=f"未找到工具: {tool_name}", tool_call_id=tool_id)
                    )
                    continue
                try:
                    tool_result = tool_fn.invoke(tool_args)
                    tool_messages.append(
                        ToolMessage(content=str(tool_result), tool_call_id=tool_id)
                    )
                except Exception as e:
                    logger.error(f"❌ [并行分析师] 工具 {tool_name} 执行失败: {e}")
                    tool_messages.append(
                        ToolMessage(content=f"工具执行失败: {e}", tool_call_id=tool_id)
                    )
            return tool_messages

        def _run_analyst_with_tool_loop(analyst_type, node_fn, ticker, trade_date):
            isolated_state = {
                "messages": [HumanMessage(content=f"请分析股票 {ticker}")],
                "company_of_interest": ticker,
                "trade_date": trade_date,
                f"{analyst_type}_tool_call_count": 0,
            }

            report_key = _ANALYST_REPORT_KEY[analyst_type]
            max_iterations = 4

            for iteration in range(max_iterations):
                result = node_fn(isolated_state)
                report = result.get(report_key, "")

                if report and len(report) > 50:
                    return report

                messages = result.get("messages", [])
                has_tool_calls = False
                for msg in messages:
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        has_tool_calls = True
                        break

                if not has_tool_calls:
                    if report:
                        return report
                    last_content = ""
                    for msg in reversed(messages):
                        if hasattr(msg, "content") and msg.content:
                            last_content = msg.content
                            break
                    if last_content:
                        return last_content
                    return f"{analyst_type} 分析未能生成有效报告"

                tools = analyst_tools_map.get(analyst_type, [])
                if not tools:
                    logger.warning(
                        f"⚠️ [并行分析师] {analyst_type} 有tool_calls但无工具列表，"
                        f"尝试强制生成"
                    )
                    isolated_state["messages"].extend(messages)
                    isolated_state[f"{analyst_type}_tool_call_count"] = 99
                    force_result = node_fn(isolated_state)
                    force_report = force_result.get(report_key, "")
                    if force_report and len(force_report) > 50:
                        return force_report
                    for msg in reversed(force_result.get("messages", [])):
                        if hasattr(msg, "content") and msg.content:
                            return msg.content
                    return f"{analyst_type} 分析未能生成有效报告"

                all_tool_calls = []
                for msg in messages:
                    if hasattr(msg, "tool_calls") and msg.tool_calls:
                        all_tool_calls.extend(msg.tool_calls)

                tool_messages = _execute_tool_calls(all_tool_calls, tools)

                isolated_state["messages"].extend(messages)
                isolated_state["messages"].extend(tool_messages)
                isolated_state[f"{analyst_type}_tool_call_count"] = (
                    isolated_state.get(f"{analyst_type}_tool_call_count", 0) + 1
                )

            logger.warning(
                f"⚠️ [并行分析师] {analyst_type} 达到最大迭代次数 {max_iterations}"
            )
            last_content = ""
            for msg in reversed(isolated_state.get("messages", [])):
                if hasattr(msg, "content") and msg.content and not hasattr(msg, "tool_calls"):
                    last_content = msg.content
                    break
            return last_content or f"{analyst_type} 分析超过最大迭代次数"

        def parallel_analysts_node(state):
            ticker = state["company_of_interest"]
            trade_date = state["trade_date"]
            logger.info(
                f"🚀 [并行分析师] 开始并行执行 {len(analyst_nodes)} 个分析师: "
                f"{list(analyst_nodes.keys())}"
            )

            reports = {}
            errors = {}

            def _run_one(item):
                analyst_type, node_fn = item
                try:
                    if analyst_type == "news_social":
                        isolated_state = {
                            "messages": [HumanMessage(content=f"请分析股票 {ticker}")],
                            "company_of_interest": ticker,
                            "trade_date": trade_date,
                        }
                        result = node_fn(isolated_state)
                        news_r = result.get("news_report", "")
                        sentiment_r = result.get("sentiment_report", "")
                        return analyst_type, {"news_report": news_r, "sentiment_report": sentiment_r}, None
                    else:
                        report = _run_analyst_with_tool_loop(
                            analyst_type, node_fn, ticker, trade_date
                        )
                        return analyst_type, report, None
                except Exception as e:
                    logger.error(
                        f"❌ [并行分析师] {analyst_type} 执行失败: {e}",
                        exc_info=True,
                    )
                    return analyst_type, f"{analyst_type} 分析失败: {e}", e

            with ThreadPoolExecutor(max_workers=len(analyst_nodes)) as pool:
                futures = {
                    pool.submit(_run_one, item): item[0]
                    for item in analyst_nodes.items()
                }
                for future in as_completed(futures):
                    analyst_type, report, err = future.result()
                    reports[analyst_type] = report
                    if err:
                        errors[analyst_type] = err

            update = {"messages": [HumanMessage(content="Continue")]}

            for analyst_type, report_val in reports.items():
                if analyst_type == "news_social":
                    if isinstance(report_val, dict):
                        update["news_report"] = report_val.get("news_report", "")
                        update["sentiment_report"] = report_val.get("sentiment_report", "")
                    update["news_tool_call_count"] = 1
                    update["sentiment_tool_call_count"] = 1
                    continue

                report_key = _ANALYST_REPORT_KEY.get(analyst_type)
                if report_key:
                    update[report_key] = report_val if isinstance(report_val, str) else ""
                count_key = _ANALYST_TOOL_COUNT_KEY.get(analyst_type)
                if count_key:
                    update[count_key] = 1

            if errors:
                logger.warning(
                    f"⚠️ [并行分析师] {len(errors)} 个分析师失败: "
                    f"{list(errors.keys())}"
                )

            logger.info(
                f"✅ [并行分析师] 全部完成，报告长度: "
                + ", ".join(
                    f"{k}={len(v)}字" for k, v in reports.items()
                )
            )

            return update

        return parallel_analysts_node

    # ------------------------------------------------------------------
    #  Serial (original) graph
    # ------------------------------------------------------------------

    def _build_serial_graph(self, selected_analysts, workflow):
        analyst_nodes = {}
        delete_nodes = {}
        tool_nodes = {}

        if "market" in selected_analysts:
            analyst_nodes["market"] = create_market_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["market"] = create_msg_delete()
            tool_nodes["market"] = self.tool_nodes["market"]

        if "social" in selected_analysts:
            analyst_nodes["social"] = create_social_media_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["social"] = create_msg_delete()
            tool_nodes["social"] = self.tool_nodes["social"]

        if "news" in selected_analysts:
            analyst_nodes["news"] = create_news_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["news"] = create_msg_delete()
            tool_nodes["news"] = self.tool_nodes["news"]

        if "fundamentals" in selected_analysts:
            analyst_nodes["fundamentals"] = create_fundamentals_analyst(
                self.quick_thinking_llm, self.toolkit
            )
            delete_nodes["fundamentals"] = create_msg_delete()
            tool_nodes["fundamentals"] = self.tool_nodes["fundamentals"]

        for analyst_type, node in analyst_nodes.items():
            workflow.add_node(f"{analyst_type.capitalize()} Analyst", node)
            workflow.add_node(
                f"Msg Clear {analyst_type.capitalize()}", delete_nodes[analyst_type]
            )
            workflow.add_node(f"tools_{analyst_type}", tool_nodes[analyst_type])

        first_analyst = selected_analysts[0]
        workflow.add_edge(START, f"{first_analyst.capitalize()} Analyst")

        for i, analyst_type in enumerate(selected_analysts):
            current_analyst = f"{analyst_type.capitalize()} Analyst"
            current_tools = f"tools_{analyst_type}"
            current_clear = f"Msg Clear {analyst_type.capitalize()}"

            workflow.add_conditional_edges(
                current_analyst,
                getattr(self.conditional_logic, f"should_continue_{analyst_type}"),
                [current_tools, current_clear],
            )
            workflow.add_edge(current_tools, current_analyst)

            if i < len(selected_analysts) - 1:
                next_analyst = f"{selected_analysts[i+1].capitalize()} Analyst"
                workflow.add_edge(current_clear, next_analyst)
            else:
                workflow.add_edge(current_clear, "Bull Researcher")

    # ------------------------------------------------------------------
    #  Parallel graph
    # ------------------------------------------------------------------

    def _build_parallel_graph(self, selected_analysts, workflow):
        parallel_node = self._make_parallel_analysts_node(selected_analysts)
        workflow.add_node("Parallel Analysts", parallel_node)
        workflow.add_edge(START, "Parallel Analysts")
        workflow.add_edge("Parallel Analysts", "Bull Researcher")

    # ------------------------------------------------------------------
    #  Common post-analyst nodes & edges
    # ------------------------------------------------------------------

    def _add_common_nodes(self, workflow):
        bull_researcher_node = create_bull_researcher(
            self.quick_thinking_llm, self.bull_memory
        )
        bear_researcher_node = create_bear_researcher(
            self.quick_thinking_llm, self.bear_memory
        )
        research_manager_node = create_research_manager(
            self.deep_thinking_llm, self.invest_judge_memory
        )
        trader_node = create_trader(self.quick_thinking_llm, self.trader_memory)

        risky_analyst = create_risky_debator(self.quick_thinking_llm)
        neutral_analyst = create_neutral_debator(self.quick_thinking_llm)
        safe_analyst = create_safe_debator(self.quick_thinking_llm)
        risk_manager_node = create_risk_manager(
            self.deep_thinking_llm, self.risk_manager_memory
        )

        workflow.add_node("Bull Researcher", bull_researcher_node)
        workflow.add_node("Bear Researcher", bear_researcher_node)
        workflow.add_node("Research Manager", research_manager_node)
        workflow.add_node("Trader", trader_node)
        workflow.add_node("Risky Analyst", risky_analyst)
        workflow.add_node("Neutral Analyst", neutral_analyst)
        workflow.add_node("Safe Analyst", safe_analyst)
        workflow.add_node("Risk Judge", risk_manager_node)

        workflow.add_conditional_edges(
            "Bull Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bear Researcher": "Bear Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_conditional_edges(
            "Bear Researcher",
            self.conditional_logic.should_continue_debate,
            {
                "Bull Researcher": "Bull Researcher",
                "Research Manager": "Research Manager",
            },
        )
        workflow.add_edge("Research Manager", "Trader")
        workflow.add_edge("Trader", "Risky Analyst")
        workflow.add_conditional_edges(
            "Risky Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Safe Analyst": "Safe Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Safe Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Neutral Analyst": "Neutral Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_conditional_edges(
            "Neutral Analyst",
            self.conditional_logic.should_continue_risk_analysis,
            {
                "Risky Analyst": "Risky Analyst",
                "Risk Judge": "Risk Judge",
            },
        )
        workflow.add_edge("Risk Judge", END)

    # ------------------------------------------------------------------
    #  Public entry point
    # ------------------------------------------------------------------

    def setup_graph(
        self,
        selected_analysts=["market", "social", "news", "fundamentals"],
        parallel=True,
    ):
        """Set up and compile the agent workflow graph.

        Args:
            selected_analysts (list): List of analyst types to include.
            parallel (bool): If True, run all analysts in parallel using
                ThreadPoolExecutor. If False, run sequentially (original
                behaviour).
        """
        if len(selected_analysts) == 0:
            raise ValueError("Trading Agents Graph Setup Error: no analysts selected!")

        workflow = StateGraph(AgentState)

        if parallel and len(selected_analysts) > 1:
            self._build_parallel_graph(selected_analysts, workflow)
        else:
            self._build_serial_graph(selected_analysts, workflow)

        self._add_common_nodes(workflow)

        return workflow.compile()
