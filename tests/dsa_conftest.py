# -*- coding: utf-8 -*-
"""CLI 工具 conftest - 共享 fixtures"""

import os
import sys
import tempfile
import pytest

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    from dsa_db.schema import DatabaseManager
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    # 清理
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def sample_daily_records():
    """生成模拟日线数据"""
    from datetime import date, timedelta
    records = []
    base = date.today() - timedelta(days=60)
    for i in range(60):
        records.append({
            "date": (base + timedelta(days=i)).isoformat(),
            "open": 100.0 + i * 0.1,
            "high": 102.0 + i * 0.1,
            "low": 99.0 + i * 0.1,
            "close": 101.0 + i * 0.1,
            "volume": 1000000.0,
            "amount": 100000000.0,
            "pct_chg": 0.5 if i % 2 == 0 else -0.3,
        })
    return records


@pytest.fixture
def sample_analysis_result():
    """生成模拟分析结果"""
    return {
        "report_type": "single",
        "sentiment_score": 72,
        "operation_advice": "买入",
        "trend_prediction": "短期看涨",
        "confidence_level": "medium",
        "analysis_summary": "多头排列，缩量回踩MA10支撑，MACD金叉，建议买入。",
        "technical_indicators": {
            "MA5": 101.5,
            "MA10": 100.2,
            "MA20": 98.5,
            "DIF": 1.2,
            "DEA": 0.8,
            "MACD": 0.8,
            "RSI6": 58.3,
            "trend": "多头排列",
        },
        "risk_factors": ["大盘回调风险", "成交量不足"],
        "ideal_buy": 100.0,
        "secondary_buy": 98.5,
        "stop_loss": 95.0,
        "take_profit": 110.0,
    }
