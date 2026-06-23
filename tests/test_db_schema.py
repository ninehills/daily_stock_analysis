# -*- coding: utf-8 -*-
"""DB Schema 测试"""

import os
import tempfile
import pytest
from datetime import date, datetime


class TestDatabaseManager:
    """DatabaseManager 单元测试"""

    def test_init_creates_db_file(self):
        """T2.1: 创建数据库 - 首次运行自动创建 stock.db 及所有表"""
        from dsa_db.schema import DatabaseManager, Base
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)

        db = DatabaseManager(path)
        # 验证文件存在
        assert os.path.exists(path)

        # 验证所有表都存在
        table_names = Base.metadata.tables.keys()
        assert "stock_daily" in table_names
        assert "analysis_results" in table_names
        assert "positions" in table_names
        assert "strategy_meta" in table_names
        assert "query_log" in table_names

        os.unlink(path)

    def test_session_context_manager(self, temp_db):
        """测试 session 上下文管理器"""
        with temp_db.session() as session:
            assert session is not None

    def test_reset_db(self, temp_db):
        """测试 reset_db"""
        from dsa_db.schema import StockDaily
        # 先写入一条数据
        with temp_db.session() as session:
            session.add(StockDaily(code="000001", date=date.today(), close=10.0))
        assert temp_db.get_session().query(StockDaily).count() == 1

        # reset
        temp_db.reset_db()
        assert temp_db.get_session().query(StockDaily).count() == 0

    def test_singleton(self, temp_db):
        """测试单例模式"""
        from dsa_db.schema import DatabaseManager
        db1 = DatabaseManager.get_instance(temp_db.db_path)
        db2 = DatabaseManager.get_instance(temp_db.db_path)
        assert db1 is db2


class TestStockDaily:
    """StockDaily ORM 模型测试"""

    def test_create_and_query(self, temp_db):
        """T2.2: 保存日线数据 - 数据正确保存"""
        from dsa_db.schema import StockDaily
        today = date.today()

        with temp_db.session() as session:
            daily = StockDaily(
                code="600519", name="贵州茅台",
                date=today, open=1800.0, high=1850.0,
                low=1790.0, close=1830.0, volume=5000000,
            )
            session.add(daily)

        # 查询
        with temp_db.session() as session:
            result = session.query(StockDaily).filter(
                StockDaily.code == "600519"
            ).first()
            assert result is not None
            assert result.name == "贵州茅台"
            assert result.close == 1830.0

    def test_unique_constraint(self, temp_db):
        """T2.3: 日线唯一约束 - 重复写入同 code+date 报错"""
        from dsa_db.schema import StockDaily
        from sqlalchemy.exc import IntegrityError
        today = date.today()

        # 第一次写入
        with temp_db.session() as session:
            session.add(StockDaily(code="000001", date=today, close=10.0))

        # 第二次写入同 code+date
        import pytest
        with pytest.raises((IntegrityError, Exception)):
            with temp_db.session() as session:
                session.add(StockDaily(code="000001", date=today, close=11.0))

    def test_to_dict(self, temp_db):
        """测试 to_dict 输出"""
        from dsa_db.schema import StockDaily
        today = date.today()

        with temp_db.session() as session:
            daily = StockDaily(
                code="600519", name="茅台",
                date=today, close=1830.0, pct_chg=1.5
            )
            session.add(daily)
            session.flush()
            d = daily.to_dict()
            assert d["code"] == "600519"
            assert d["name"] == "茅台"
            assert d["close"] == 1830.0
            assert d["pct_chg"] == 1.5


class TestAnalysisResult:
    """AnalysisResult ORM 模型测试"""

    def test_create_and_query(self, temp_db):
        """T2.4: 保存分析结果 - 含 score/advice/summary"""
        from dsa_db.schema import AnalysisResult

        with temp_db.session() as session:
            r = AnalysisResult(
                code="600519", name="贵州茅台",
                strategy="bull_trend",
                sentiment_score=72,
                operation_advice="买入",
                trend_prediction="短期看涨",
                analysis_summary="多头排列，建议买入",
                ideal_buy=1800.0,
                stop_loss=1750.0,
            )
            session.add(r)

        # 查询
        with temp_db.session() as session:
            result = session.query(AnalysisResult).filter(
                AnalysisResult.code == "600519"
            ).first()
            assert result is not None
            assert result.sentiment_score == 72
            assert result.strategy == "bull_trend"

    def test_to_dict(self, temp_db):
        """测试 to_dict 输出"""
        from dsa_db.schema import AnalysisResult

        with temp_db.session() as session:
            r = AnalysisResult(
                code="000001", name="平安银行",
                strategy="wave_theory",
                sentiment_score=65,
                operation_advice="持有",
                ideal_buy=10.5,
                stop_loss=9.8,
            )
            session.add(r)
            session.flush()
            d = r.to_dict()
            assert d["code"] == "000001"
            assert d["sentiment_score"] == 65
            assert d["operation_advice"] == "持有"
            assert d["ideal_buy"] == 10.5


class TestPosition:
    """Position ORM 模型测试"""

    def test_create_and_query(self, temp_db):
        """T2.6: 保存持仓 - 含 code/cost/shares/date"""
        from dsa_db.schema import Position
        today = date.today()

        with temp_db.session() as session:
            pos = Position(
                code="600519", name="贵州茅台",
                market="cn", shares=100,
                cost_price=1800.0, total_cost=180000.0,
                first_buy_date=today,
            )
            session.add(pos)

        with temp_db.session() as session:
            p = session.query(Position).filter(Position.code == "600519").first()
            assert p is not None
            assert p.shares == 100
            assert p.cost_price == 1800.0
            assert p.is_held is True

    def test_profit_calculation(self, temp_db):
        """T2.8: 盈亏计算 - 正确计算浮动盈亏"""
        from dsa_db.schema import Position
        today = date.today()

        with temp_db.session() as session:
            pos = Position(
                code="600519", name="贵州茅台",
                shares=100, cost_price=1800.0,
                current_price=1850.0,
                first_buy_date=today,
            )
            session.add(pos)
            session.flush()

            # 盈亏 = (1850 - 1800) * 100 = 5000
            assert pos.profit_amount == 5000.0
            # 盈亏率 = (1850 - 1800) / 1800 = 2.78%
            assert pos.profit_pct == pytest.approx(2.78, 0.01)

    def test_unique_constraint(self, temp_db):
        """T2.7: 更新持仓 - 同 code 更新信息"""
        from dsa_db.schema import Position
        from sqlalchemy.exc import IntegrityError
        today = date.today()

        with temp_db.session() as session:
            session.add(Position(code="000001", name="平安银行", cost_price=10.0))
        # 重复 code 应报错
        with pytest.raises((IntegrityError, Exception)):
            with temp_db.session() as session:
                session.add(Position(code="000001", name="平安银行", cost_price=11.0))

    def test_to_dict(self, temp_db):
        """测试 to_dict 输出"""
        from dsa_db.schema import Position

        with temp_db.session() as session:
            pos = Position(code="600519", name="茅台", shares=100,
                          cost_price=1800, current_price=1850)
            session.add(pos)
            session.flush()
            d = pos.to_dict()
            assert d["code"] == "600519"
            assert d["shares"] == 100
            assert "cost_price" in d
