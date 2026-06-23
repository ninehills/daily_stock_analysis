# -*- coding: utf-8 -*-
"""StockRepository 测试"""

import pytest
from datetime import date, timedelta


class TestStockRepository:
    """StockRepository 单元测试"""

    def test_save_daily(self, temp_db):
        """T2.2: 保存日线数据"""
        from dsa_db.stock_repo import StockRepository
        repo = StockRepository(temp_db)

        records = [
            {"date": date.today(), "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000000, "amount": 100000000, "pct_chg": 1.0},
            {"date": date.today() - timedelta(days=1), "open": 99, "high": 101, "low": 98, "close": 100, "volume": 900000, "amount": 90000000, "pct_chg": 0.5},
        ]
        saved = repo.save_daily("600519", "贵州茅台", records)
        assert saved == 2

        # 验证数据
        count = repo.count_records("600519")
        assert count == 2

    def test_save_daily_upsert(self, temp_db):
        """T2.3: upsert - 重复写入同 code+date 自动更新"""
        from dsa_db.stock_repo import StockRepository
        repo = StockRepository(temp_db)

        today = date.today()
        records = [{"date": today, "close": 100, "open": 99, "high": 101, "low": 98, "volume": 1000000, "amount": 100000000, "pct_chg": 1.0}]
        repo.save_daily("000001", "测试股", records)

        # 写入同一天（close 不同）
        records2 = [{"date": today, "close": 105, "open": 100, "high": 106, "low": 99, "volume": 2000000, "amount": 200000000, "pct_chg": 5.0}]
        repo.save_daily("000001", "测试股", records2)

        # 验证只有 1 条记录，且是更新后的值
        count = repo.count_records("000001")
        assert count == 1

        history = repo.get_history("000001", 1)
        assert len(history) == 1
        assert history[0].close == 105

    def test_get_history(self, temp_db):
        """获取历史日线"""
        from dsa_db.stock_repo import StockRepository
        repo = StockRepository(temp_db)

        today = date.today()
        records = []
        for i in range(60):
            records.append({
                "date": today - timedelta(days=i),
                "open": 100 + i * 0.1,
                "high": 102 + i * 0.1,
                "low": 99 + i * 0.1,
                "close": 101 + i * 0.1,
                "volume": 1000000.0,
                "amount": 100000000.0,
                "pct_chg": 0.5,
            })
        repo.save_daily("600519", "茅台", records)

        # 获取最近 10 天
        history = repo.get_history("600519", 10)
        assert len(history) == 10
        assert history[0].code == "600519"

    def test_get_range(self, temp_db):
        """获取日期范围数据"""
        from dsa_db.stock_repo import StockRepository
        repo = StockRepository(temp_db)

        today = date.today()
        records = []
        for i in range(30):
            records.append({
                "date": today - timedelta(days=i),
                "open": 100, "high": 102, "low": 99, "close": 101,
                "volume": 1000000.0, "amount": 100000000.0, "pct_chg": 0.5,
            })
        repo.save_daily("000001", "测试", records)

        start = today - timedelta(days=10)
        end = today
        results = repo.get_range("000001", start, end)
        assert len(results) == 11  # 包含 start 和 end

    def test_count_records(self, temp_db):
        """统计记录数"""
        from dsa_db.stock_repo import StockRepository
        repo = StockRepository(temp_db)

        assert repo.count_records("nonexistent") == 0

        records = [{
            "date": date.today(), "open": 100, "high": 102, "low": 99,
            "close": 101, "volume": 1000000.0, "amount": 100000000.0, "pct_chg": 0.5,
        }]
        repo.save_daily("600519", "茅台", records)
        assert repo.count_records("600519") == 1


class TestAnalysisRepository:
    """AnalysisRepository 单元测试"""

    def test_save_and_query(self, temp_db, sample_analysis_result):
        """T2.4: 保存并查询分析结果"""
        from dsa_db.analysis_repo import AnalysisRepository
        repo = AnalysisRepository(temp_db)

        record = repo.save("600519", "贵州茅台", "bull_trend", sample_analysis_result)
        assert record is not None
        assert record.code == "600519"
        assert record.sentiment_score == 72

        # 查询
        results = repo.get_by_code("600519")
        assert len(results) == 1
        assert results[0].strategy == "bull_trend"

    def test_count_by_code(self, temp_db, sample_analysis_result):
        """统计分析次数"""
        from dsa_db.analysis_repo import AnalysisRepository
        repo = AnalysisRepository(temp_db)

        assert repo.count_by_code("600519") == 0
        repo.save("600519", "茅台", "bull_trend", sample_analysis_result)
        repo.save("600519", "茅台", "chan_theory", sample_analysis_result)
        assert repo.count_by_code("600519") == 2

    def test_get_latest(self, temp_db, sample_analysis_result):
        """获取最新分析"""
        from dsa_db.analysis_repo import AnalysisRepository
        repo = AnalysisRepository(temp_db)

        assert repo.get_latest("600519") is None

        r1 = sample_analysis_result.copy()
        r1["sentiment_score"] = 60
        repo.save("600519", "茅台", "bull_trend", r1)

        import time
        time.sleep(0.01)

        r2 = sample_analysis_result.copy()
        r2["sentiment_score"] = 80
        repo.save("600519", "茅台", "chan_theory", r2)

        latest = repo.get_latest("600519")
        assert latest is not None
        assert latest.sentiment_score == 80  # 最新的是 80

    def test_get_by_strategy(self, temp_db, sample_analysis_result):
        """按策略查询"""
        from dsa_db.analysis_repo import AnalysisRepository
        repo = AnalysisRepository(temp_db)

        repo.save("600519", "茅台", "bull_trend", sample_analysis_result)
        repo.save("600519", "茅台", "chan_theory", sample_analysis_result)

        bull = repo.get_by_strategy("600519", "bull_trend")
        assert len(bull) == 1

        chan = repo.get_by_strategy("600519", "chan_theory")
        assert len(chan) == 1


class TestPositionRepository:
    """PositionRepository 单元测试"""

    def test_upsert_create(self, temp_db):
        """创建持仓"""
        from dsa_db.position_repo import PositionRepository
        repo = PositionRepository(temp_db)

        pos = repo.upsert(code="600519", name="贵州茅台", shares=100, cost_price=1800.0)
        assert pos.code == "600519"
        assert pos.shares == 100
        assert pos.is_held is True
        assert repo.count_held() == 1

    def test_upsert_update(self, temp_db):
        """T2.7: 更新持仓"""
        from dsa_db.position_repo import PositionRepository
        repo = PositionRepository(temp_db)

        repo.upsert(code="600519", name="茅台", shares=100, cost_price=1800.0)
        # 更新
        repo.upsert(code="600519", name="贵州茅台", shares=200, cost_price=1850.0)

        pos = repo.get("600519")
        assert pos.shares == 200
        assert pos.cost_price == 1850.0
        assert pos.name == "贵州茅台"
        # 应仍只有一条记录
        assert repo.count_held() == 1

    def test_close_position(self, temp_db):
        """标记卖出"""
        from dsa_db.position_repo import PositionRepository
        repo = PositionRepository(temp_db)

        repo.upsert(code="000001", name="平安银行", shares=500, cost_price=10.0)
        assert repo.count_held() == 1

        ok = repo.close_position("000001")
        assert ok is True
        assert repo.count_held() == 0

        pos = repo.get("000001")
        assert pos.is_held is False

    def test_update_price(self, temp_db):
        """更新当前价格"""
        from dsa_db.position_repo import PositionRepository
        repo = PositionRepository(temp_db)

        repo.upsert(code="600519", name="茅台", shares=100, cost_price=1800.0)
        ok = repo.update_price("600519", 1900.0)
        assert ok is True

        pos = repo.get("600519")
        assert pos.current_price == 1900.0

    def test_portfolio_summary(self, temp_db):
        """组合概要"""
        from dsa_db.position_repo import PositionRepository
        repo = PositionRepository(temp_db)

        repo.upsert(code="600519", name="茅台", shares=100, cost_price=1800.0)
        repo.update_price("600519", 1900.0)
        repo.upsert(code="000001", name="平安银行", shares=500, cost_price=10.0)
        repo.update_price("000001", 11.0)

        summary = repo.get_portfolio_summary()
        assert summary["count"] == 2
        assert summary["total_cost"] == 185000.0  # 180000 + 5000
        assert summary["total_value"] == pytest.approx(195500.0)  # 190000 + 5500

    def test_list_all(self, temp_db):
        """列出持仓"""
        from dsa_db.position_repo import PositionRepository
        repo = PositionRepository(temp_db)

        repo.upsert(code="A", shares=100, cost_price=10.0)
        repo.upsert(code="B", shares=200, cost_price=20.0)
        repo.close_position("B")

        held = repo.list_all(held_only=True)
        assert len(held) == 1
        assert held[0].code == "A"

        all_pos = repo.list_all(held_only=False)
        assert len(all_pos) == 2
