"""
TradingAgents-CN MCP Server 入口

启动方式:
  stdio:    python -m tradingagents_mcp
  http:     MCP_TRANSPORT=streamable-http python -m tradingagents_mcp
  check:    python -m tradingagents_mcp check
"""

import os
import sys
import logging
from pathlib import Path


def _setup_logging():
    from tradingagents.utils.logging_manager import setup_logging

    level = os.getenv("TRADINGAGENTS_LOG_LEVEL", "WARNING").upper()
    log_dir = os.getenv(
        "TRADINGAGENTS_LOG_DIR",
        str(Path.home() / ".local" / "share" / "opencode" / "log" / "tradingagents-mcp"),
    )

    config = {
        "level": level,
        "format": {
            "console": "%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            "file": "%(asctime)s | %(name)-20s | %(levelname)-8s | %(module)s:%(funcName)s:%(lineno)d | %(message)s",
        },
        "handlers": {
            "console": {
                "enabled": True,
                "stream": "stderr",
                "colored": False,
                "level": level,
            },
            "file": {
                "enabled": True,
                "level": "DEBUG",
                "backup_count": 7,
                "directory": log_dir,
            },
            "error": {
                "enabled": True,
                "level": "WARNING",
                "backup_count": 7,
                "directory": log_dir,
                "filename": "error.log",
            },
            "structured": {"enabled": False, "level": "INFO", "directory": log_dir},
        },
        "loggers": {
            "tradingagents": {"level": level},
            "urllib3": {"level": "WARNING"},
            "requests": {"level": "WARNING"},
            "httpx": {"level": "WARNING"},
            "httpcore": {"level": "WARNING"},
            "matplotlib": {"level": "WARNING"},
        },
        "docker": {"enabled": False, "stdout_only": False},
    }

    setup_logging(config)


def _run_check():
    from tradingagents_mcp.validators import check_health, build_config

    print("=" * 60)
    print("  TradingAgents-CN MCP 环境检查")
    print("=" * 60)

    health = check_health()
    config = build_config()

    print(f"\n📋 MCP Server: {health.get('mcp_server', 'unknown')}")

    print(f"\n🔑 LLM 配置:")
    print(f"   Provider: {config.get('llm_provider', '未配置')}")
    print(f"   Deep Think: {config.get('deep_think_llm', '未配置')}")
    print(f"   Quick Think: {config.get('quick_think_llm', '未配置')}")
    print(f"   API Key: {health.get('llm_api_key', 'unknown')}")

    print(f"\n📊 数据源:")
    for pkg in ["akshare", "yfinance", "tushare", "baostock"]:
        status = health.get(pkg, "unknown")
        icon = "✅" if status == "ok" else "❌"
        print(f"   {icon} {pkg}: {status}")

    print(f"\n⚙️  运行配置:")
    print(f"   online_tools: {config.get('online_tools', False)}")
    print(f"   online_news: {config.get('online_news', False)}")

    all_ok = (
        health.get("mcp_server") == "ok"
        and "missing" not in str(health.get("llm_api_key", ""))
    )

    print(f"\n{'✅ 环境检查通过！' if all_ok else '⚠️  存在问题，请根据上述提示修复'}")
    print("=" * 60)

    return 0 if all_ok else 1


def _run_server():
    _setup_logging()

    from tradingagents_mcp.server import mcp

    transport = os.getenv("MCP_TRANSPORT", "stdio")
    if transport == "streamable-http":
        host = os.getenv("MCP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_PORT", "9000"))
        mcp.run(transport="streamable-http", host=host, port=port)
    else:
        mcp.run(transport="stdio")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "check":
        sys.exit(_run_check())
    _run_server()


if __name__ == "__main__":
    main()
