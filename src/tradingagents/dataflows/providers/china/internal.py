"""
TransMatrix 内部数据源 Provider

通过 transwarp.timelyre.timelyre_public.DatabaseConn 连接 TransMatrix 内部数据库，
提供 A 股行情、K 线、基本面数据。新闻和舆情暂不实现，降级到原有数据源。
"""

import logging
from datetime import datetime, timedelta, date
from typing import Dict, Any, List, Optional, Union

import pandas as pd

from ..base_provider import BaseStockDataProvider
from .internal_code_mapper import to_tm_code, to_internal_code

logger = logging.getLogger(__name__)


class InternalProvider(BaseStockDataProvider):

    def __init__(self):
        super().__init__(provider_name="internal")

    # ==================== 连接管理 ====================

    async def connect(self) -> bool:
        self.connected = self.health_check()
        return self.connected

    def _ensure_connected(self) -> bool:
        if self.connected:
            return True
        try:
            from .internal_queries import health_check
            self.connected = health_check()
            return self.connected
        except Exception as e:
            logger.warning(f"TransMatrix DB 连接失败: {e}")
            return False

    def health_check(self) -> bool:
        try:
            from .internal_queries import health_check as _hc
            ok = _hc()
            self.connected = ok
            return ok
        except Exception as e:
            logger.warning(f"TransMatrix DB 健康检查失败: {e}")
            self.connected = False
            return False

    # ==================== 核心数据接口（BaseStockDataProvider 抽象方法实现） ====================

    async def get_stock_basic_info(self, symbol: str = None) -> Optional[Union[Dict[str, Any], List[Dict[str, Any]]]]:
        if symbol is None:
            return self.get_stock_list()
        return self.get_stock_info(symbol)

    async def get_stock_quotes(self, symbol: str) -> Optional[Dict[str, Any]]:
        return self._get_stock_quotes_sync(symbol)

    async def get_historical_data(
        self,
        symbol: str,
        start_date: Union[str, date],
        end_date: Union[str, date] = None,
    ) -> Optional[pd.DataFrame]:
        return self.get_stock_data(symbol, str(start_date), str(end_date) if end_date else str(start_date))

    # ==================== 股票基本信息 ====================

    def get_stock_info(self, symbol: str) -> dict:
        from .internal_queries import get_stock_info as _get_info
        info = _get_info(symbol)
        if not info:
            return {"code": symbol, "name": f"股票{symbol}", "error": "未找到"}
        info["code"] = to_internal_code(info.get("code", symbol))
        return info

    def get_stock_list(self) -> List[dict]:
        from .internal_queries import get_stock_list
        df = get_stock_list()
        df["code"] = df["code"].apply(to_internal_code)
        return df.to_dict("records")

    # ==================== K 线数据 ====================

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        from .internal_queries import get_daily_kline
        df = get_daily_kline(symbol, start_date, end_date)
        if df.empty:
            logger.warning(f"TransMatrix 无 K 线数据: {symbol}，降级 AKShare")
            return self._fallback_akshare_kline(symbol, start_date, end_date)
        return self._standardize_kline(df)

    # ==================== 实时行情 ====================

    def _get_stock_quotes_sync(self, symbol: str) -> dict:
        from .internal_queries import get_snapshot
        snap = get_snapshot(symbol)
        if not snap:
            return {}
        snap["code"] = to_internal_code(snap.get("code", symbol))
        return {
            "code": snap["code"],
            "close": snap.get("last_price"),
            "open": snap.get("open"),
            "high": snap.get("high"),
            "low": snap.get("low"),
            "pre_close": snap.get("pre_close"),
            "volume": snap.get("volume"),
            "amount": snap.get("turnover"),
            "limit_up": snap.get("limit_up"),
            "limit_down": snap.get("limit_down"),
        }

    # ==================== 基本面（估值+财务指标+三大表） ====================

    def get_fundamentals(self, symbol: str) -> str:
        tm_code = to_tm_code(symbol)

        try:
            from .internal_queries import (
                get_stock_info,
                get_valuation,
                get_finance_indicator,
                get_income,
                get_balance,
                get_cashflow,
                get_dividend,
            )

            info = get_stock_info(symbol) or {}
            val = get_valuation(symbol) or {}
            fi = get_finance_indicator(symbol, limit=1)
            fi_row = fi.iloc[0].to_dict() if not fi.empty else {}

            report = f"{symbol} 基本面分析（TransMatrix 数据源）\n\n"
            report += f"股票名称: {info.get('name', '未知')}\n"
            report += f"所属行业: {info.get('industry', '未知')}\n"
            report += f"所属地区: {info.get('area', '未知')}\n"
            report += f"上市日期: {info.get('list_date', '未知')}\n\n"

            report += "估值指标:\n"
            if val:
                report += f"   总市值: {val.get('market_cap', 'N/A')}亿元\n"
                report += f"   流通市值: {val.get('circulating_market_cap', 'N/A')}亿元\n"
                report += f"   PE(TTM): {val.get('pe_ratio', 'N/A')}\n"
                report += f"   PE(LYR): {val.get('pe_ratio_lyr', 'N/A')}\n"
                report += f"   PB: {val.get('pb_ratio', 'N/A')}\n"
                report += f"   PS(TTM): {val.get('ps_ratio', 'N/A')}\n"
                report += f"   PCF(TTM): {val.get('pcf_ratio', 'N/A')}\n"
                report += f"   换手率: {val.get('turnover_ratio', 'N/A')}%\n"
                report += f"   总股本: {val.get('capitalization', 'N/A')}万股\n"
                report += f"   流通股本: {val.get('circulating_cap', 'N/A')}万股\n"
            report += "\n"

            if fi_row:
                report += "盈利能力:\n"
                report += f"   EPS: {fi_row.get('eps', 'N/A')}\n"
                report += f"   ROE: {fi_row.get('roe', 'N/A')}\n"
                report += f"   ROA: {fi_row.get('roa', 'N/A')}\n"
                report += f"   净利率: {fi_row.get('net_profit_margin', 'N/A')}\n"
                report += f"   毛利率: {fi_row.get('gross_profit_margin', 'N/A')}\n"
                report += "\n成长能力:\n"
                report += f"   营收同比增长: {fi_row.get('inc_revenue_year_on_year', 'N/A')}%\n"
                report += f"   净利润同比增长: {fi_row.get('inc_net_profit_year_on_year', 'N/A')}%\n"
                report += f"   营业利润同比增长: {fi_row.get('inc_operation_profit_year_on_year', 'N/A')}%\n"
                report += "\n"

            div_df = get_dividend(symbol, limit=3)
            if not div_df.empty:
                report += "近期分红:\n"
                for _, row in div_df.iterrows():
                    report += f"   {row.get('report_date', 'N/A')}: {row.get('implementation_bonusnote', 'N/A')}\n"
                report += "\n"

            return report

        except Exception as e:
            logger.error(f"TransMatrix 基本面获取失败: {e}")
            return f"获取{symbol}基本面数据失败: {e}"

    async def get_financial_data(self, symbol: str, report_type: str = "annual") -> Optional[Dict[str, Any]]:
        report = self.get_fundamentals(symbol)
        return {"symbol": symbol, "report": report, "report_type": report_type}

    # ==================== 资金流向（增强数据） ====================

    def get_money_flow(self, symbol: str, start_date: str, end_date: str) -> str:
        from .internal_queries import get_money_flow
        df = get_money_flow(symbol, start_date, end_date)
        if df.empty:
            return ""
        latest = df.iloc[-1]
        report = f"{symbol} 资金流向 ({latest.get('trade_day', '')})\n\n"
        report += f"   涨跌幅: {latest.get('change_pct', 'N/A')}%\n"
        report += f"   主力净额: {latest.get('net_amount_main', 'N/A')}万\n"
        report += f"   主力净占比: {latest.get('net_pct_main', 'N/A')}%\n"
        report += f"   超大单净额: {latest.get('net_amount_xl', 'N/A')}万\n"
        report += f"   大单净额: {latest.get('net_amount_l', 'N/A')}万\n"
        report += f"   中单净额: {latest.get('net_amount_m', 'N/A')}万\n"
        report += f"   小单净额: {latest.get('net_amount_s', 'N/A')}万\n"
        return report

    # ==================== 全市场快照（筛选） ====================

    def get_market_snapshot(self) -> Optional[pd.DataFrame]:
        from .internal_queries import get_market_snapshot
        return get_market_snapshot()

    # ==================== 内部工具方法 ====================

    def _standardize_kline(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        df = df.copy()
        df["code"] = df["code"].apply(to_internal_code)
        df = df.rename(columns={
            "trade_day": "date",
            "volume": "vol",
            "turnover": "amount",
        })
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date")
        if "pct_change" not in df.columns and "close" in df.columns:
            df["pct_change"] = df["close"].pct_change() * 100.0
        return df

    def _fallback_akshare_kline(self, symbol, start_date, end_date):
        try:
            from .akshare import get_akshare_provider
            import asyncio
            provider = get_akshare_provider()
            try:
                loop = asyncio.get_event_loop()
                if loop.is_closed():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            data = loop.run_until_complete(
                provider.get_historical_data(symbol, start_date, end_date)
            )
            return data if data is not None else pd.DataFrame()
        except Exception as e:
            logger.warning(f"AKShare K 线降级失败: {e}")
            return pd.DataFrame()


_internal_provider = None


def get_internal_provider() -> InternalProvider:
    global _internal_provider
    if _internal_provider is None:
        _internal_provider = InternalProvider()
    return _internal_provider
