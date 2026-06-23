# -*- coding: utf-8 -*-
"""
持仓信息仓库
"""

import logging
from datetime import date, datetime
from typing import Optional, List, Dict, Any

from dsa_db.schema import DatabaseManager, Position

logger = logging.getLogger(__name__)


class PositionRepository:
    """持仓信息仓库"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager.get_instance()

    def upsert(self, code: str, name: str = "", market: str = "cn",
               shares: int = 0, cost_price: float = 0.0,
               first_buy_date: Optional[date] = None,
               notes: str = "") -> Position:
        """
        创建或更新持仓 (upsert by code)

        Args:
            code: 股票代码
            name: 股票名称
            market: 市场 cn/hk/us
            shares: 持仓数量
            cost_price: 成本价
            first_buy_date: 首次买入日期
            notes: 备注

        Returns:
            Position 对象
        """
        total_cost = round(shares * cost_price, 2) if shares and cost_price else 0.0

        with self.db.session() as session:
            existing = session.query(Position).filter(Position.code == code).first()
            if existing:
                existing.name = name or existing.name
                existing.market = market
                existing.shares = shares
                existing.cost_price = cost_price
                existing.total_cost = total_cost
                existing.first_buy_date = first_buy_date or existing.first_buy_date
                existing.notes = notes or existing.notes
                existing.is_held = True
                existing.updated_at = datetime.now()
                pos = existing
            else:
                pos = Position(
                    code=code,
                    name=name,
                    market=market,
                    shares=shares,
                    cost_price=cost_price,
                    total_cost=total_cost,
                    first_buy_date=first_buy_date,
                    notes=notes,
                    is_held=True,
                )
                session.add(pos)
            session.flush()
        return pos

    def get(self, code: str) -> Optional[Position]:
        """查询持仓"""
        with self.db.session() as session:
            return session.query(Position).filter(Position.code == code).first()

    def list_all(self, held_only: bool = True) -> List[Position]:
        """列出所有持仓"""
        with self.db.session() as session:
            query = session.query(Position)
            if held_only:
                query = query.filter(Position.is_held == True)
            return query.all()

    def close_position(self, code: str) -> bool:
        """标记卖出（不再持有）"""
        with self.db.session() as session:
            pos = session.query(Position).filter(Position.code == code).first()
            if pos:
                pos.is_held = False
                pos.updated_at = datetime.now()
                return True
        return False

    def update_price(self, code: str, current_price: float) -> bool:
        """更新当前价格缓存"""
        with self.db.session() as session:
            pos = session.query(Position).filter(Position.code == code).first()
            if pos:
                pos.current_price = current_price
                pos.updated_at = datetime.now()
                return True
        return False

    def count_held(self) -> int:
        """统计持仓数量"""
        with self.db.session() as session:
            return session.query(Position).filter(Position.is_held == True).count()

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """获取组合概要"""
        positions = self.list_all(held_only=True)
        total_cost = sum(p.total_cost or 0 for p in positions)
        # 当前市值需要 current_price
        total_value = sum(
            (p.current_price or p.cost_price or 0) * (p.shares or 0)
            for p in positions
        )
        return {
            "count": len(positions),
            "total_cost": round(total_cost, 2),
            "total_value": round(total_value, 2),
            "total_pnl": round(total_value - total_cost, 2),
            "total_pnl_pct": round((total_value - total_cost) / total_cost * 100, 2) if total_cost > 0 else 0,
        }
