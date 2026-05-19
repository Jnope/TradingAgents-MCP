from mcp.server.fastmcp import FastMCP


def register_prompts(mcp: FastMCP):

    @mcp.prompt(title="股票分析")
    def stock_analysis_prompt(symbol: str, trade_date: str) -> str:
        return (
            f"请对股票 {symbol} 进行全面分析，交易日为 {trade_date}。\n"
            "使用 trading_agent 工具执行完整分析流程。\n"
            "全流程需要3-10分钟，分析完成后基于返回的报告和决策给出综合解读。"
        )

    @mcp.prompt(title="技术面分析")
    def technical_analysis_prompt(symbol: str, trade_date: str) -> str:
        return (
            f"请分析 {symbol} 的技术面，交易日 {trade_date}。\n"
            "使用 market_analyst 工具获取技术分析报告，大约需要30秒。"
        )

    @mcp.prompt(title="基本面分析")
    def fundamentals_prompt(symbol: str, trade_date: str) -> str:
        return (
            f"请分析 {symbol} 的基本面，交易日 {trade_date}。\n"
            "使用 fundamentals_analyst 工具获取估值和财务分析报告。"
        )

    @mcp.prompt(title="A股分析")
    def china_stock_prompt(stock_code: str, trade_date: str) -> str:
        return (
            f"请分析A股 {stock_code}，交易日 {trade_date}。\n"
            "使用 trading_agent 工具，A股会自动使用中文数据源。"
        )

    @mcp.prompt(title="对比分析")
    def compare_stocks_prompt(symbols: str, trade_date: str) -> str:
        return (
            f"请对比分析以下股票：{symbols}，交易日 {trade_date}。\n"
            "使用 compare_stocks 工具进行多股横向对比和排名推荐。"
        )

    @mcp.prompt(title="区间走势分析")
    def period_compare_prompt(symbol: str, start_date: str, end_date: str) -> str:
        return (
            f"请分析 {symbol} 在 {start_date} 至 {end_date} 期间的走势表现。\n"
            "使用 period_compare 工具获取区间统计数据和走势分析报告。\n"
            "如需与基准对比，可传入 compare_with 参数（如沪深300代码 '000300'）。"
        )

    @mcp.prompt(title="股票筛选")
    def screen_stocks_prompt(description: str) -> str:
        return (
            f"请根据以下描述筛选股票：{description}\n"
            "使用 screen_stocks 工具，将描述转换为筛选条件后执行。\n"
            "例如：'低估值银行股' → conditions=[{field:'pe',operator:'between',value:[4,10]},{field:'industry',operator:'in',value:['银行']}]"
        )
