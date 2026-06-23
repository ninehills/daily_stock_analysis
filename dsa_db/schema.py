# -*- coding: utf-8 -*-
"""
数据库 Schema 定义

表结构：
- stock_daily: 股票日线数据 (OHLCV + 技术指标)
- analysis_results: 分析结果历史
- positions: 用户持仓信息
- strategy_meta: 策略元数据
- query_log: 查询日志
"""

import os
import logging
from datetime import datetime, date
from contextlib import contextmanager
from typing import Optional

from sqlalchemy import (
    create_engine, Column, String, Float, Integer, Date,
    DateTime, Text, Boolean, Index, UniqueConstraint, text,
)
from sqlalchemy.orm import declarative_base, sessionmaker, Session

logger = logging.getLogger(__name__)

Base = declarative_base()

# 默认数据库路径
DEFAULT_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "stock.db")


# ============================================================
# ORM 模型
# ============================================================

class StockDaily(Base):
    """股票日线数据"""
    __tablename__ = "stock_daily"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), nullable=False, index=True, comment="股票代码")
    name = Column(String(64), comment="股票名称")
    date = Column(Date, nullable=False, index=True, comment="交易日期")

    # OHLCV
    open = Column(Float, comment="开盘价")
    high = Column(Float, comment="最高价")
    low = Column(Float, comment="最低价")
    close = Column(Float, comment="收盘价")
    volume = Column(Float, comment="成交量（股）")
    amount = Column(Float, comment="成交额（元）")
    pct_chg = Column(Float, comment="涨跌幅(%)")

    # 技术指标
    ma5 = Column(Float, comment="5日均线")
    ma10 = Column(Float, comment="10日均线")
    ma20 = Column(Float, comment="20日均线")
    ma60 = Column(Float, comment="60日均线")
    volume_ratio = Column(Float, comment="量比")

    # 元数据
    data_source = Column(String(50), comment="数据来源")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    __table_args__ = (
        UniqueConstraint("code", "date", name="uix_code_date"),
        Index("ix_code_date", "code", "date"),
    )

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "date": self.date.isoformat() if self.date else None,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "volume": self.volume,
            "amount": self.amount,
            "pct_chg": self.pct_chg,
            "ma5": self.ma5,
            "ma10": self.ma10,
            "ma20": self.ma20,
            "ma60": self.ma60,
            "volume_ratio": self.volume_ratio,
        }


class AnalysisResult(Base):
    """分析结果历史记录"""
    __tablename__ = "analysis_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query_id = Column(String(64), index=True, comment="查询ID")
    code = Column(String(16), nullable=False, index=True, comment="股票代码")
    name = Column(String(64), comment="股票名称")
    strategy = Column(String(64), index=True, comment="使用的策略名称")
    report_type = Column(String(16), comment="报告类型")

    # 分析结论
    sentiment_score = Column(Integer, comment="情绪评分 0-100")
    operation_advice = Column(String(32), comment="操作建议: 买入/持有/卖出/观望")
    trend_prediction = Column(String(64), comment="趋势预测")
    confidence_level = Column(String(16), comment="置信度: high/medium/low")

    # 详细内容
    analysis_summary = Column(Text, comment="分析摘要")
    technical_indicators = Column(Text, comment="技术指标JSON")
    risk_factors = Column(Text, comment="风险因素JSON")

    # 狙击点位
    ideal_buy = Column(Float, comment="理想买入价")
    secondary_buy = Column(Float, comment="次优买入价")
    stop_loss = Column(Float, comment="止损价")
    take_profit = Column(Float, comment="止盈价")

    # 原始数据快照
    raw_result = Column(Text, comment="原始分析结果JSON")
    context_snapshot = Column(Text, comment="上下文快照JSON")

    created_at = Column(DateTime, default=datetime.now, index=True)

    __table_args__ = (
        Index("ix_analysis_code_time", "code", "created_at"),
        Index("ix_analysis_strategy", "strategy", "created_at"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "query_id": self.query_id,
            "code": self.code,
            "name": self.name,
            "strategy": self.strategy,
            "report_type": self.report_type,
            "sentiment_score": self.sentiment_score,
            "operation_advice": self.operation_advice,
            "trend_prediction": self.trend_prediction,
            "confidence_level": self.confidence_level,
            "analysis_summary": self.analysis_summary,
            "ideal_buy": self.ideal_buy,
            "secondary_buy": self.secondary_buy,
            "stop_loss": self.stop_loss,
            "take_profit": self.take_profit,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class Position(Base):
    """用户持仓信息"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    code = Column(String(16), nullable=False, unique=True, index=True, comment="股票代码")
    name = Column(String(64), comment="股票名称")
    market = Column(String(8), default="cn", comment="市场: cn/hk/us")

    # 持仓数据
    shares = Column(Integer, default=0, comment="持仓数量（股）")
    cost_price = Column(Float, comment="成本价")
    current_price = Column(Float, comment="当前价(缓存)")
    total_cost = Column(Float, comment="总成本")

    # 状态
    is_held = Column(Boolean, default=True, index=True, comment="是否持有中")
    first_buy_date = Column(Date, comment="首次买入日期")
    last_update = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # 备注
    notes = Column(Text, comment="备注")

    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    def to_dict(self):
        return {
            "id": self.id,
            "code": self.code,
            "name": self.name,
            "market": self.market,
            "shares": self.shares,
            "cost_price": self.cost_price,
            "current_price": self.current_price,
            "total_cost": self.total_cost,
            "is_held": self.is_held,
            "first_buy_date": self.first_buy_date.isoformat() if self.first_buy_date else None,
            "notes": self.notes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    @property
    def profit_pct(self) -> Optional[float]:
        """浮动盈亏百分比"""
        if self.cost_price and self.current_price and self.cost_price > 0:
            return round((self.current_price - self.cost_price) / self.cost_price * 100, 2)
        return None

    @property
    def profit_amount(self) -> Optional[float]:
        """浮动盈亏金额"""
        if self.shares and self.cost_price and self.current_price:
            return round((self.current_price - self.cost_price) * self.shares, 2)
        return None


class StrategyMeta(Base):
    """策略元数据"""
    __tablename__ = "strategy_meta"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(64), nullable=False, unique=True, index=True)
    display_name = Column(String(128), comment="显示名称")
    category = Column(String(32), comment="分类: trend/framework/event")
    description = Column(Text, comment="策略描述")
    default_priority = Column(Integer, default=50)
    is_active = Column(Boolean, default=True)
    config_json = Column(Text, comment="策略配置JSON")

    created_at = Column(DateTime, default=datetime.now)


class QueryLog(Base):
    """查询日志"""
    __tablename__ = "query_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    command = Column(String(64), index=True, comment="命令: quote/history/indicators")
    params = Column(Text, comment="参数JSON")
    source = Column(String(16), comment="来源: cache/network")
    duration_ms = Column(Float, comment="耗时(毫秒)")
    error = Column(Text, comment="错误信息")
    created_at = Column(DateTime, default=datetime.now, index=True)


class SourceHealth(Base):
    """数据源健康状态（熔断器）"""
    __tablename__ = "source_health"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source_name = Column(String(32), nullable=False, unique=True, index=True, comment="数据源名称")
    fail_count = Column(Integer, default=0, comment="连续失败次数")
    total_failures = Column(Integer, default=0, comment="总失败次数")
    total_successes = Column(Integer, default=0, comment="总成功次数")
    last_success = Column(DateTime, comment="最后一次成功时间")
    last_failure = Column(DateTime, comment="最后一次失败时间")
    last_error = Column(Text, comment="最后一次错误信息")
    banned_until = Column(DateTime, index=True, comment="熔断解除时间")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


# ============================================================
# 数据库管理器
# ============================================================

class DatabaseManager:
    """SQLite 数据库管理器（单例）"""

    _instance: Optional["DatabaseManager"] = None
    _engine = None
    _SessionLocal = None

    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self._engine = create_engine(
            f"sqlite:///{db_path}",
            echo=False,
            connect_args={"check_same_thread": False},
        )
        self._SessionLocal = sessionmaker(bind=self._engine, expire_on_commit=False)

        # 自动创建表
        Base.metadata.create_all(self._engine)
        logger.info(f"数据库已初始化: {db_path}")

    @classmethod
    def get_instance(cls, db_path: str = DEFAULT_DB_PATH) -> "DatabaseManager":
        if cls._instance is None:
            cls._instance = cls(db_path)
        return cls._instance

    @contextmanager
    def session(self) -> Session:
        """获取数据库会话上下文管理器"""
        session = self._SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def get_session(self) -> Session:
        """获取原始会话（调用方负责关闭）"""
        return self._SessionLocal()

    def reset_db(self):
        """重置数据库（仅用于测试）"""
        Base.metadata.drop_all(self._engine)
        Base.metadata.create_all(self._engine)
