# -*- coding: utf-8 -*-
"""
技术指标计算模块

纯 Python 实现，不依赖外部库（除 pandas/numpy）。
支持: MA, MACD, RSI, KDJ, BOLL
"""

import logging
from typing import Dict, Any, List, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def calculate_ma(df: pd.DataFrame, periods: List[int] = [5, 10, 20, 60]) -> pd.DataFrame:
    """计算移动均线"""
    df = df.copy()
    for p in periods:
        df[f"MA{p}"] = df["close"].rolling(window=p).mean()
    return df


def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """计算 MACD"""
    df = df.copy()
    df["EMA_fast"] = df["close"].ewm(span=fast, adjust=False).mean()
    df["EMA_slow"] = df["close"].ewm(span=slow, adjust=False).mean()
    df["DIF"] = df["EMA_fast"] - df["EMA_slow"]
    df["DEA"] = df["DIF"].ewm(span=signal, adjust=False).mean()
    df["MACD"] = 2 * (df["DIF"] - df["DEA"])
    return df


def calculate_rsi(df: pd.DataFrame, periods: List[int] = [6, 12, 24]) -> pd.DataFrame:
    """计算 RSI"""
    df = df.copy()
    for p in periods:
        delta = df["close"].diff()
        gain = delta.where(delta > 0, 0.0)
        loss = (-delta).where(delta < 0, 0.0)
        avg_gain = gain.ewm(alpha=1/p, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1/p, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        df[f"RSI{p}"] = 100 - (100 / (1 + rs))
    return df


def calculate_kdj(df: pd.DataFrame, n: int = 9, m1: int = 3, m2: int = 3) -> pd.DataFrame:
    """计算 KDJ"""
    df = df.copy()
    low_n = df["low"].rolling(window=n).min()
    high_n = df["high"].rolling(window=n).max()
    rsv = (df["close"] - low_n) / (high_n - low_n).replace(0, np.nan) * 100

    df["K"] = rsv.ewm(com=m1-1, adjust=False).mean()
    df["D"] = df["K"].ewm(com=m2-1, adjust=False).mean()
    df["J"] = 3 * df["K"] - 2 * df["D"]
    return df


def calculate_boll(df: pd.DataFrame, period: int = 20, std: int = 2) -> pd.DataFrame:
    """计算布林带"""
    df = df.copy()
    df["BOLL_MID"] = df["close"].rolling(window=period).mean()
    std_val = df["close"].rolling(window=period).std()
    df["BOLL_UP"] = df["BOLL_MID"] + std * std_val
    df["BOLL_DN"] = df["BOLL_MID"] - std * std_val
    return df


def calculate_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有技术指标"""
    df = df.sort_values("date").reset_index(drop=True)
    df = calculate_ma(df)
    df = calculate_macd(df)
    df = calculate_rsi(df)
    df = calculate_kdj(df)
    df = calculate_boll(df)
    return df


def get_latest_indicators(df: pd.DataFrame) -> Dict[str, Any]:
    """从 DataFrame 提取最新的指标值"""
    if df.empty:
        return {}

    latest = df.iloc[-1]
    indicators = {}

    # 价格
    for col in ["open", "high", "low", "close", "volume"]:
        if col in df.columns:
            indicators[col] = float(latest[col]) if not pd.isna(latest[col]) else None

    # MA
    for p in [5, 10, 20, 60]:
        col = f"MA{p}"
        if col in df.columns:
            indicators[col] = float(latest[col]) if not pd.isna(latest[col]) else None

    # MACD
    for col in ["DIF", "DEA", "MACD"]:
        if col in df.columns:
            indicators[col] = float(latest[col]) if not pd.isna(latest[col]) else None

    # RSI
    for p in [6, 12, 24]:
        col = f"RSI{p}"
        if col in df.columns:
            indicators[col] = float(latest[col]) if not pd.isna(latest[col]) else None

    # KDJ
    for col in ["K", "D", "J"]:
        if col in df.columns:
            indicators[col] = float(latest[col]) if not pd.isna(latest[col]) else None

    # BOLL
    for col in ["BOLL_UP", "BOLL_MID", "BOLL_DN"]:
        if col in df.columns:
            indicators[col] = float(latest[col]) if not pd.isna(latest[col]) else None

    # 趋势判断
    indicators["trend"] = _judge_trend(indicators)
    indicators["ma_alignment"] = _judge_ma_alignment(indicators)
    indicators["bias_ma5"] = _calc_bias(indicators, "MA5")
    indicators["bias_ma20"] = _calc_bias(indicators, "MA20")

    return indicators


def _judge_trend(ind: Dict) -> str:
    """判断趋势"""
    ma5 = ind.get("MA5") or 0
    ma10 = ind.get("MA10") or 0
    ma20 = ind.get("MA20") or 0
    if ma5 > ma10 > ma20:
        return "强势多头"
    elif ma5 > ma10:
        return "多头排列"
    elif ma5 < ma10 < ma20:
        return "强势空头"
    elif ma5 < ma10:
        return "空头排列"
    else:
        return "盘整"


def _judge_ma_alignment(ind: Dict) -> str:
    """判断均线排列"""
    ma5 = ind.get("MA5") or 0
    ma10 = ind.get("MA10") or 0
    ma20 = ind.get("MA20") or 0
    if ma5 > ma10 > ma20:
        return "MA5>MA10>MA20 多头排列"
    elif ma5 < ma10 < ma20:
        return "MA5<MA10<MA20 空头排列"
    else:
        return "均线缠绕"


def _calc_bias(ind: Dict, ma_key: str) -> Optional[float]:
    """计算乖离率"""
    close = ind.get("close")
    ma = ind.get(ma_key)
    if close and ma and ma > 0:
        return round((close - ma) / ma * 100, 2)
    return None
