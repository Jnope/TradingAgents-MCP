from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import AIMessage, HumanMessage
from datetime import datetime

from tradingagents.utils.logging_init import get_logger
from tradingagents.utils.tool_logging import log_analyst_module
from tradingagents.tools.unified_news_tool import UnifiedNewsAnalyzer
from tradingagents.utils.stock_utils import StockUtils
from tradingagents.agents.utils.google_tool_handler import GoogleToolCallHandler

logger = get_logger("analysts.news")


_NEWS_PROMPT = """您是一位专业的财经新闻分析师，负责分析最新的市场新闻和事件对股票价格的潜在影响。

您的主要职责包括：
1. 分析最新的实时新闻（优先15-30分钟内的新闻）
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
- 管理层变动和战略调整

分析要点：
- 新闻的时效性（发布时间距离现在多久）
- 新闻的可信度（来源权威性）
- 市场影响程度（对股价的潜在影响）
- 投资者情绪变化（正面/负面/中性）
- 与历史类似事件的对比

📊 新闻影响分析要求：
- 评估新闻对股价的短期影响（1-3天）和市场情绪变化
- 分析新闻的利好/利空程度和可能的市场反应
- 评估新闻对公司基本面和长期投资价值的影响
- 识别新闻中的关键信息点和潜在风险
- 对比历史类似事件的市场反应
- 不允许回复'无法评估影响'或'需要更多信息'

请特别注意：
⚠️ 如果新闻数据存在滞后（超过2小时），请在分析中明确说明时效性限制
✅ 优先分析最新的、高相关性的新闻事件
📊 提供新闻对市场情绪和投资者信心的影响评估
💰 必须包含基于新闻的市场反应预期和投资建议
🎯 聚焦新闻内容本身的解读，不涉及技术指标分析

请撰写详细的中文分析报告，并在报告末尾附上Markdown表格总结关键发现。"""


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
        logger.error(f"[新闻分析师] 获取公司名称失败: {e}")
        return f"股票{ticker}"


def create_news_analyst(llm, toolkit, progress_callback=None):
    @log_analyst_module("news")
    def news_analyst_node(state):
        start_time = datetime.now()
        tool_call_count = state.get("news_tool_call_count", 0)
        current_date = state["trade_date"]
        ticker = state["company_of_interest"]

        if progress_callback:
            progress_callback("正在获取新闻数据...")

        logger.info(f"[新闻分析师] 开始分析 {ticker} 的新闻，交易日期: {current_date}")

        market_info = StockUtils.get_market_info(ticker)
        company_name = _get_company_name(ticker, market_info)
        logger.info(f"[新闻分析师] 公司名称: {company_name}")

        analyzer = UnifiedNewsAnalyzer(toolkit)
        stock_news = ""
        try:
            stock_news = analyzer.get_stock_news_unified(stock_code=ticker, max_news=10, model_info="", trade_date=current_date)
        except Exception as e:
            logger.error(f"[新闻分析师] 新闻获取失败: {e}")

        if not stock_news or len(stock_news.strip()) <= 100:
            logger.warning(f"[新闻分析师] 新闻数据不足")
            stock_news = f"未能获取到 {ticker}（{company_name}）的有效新闻数据，请基于已知信息进行分析。"

        if progress_callback:
            progress_callback("新闻数据已获取，正在生成分析报告...")

        try:
            if GoogleToolCallHandler.is_google_model(llm):
                analysis_prompt = f"""请对 {ticker}（{company_name}）进行新闻分析。

=== 新闻数据 ===
{stock_news}

当前日期: {current_date}

{_NEWS_PROMPT}"""
                result = llm.invoke([HumanMessage(content=analysis_prompt)])
            else:
                prompt = ChatPromptTemplate.from_messages([
                    ("system", "{system_prompt}\n\n当前日期: {current_date}。请用中文撰写分析内容。"),
                    ("user", "请对 {ticker}（{company_name}）进行新闻分析。\n\n=== 新闻数据 ===\n{stock_news}"),
                ])
                chain = prompt | llm
                result = chain.invoke({
                    "system_prompt": _NEWS_PROMPT,
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
            logger.error(f"[新闻分析师] 报告生成失败: {e}")
            report = f"新闻分析报告生成失败: {e}"

        end_time = datetime.now()
        time_taken = (end_time - start_time).total_seconds()
        logger.info(f"[新闻分析师] 新闻分析完成，总耗时: {time_taken:.2f}秒")

        return {
            "messages": [AIMessage(content=report)],
            "news_report": report,
            "news_tool_call_count": tool_call_count + 1
        }

    return news_analyst_node
