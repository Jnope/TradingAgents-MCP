"""
TransMatrix 内部数据库 SQL 查询封装

通过 transwarp.timelyre.timelyre_public.DatabaseConn 连接内部数据库，
使用 JDBC HTTP Proxy 执行 SQL 查询。
"""

import os
import logging
import re
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

from .internal_code_mapper import to_tm_code

logger = logging.getLogger(__name__)


def _date_start(date_str: str) -> str:
    return f"{date_str} 00:00:00"


def _date_end(date_str: str) -> str:
    dt = datetime.strptime(date_str, "%Y-%m-%d") + timedelta(days=1)
    return f"{dt.strftime('%Y-%m-%d')} 00:00:00"

_db_conn = None


def _get_db_conn():
    """获取/创建 DatabaseConn 单例"""
    global _db_conn
    if _db_conn is not None:
        return _db_conn

    try:
        from transwarp.timelyre.timelyre_public import DatabaseConn
    except ImportError:
        raise ImportError(
            "transwarp-timelyre 未安装，无法连接内部数据库。"
            "请联系管理员安装或切换到其他数据源。"
        )

    jdbc_http_proxy = os.environ.get("JDBC_HTTP_PROXY", "172.18.192.74:9998")
    real_conn = os.environ.get(
        "TM_REAL_CONN", "jdbc:hive2://172.18.192.75:10006"
    )
    db_name = os.environ.get("TM_DB_NAME", "meta_data")
    db_user = os.environ.get("TM_DB_USER", "admin")
    password = os.environ.get("TM_DB_PASSWORD", "admin")
    token = os.environ.get("GUARDIAN_TOKEN", "UgJRRGe7qMAKcirOQ017-TDH")

    try:
        _db_conn = DatabaseConn(
            jdbc_http_proxy=jdbc_http_proxy,
            real_conn=real_conn,
            db=db_name,
            auth_type="ldap",
            username=db_user,
            password=password,
            token=token,
            disable_cancel=True,
        )
        logger.info("TransMatrix DatabaseConn 初始化成功")
        return _db_conn
    except Exception as e:
        logger.error(f"DatabaseConn初始化失败: {e}")
        raise e



def _extract_table_name(sql: str) -> str:
    m = re.search(r'\bFROM\s+`?(\w+)`?', sql, re.IGNORECASE)
    return m.group(1) if m else ""


def query(sql: str, table: str = "") -> pd.DataFrame:
    """
    执行 SQL 查询并返回 DataFrame

    使用 DatabaseConn.query_as_df() 方法，第一个参数为表名，query 参数为完整 SQL。

    Args:
        sql: SQL 查询语句
        table: 表名，未传入时自动从 SQL 中提取

    Returns:
        查询结果 DataFrame
    """
    conn = _get_db_conn()
    table_name = table or _extract_table_name(sql)
    try:
        result = conn.query_as_df(table_name, query=sql, combine_ignore_index=True)
        if result is None:
            return pd.DataFrame()
        if isinstance(result, pd.DataFrame):
            return result
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"TransMatrix SQL 查询失败: {e}\nSQL: {sql[:200]}")
        raise e


def health_check() -> bool:
    try:
        conn = _get_db_conn()
        conn.show_databases()
        return True
    except Exception as e:
        logger.warning(f"TransMatrix DB 健康检查失败: {e}")
        return False


# ==================== 股票基本信息 ====================

def get_stock_info(symbol: str) -> Optional[dict]:
    tm_code = to_tm_code(symbol)
    df = query(f"SELECT * FROM stock_code WHERE code = '{tm_code}'", table="stock_code")
    return df.iloc[0].to_dict() if not df.empty else None


def get_stock_list() -> pd.DataFrame:
    return query("SELECT * FROM stock_code WHERE delist_date IS NULL", table="stock_code")


def get_sw_industry(symbol: str) -> Optional[dict]:
    tm_code = to_tm_code(symbol)
    df = query(
        f"SELECT * FROM sw_industry WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT 1",
        table="sw_industry",
    )
    return df.iloc[0].to_dict() if not df.empty else None


# ==================== K 线数据 ====================

def get_daily_kline(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT `trade_day`, `open`, `high`, `low`, `close`, `volume`, `turnover`, `vwap`, `factor` "
        f"FROM `stock_bar_1day` "
        f"WHERE `code` = '{tm_code}' AND `datetime` >= '{_date_start(start_date)}' AND `datetime` < '{_date_end(end_date)}' ",
        table="stock_bar_1day",
    )


def get_minute_kline(symbol: str, freq: str = "1min",
                     start_date: str = None, end_date: str = None) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    table_map = {
        "1min": "stock_bar_1min",
        "5min": "stock_bar_5min",
        "10min": "stock_bar_10min",
        "30min": "stock_bar_30min",
        "60min": "stock_bar_60min",
    }
    table = table_map.get(freq, "stock_bar_1min")
    where = f"WHERE code = '{tm_code}'"
    if start_date:
        where += f" AND datetime >= '{_date_start(start_date)}'"
    if end_date:
        where += f" AND datetime < '{_date_end(end_date)}'"
    return query(
        f"SELECT code, trade_day, trade_time, open, high, low, close, volume, turnover, vwap "
        f"FROM {table} {where} ORDER BY trade_day, trade_time",
        table=table,
    )


# ==================== 实时快照 ====================

def get_snapshot(symbol: str) -> Optional[dict]:
    tm_code = to_tm_code(symbol)
    df = query(
        f"SELECT * FROM stock_snapshot WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT 1",
        table="stock_snapshot",
    )
    return df.iloc[0].to_dict() if not df.empty else None


def get_all_snapshots(trade_day: str) -> pd.DataFrame:
    return query(
        f"SELECT * FROM stock_snapshot WHERE datetime >= '{_date_start(trade_day)}' AND datetime < '{_date_end(trade_day)}'",
        table="stock_snapshot",
    )


# ==================== 估值数据 ====================

def get_valuation(symbol: str, trade_day: str = None) -> Optional[dict]:
    tm_code = to_tm_code(symbol)
    if trade_day:
        df = query(
            f"SELECT * FROM capital WHERE code = '{tm_code}' "
            f"AND datetime < '{_date_end(trade_day)}' ORDER BY datetime DESC LIMIT 1",
            table="capital",
        )
    else:
        df = query(
            f"SELECT * FROM capital WHERE code = '{tm_code}' "
            f"ORDER BY datetime DESC LIMIT 1",
            table="capital",
        )
    return df.iloc[0].to_dict() if not df.empty else None


# ==================== 财务指标 ====================

def get_finance_indicator(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM finance_indicator WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}",
        table="finance_indicator",
    )


# ==================== 三大财务报表 ====================

def get_balance(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM balance WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}",
        table="balance",
    )


def get_income(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM income WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}",
        table="income",
    )


def get_cashflow(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM cashflow WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}",
        table="cashflow",
    )


# ==================== 资金流向 ====================

def get_money_flow(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM stock_money_flow "
        f"WHERE code = '{tm_code}' AND datetime >= '{_date_start(start_date)}' AND datetime < '{_date_end(end_date)}' "
        f"ORDER BY trade_day",
        table="stock_money_flow",
    )


# ==================== 股东数据 ====================

def get_top10_shareholders(symbol: str, limit: int = 2) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM shareholders_top10 WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit * 10}",
        table="shareholders_top10",
    )


def get_shareholder_num(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM shareholder_num WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}",
        table="shareholder_num",
    )


# ==================== 分红配股 ====================

def get_dividend(symbol: str, limit: int = 5) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM dividend_allocation WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}",
        table="dividend_allocation",
    )


# ==================== 指数数据 ====================

def get_index_kline(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    return query(
        f"SELECT * FROM index_bar_1day "
        f"WHERE code = '{code}' AND datetime >= '{_date_start(start_date)}' AND datetime < '{_date_end(end_date)}' "
        f"ORDER BY trade_day",
        table="index_bar_1day",
    )


# ==================== 全市场快照（筛选） ====================

def get_market_snapshot() -> pd.DataFrame:
    return query(
        "SELECT s.code, c.name, s.last_price AS close, s.pre_close, "
        "s.open, s.high, s.low, s.volume, s.turnover, "
        "s.limit_up, s.limit_down "
        "FROM stock_snapshot s "
        "JOIN stock_code c ON s.code = c.code "
        "WHERE s.trade_day = (SELECT MAX(trade_day) FROM stock_snapshot)",
        table="stock_snapshot",
    )


# ==================== 宏观数据 ====================

def get_macro_pmi() -> pd.DataFrame:
    return query("SELECT * FROM official_pmi ORDER BY datetime DESC", table="official_pmi")


def get_macro_cpi() -> pd.DataFrame:
    return query("SELECT * FROM cpi ORDER BY datetime DESC", table="cpi")


def get_macro_m2() -> pd.DataFrame:
    return query("SELECT * FROM m2_supply ORDER BY datetime DESC", table="m2_supply")
