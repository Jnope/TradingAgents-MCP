#!/usr/bin/env python3
"""
统一新闻分析工具
整合A股、港股、美股等不同市场的新闻获取逻辑到一个工具函数中
让大模型只需要调用一个工具就能获取所有类型股票的新闻数据
"""

import logging
from datetime import datetime, timedelta
import re

logger = logging.getLogger(__name__)

class UnifiedNewsAnalyzer:
    """统一新闻分析器，整合所有新闻获取逻辑"""
    
    def __init__(self, toolkit):
        """初始化统一新闻分析器
        
        Args:
            toolkit: 包含各种新闻获取工具的工具包
        """
        self.toolkit = toolkit
        
    def get_stock_news_unified(self, stock_code: str, max_news: int = 10, model_info: str = "", trade_date: str = "") -> str:
        """
        统一新闻获取接口（个股新闻 + 宏观新闻）
        """
        return self._fetch_combined(stock_code, max_news, model_info, include_macro=True, trade_date=trade_date)

    def get_stock_news_only(self, stock_code: str, max_news: int = 10, model_info: str = "", trade_date: str = "") -> str:
        """
        仅获取个股新闻（不含宏观新闻）
        """
        return self._fetch_combined(stock_code, max_news, model_info, include_macro=False, trade_date=trade_date)

    def _fetch_combined(self, stock_code: str, max_news: int, model_info: str, include_macro: bool, trade_date: str = "") -> str:
        logger.info(f"[统一新闻工具] 开始获取 {stock_code} 的新闻，模型: {model_info}，包含宏观: {include_macro}，日期: {trade_date}")
        
        stock_type = self._identify_stock_type(stock_code)
        logger.info(f"[统一新闻工具] 股票类型: {stock_type}")
        
        if stock_type == "A股":
            result = self._get_a_share_news(stock_code, max_news, model_info, include_macro=include_macro, trade_date=trade_date)
        elif stock_type == "港股":
            result = self._get_hk_share_news(stock_code, max_news, model_info, include_macro=include_macro, trade_date=trade_date)
        elif stock_type == "美股":
            result = self._get_us_share_news(stock_code, max_news, model_info, trade_date=trade_date)
        else:
            result = self._get_a_share_news(stock_code, max_news, model_info, include_macro=include_macro, trade_date=trade_date)
        
        logger.info(f"[统一新闻工具] 新闻获取完成，结果长度: {len(result)} 字符")
        
        if not result or len(result.strip()) < 50:
            logger.warning(f"[统一新闻工具] 返回结果异常短或为空！")
        
        return result
    
    def _identify_stock_type(self, stock_code: str) -> str:
        """识别股票类型"""
        stock_code = stock_code.upper().strip()
        
        # A股判断
        if re.match(r'^(00|30|60|68)\d{4}$', stock_code):
            return "A股"
        elif re.match(r'^(SZ|SH)\d{6}$', stock_code):
            return "A股"
        
        # 港股判断
        elif re.match(r'^\d{4,5}\.HK$', stock_code):
            return "港股"
        elif re.match(r'^\d{4,5}$', stock_code) and len(stock_code) <= 5:
            return "港股"
        
        # 美股判断
        elif re.match(r'^[A-Z]{1,5}$', stock_code):
            return "美股"
        elif '.' in stock_code and not stock_code.endswith('.HK'):
            return "美股"
        
        # 默认按A股处理
        else:
            return "A股"

    def _get_cctv_macro_news(self, trade_date: str = "") -> str:
        """获取央视财经宏观新闻"""
        try:
            import akshare as ak
            base = datetime.strptime(trade_date, "%Y-%m-%d") if trade_date else datetime.now()
            news_df = None
            for offset in range(3):
                d = base - timedelta(days=offset)
                try:
                    news_df = ak.news_cctv(date=d.strftime("%Y%m%d"))
                    if news_df is not None and not news_df.empty:
                        break
                except Exception:
                    continue
            if news_df is None or news_df.empty:
                return ""
            news_str = ""
            count = 0
            for _, row in news_df.iterrows():
                title = str(row.get("title", "") or row.get("标题", ""))
                content = str(row.get("content", "") or row.get("内容", ""))
                url = str(row.get("url", "") or row.get("链接", ""))
                if not title:
                    continue
                news_str += f"### {title}\n"
                if content:
                    summary = content[:200] + "..." if len(content) > 200 else content
                    news_str += f"{summary}\n"
                if url:
                    news_str += f"链接: {url}\n"
                news_str += "\n"
                count += 1
                if count >= 10:
                    break
            if count == 0:
                return ""
            return f"## 宏观新闻（央视财经）\n\n{news_str}"
        except Exception as e:
            logger.warning(f"[统一新闻工具] 央视财经宏观新闻获取失败: {e}")
            return ""

    def _get_stock_news_akshare(self, stock_code: str) -> str:
        """toolkit 不可用时，直接用 AKShare 获取个股新闻"""
        try:
            import akshare as ak
            clean_code = stock_code.replace('.SH', '').replace('.SZ', '').replace('.SS', '')\
                           .replace('.XSHE', '').replace('.XSHG', '').replace('.HK', '').replace('.hk', '')
            code = clean_code[:6].zfill(6)
            news_df = ak.stock_news_em(symbol=code)
            if news_df is None or news_df.empty:
                return ""
            news_str = ""
            count = 0
            for _, row in news_df.iterrows():
                title = str(row.get('新闻标题', '') or row.get('标题', ''))
                content = str(row.get('新闻内容', '') or row.get('内容', ''))
                source = str(row.get('文章来源', '') or row.get('来源', ''))
                pub_time = str(row.get('发布时间', '') or row.get('时间', ''))
                url = str(row.get('新闻链接', '') or row.get('链接', ''))
                if not title:
                    continue
                news_str += f"### {title}\n"
                news_str += f"来源: {source} | 时间: {pub_time}\n"
                if content:
                    summary = content[:200] + "..." if len(content) > 200 else content
                    news_str += f"{summary}\n"
                if url:
                    news_str += f"链接: {url}\n"
                news_str += "\n"
                count += 1
                if count >= 10:
                    break
            return news_str if count > 0 else ""
        except Exception as e:
            logger.warning(f"[统一新闻工具] AKShare个股新闻获取失败: {e}")
            return ""

    def _get_a_share_news(self, stock_code: str, max_news: int, model_info: str = "", include_macro: bool = True, trade_date: str = "") -> str:
        """获取A股新闻（个股新闻，可选宏观新闻）"""
        logger.info(f"[统一新闻工具] 获取A股 {stock_code} 新闻")
        curr_date = trade_date if trade_date else datetime.now().strftime("%Y-%m-%d")
        sections = []

        # 1. 东方财富个股新闻
        try:
            if self.toolkit and hasattr(self.toolkit, 'get_realtime_stock_news'):
                logger.info(f"[统一新闻工具] 尝试东方财富实时新闻...")
                result = self.toolkit.get_realtime_stock_news.invoke({"ticker": stock_code, "curr_date": curr_date})
                if result and len(result.strip()) > 100:
                    logger.info(f"[统一新闻工具] ✅ 东方财富新闻获取成功: {len(result)} 字符")
                    sections.append(result)
                else:
                    logger.warning(f"[统一新闻工具] ⚠️ 东方财富新闻内容过短或为空")
            else:
                akshare_news = self._get_stock_news_akshare(stock_code)
                if akshare_news:
                    sections.append(akshare_news)
        except Exception as e:
            logger.warning(f"[统一新闻工具] 东方财富新闻获取失败: {e}")
            akshare_news = self._get_stock_news_akshare(stock_code)
            if akshare_news:
                sections.append(akshare_news)

        # 2. 央视财经宏观新闻（可选）
        if include_macro:
            cctv_news = self._get_cctv_macro_news(trade_date=trade_date)
            if cctv_news:
                sections.append(cctv_news)

        if sections:
            combined = "\n\n---\n\n".join(sections)
            source_label = "东方财富个股新闻+央视宏观新闻" if include_macro else "东方财富个股新闻"
            return self._format_news_result(combined, source_label, model_info)

        return "❌ 无法获取A股新闻数据，东方财富新闻源不可用"
    
    def _get_hk_share_news(self, stock_code: str, max_news: int, model_info: str = "", include_macro: bool = True, trade_date: str = "") -> str:
        """获取港股新闻（个股新闻，可选宏观新闻）"""
        logger.info(f"[统一新闻工具] 获取港股 {stock_code} 新闻")
        curr_date = trade_date if trade_date else datetime.now().strftime("%Y-%m-%d")
        sections = []

        # 1. 东方财富个股新闻
        try:
            if self.toolkit and hasattr(self.toolkit, 'get_realtime_stock_news'):
                logger.info(f"[统一新闻工具] 尝试东方财富港股新闻...")
                result = self.toolkit.get_realtime_stock_news.invoke({"ticker": stock_code, "curr_date": curr_date})
                if result and len(result.strip()) > 100:
                    logger.info(f"[统一新闻工具] ✅ 东方财富港股新闻获取成功: {len(result)} 字符")
                    sections.append(result)
            else:
                akshare_news = self._get_stock_news_akshare(stock_code)
                if akshare_news:
                    sections.append(akshare_news)
        except Exception as e:
            logger.warning(f"[统一新闻工具] 东方财富港股新闻获取失败: {e}")
            akshare_news = self._get_stock_news_akshare(stock_code)
            if akshare_news:
                sections.append(akshare_news)

        # 2. 央视财经宏观新闻（可选）
        if include_macro:
            cctv_news = self._get_cctv_macro_news(trade_date=trade_date)
            if cctv_news:
                sections.append(cctv_news)

        if sections:
            combined = "\n\n---\n\n".join(sections)
            source_label = "东方财富港股新闻+央视宏观新闻" if include_macro else "东方财富港股新闻"
            return self._format_news_result(combined, source_label, model_info)
        
        return "❌ 无法获取港股新闻数据，东方财富新闻源不可用"
    
    def _get_us_share_news(self, stock_code: str, max_news: int, model_info: str = "", trade_date: str = "") -> str:
        """获取美股新闻"""
        logger.info(f"[统一新闻工具] 获取美股 {stock_code} 新闻")
        curr_date = trade_date if trade_date else datetime.now().strftime("%Y-%m-%d")
        
        # FinnHub个股新闻
        try:
            if hasattr(self.toolkit, 'get_finnhub_news'):
                logger.info(f"[统一新闻工具] 尝试FinnHub美股新闻...")
                result = self.toolkit.get_finnhub_news.invoke({"symbol": stock_code, "max_results": min(max_news, 50)})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ FinnHub美股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "FinnHub美股新闻", model_info)
        except Exception as e:
            logger.warning(f"[统一新闻工具] FinnHub美股新闻获取失败: {e}")
        
        # Google新闻（英文搜索）
        try:
            if hasattr(self.toolkit, 'get_google_news'):
                logger.info(f"[统一新闻工具] 尝试Google美股新闻...")
                query = f"{stock_code} stock news earnings financial"
                result = self.toolkit.get_google_news.invoke({"query": query, "curr_date": curr_date})
                if result and len(result.strip()) > 50:
                    logger.info(f"[统一新闻工具] ✅ Google美股新闻获取成功: {len(result)} 字符")
                    return self._format_news_result(result, "Google美股新闻", model_info)
        except Exception as e:
            logger.warning(f"[统一新闻工具] Google美股新闻获取失败: {e}")
        
        return "❌ 无法获取美股新闻数据，所有新闻源均不可用"
    
    def _format_news_result(self, news_content: str, source: str, model_info: str = "") -> str:
        """格式化新闻结果"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 🔍 添加调试日志：打印原始新闻内容
        logger.info(f"[统一新闻工具] 📋 原始新闻内容预览 (前500字符): {news_content[:500]}")
        logger.info(f"[统一新闻工具] 📊 原始内容长度: {len(news_content)} 字符")
        
        # 检测是否为Google/Gemini模型
        is_google_model = any(keyword in model_info.lower() for keyword in ['google', 'gemini', 'gemma'])
        original_length = len(news_content)
        google_control_applied = False
        
        # 🔍 添加Google模型检测日志
        if is_google_model:
            logger.info(f"[统一新闻工具] 🤖 检测到Google模型，启用特殊处理")
        
        # 对Google模型进行特殊的长度控制
        if is_google_model and len(news_content) > 5000:  # 降低阈值到5000字符
            logger.warning(f"[统一新闻工具] 🔧 检测到Google模型，新闻内容过长({len(news_content)}字符)，进行长度控制...")
            
            # 更严格的长度控制策略
            lines = news_content.split('\n')
            important_lines = []
            char_count = 0
            target_length = 3000  # 目标长度设为3000字符
            
            # 第一轮：优先保留包含关键词的重要行
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                # 检查是否包含重要关键词
                important_keywords = ['股票', '公司', '财报', '业绩', '涨跌', '价格', '市值', '营收', '利润', 
                                    '增长', '下跌', '上涨', '盈利', '亏损', '投资', '分析', '预期', '公告']
                
                is_important = any(keyword in line for keyword in important_keywords)
                
                if is_important and char_count + len(line) < target_length:
                    important_lines.append(line)
                    char_count += len(line)
                elif not is_important and char_count + len(line) < target_length * 0.7:  # 非重要内容更严格限制
                    important_lines.append(line)
                    char_count += len(line)
                
                # 如果已达到目标长度，停止添加
                if char_count >= target_length:
                    break
            
            # 如果提取的重要内容仍然过长，进行进一步截断
            if important_lines:
                processed_content = '\n'.join(important_lines)
                if len(processed_content) > target_length:
                    processed_content = processed_content[:target_length] + "...(内容已智能截断)"
                
                news_content = processed_content
                google_control_applied = True
                logger.info(f"[统一新闻工具] ✅ Google模型智能长度控制完成，从{original_length}字符压缩至{len(news_content)}字符")
            else:
                # 如果没有重要行，直接截断到目标长度
                news_content = news_content[:target_length] + "...(内容已强制截断)"
                google_control_applied = True
                logger.info(f"[统一新闻工具] ⚠️ Google模型强制截断至{target_length}字符")
        
        # 计算最终的格式化结果长度，确保总长度合理
        base_format_length = 300  # 格式化模板的大概长度
        if is_google_model and (len(news_content) + base_format_length) > 4000:
            # 如果加上格式化后仍然过长，进一步压缩新闻内容
            max_content_length = 3500
            if len(news_content) > max_content_length:
                news_content = news_content[:max_content_length] + "...(已优化长度)"
                google_control_applied = True
                logger.info(f"[统一新闻工具] 🔧 Google模型最终长度优化，内容长度: {len(news_content)}字符")
        
        formatted_result = f"""
=== 📰 新闻数据来源: {source} ===
获取时间: {timestamp}
数据长度: {len(news_content)} 字符
{f"模型类型: {model_info}" if model_info else ""}
{f"🔧 Google模型长度控制已应用 (原长度: {original_length} 字符)" if google_control_applied else ""}

=== 📋 新闻内容 ===
{news_content}

=== ✅ 数据状态 ===
状态: 成功获取
来源: {source}
时间戳: {timestamp}
"""
        return formatted_result.strip()


def create_unified_news_tool(toolkit):
    """创建统一新闻工具函数"""
    analyzer = UnifiedNewsAnalyzer(toolkit)
    
    def get_stock_news_unified(stock_code: str, max_news: int = 100, model_info: str = "", trade_date: str = ""):
        """
        统一新闻获取工具
        
        Args:
            stock_code (str): 股票代码 (支持A股如000001、港股如0700.HK、美股如AAPL)
            max_news (int): 最大新闻数量，默认100
            model_info (str): 当前使用的模型信息，用于特殊处理
            trade_date (str): 交易日期 YYYY-MM-DD，默认空字符串表示当天
        
        Returns:
            str: 格式化的新闻内容
        """
        if not stock_code:
            return "❌ 错误: 未提供股票代码"
        
        return analyzer.get_stock_news_unified(stock_code, max_news, model_info, trade_date=trade_date)
    
    # 设置工具属性
    get_stock_news_unified.name = "get_stock_news_unified"
    get_stock_news_unified.description = """
统一新闻获取工具 - 根据股票代码自动获取相应市场的新闻

功能:
- 自动识别股票类型（A股/港股/美股）
- 根据股票类型选择最佳新闻源
- A股: 优先东方财富 -> Google中文 -> OpenAI
- 港股: 优先Google -> OpenAI -> 实时新闻
- 美股: 优先OpenAI -> Google英文 -> FinnHub
- 返回格式化的新闻内容
- 支持Google模型的特殊长度控制
"""
    
    return get_stock_news_unified


def create_unified_social_tool(toolkit):
    """创建统一新闻工具函数"""
    analyzer = UnifiedNewsAnalyzer(toolkit)

    def get_stock_news_only(stock_code: str, max_news: int = 100, model_info: str = "", trade_date: str = ""):
        """
        统一新闻获取工具

        Args:
            stock_code (str): 股票代码 (支持A股如000001、港股如0700.HK、美股如AAPL)
            max_news (int): 最大新闻数量，默认100
            model_info (str): 当前使用的模型信息，用于特殊处理
            trade_date (str): 交易日期 YYYY-MM-DD，默认空字符串表示当天

        Returns:
            str: 格式化的新闻内容
        """
        if not stock_code:
            return "❌ 错误: 未提供股票代码"

        return analyzer.get_stock_news_only(stock_code, max_news, model_info, trade_date=trade_date)

    # 设置工具属性
    get_stock_news_only.name = "get_stock_news_only"
    get_stock_news_only.description = """
统一新闻获取工具（仅个股新闻，不含宏观新闻） - 根据股票代码自动获取相应市场的新闻
"""

    return get_stock_news_only