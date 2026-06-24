# -*- coding: utf-8 -*-
"""测试 _forward_adjust 前复权逻辑"""

import sys
import os
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsa_cli.multi_fetcher import _forward_adjust


class TestForwardAdjust:
    """前复权单元测试"""

    def test_no_records(self):
        """空列表 / 单条记录不报错"""
        assert _forward_adjust([]) == []
        assert _forward_adjust([{"date": "2026-06-23", "close": 100, "open": 100, "high": 105, "low": 95}]) == [
            {"date": "2026-06-23", "close": 100, "open": 100, "high": 105, "low": 95}
        ]

    def test_no_gap_no_change(self):
        """无除权缺口 → 原样返回"""
        records = [
            {"date": "2026-06-24", "close": 555, "open": 552, "high": 575, "low": 546},
            {"date": "2026-06-23", "close": 552, "open": 575, "high": 587, "low": 540},
            {"date": "2026-06-22", "close": 580, "open": 584, "high": 591, "low": 560},
        ]
        result = _forward_adjust(records)
        # 无缺口，应完全相同
        for r_orig, r_adj in zip(records, result):
            assert r_orig["close"] == r_adj["close"]
            assert r_orig["open"] == r_adj["open"]

    def test_single_ex_rights_newest_first(self):
        """一次除权：数据最新在前（THS默认顺序）→ 历史价格按因子缩小"""
        # 模拟新易盛 6/11 除权场景
        records = [
            # 最新在前（除权后）
            {"date": "2026-06-23", "open": 575, "high": 587, "low": 540, "close": 552, "volume": 444398, "amount": 2488629},
            {"date": "2026-06-22", "open": 584, "high": 591, "low": 560, "close": 580, "volume": 455114, "amount": 2630629},
            {"date": "2026-06-18", "open": 553, "high": 588, "low": 551, "close": 581, "volume": 428749, "amount": 2473982},
            {"date": "2026-06-17", "open": 546, "high": 559, "low": 537, "close": 558, "volume": 389548, "amount": 2134968},
            {"date": "2026-06-16", "open": 542, "high": 562, "low": 535, "close": 549, "volume": 405700, "amount": 2224514},
            {"date": "2026-06-15", "open": 515, "high": 541, "low": 490, "close": 540, "volume": 612302, "amount": 3180394},
            {"date": "2026-06-12", "open": 540, "high": 545, "low": 503, "close": 506, "volume": 654443, "amount": 3373413},
            # 除权日：今开 552 vs 前收 772 → 因子 = 552/772 ≈ 0.7146
            {"date": "2026-06-11", "open": 552, "high": 575, "low": 499, "close": 526, "volume": 667564, "amount": 3561026},
            # 除权前（旧价格，应被调整）
            {"date": "2026-06-10", "open": 770, "high": 800, "low": 760, "close": 772, "volume": 308882, "amount": 2403863},
            {"date": "2026-06-09", "open": 749, "high": 795, "low": 738, "close": 786, "volume": 348609, "amount": 2680364},
        ]
        result = _forward_adjust(records)
        
        # 验证返回顺序（最新在前）
        assert result[0]["date"] == "2026-06-23"
        assert result[-1]["date"] == "2026-06-09"
        
        # 除权后的记录不应被调整
        for r in result[:8]:  # 6/23 到 6/11
            orig = [x for x in records if x["date"] == r["date"]][0]
            assert r["close"] == orig["close"], f"{r['date']}: close should be unchanged"
            assert r["open"] == orig["open"], f"{r['date']}: open should be unchanged"
        
        # 除权前的记录应被调整（前复权因子 552/772 ≈ 0.7150）
        factor = 552 / 772
        for r in result[8:]:  # 6/10, 6/09
            orig = [x for x in records if x["date"] == r["date"]][0]
            expected = round(orig["close"] * factor, 2)
            assert r["close"] == pytest.approx(expected, rel=1e-4), f"{r['date']}: close {r['close']} != {expected}"
            assert r["open"] == pytest.approx(round(orig["open"] * factor, 2), rel=1e-4), f"{r['date']}: open"
            assert r["high"] == pytest.approx(round(orig["high"] * factor, 2), rel=1e-4), f"{r['date']}: high"
            assert r["low"] == pytest.approx(round(orig["low"] * factor, 2), rel=1e-4), f"{r['date']}: low"

    def test_multiple_ex_rights(self):
        """多次除权：累计因子正确"""
        records = [
            # 最新（第二次除权后）
            {"date": "2026-06-20", "open": 50, "high": 55, "low": 48, "close": 52, "volume": 100, "amount": 500},
            {"date": "2026-06-19", "open": 49, "high": 52, "low": 47, "close": 51, "volume": 100, "amount": 500},
            # 第二次除权日：今开 50 vs 前收 100 → 因子 0.5
            {"date": "2026-06-18", "open": 50, "high": 51, "low": 48, "close": 49, "volume": 100, "amount": 500},
            # 第一次除权后
            {"date": "2026-06-17", "open": 98, "high": 102, "low": 96, "close": 100, "volume": 100, "amount": 500},
            {"date": "2026-06-16", "open": 95, "high": 100, "low": 94, "close": 99, "volume": 100, "amount": 500},
            # 第一次除权日：今开 100 vs 前收 200 → 因子 0.5
            {"date": "2026-06-15", "open": 100, "high": 102, "low": 98, "close": 99, "volume": 100, "amount": 500},
            # 除权前（旧价格）
            {"date": "2026-06-14", "open": 198, "high": 205, "low": 195, "close": 200, "volume": 100, "amount": 500},
            {"date": "2026-06-13", "open": 195, "high": 200, "low": 190, "close": 198, "volume": 100, "amount": 500},
        ]
        result = _forward_adjust(records)
        
        # 最新 2 条（第二次除权后）→ 不变
        for r in result[:2]:
            orig = [x for x in records if x["date"] == r["date"]][0]
            assert r["close"] == orig["close"], f"{r['date']}: should be unchanged"
        
        # 两次除权之间（6/17, 6/16）→ 乘以第二次因子 0.5
        # 注意：6/18 是除权日，价格已反映新价，不需要调整
        factor2 = 50 / 100  # 0.5
        for date in ["2026-06-17", "2026-06-16"]:
            r = [x for x in result if x["date"] == date][0]
            orig = [x for x in records if x["date"] == date][0]
            expected = round(orig["close"] * factor2, 2)
            assert r["close"] == pytest.approx(expected, rel=1e-4), f"{date}: close"
        
        # 第一次除权前（6/15, 6/14, 6/13）→ 累计因子 0.5 * 0.5 = 0.25
        # 注意：6/15 是第一个除权日，其价格需乘以第二次的因子 0.5（它在两次除权之间）
        # 6/14, 6/13 是第一次除权前，需乘以累计 0.25
        factor_cum = (100/200) * (50/100)  # 0.25
        for date in ["2026-06-14", "2026-06-13"]:
            r = [x for x in result if x["date"] == date][0]
            orig = [x for x in records if x["date"] == date][0]
            expected = round(orig["close"] * factor_cum, 2)
            assert r["close"] == pytest.approx(expected, rel=1e-4), f"{date}: close"
        
        # 6/15 是第一次除权日，只需第二次因子（它已在第一次除权后）
        r = [x for x in result if x["date"] == "2026-06-15"][0]
        orig = [x for x in records if x["date"] == "2026-06-15"][0]
        expected = round(orig["close"] * (50/100), 2)  # only second factor
        assert r["close"] == pytest.approx(expected, rel=1e-4), f"2026-06-15: close"
        
        # 6/18 是第二次除权日，价格不变
        r = [x for x in result if x["date"] == "2026-06-18"][0]
        orig = [x for x in records if x["date"] == "2026-06-18"][0]
        assert r["close"] == orig["close"], "2026-06-18: ex-date, should be unchanged"

    def test_volume_amount_unchanged(self):
        """volume 和 amount 不因复权而改变"""
        records = [
            {"date": "2026-06-12", "open": 50, "high": 51, "low": 48, "close": 49, "volume": 123456, "amount": 987654},
            {"date": "2026-06-11", "open": 50, "high": 52, "low": 48, "close": 50, "volume": 234567, "amount": 876543},
            {"date": "2026-06-10", "open": 98, "high": 105, "low": 95, "close": 100, "volume": 345678, "amount": 765432},
        ]
        result = _forward_adjust(records)
        for r in result:
            orig = [x for x in records if x["date"] == r["date"]][0]
            assert r["volume"] == orig["volume"]
            assert r["amount"] == orig["amount"]

    def test_threshold_boundary(self):
        """阈值边界：超过 15% 触发，低于不触发"""
        # 14% 缺口 → 不触发
        records_14 = [
            {"date": "2026-06-11", "open": 86, "high": 88, "low": 84, "close": 87, "volume": 100, "amount": 500},
            {"date": "2026-06-10", "open": 98, "high": 102, "low": 96, "close": 100, "volume": 100, "amount": 500},
        ]
        result = _forward_adjust(records_14, threshold=0.15)
        # 不触发：|86-100|/100 = 0.14 < 0.15
        assert result[1]["close"] == 100, "14% gap should not trigger adjustment"

        # 16% 缺口 → 触发（用16%确保超过15%阈值）
        records_16 = [
            {"date": "2026-06-11", "open": 84, "high": 88, "low": 80, "close": 87, "volume": 100, "amount": 500},
            {"date": "2026-06-10", "open": 98, "high": 102, "low": 96, "close": 100, "volume": 100, "amount": 500},
        ]
        result = _forward_adjust(records_16, threshold=0.15)
        # 触发：|84-100|/100 = 0.16 > 0.15
        factor = 84 / 100
        assert result[1]["close"] == pytest.approx(round(100 * factor, 2), rel=1e-4), "16% gap should trigger"

    def test_zero_prices_handled(self):
        """零价格不触发除权误判"""
        records = [
            {"date": "2026-06-12", "open": 50, "high": 51, "low": 48, "close": 49, "volume": 100, "amount": 500},
            {"date": "2026-06-11", "open": 0, "high": 0, "low": 0, "close": 0, "volume": 100, "amount": 500},
            {"date": "2026-06-10", "open": 0, "high": 0, "low": 0, "close": 100, "volume": 100, "amount": 500},
        ]
        result = _forward_adjust(records)
        # 应该原样返回，不报错
        assert len(result) == 3
        assert result[0]["close"] == 49

    def test_reverse_chronological_preserved(self):
        """返回顺序保持最新在前"""
        records = [
            {"date": "2026-06-20", "open": 50, "high": 55, "low": 48, "close": 52, "volume": 100, "amount": 500},
            {"date": "2026-06-15", "open": 45, "high": 50, "low": 44, "close": 48, "volume": 100, "amount": 500},
            {"date": "2026-06-10", "open": 98, "high": 105, "low": 95, "close": 100, "volume": 100, "amount": 500},
            {"date": "2026-06-05", "open": 90, "high": 95, "low": 88, "close": 93, "volume": 100, "amount": 500},
        ]
        result = _forward_adjust(records)
        assert result[0]["date"] == "2026-06-20"
        assert result[-1]["date"] == "2026-06-05"
