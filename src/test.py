"""测试 news + social 分析师同时运行，不执行后续辩论"""

import asyncio

def test_news_and_social():
    import akshare as ak
    news_df = ak.stock_news_em(symbol='688031')
    print(news_df.head())

if __name__ == "__main__":
    test_news_and_social()
