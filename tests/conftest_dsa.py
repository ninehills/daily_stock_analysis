# -*- coding: utf-8 -*-
"""CLI 工具 conftest - 共享 fixtures（覆盖原有 conftest）"""
import os
import sys
import tempfile
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_db():
    """创建临时数据库"""
    from dsa_db.schema import DatabaseManager
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    if os.path.exists(path):
        os.unlink(path)


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
