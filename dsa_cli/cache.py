# -*- coding: utf-8 -*-
"""
股票信息缓存层

使用 SQLite 缓存股票数据，避免重复网络请求。
- 实时行情: TTL = 5 分钟
- 历史日线: TTL = 1 天（当日数据重新获取）
"""

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# 缓存 TTL 配置
QUOTE_CACHE_TTL = 300        # 实时行情 5 分钟
HISTORY_CACHE_TTL = 86400    # 历史日线 1 天
INDICATORS_CACHE_TTL = 300   # 技术指标 5 分钟

# 内存缓存（进程内加速）
_memory_cache: Dict[str, tuple] = {}  # key -> (data, timestamp)


class StockCache:
    """股票数据缓存管理器"""

    def __init__(self, db_manager=None):
        self._use_db = db_manager is not None
        self._db = db_manager

    def _db_key(self, code: str, data_type: str) -> str:
        return f"cache:{data_type}:{code}"

    def get(self, code: str, data_type: str = "quote") -> Optional[Dict[str, Any]]:
        """获取缓存数据"""
        # 1. 内存缓存
        mem_key = self._db_key(code, data_type)
        if mem_key in _memory_cache:
            data, ts = _memory_cache[mem_key]
            ttl = self._get_ttl(data_type)
            if time.time() - ts < ttl:
                return data
            else:
                del _memory_cache[mem_key]

        # 2. 数据库缓存 (暂未实现，预留给后续扩展)
        return None

    def set(self, code: str, data_type: str, data: Dict[str, Any]):
        """设置缓存"""
        mem_key = self._db_key(code, data_type)
        _memory_cache[mem_key] = (data, time.time())

    def invalidate(self, code: str, data_type: str = None):
        """清除缓存"""
        if data_type:
            mem_key = self._db_key(code, data_type)
            _memory_cache.pop(mem_key, None)
        else:
            prefix = f"cache:"
            keys_to_del = [k for k in _memory_cache if k.startswith(prefix) and code in k]
            for k in keys_to_del:
                del _memory_cache[k]

    def _get_ttl(self, data_type: str) -> int:
        ttls = {
            "quote": QUOTE_CACHE_TTL,
            "history": HISTORY_CACHE_TTL,
            "indicators": INDICATORS_CACHE_TTL,
        }
        return ttls.get(data_type, 300)

    def is_fresh(self, code: str, data_type: str = "quote") -> bool:
        """检查缓存是否新鲜"""
        return self.get(code, data_type) is not None


# 全局缓存实例
_cache = StockCache()
