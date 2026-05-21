"""
TransMatrix 内部数据库代码格式转换

系统内部使用 6 位纯数字 (000001), TransMatrix 使用带交易所后缀 (000001.SZ)
"""

_CODE_SUFFIX_MAP = {
    "6": ".SH",
    "9": ".SH",
    "0": ".SZ",
    "3": ".SZ",
    "2": ".SZ",
    "8": ".BJ",
    "4": ".BJ",
}


def to_tm_code(code: str) -> str:
    """6位纯数字 -> TransMatrix 格式: 000001 -> 000001.SZ"""
    if not code or "." in code:
        return code
    suffix = _CODE_SUFFIX_MAP.get(code[0], ".SZ")
    return f"{code}{suffix}"


def to_internal_code(tm_code: str) -> str:
    """TransMatrix -> 6位纯数字: 000001.SZ -> 000001"""
    if not tm_code:
        return tm_code
    return tm_code.split(".")[0] if "." in tm_code else tm_code


def is_tm_code(code: str) -> bool:
    """判断是否为 TransMatrix 格式代码"""
    return "." in code if code else False
