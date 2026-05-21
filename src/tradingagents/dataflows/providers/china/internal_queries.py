"""
TransMatrix 内部数据库 SQL 查询封装

通过 transwarp.timelyre.timelyre_public.DatabaseConn 连接内部数据库，
使用 JDBC HTTP Proxy 执行 SQL 查询。
"""

import os
import logging
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

    jdbc_http_proxy = os.environ.get("JDBC_HTTP_PROXY", "192.168.100.101:9998")
    real_conn = os.environ.get(
        "TM_REAL_CONN", "jdbc:hive2://192.168.100.102:10006"
    )
    db_name = os.environ.get("TM_DB_NAME", "meta_data")
    db_user = os.environ.get("TM_DB_USER", "transmatrix_admin")
    password = os.environ.get("TM_DB_PASSWORD", "Transmatrix123")
    token = os.environ.get("GUARDIAN_TOKEN", "UgJRRGe7qMAKcirOQ017-TDH")

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


def query(sql: str) -> pd.DataFrame:
    """
    执行 SQL 查询并返回 DataFrame

    使用 DatabaseConn.query_as_df() 方法，传入完整 SQL 作为 query 参数。

    Args:
        sql: SQL 查询语句

    Returns:
        查询结果 DataFrame
    """
    conn = _get_db_conn()
    try:
        result = conn.query_as_df("", query=sql, combine_ignore_index=True)
        if result is None:
            return pd.DataFrame()
        if isinstance(result, pd.DataFrame):
            return result
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"TransMatrix SQL 查询失败: {e}\nSQL: {sql[:200]}")
        raise


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
    df = query(f"SELECT * FROM stock_code WHERE code = '{tm_code}'")
    return df.iloc[0].to_dict() if not df.empty else None


def get_stock_list() -> pd.DataFrame:
    return query("SELECT * FROM stock_code WHERE delist_date IS NULL")


def get_sw_industry(symbol: str) -> Optional[dict]:
    tm_code = to_tm_code(symbol)
    df = query(
        f"SELECT * FROM sw_industry WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT 1"
    )
    return df.iloc[0].to_dict() if not df.empty else None


# ==================== K 线数据 ====================

def get_daily_kline(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT `trade_day`, `open`, `high`, `low`, `close`, `volume`, `turnover`, `vwap`, `factor` "
        f"FROM `stock_bar_1day` "
        f"WHERE `code` = '{tm_code}' AND `datetime` >= '{_date_start(start_date)}' AND `datetime` < '{_date_end(end_date)}' "
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
        f"FROM {table} {where} ORDER BY trade_day, trade_time"
    )


# ==================== 实时快照 ====================

def get_snapshot(symbol: str) -> Optional[dict]:
    tm_code = to_tm_code(symbol)
    df = query(
        f"SELECT * FROM stock_snapshot WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT 1"
    )
    return df.iloc[0].to_dict() if not df.empty else None


def get_all_snapshots(trade_day: str) -> pd.DataFrame:
    return query(
        f"SELECT * FROM stock_snapshot WHERE datetime >= '{_date_start(trade_day)}' AND datetime < '{_date_end(trade_day)}'"
    )


# ==================== 估值数据 ====================

def get_valuation(symbol: str, trade_day: str = None) -> Optional[dict]:
    tm_code = to_tm_code(symbol)
    if trade_day:
        df = query(
            f"SELECT * FROM capital WHERE code = '{tm_code}' "
            f"AND datetime < '{_date_end(trade_day)}' ORDER BY datetime DESC LIMIT 1"
        )
    else:
        df = query(
            f"SELECT * FROM capital WHERE code = '{tm_code}' "
            f"ORDER BY datetime DESC LIMIT 1"
        )
    return df.iloc[0].to_dict() if not df.empty else None


# ==================== 财务指标 ====================

def get_finance_indicator(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM finance_indicator WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}"
    )


# ==================== 三大财务报表 ====================

def get_balance(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM balance WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}"
    )


def get_income(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM income WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}"
    )


def get_cashflow(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM cashflow WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}"
    )


# ==================== 资金流向 ====================

def get_money_flow(symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM stock_money_flow "
        f"WHERE code = '{tm_code}' AND datetime >= '{_date_start(start_date)}' AND datetime < '{_date_end(end_date)}' "
        f"ORDER BY trade_day"
    )


# ==================== 股东数据 ====================

def get_top10_shareholders(symbol: str, limit: int = 2) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM shareholders_top10 WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit * 10}"
    )


def get_shareholder_num(symbol: str, limit: int = 4) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM shareholder_num WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}"
    )


# ==================== 分红配股 ====================

def get_dividend(symbol: str, limit: int = 5) -> pd.DataFrame:
    tm_code = to_tm_code(symbol)
    return query(
        f"SELECT * FROM dividend_allocation WHERE code = '{tm_code}' "
        f"ORDER BY datetime DESC LIMIT {limit}"
    )


# ==================== 指数数据 ====================

def get_index_kline(code: str, start_date: str, end_date: str) -> pd.DataFrame:
    return query(
        f"SELECT * FROM index_bar_1day "
        f"WHERE code = '{code}' AND datetime >= '{_date_start(start_date)}' AND datetime < '{_date_end(end_date)}' "
        f"ORDER BY trade_day"
    )


# ==================== 全市场快照（筛选） ====================

def get_market_snapshot() -> pd.DataFrame:
    return query(
        "SELECT s.code, c.name, s.last_price AS close, s.pre_close, "
        "s.open, s.high, s.low, s.volume, s.turnover, "
        "s.limit_up, s.limit_down "
        "FROM stock_snapshot s "
        "JOIN stock_code c ON s.code = c.code "
        "WHERE s.trade_day = (SELECT MAX(trade_day) FROM stock_snapshot)"
    )


# ==================== 宏观数据 ====================

def get_macro_pmi() -> pd.DataFrame:
    return query("SELECT * FROM official_pmi ORDER BY datetime DESC")


def get_macro_cpi() -> pd.DataFrame:
    return query("SELECT * FROM cpi ORDER BY datetime DESC")


def get_macro_m2() -> pd.DataFrame:
    return query("SELECT * FROM m2_supply ORDER BY datetime DESC")
