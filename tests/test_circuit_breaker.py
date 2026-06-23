# -*- coding: utf-8 -*-
"""熔断器 (Circuit Breaker) 测试"""

import os
import tempfile
import time
import pytest
from datetime import datetime, timedelta


@pytest.fixture
def breaker_db():
    """创建带熔断器的临时数据库"""
    from dsa_db.schema import DatabaseManager
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = DatabaseManager(path)
    yield db
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def breaker(breaker_db):
    from dsa_cli.circuit_breaker import CircuitBreaker
    return CircuitBreaker(breaker_db)


class TestCircuitBreaker:
    """熔断器基本功能"""

    def test_initial_state(self, breaker):
        """初始状态：未被熔断"""
        assert not breaker.is_banned("sina")
        status = breaker.get_status("sina")
        assert status is None  # 从未被记录

    def test_record_failure_first(self, breaker):
        """首次失败：熔断 5s"""
        breaker.record_failure("sina", "timeout")
        status = breaker.get_status("sina")
        assert status is not None
        assert status["fail_count"] == 1
        assert status["banned"] is True
        assert 4 <= status["remaining_seconds"] <= 5

    def test_record_failure_exponential(self, breaker):
        """指数退避"""
        from dsa_cli.circuit_breaker import BASE_BACKOFF_SECONDS

        # 第 1 次
        breaker.record_failure("test_expo")
        s1 = breaker.get_status("test_expo")
        assert s1["fail_count"] == 1

        # 第 2 次 -> 5*2^1 = 10s
        breaker.record_failure("test_expo")
        s2 = breaker.get_status("test_expo")
        assert s2["fail_count"] == 2

        # 第 3 次 -> 5*2^2 = 20s
        breaker.record_failure("test_expo")
        s3 = breaker.get_status("test_expo")
        assert s3["fail_count"] == 3

    def test_max_backoff_capped(self, breaker):
        """最大退避不超过 1 天"""
        from dsa_cli.circuit_breaker import MAX_BACKOFF_SECONDS
        # 模拟已经是第 30 次失败
        with breaker._db.session() as session:
            from dsa_db.schema import SourceHealth
            h = session.query(SourceHealth).filter(SourceHealth.source_name == "max_test").first()
            if not h:
                h = SourceHealth(source_name="max_test", fail_count=29)
                session.add(h)
            else:
                h.fail_count = 29

        breaker.record_failure("max_test")
        status = breaker.get_status("max_test")
        assert status["remaining_seconds"] <= MAX_BACKOFF_SECONDS

    def test_success_resets(self, breaker):
        """成功一次重置全部熔断"""
        breaker.record_failure("test_reset")
        assert breaker.is_banned("test_reset")

        breaker.record_success("test_reset")
        assert not breaker.is_banned("test_reset")
        status = breaker.get_status("test_reset")
        assert status["fail_count"] == 0
        assert status["total_successes"] == 1

    def test_is_banned_false_after_expiry(self, breaker):
        """熔断过期后自动解禁"""
        with breaker._db.session() as session:
            from dsa_db.schema import SourceHealth
            h = SourceHealth(
                source_name="expired_test",
                fail_count=1,
                banned_until=datetime.now() - timedelta(seconds=10),  # 10 秒前过期
            )
            session.add(h)

        assert not breaker.is_banned("expired_test")

    def test_list_all_status(self, breaker):
        """列出所有源状态"""
        breaker.record_failure("sina", "timeout")
        breaker.record_success("sohu")

        all_status = breaker.list_all_status()
        assert "sina" in all_status
        assert "sohu" in all_status
        assert all_status["sina"]["banned"] is True
        assert all_status["sohu"]["banned"] is False
