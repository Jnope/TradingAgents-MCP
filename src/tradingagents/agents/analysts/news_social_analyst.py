from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.utils.stock_utils import StockUtils
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("analysts.news_social")


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
        logger.error(f"[新闻舆情分析师] 获取公司名称失败: {e}")
        return f"股票{ticker}"


_NEWS_PROMPT = """您是一位专业的财经新闻分析师，负责分析最新的市场新闻和事件对股票价格的潜在影响。

您的主要职责包括：
1. 分析最新的实时新闻和宏观新闻
2. 评估新闻事件的紧急程度和市场影响
3. 识别可能影响股价的关键信息
4. 分析新闻的时效性和可靠性
5. 提供基于新闻的交易建议和价格影响评估

重点关注的新闻类型：
- 财报发布和业绩指导
- 重大合作和并购消息
- 政策变化和监管动态
- 突发事件和危机管理
- 行业趋势和技术突破
- 宏观经济数据和政策动向

分析要点：
- 新闻的时效性（发布时间距离现在多久）
- 新闻的可信度（来源权威性）
- 市场影响程度（对股价的潜在影响）
- 投资者情绪变化（正面/负面/中性）
- 与历史类似事件的对比

请基于提供的新闻数据撰写详细的中文分析报告，并在报告末尾附上Markdown表格总结关键发现。"""


_SOCIAL_PROMPT = """您是一位专业的社交媒体和舆情分析师，负责从舆情和情绪视角分析新闻数据。

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

请基于提供的新闻数据撰写详细的中文舆情分析报告，并在报告末尾附上Markdown表格总结关键发现。"""


def create_news_social_analyst(llm, toolkit, progress_callback=None):
    @log_analyst_module("news_social")
    def news_social_analyst_node(state):
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        if progress_callback:
            progress_callback("正在获取新闻与舆情数据...")

        market_info = StockUtils.get_market_info(ticker)
        company_name = _get_company_name(ticker, market_info)
        logger.info(f"[新闻舆情分析师] 公司名称: {company_name}")

        # 一次性获取个股新闻，再单独获取宏观新闻
        if progress_callback:
            progress_callback("正在获取新闻数据...")

        from tradingagents.tools.unified_news_tool import UnifiedNewsAnalyzer
        analyzer = UnifiedNewsAnalyzer(toolkit)

        model_info = ""
        try:
            model_info = f"{llm.__class__.__name__}:{llm.model_name}" if hasattr(llm, 'model_name') else llm.__class__.__name__
        except Exception:
            model_info = "Unknown"

        # 个股新闻（新闻+舆情共用）
        stock_news = ""
        try:
            stock_news = analyzer.get_stock_news_only(stock_code=ticker, max_news=10, model_info=model_info)
            logger.info(f"[新闻舆情分析师] 个股新闻获取完成: {len(stock_news) if stock_news else 0} 字符")
        except Exception as e:
            logger.error(f"[新闻舆情分析师] 个股新闻获取失败: {e}")

        if not stock_news or len(stock_news.strip()) <= 100:
            logger.warning(f"[新闻舆情分析师] 新闻数据不足，使用降级报告")
            stock_news = f"未能获取到 {ticker}（{company_name}）的有效新闻数据，请基于已知信息进行分析。"

        # 宏观新闻（仅新闻分析师使用）
        macro_news = ""
        try:
            macro_news = analyzer._get_cctv_macro_news()
            if macro_news:
                logger.info(f"[新闻舆情分析师] 宏观新闻获取完成: {len(macro_news)} 字符")
        except Exception as e:
            logger.warning(f"[新闻舆情分析师] 宏观新闻获取失败: {e}")

        # 新闻分析师数据 = 个股新闻 + 宏观新闻
        news_data = stock_news
        if macro_news:
            news_data = stock_news + "\n\n---\n\n" + macro_news

        # 生成新闻分析报告（个股+宏观）
        if progress_callback:
            progress_callback("新闻数据已获取，正在生成新闻分析报告...")

        news_report = _generate_report(
            llm, ticker, company_name, current_date, news_data, _NEWS_PROMPT, "新闻分析"
        )

        # 生成舆情分析报告（仅个股新闻）
        if progress_callback:
            progress_callback("正在生成舆情分析报告...")

        sentiment_report = _generate_report(
            llm, ticker, company_name, current_date, stock_news, _SOCIAL_PROMPT, "舆情分析"
        )

        logger.info(f"[新闻舆情分析师] 完成: 新闻报告 {len(news_report)} 字符, 舆情报告 {len(sentiment_report)} 字符")

        return {
            "messages": [AIMessage(content=news_report)],
            "news_report": news_report,
            "sentiment_report": sentiment_report,
            "news_tool_call_count": state.get("news_tool_call_count", 0) + 1,
            "sentiment_tool_call_count": state.get("sentiment_tool_call_count", 0) + 1,
        }

    return news_social_analyst_node


def _generate_report(llm, ticker: str, company_name: str, current_date: str,
                     news_data: str, system_prompt: str, report_type: str) -> str:
    """用同一份新闻数据、不同 prompt 生成报告"""
    try:
        if GoogleToolCallHandler.is_google_model(llm):
            prompt_text = f"""请对 {ticker}（{company_name}）进行{report_type}。

=== 新闻数据 ===
{news_data}

当前日期: {current_date}

{system_prompt}"""
            result = llm.invoke([HumanMessage(content=prompt_text)])
        else:
            prompt = ChatPromptTemplate.from_messages([
                ("system", "{system_prompt}\n\n当前日期: {current_date}。请用中文撰写分析内容。"),
                ("user", "请对 {ticker}（{company_name}）进行{report_type}。\n\n=== 新闻数据 ===\n{news_data}"),
            ])
            chain = prompt | llm
            result = chain.invoke({
                "system_prompt": system_prompt,
                "current_date": current_date,
                "ticker": ticker,
                "company_name": company_name,
                "report_type": report_type,
                "news_data": news_data,
            })

        if hasattr(result, 'content') and result.content:
            return result.content

    except Exception as e:
        logger.error(f"[新闻舆情分析师] {report_type}报告生成失败: {e}")

    return f"{report_type}报告生成失败"
