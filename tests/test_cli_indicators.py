# -*- coding: utf-8 -*-
"""技术指标计算测试"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta


def _make_ohlcv_data(n_days=120):
    """生成模拟 OHLCV 数据"""
    today = date.today()
    dates = [today - timedelta(days=i) for i in range(n_days - 1, -1, -1)]
    np.random.seed(42)
    close = 100.0
    data = []
    for i, d in enumerate(dates):
        change = np.random.normal(0.1, 1.0)
        close = close + change
        data.append({
            "date": d.isoformat(),
            "open": close - np.random.uniform(0, 0.5),
            "high": close + np.random.uniform(0.5, 1.5),
            "low": close - np.random.uniform(0.5, 1.5),
            "close": close,
            "volume": np.random.uniform(500000, 2000000),
        })
    return pd.DataFrame(data)


class TestIndicatorsBasic:
    """基础指标计算测试"""

    def test_calculate_ma(self):
        """计算移动均线"""
        from dsa_cli.indicators import calculate_ma
        df = _make_ohlcv_data(30)
        result = calculate_ma(df)

        assert "MA5" in result.columns
        assert "MA10" in result.columns
        assert "MA20" in result.columns

        # MA5 前 4 行应为 NaN
        assert pd.isna(result["MA5"].iloc[0])
        assert not pd.isna(result["MA5"].iloc[10])

    def test_calculate_macd(self):
        """计算 MACD"""
        from dsa_cli.indicators import calculate_macd
        df = _make_ohlcv_data(60)
        result = calculate_macd(df)

        assert "DIF" in result.columns
        assert "DEA" in result.columns
        assert "MACD" in result.columns
        assert not pd.isna(result["DIF"].iloc[-1])

    def test_calculate_rsi(self):
        """计算 RSI"""
        from dsa_cli.indicators import calculate_rsi
        df = _make_ohlcv_data(60)
        result = calculate_rsi(df)

        assert "RSI6" in result.columns
        assert "RSI12" in result.columns
        assert "RSI24" in result.columns

        # RSI 值应在 0-100 之间
        last_rsi = result["RSI6"].iloc[-1]
        assert 0 <= last_rsi <= 100

    def test_calculate_kdj(self):
        """计算 KDJ"""
        from dsa_cli.indicators import calculate_kdj
        df = _make_ohlcv_data(30)
        result = calculate_kdj(df)

        assert "K" in result.columns
        assert "D" in result.columns
        assert "J" in result.columns

    def test_calculate_boll(self):
        """计算布林带"""
        from dsa_cli.indicators import calculate_boll
        df = _make_ohlcv_data(30)
        result = calculate_boll(df)

        assert "BOLL_UP" in result.columns
        assert "BOLL_MID" in result.columns
        assert "BOLL_DN" in result.columns

        # 上轨应大于下轨
        last = result.iloc[-1]
        if not pd.isna(last["BOLL_UP"]) and not pd.isna(last["BOLL_DN"]):
            assert last["BOLL_UP"] >= last["BOLL_DN"]

    def test_calculate_all_indicators(self):
        """计算所有指标"""
        from dsa_cli.indicators import calculate_all_indicators
        df = _make_ohlcv_data(120)
        result = calculate_all_indicators(df)

        expected_cols = ["MA5", "MA10", "MA20", "MA60", "DIF", "DEA", "MACD",
                         "RSI6", "RSI12", "RSI24", "K", "D", "J",
                         "BOLL_UP", "BOLL_MID", "BOLL_DN"]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_get_latest_indicators(self):
        """获取最新指标值"""
        from dsa_cli.indicators import calculate_all_indicators, get_latest_indicators
        df = _make_ohlcv_data(120)
        df = calculate_all_indicators(df)
        result = get_latest_indicators(df)

        assert "close" in result
        assert "MA5" in result
        assert "DIF" in result
        assert "RSI6" in result
        assert "K" in result
        assert "trend" in result
        assert "ma_alignment" in result
        assert result["close"] is not None

    def test_trend_judgment(self):
        """趋势判断"""
        from dsa_cli.indicators import get_latest_indicators, calculate_all_indicators
        df = _make_ohlcv_data(120)
        df = calculate_all_indicators(df)
        result = get_latest_indicators(df)

        assert result["trend"] in ["强势多头", "多头排列", "强势空头", "空头排列", "盘整"]

    def test_bias_calculation(self):
        """乖离率计算"""
        from dsa_cli.indicators import get_latest_indicators, calculate_all_indicators
        df = _make_ohlcv_data(120)
        df = calculate_all_indicators(df)
        result = get_latest_indicators(df)

        # 乖离率应该有值
        if result.get("bias_ma5") is not None:
            assert isinstance(result["bias_ma5"], float)
        if result.get("bias_ma20") is not None:
            assert isinstance(result["bias_ma20"], float)

    def test_empty_dataframe(self):
        """空 DataFrame 不报错"""
        from dsa_cli.indicators import get_latest_indicators
        result = get_latest_indicators(pd.DataFrame())
        assert result == {}


class TestCache:
    """缓存层测试"""

    def test_set_and_get(self):
        """T1.11: 缓存命中"""
        from dsa_cli.cache import _cache as cache
        cache.invalidate("600519", "quote")

        test_data = {"code": "600519", "price": 1850.0}
        cache.set("600519", "quote", test_data)

        cached = cache.get("600519", "quote")
        assert cached is not None
        assert cached["price"] == 1850.0

    def test_is_fresh(self):
        """检查缓存新鲜度"""
        from dsa_cli.cache import _cache as cache
        cache.set("000001", "quote", {"price": 10.0})
        assert cache.is_fresh("000001", "quote") is True
        assert cache.is_fresh("nonexistent", "quote") is False

    def test_invalidate(self):
        """清除缓存"""
        from dsa_cli.cache import _cache as cache
        cache.set("600519", "quote", {"price": 100.0})
        cache.set("600519", "history", {"records": []})

        cache.invalidate("600519", "quote")
        assert cache.get("600519", "quote") is None
        assert cache.get("600519", "history") is not None  # history 还在

        cache.invalidate("600519")  # 清除全部
        assert cache.get("600519", "history") is None
