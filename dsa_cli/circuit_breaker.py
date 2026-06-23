# -*- coding: utf-8 -*-
"""
数据源熔断器 (Circuit Breaker)

指数退避策略：
- 首次失败：熔断 5 秒
- 第 N 次连续失败：熔断 5 × 2^(N-1) 秒
- 最大熔断时间：86400 秒（1 天）
- 成功一次后立即重置 fail_count = 0

状态持久化在 SQLite `source_health` 表中，跨 CLI 调用生效。
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict

from dsa_db.schema import DatabaseManager, SourceHealth

logger = logging.getLogger(__name__)

# 配置常量
BASE_BACKOFF_SECONDS = 5       # 基础退避时间
MAX_BACKOFF_SECONDS = 86400    # 最大退避（1天）


class CircuitBreaker:
    """数据源熔断器"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self._db = db or DatabaseManager.get_instance()

    def is_banned(self, source_name: str) -> bool:
        """检查数据源是否处于熔断状态"""
        health = self._get_health(source_name)
        if health is None or health.banned_until is None:
            return False

        if health.banned_until > datetime.now():
            remaining = (health.banned_until - datetime.now()).total_seconds()
            logger.debug(f"源 {source_name} 熔断中，剩余 {remaining:.0f}s")
            return True

        # 熔断已过期，但不重置 fail_count —— 等成功后再重置
        return False

    def record_success(self, source_name: str):
        """记录成功，重置熔断状态"""
        with self._db.session() as session:
            health = session.query(SourceHealth).filter(
                SourceHealth.source_name == source_name
            ).first()

            if health is None:
                health = SourceHealth(source_name=source_name)
                session.add(health)

            health.fail_count = 0
            health.banned_until = None
            health.total_successes = (health.total_successes or 0) + 1
            health.last_success = datetime.now()
            health.last_error = None
            logger.info(f"✅ 源 {source_name} 恢复健康")

    def record_failure(self, source_name: str, error: str = ""):
        """记录失败，计算新的熔断时间"""
        with self._db.session() as session:
            health = session.query(SourceHealth).filter(
                SourceHealth.source_name == source_name
            ).first()

            if health is None:
                health = SourceHealth(source_name=source_name)
                session.add(health)

            health.fail_count = (health.fail_count or 0) + 1
            health.total_failures = (health.total_failures or 0) + 1
            health.last_failure = datetime.now()
            health.last_error = error[:500] if error else ""

            # 指数退避: 5 * 2^(fail_count-1) 秒
            backoff = min(BASE_BACKOFF_SECONDS * (2 ** (health.fail_count - 1)), MAX_BACKOFF_SECONDS)
            health.banned_until = datetime.now() + timedelta(seconds=backoff)

            logger.warning(
                f"❌ 源 {source_name} 第 {health.fail_count} 次失败，"
                f"熔断 {backoff:.0f}s (至 {health.banned_until.strftime('%H:%M:%S')})"
            )

    def get_status(self, source_name: str) -> Optional[Dict]:
        """获取数据源状态详情"""
        health = self._get_health(source_name)
        if health is None:
            return None

        banned = health.banned_until and health.banned_until > datetime.now()
        remaining = 0
        if banned and health.banned_until:
            remaining = max(0, (health.banned_until - datetime.now()).total_seconds())

        return {
            "source_name": health.source_name,
            "banned": banned,
            "remaining_seconds": int(remaining),
            "fail_count": health.fail_count or 0,
            "total_failures": health.total_failures or 0,
            "total_successes": health.total_successes or 0,
            "last_success": health.last_success.isoformat() if health.last_success else None,
            "last_failure": health.last_failure.isoformat() if health.last_failure else None,
            "last_error": health.last_error,
        }

    def list_all_status(self) -> Dict[str, Dict]:
        """列出所有已知数据源状态"""
        with self._db.session() as session:
            records = session.query(SourceHealth).all()
            return {
                r.source_name: {
                    "banned": bool(r.banned_until and r.banned_until > datetime.now()),
                    "remaining_seconds": int(max(0, (r.banned_until - datetime.now()).total_seconds())) if r.banned_until else 0,
                    "fail_count": r.fail_count or 0,
                    "total_successes": r.total_successes or 0,
                    "total_failures": r.total_failures or 0,
                    "last_error": r.last_error,
                }
                for r in records
            }

    def _get_health(self, source_name: str) -> Optional[SourceHealth]:
        with self._db.session() as session:
            return session.query(SourceHealth).filter(
                SourceHealth.source_name == source_name
            ).first()
