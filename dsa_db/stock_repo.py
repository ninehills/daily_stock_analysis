# -*- coding: utf-8 -*-
"""
股票日线数据仓库
"""

import logging
from datetime import date, timedelta
from typing import Optional, List, Dict, Any

from sqlalchemy import desc, and_

from dsa_db.schema import DatabaseManager, StockDaily

logger = logging.getLogger(__name__)


class StockRepository:
    """股票日线数据仓库"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager.get_instance()

    def save_daily(self, code: str, name: str, records: List[Dict[str, Any]], source: str = "akshare") -> int:
        """
        批量保存日线数据 (upsert)

        Args:
            code: 股票代码
            name: 股票名称
            records: 日线数据列表, 每条含 date/open/high/low/close/volume/amount/pct_chg
            source: 数据来源

        Returns:
            保存的记录数
        """
        saved = 0
        with self.db.session() as session:
            for r in records:
                trade_date = r.get("date")
                if not trade_date:
                    continue
                if isinstance(trade_date, str):
                    trade_date = date.fromisoformat(trade_date)

                existing = session.query(StockDaily).filter(
                    and_(StockDaily.code == code, StockDaily.date == trade_date)
                ).first()

                if existing:
                    # 更新
                    existing.name = name
                    existing.open = r.get("open")
                    existing.high = r.get("high")
                    existing.low = r.get("low")
                    existing.close = r.get("close")
                    existing.volume = r.get("volume")
                    existing.amount = r.get("amount")
                    existing.pct_chg = r.get("pct_chg")
                    existing.data_source = source
                else:
                    daily = StockDaily(
                        code=code,
                        name=name,
                        date=trade_date,
                        open=r.get("open"),
                        high=r.get("high"),
                        low=r.get("low"),
                        close=r.get("close"),
                        volume=r.get("volume"),
                        amount=r.get("amount"),
                        pct_chg=r.get("pct_chg"),
                        data_source=source,
                    )
                    session.add(daily)
                saved += 1
        return saved

    def get_history(self, code: str, days: int = 60) -> List[StockDaily]:
        """获取最近 N 天日线数据"""
        with self.db.session() as session:
            return (
                session.query(StockDaily)
                .filter(StockDaily.code == code)
                .order_by(desc(StockDaily.date))
                .limit(days)
                .all()
            )

    def get_range(self, code: str, start_date: date, end_date: date) -> List[StockDaily]:
        """获取日期范围内的数据"""
        with self.db.session() as session:
            return (
                session.query(StockDaily)
                .filter(
                    and_(
                        StockDaily.code == code,
                        StockDaily.date >= start_date,
                        StockDaily.date <= end_date,
                    )
                )
                .order_by(StockDaily.date)
                .all()
            )

    def get_latest(self, code: str, days: int = 1) -> List[StockDaily]:
        """获取最近 N 天数据（升序）"""
        with self.db.session() as session:
            return (
                session.query(StockDaily)
                .filter(StockDaily.code == code)
                .order_by(desc(StockDaily.date))
                .limit(days)
                .all()
            )

    def count_records(self, code: str) -> int:
        """统计某股票记录数"""
        with self.db.session() as session:
            return session.query(StockDaily).filter(StockDaily.code == code).count()
