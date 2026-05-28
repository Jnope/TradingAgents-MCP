from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.tools.unified_news_tool import UnifiedNewsAnalyzer
from tradingagents.utils.stock_utils import StockUtils
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("analysts.social_media")


_SOCIAL_PROMPT = """您是一位专业的社交媒体和舆情分析师，负责从舆情和情绪视角分析个股新闻数据。

您的主要职责包括：
1. 分析投资者对新闻的情绪反应
2. 识别影响股价的热点事件和市场传言
3. 评估散户与机构投资者的观点差异
4. 分析政策变化对投资者情绪的影响
5. 评估情绪变化对股价的潜在影响

分析要点：
- 投资者情绪的变化趋势和原因
- 关键意见领袖(KOL)的观点和影响力
- 热点事件对股价预期的影响
- 散户情绪与机构观点的差异
- 情绪极端点和可能的反转信号

📊 情绪影响分析要求：
- 量化投资者情绪强度（乐观/悲观程度）和情绪变化趋势
- 评估情绪变化对短期市场反应的影响（1-5天）
- 识别情绪极端点和可能的情绪反转信号

💰 必须包含：
- 情绪指数评分（1-10分）
- 预期价格波动幅度
- 基于情绪的交易时机建议

请基于提供的个股新闻数据撰写详细的中文舆情分析报告，并在报告末尾附上Markdown表格总结关键发现。"""


def _get_company_name(ticker: str, market_info: dict) -> str:
    try:
        if market_info['is_china']:
            from tradingagents.dataflows.interface import get_china_stock_info_unified
            stock_info = get_china_stock_info_unified(ticker)
            if stock_info and "股票名称:" in stock_info:
                return stock_info.split("股票名称:")[1].split("\n")[0].strip()
            try:
                from tradingagents.dataflows.data_source_manager import get_china_stock_info_unified as get_info_dict
                info_dict = get_info_dict(ticker)
                if info_dict and info_dict.get('name'):
                    return info_dict['name']
            except Exception:
                pass
            return f"股票代码{ticker}"

        elif market_info['is_hk']:
            try:
                from tradingagents.dataflows.providers.hk.improved_hk import get_hk_company_name_improved
                return get_hk_company_name_improved(ticker)
            except Exception:
                return f"港股{ticker.replace('.HK', '').replace('.hk', '')}"

        elif market_info['is_us']:
            us_stock_names = {
                'AAPL': '苹果公司', 'TSLA': '特斯拉', 'NVDA': '英伟达',
                'MSFT': '微软', 'GOOGL': '谷歌', 'AMZN': '亚马逊',
                'META': 'Meta', 'NFLX': '奈飞',
            }
            return us_stock_names.get(ticker.upper(), f"美股{ticker}")

        else:
            return f"股票{ticker}"

    except Exception as e:
        logger.error(f"[社交媒体分析师] 获取公司名称失败: {e}")
        return f"股票{ticker}"


def create_social_media_analyst(llm, toolkit, progress_callback=None):
    @log_analyst_module("social_media")
    def social_media_analyst_node(state):
        tool_call_count = state.get("sentiment_tool_call_count", 0)
        logger.info(f"[社交媒体分析师] 当前工具调用次数: {tool_call_count}")

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        if progress_callback:
            progress_callback("正在获取舆情数据...")

        market_info = StockUtils.get_market_info(ticker)
        company_name = _get_company_name(ticker, market_info)
        logger.info(f"[社交媒体分析师] 公司名称: {company_name}")

        # 舆情分析只需要个股新闻，不需要宏观新闻
        analyzer = UnifiedNewsAnalyzer(toolkit)
        stock_news = ""
        try:
            stock_news = analyzer.get_stock_news_only(stock_code=ticker, max_news=10, model_info="", trade_date=current_date)
        except Exception as e:
            logger.error(f"[社交媒体分析师] 个股新闻获取失败: {e}")

        if not stock_news or len(stock_news.strip()) <= 100:
            logger.warning(f"[社交媒体分析师] 新闻数据不足")
            stock_news = f"未能获取到 {ticker}（{company_name}）的有效新闻数据，请基于已知信息进行分析。"

        if progress_callback:
            progress_callback("数据已获取，正在生成舆情分析报告...")

        try:
            if GoogleToolCallHandler.is_google_model(llm):
                analysis_prompt = f"""请对 {ticker}（{company_name}）进行舆情分析。

=== 个股新闻数据 ===
{stock_news}

当前日期: {current_date}

{_SOCIAL_PROMPT}"""
                result = llm.invoke([HumanMessage(content=analysis_prompt)])
            else:
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "{system_prompt}\n\n当前日期: {current_date}。请用中文撰写分析内容。"),
                    ("user", "请对 {ticker}（{company_name}）进行舆情分析。\n\n=== 个股新闻数据 ===\n{stock_news}"),
                ])
                chain = prompt | llm
                result = chain.invoke({
                    "system_prompt": _SOCIAL_PROMPT,
                    "current_date": current_date,
                    "ticker": ticker,
                    "company_name": company_name,
                    "stock_news": stock_news,
                })

            if hasattr(result, 'content') and result.content:
                report = result.content
            else:
                report = ""
        except Exception as e:
            logger.error(f"[社交媒体分析师] 报告生成失败: {e}")
            report = f"舆情分析报告生成失败: {e}"

        return {
            "messages": [AIMessage(content=report)],
            "sentiment_report": report,
            "sentiment_tool_call_count": tool_call_count + 1
        }

    return social_media_analyst_node
