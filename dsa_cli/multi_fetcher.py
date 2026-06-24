# -*- coding: utf-8 -*-
"""
多数据源并行获取器

从原 daily_stock_analysis 的 data_provider 架构进化而来：
- 9 个数据源按优先级并行尝试
- 任何源先返回即用，超时自动 fallback
- 支持实时行情、历史日线、股票搜索
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional, Dict, Any, List, Callable

from dotenv import load_dotenv, find_dotenv
_dotenv_path = find_dotenv(usecwd=True)
if _dotenv_path:
    load_dotenv(dotenv_path=_dotenv_path, override=True)  # 自动加载项目根目录 .env 中的 API Key 等配置

logger = logging.getLogger(__name__)


class DataSource:
    """数据源定义"""

    def __init__(self, name: str, priority: int, fetch_fn: Callable, markets: List[str] = None):
        self.name = name
        self.priority = priority  # 越小越优先
        self.fetch_fn = fetch_fn  # 获取函数
        self.markets = markets or ["cn"]  # 支持的市场


# ============================================================
# 各数据源实现
# ============================================================

def _fetch_quote_sina(code: str) -> Optional[Dict]:
    """新浪财经实时行情"""
    try:
        import requests
        url = f"https://hq.sinajs.cn/list=sh{code}"
        headers = {"Referer": "https://finance.sina.com.cn"}
        resp = requests.get(url, headers=headers, timeout=5)
        if resp.status_code != 200 or not resp.text:
            return None
        # 解析 var hq_str_sh601899="xxx,xxx,..."
        data = resp.text.split('"')[1] if '"' in resp.text else ""
        if not data:
            return None
        parts = data.split(",")
        if len(parts) < 32:
            return None
        return {
            "code": code,
            "name": parts[0],
            "open": float(parts[1]),
            "pre_close": float(parts[2]),
            "price": float(parts[3]),
            "high": float(parts[4]),
            "low": float(parts[5]),
            "volume": float(parts[8]),
            "amount": float(parts[9]),
            "change_pct": round((float(parts[3]) - float(parts[2])) / float(parts[2]) * 100, 2),
            "source": "sina",
        }
    except Exception as e:
        logger.debug(f"sina quote failed: {e}")
        return None


def _fetch_quote_efinance(code: str) -> Optional[Dict]:
    """efinance 实时行情"""
    try:
        import efinance as ef
        df = ef.stock.get_realtime_quotes()
        row = df[df["股票代码"] == code]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "code": str(r["股票代码"]),
            "name": str(r["股票名称"]),
            "price": float(r["最新价"]),
            "change_pct": float(r["涨跌幅"]),
            "change_amount": float(r["涨跌额"]),
            "volume": float(r["成交量"]),
            "amount": float(r["成交额"]),
            "high": float(r["最高"]),
            "low": float(r["最低"]),
            "open": float(r["今开"]),
            "pre_close": float(r["昨收"]),
            "turnover_rate": float(r.get("换手率", 0)) if "换手率" in r.index else None,
            "volume_ratio": float(r.get("量比", 0)) if "量比" in r.index else None,
            "source": "efinance",
        }
    except Exception as e:
        logger.debug(f"efinance quote failed: {e}")
        return None


def _fetch_quote_akshare(code: str) -> Optional[Dict]:
    """akshare 实时行情"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if row.empty:
            return None
        r = row.iloc[0]
        return {
            "code": str(r["代码"]),
            "name": str(r["名称"]),
            "price": float(r["最新价"]) if r["最新价"] != "-" else None,
            "change_pct": float(r["涨跌幅"]) if r["涨跌幅"] != "-" else None,
            "change_amount": float(r["涨跌额"]) if r["涨跌额"] != "-" else None,
            "volume": float(r["成交量"]) if r["成交量"] != "-" else None,
            "amount": float(r["成交额"]) if r["成交额"] != "-" else None,
            "high": float(r["最高"]) if r["最高"] != "-" else None,
            "low": float(r["最低"]) if r["最低"] != "-" else None,
            "open": float(r["今开"]) if r["今开"] != "-" else None,
            "pre_close": float(r["昨收"]) if r["昨收"] != "-" else None,
            "turnover_rate": float(r["换手率"]) if r["换手率"] != "-" else None,
            "volume_ratio": float(r["量比"]) if r["量比"] != "-" else None,
            "market_cap": float(r["总市值"]) if r["总市值"] != "-" else None,
            "source": "akshare",
        }
    except Exception as e:
        logger.debug(f"akshare quote failed: {e}")
        return None


def _fetch_quote_eastmoney(code: str) -> Optional[Dict]:
    """东方财富 push2 实时行情（免费、低延迟、无需 API Key）"""
    try:
        import urllib.request, json
        if code.startswith("HK"):
            market_id = "116"
        elif code.isdigit() and len(code) == 6:
            market_id = "1" if code.startswith(("60", "68")) else "0"
        else:
            market_id = "1"
        url = f"https://push2.eastmoney.com/api/qt/stock/get?secid={market_id}.{code}&fields=f43,f44,f45,f46,f47,f48,f57,f58,f60,f170"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://quote.eastmoney.com/",
        })
        resp = urllib.request.urlopen(req, timeout=6)
        d = json.loads(resp.read()).get("data")
        if not d or d.get("f43") is None:
            return None
        price = d["f43"] / 100
        prev = d.get("f60", 0) / 100
        chg = round((price - prev) / prev * 100, 2) if prev else None
        return {
            "code": code,
            "name": d.get("f58", ""),
            "price": price,
            "pre_close": prev,
            "open": d.get("f46", 0) / 100,
            "high": d.get("f44", 0) / 100,
            "low": d.get("f45", 0) / 100,
            "volume": d.get("f47"),
            "amount": d.get("f48"),
            "change_pct": chg,
            "source": "eastmoney",
        }
    except Exception as e:
        logger.debug(f"eastmoney quote failed: {e}")
        return None


def _fetch_quote_yfinance(code: str) -> Optional[Dict]:
    """yfinance 美股/港股（A股已由 eastmoney 覆盖，仅作 HK/US 后备）"""
    try:
        import yfinance as yf
        market_map = {"cn": ".SS", "hk": ".HK", "us": ""}
        market = "cn" if code.isdigit() and len(code) == 6 else ("hk" if code.upper().startswith("HK") else "us")
        suffix = market_map.get(market, "")
        ticker_str = code + suffix if suffix else code
        ticker = yf.Ticker(ticker_str)
        info = ticker.info
        if not info or "currentPrice" not in info:
            return None
        return {
            "code": code,
            "name": info.get("longName", info.get("shortName", "")),
            "price": info.get("currentPrice"),
            "pre_close": info.get("previousClose"),
            "open": info.get("open"),
            "high": info.get("dayHigh"),
            "low": info.get("dayLow"),
            "volume": info.get("volume"),
            "change_pct": round((info.get("currentPrice", 0) - info.get("previousClose", 0)) / info.get("previousClose", 1) * 100, 2),
            "market_cap": info.get("marketCap"),
            "pe": info.get("trailingPE"),
            "source": "yfinance",
        }
    except Exception as e:
        logger.debug(f"yfinance quote failed: {e}")
        return None


def _fetch_history_efinance(code: str, days: int = 120) -> Optional[List[Dict]]:
    """efinance 历史日线"""
    try:
        import efinance as ef
        df = ef.stock.get_quote_history(code)
        if df is None or df.empty:
            return None
        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "涨跌幅": "pct_chg",
        }
        df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
        records = []
        for _, row in df.tail(days).iterrows():
            records.append({
                "date": str(row["date"])[:10],
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
                "amount": float(row.get("amount", 0)),
                "pct_chg": float(row.get("pct_chg", 0)),
            })
        return records
    except Exception as e:
        logger.debug(f"efinance history failed: {e}")
        return None


def _fetch_history_akshare(code: str, days: int = 120) -> Optional[List[Dict]]:
    """akshare 历史日线"""
    try:
        import akshare as ak
        from datetime import date, timedelta
        import pandas as pd
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=days + 30)).strftime("%Y%m%d")
        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start_date, end_date=end_date, adjust="qfq")
        if df is None or df.empty:
            return None
        col_map = {
            "日期": "date", "开盘": "open", "收盘": "close",
            "最高": "high", "最低": "low", "成交量": "volume",
            "成交额": "amount", "涨跌幅": "pct_chg",
        }
        df = df.rename(columns=col_map)
        records = []
        for _, row in df.tail(days).iterrows():
            records.append({
                "date": str(row["date"])[:10],
                "open": float(row.get("open", 0)),
                "high": float(row.get("high", 0)),
                "low": float(row.get("low", 0)),
                "close": float(row.get("close", 0)),
                "volume": float(row.get("volume", 0)),
                "amount": float(row.get("amount", 0)),
                "pct_chg": float(row.get("pct_chg", 0)) if pd.notna(row.get("pct_chg")) else 0,
            })
        return records
    except Exception as e:
        logger.debug(f"akshare history failed: {e}")
        return None


def _fetch_history_yfinance(code: str, days: int = 120) -> Optional[List[Dict]]:
    """yfinance 历史日线"""
    try:
        import yfinance as yf
        market_map = {"cn": ".SS", "hk": ".HK", "us": ""}
        market = "cn" if code.isdigit() and len(code) == 6 else ("hk" if code.upper().startswith("HK") else "us")
        suffix = market_map.get(market, "")
        ticker_str = code + suffix if suffix else code
        ticker = yf.Ticker(ticker_str)
        hist = ticker.history(period="6mo")
        if hist is None or hist.empty:
            return None
        records = []
        for idx, r in hist.tail(days).iterrows():
            records.append({
                "date": idx.strftime("%Y-%m-%d"),
                "open": float(r["Open"]),
                "high": float(r["High"]),
                "low": float(r["Low"]),
                "close": float(r["Close"]),
                "volume": float(r["Volume"]),
                "pct_chg": 0,
            })
        return records
    except Exception as e:
        logger.debug(f"yfinance history failed: {e}")
        return None


def _fetch_history_sohu(code: str, days: int = 120) -> Optional[List[Dict]]:
    """搜狐历史数据（纯 HTTP，不依赖第三方库）"""
    try:
        import requests
        import json as _json
        url = f"https://q.stock.sohu.com/hisHq?code=cn_{code}&stat=1&order=D&period=d&callback=jsonp&rt=jsonp"
        resp = requests.get(url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
        if resp.status_code != 200:
            return None
        text = resp.text
        # 去回调包装: jsonp([{...}])
        if text.startswith("jsonp("):
            text = text[6:]
        if text.endswith(")"):
            text = text[:-1]
        # Sohu 返回的 JSON 后面可能跟了额外数据（统计摘要），只解析第一个完整 JSON 数组
        depth = 0
        end = 0
        for i, ch in enumerate(text):
            if ch == '[':
                depth += 1
            elif ch == ']':
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end > 0:
            text = text[:end]
        data = _json.loads(text)
        hq = data[0]["hq"]
        records = []
        for item in hq[:days]:
            records.append({
                "date": item[0],
                "open": float(item[1]),
                "close": float(item[2]),
                "high": float(item[6]) if len(item) > 6 else float(item[2]),
                "low": float(item[5]) if len(item) > 5 else float(item[2]),
                "volume": float(item[7]) if len(item) > 7 else 0,
                "amount": float(item[8]) if len(item) > 8 else 0,
                "pct_chg": float(item[4].replace("%", "")) if len(item) > 4 else 0,
            })
        return records
    except Exception as e:
        logger.debug(f"sohu history failed: {e}")
        return None


def _fetch_quote_tickflow(code: str) -> Optional[Dict]:
    """TickFlow 实时行情（付费 API，最快最准）"""
    try:
        from tickflow import TickFlow
        import os
        api_key = os.environ.get("TICKFLOW_API_KEY", "")
        if not api_key:
            return None
        # Determine market suffix
        code_upper = code.upper()
        if code_upper.startswith("HK"):
            symbol = code_upper
        elif code.isdigit() and len(code) == 6:
            if code.startswith(("60", "68")):
                symbol = f"{code}.SH"
            else:
                symbol = f"{code}.SZ"
        else:
            symbol = code
        tf = TickFlow(api_key=api_key, timeout=8)
        quotes = tf.quotes.get(symbols=[symbol])
        if not quotes:
            return None
        q = quotes[0]
        ext = q.get("ext") or {}
        price = float(q.get("last_price", 0)) or None
        prev = float(q.get("prev_close", 0)) or None
        chg_pct = float(ext.get("change_pct", 0)) * 100 if ext.get("change_pct") else None
        if chg_pct is None and price and prev:
            chg_pct = round((price - prev) / prev * 100, 2)
        return {
            "code": code,
            "name": ext.get("name") or q.get("name", ""),
            "price": price,
            "pre_close": prev,
            "open": float(q.get("open", 0)) or None,
            "high": float(q.get("high", 0)) or None,
            "low": float(q.get("low", 0)) or None,
            "volume": float(q.get("volume", 0)) or None,
            "amount": float(q.get("amount", 0)) or None,
            "change_pct": chg_pct,
            "change_amount": float(ext.get("change_amount", 0)) or None,
            "source": "tickflow",
        }
    except Exception as e:
        logger.debug(f"tickflow quote failed: {e}")
        return None


def _fetch_quote_miaoxiang(code: str) -> Optional[Dict]:
    """妙想金融数据 API（东方财富官方，自然语言查询）"""
    try:
        import requests, json, os
        api_key = os.environ.get("MX_APIKEY", "")
        if not api_key:
            return None
        url = "https://mkapi2.dfcfs.com/finskillshub/api/claw/query"
        resp = requests.post(url,
            headers={"Content-Type": "application/json", "apikey": api_key},
            json={"toolQuery": f"股票{code}最新价 涨跌幅 最高价 最低价 开盘价 成交量 成交额 换手率"},
            timeout=8)
        if resp.status_code != 200:
            return None
        r = resp.json()
        if r.get("status") != 0:
            return None
        # Parse the structured response
        data = r.get("data", {}).get("data", {}).get("searchDataResultDTO", {})
        dto_list = data.get("dataTableDTOList", [])
        if not dto_list:
            return None
        dto = dto_list[0]
        table = dto.get("table", {})
        name_map = dto.get("nameMap", {})
        entity = dto.get("entityName", "")
        # Extract name from entity like "贵州茅台(600519.SH)"
        stock_name = entity.split("(")[0] if "(" in entity else entity
        # Build indicator map: label -> value
        indicators = {}
        for key, values in table.items():
            if key == "headName":
                continue
            label = name_map.get(str(key), key)
            val = values[-1] if isinstance(values, list) and values else values
            try:
                val = float(val)
            except (ValueError, TypeError):
                pass
            indicators[label] = val
        price = indicators.get("最新价")
        prev = indicators.get("昨收") or indicators.get("前收盘")
        chg = indicators.get("涨跌幅")
        if chg and isinstance(chg, str) and chg.endswith("%"):
            chg = float(chg.replace("%", ""))
        return {
            "code": code,
            "name": stock_name,
            "price": price,
            "pre_close": prev,
            "open": indicators.get("开盘价") or indicators.get("今开"),
            "high": indicators.get("最高价") or indicators.get("最高"),
            "low": indicators.get("最低价") or indicators.get("最低"),
            "volume": indicators.get("成交量"),
            "amount": indicators.get("成交额"),
            "change_pct": chg,
            "turnover_rate": indicators.get("换手率"),
            "source": "miaoxiang",
        }
    except Exception as e:
        logger.debug(f"miaoxiang quote failed: {e}")
        return None


def _fetch_news_miaoxiang(query: str) -> Optional[List[Dict]]:
    """妙想资讯搜索（东方财富官方金融搜索）"""
    try:
        import requests, os
        api_key = os.environ.get("MX_APIKEY", "")
        if not api_key:
            return None
        url = "https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search"
        resp = requests.post(url,
            headers={"Content-Type": "application/json", "apikey": api_key},
            json={"query": query},
            timeout=8)
        if resp.status_code != 200:
            return None
        r = resp.json()
        if r.get("status") != 0:
            return None
        items = r.get("data", {}).get("data", {}).get("llmSearchResponse", {}).get("data", [])
        return [
            {
                "title": i.get("title", ""),
                "content": i.get("content", "")[:500],
                "source": i.get("insName", ""),
                "date": i.get("date", ""),
                "type": i.get("informationType", ""),
                "rating": i.get("rating", ""),
                "entity": i.get("entityFullName", ""),
            }
            for i in items
        ][:10]
    except Exception as e:
        logger.debug(f"miaoxiang search failed: {e}")
        return None


def _fetch_history_tickflow(code: str, days: int = 120) -> Optional[List[Dict]]:
    """TickFlow K线数据"""
    try:
        from tickflow import TickFlow
        from datetime import datetime
        import os
        api_key = os.environ.get("TICKFLOW_API_KEY", "")
        if not api_key:
            return None
        # Determine symbol suffix
        code_upper = code.upper()
        if code_upper.startswith("HK"):
            symbol = code_upper
        elif code.isdigit() and len(code) == 6:
            symbol = f"{code}.{'SH' if code.startswith(('60','68')) else 'SZ'}"
        else:
            symbol = code
        tf = TickFlow(api_key=api_key, timeout=10)
        r = tf.klines.get(symbol=symbol, period="1d", count=days)
        if not r or not r.get("timestamp"):
            return None
        records = []
        n = len(r["timestamp"])
        for i in range(n):
            ts = r["timestamp"][i]
            if isinstance(ts, (int, float)):
                ts = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d")
            records.append({
                "date": str(ts)[:10],
                "open": float(r["open"][i]) if i < len(r.get("open", [])) else 0,
                "high": float(r["high"][i]) if i < len(r.get("high", [])) else 0,
                "low": float(r["low"][i]) if i < len(r.get("low", [])) else 0,
                "close": float(r["close"][i]) if i < len(r.get("close", [])) else 0,
                "volume": float(r["volume"][i]) if i < len(r.get("volume", [])) else 0,
                "amount": float(r["amount"][i]) if i < len(r.get("amount", [])) else 0,
                "pct_chg": 0,
            })
        return records
    except Exception as e:
        logger.debug(f"tickflow history failed: {e}")
        return None


def _ths_code(code: str) -> str:
    """Convert 6-digit code to THSCODE format"""
    cu = code.upper()
    if cu.startswith("HK"):
        return f"UHKG{cu[2:]}"
    if code.isdigit() and len(code) == 6:
        return f"USHA{code}" if code.startswith(("60", "68")) else f"USZA{code}"
    return code


def _fetch_quote_ths(code: str) -> Optional[Dict]:
    """同花顺 THS 实时行情（游客模式，免费）"""
    try:
        from thsdk import THS
        thscode = _ths_code(code)
        with THS() as ths:
            r = ths.market_data_cn(thscode)
            if not r.data:
                return None
            d = r.data[0]
            price = d.get("价格")
            prev = d.get("昨收价")
            chg = None
            if price and prev and prev > 0:
                chg = round((price - prev) / prev * 100, 2)
            return {
                "code": code,
                "name": d.get("名称", ""),
                "price": price,
                "pre_close": prev,
                "open": d.get("开盘价"),
                "high": d.get("最高价"),
                "low": d.get("最低价"),
                "volume": d.get("成交量"),
                "amount": d.get("总金额"),
                "change_pct": chg,
                "source": "ths",
            }
    except Exception as e:
        logger.debug(f"ths quote failed: {e}")
        return None


def _forward_adjust(records: List[Dict], threshold: float = 0.15) -> List[Dict]:
    """
    前复权处理：检测除权除息缺口，将历史价格按复权因子调整。

    THS 返回的是不复权数据，除权日前后会出现价格断层（通常>15%）。
    扫描相邻两日，用 (除权日开盘价 / 前日收盘价) 作为复权因子，
    将除权日**之前**的价格按累计因子缩放，使历史价格与最新价可比。

    Args:
        records: 历史K线列表（最新在前，THS默认顺序）
        threshold: 前收→今开变化率阈值，默认 0.15 (15%)

    Returns:
        前复权后的K线列表（保持原顺序）
    """
    if not records or len(records) < 2:
        return records

    # 转为日期升序（旧→新），深拷贝避免修改原数据
    import copy
    sorted_recs = sorted(copy.deepcopy(records), key=lambda r: r["date"])
    n = len(sorted_recs)

    # 找出所有除权断点：index=断点位置（新数据起始），factor=本次除权因子
    # 累计因子从最早到最新累积
    breakpoints = []  # [(break_index, single_factor, cumulative_factor), ...]
    cum_factor = 1.0

    for i in range(1, n):
        prev_close = sorted_recs[i - 1]["close"]
        curr_open = sorted_recs[i]["open"]
        if prev_close <= 0 or curr_open <= 0:
            continue

        gap = abs(curr_open - prev_close) / prev_close
        if gap > threshold:
            single_factor = curr_open / prev_close
            cum_factor *= single_factor
            breakpoints.append((i, single_factor, cum_factor))
            logger.info(
                f"[前复权] 检测到除权: {sorted_recs[i-1]['date']}→{sorted_recs[i]['date']} "
                f"前收={prev_close:.2f} 今开={curr_open:.2f} "
                f"因子={single_factor:.4f} 累计={cum_factor:.4f}"
            )

    if not breakpoints:
        return records  # 无除权，原样返回

    # 应用复权：
    # 每个除权断点之后的单因子独立，历史数据需要的是"从此断点之后所有因子之积"
    # 从最后往前回溯：当前累计 = 1.0，每遇到一个断点就乘上该断点因子
    # 段 = 断点k-1..断点k（开区间），用 当前累计 调整
    segment_factor = 1.0
    prev_idx = n  # 从最新端开始
    for break_i, single_factor, _ in reversed(breakpoints):
        # 当前段 = [break_i, prev_idx)，用 segment_factor 调整
        for j in range(break_i, prev_idx):
            rec = sorted_recs[j]
            rec["open"] = round(rec["open"] * segment_factor, 2)
            rec["high"] = round(rec["high"] * segment_factor, 2)
            rec["low"] = round(rec["low"] * segment_factor, 2)
            rec["close"] = round(rec["close"] * segment_factor, 2)
        segment_factor *= single_factor
        prev_idx = break_i

    # 最后一段：最旧的数据用最终累计因子
    for j in range(0, prev_idx):
        rec = sorted_recs[j]
        rec["open"] = round(rec["open"] * segment_factor, 2)
        rec["high"] = round(rec["high"] * segment_factor, 2)
        rec["low"] = round(rec["low"] * segment_factor, 2)
        rec["close"] = round(rec["close"] * segment_factor, 2)

    logger.info(
        f"[前复权] 完成: {len(breakpoints)} 个除权点, "
        f"调整了 {breakpoints[-1][0]} 条历史记录"
    )

    # 返回原顺序（最新在前）
    return sorted(sorted_recs, key=lambda r: r["date"], reverse=True)


def _fetch_history_ths(code: str, days: int = 120) -> Optional[List[Dict]]:
    """同花顺 THS 日K线（游客模式，免费）。自动前复权处理。"""
    try:
        from thsdk import THS
        from datetime import datetime
        from zoneinfo import ZoneInfo
        thscode = _ths_code(code)
        with THS() as ths:
            r = ths.klines(thscode, interval="day", count=days)
            if not r.data:
                return None
            records = []
            for k in r.data:
                # thsdk 1.7.x 返回中文键名；兼容处理
                def _get(key_en, key_cn, default=None):
                    val = k.get(key_en) or k.get(key_cn)
                    return val if val is not None else default
                date_val = _get("time", "时间", "")
                if date_val is None:
                    date_val = ""
                if hasattr(date_val, 'strftime'):
                    date_val = date_val.strftime("%Y-%m-%d")
                else:
                    date_val = str(date_val)[:10]
                records.append({
                    "date": date_val,
                    "open": float(_get("open", "开盘价", 0)),
                    "high": float(_get("high", "最高价", 0)),
                    "low": float(_get("low", "最低价", 0)),
                    "close": float(_get("close", "收盘价", 0)),
                    "volume": float(_get("volume", "成交量", 0)) / 100,  # 股→手
                    "amount": float(_get("amount", "总金额", 0)) / 100,  # 分→元？
                    "pct_chg": 0,
                })
            # 前复权处理：将历史价格调整到最新价基准
            records = _forward_adjust(records)
            return records
    except Exception as e:
        logger.debug(f"ths history failed: {e}")
        return None


# ============================================================
# 数据源注册表
# ============================================================

QUOTE_SOURCES: List[DataSource] = [
    DataSource("tickflow", 0, _fetch_quote_tickflow, ["cn"]),      # P0: 付费最优
    DataSource("eastmoney", 0, _fetch_quote_eastmoney, ["cn"]),    # P0: 东方财富免费实时（并行抢答）
    DataSource("miaoxiang", 1, _fetch_quote_miaoxiang, ["cn"]),    # P1: 东财官方
    DataSource("sina", 2, _fetch_quote_sina, ["cn"]),
    DataSource("efinance", 3, _fetch_quote_efinance, ["cn"]),
    DataSource("akshare", 4, _fetch_quote_akshare, ["cn"]),
    DataSource("yfinance", 99, _fetch_quote_yfinance, ["hk", "us"]),  # 仅港股美股后备
]

HISTORY_SOURCES: List[DataSource] = [
    DataSource("tickflow", 0, _fetch_history_tickflow, ["cn"]),    # P0: 最优 (前复权)
    DataSource("sohu", 1, _fetch_history_sohu, ["cn"]),            # P1: 纯HTTP免费
    DataSource("efinance", 2, _fetch_history_efinance, ["cn"]),
    DataSource("akshare", 3, _fetch_history_akshare, ["cn"]),
    DataSource("yfinance", 99, _fetch_history_yfinance, ["hk", "us"]),  # 仅港股美股后备
]


# ============================================================
# 并行获取引擎（带熔断器）
# ============================================================

# 每源超时配置
FETCH_TIMEOUTS = {
    "tickflow": 3,
    "eastmoney": 3,
    "miaoxiang": 4,
    "sohu": 3,
    "sina": 4,
    "efinance": 5,
    "akshare": 6,
    "yfinance": 6,
}
DEFAULT_FETCH_TIMEOUT = 5
OVERALL_TIMEOUT = 15  # 整体超时

# 全局熔断器（懒加载）
_breaker: Optional["CircuitBreaker"] = None


def _get_breaker() -> "CircuitBreaker":
    global _breaker
    if _breaker is None:
        from dsa_cli.circuit_breaker import CircuitBreaker
        _breaker = CircuitBreaker()
    return _breaker


def _run_one_source(source_name: str, fn: Callable, timeout: float, *args, **kwargs):
    """在线程中运行一个数据源，带超时和熔断记录"""
    breaker = _get_breaker()
    try:
        import threading
        result_holder = {"data": None, "error": None, "timed_out": False}

        def target():
            try:
                result_holder["data"] = fn(*args, **kwargs)
            except Exception as e:
                result_holder["error"] = str(e)

        t = threading.Thread(target=target, daemon=True)
        t.start()
        t.join(timeout)

        if t.is_alive():
            result_holder["timed_out"] = True
            # 不 raise，线程会随着进程结束被回收
            breaker.record_failure(source_name, f"超时 ({timeout}s)")
            return None

        if result_holder["error"]:
            breaker.record_failure(source_name, result_holder["error"])
            return None

        if result_holder["data"]:
            breaker.record_success(source_name)

        return result_holder["data"]
    except Exception as e:
        breaker.record_failure(source_name, str(e))
        return None


def _get_available_sources(source_list: List[DataSource], market: str = "cn") -> List[DataSource]:
    """过滤出未熔断且支持目标市场的数据源"""
    breaker = _get_breaker()
    available = []
    for s in source_list:
        if market not in (s.markets or ["cn"]):
            continue
        if breaker.is_banned(s.name):
            continue
        available.append(s)
    # 按优先级排序
    available.sort(key=lambda s: s.priority)
    return available


def fetch_quote(code: str) -> Optional[Dict[str, Any]]:
    """
    并行从多源获取实时行情，首个成功即返回。

    - 跳过已熔断的数据源
    - 所有可用源并行启动
    - 单源超时 3-6s，整体超时 15s
    - 成功/失败自动记录到熔断器
    - 首结果返回后不阻塞：其余源在后台继续，结果仍会被记录
    """
    available = _get_available_sources(QUOTE_SOURCES)
    if not available:
        return {"code": code, "error": "所有数据源均处于熔断状态"}

    logger.info(f"可用行情源: {[s.name for s in available]}")

    executor = ThreadPoolExecutor(max_workers=len(available))
    futures = {}
    for s in available:
        timeout = FETCH_TIMEOUTS.get(s.name, DEFAULT_FETCH_TIMEOUT)
        fut = executor.submit(_run_one_source, s.name, s.fetch_fn, timeout, code)
        futures[fut] = s.name

    best_result = None
    try:
        for future in as_completed(futures, timeout=OVERALL_TIMEOUT):
            name = futures[future]
            try:
                result = future.result(timeout=0.5)
                if result and isinstance(result, dict) and "error" not in result:
                    if best_result is None:
                        best_result = result
                        logger.info(f"行情来自: {name} (首个成功)")
                    # 不 break，让其他源继续跑以记录状态
            except Exception:
                pass
    except Exception:
        pass

    # 不等待剩余任务，后台继续跑
    executor.shutdown(wait=False)
    return best_result or {"code": code, "error": "所有数据源均失败（超时或熔断）"}


def fetch_history(code: str, days: int = 120) -> Optional[List[Dict[str, Any]]]:
    """
    并行从多源获取历史日线，首个成功即返回。

    所有可用源（未熔断）并行启动，不阻塞等待。
    """
    available = _get_available_sources(HISTORY_SOURCES)
    if not available:
        return []

    logger.info(f"可用日线源: {[s.name for s in available]}")

    executor = ThreadPoolExecutor(max_workers=len(available))
    futures = {}
    for s in available:
        timeout = FETCH_TIMEOUTS.get(s.name, DEFAULT_FETCH_TIMEOUT)
        fut = executor.submit(_run_one_source, s.name, s.fetch_fn, timeout, code, days)
        futures[fut] = s.name

    best_result = None
    try:
        for future in as_completed(futures, timeout=OVERALL_TIMEOUT):
            name = futures[future]
            try:
                result = future.result(timeout=0.5)
                if result and len(result) > 0:
                    if best_result is None:
                        best_result = result
                        logger.info(f"日线来自: {name} (首个成功)")
            except Exception:
                pass
    except Exception:
        pass

    executor.shutdown(wait=False)
    return best_result or []


def fetch_resolve(keyword: str) -> Optional[List[Dict]]:
    """搜索股票（efinance → akshare → sina 多源 fallback）"""
    try:
        import efinance as ef
        df = ef.stock.get_realtime_quotes()
        results = []
        # 精确
        exact = df[df["股票名称"] == keyword]
        for _, r in exact.head(5).iterrows():
            results.append({"code": r["股票代码"], "name": r["股票名称"], "match": "exact"})
        # 模糊
        fuzzy = df[df["股票名称"].str.contains(keyword, na=False)]
        for _, r in fuzzy.head(10).iterrows():
            if r["股票代码"] not in [x["code"] for x in results]:
                results.append({"code": r["股票代码"], "name": r["股票名称"], "match": "fuzzy"})
        return results[:20]
    except:
        pass
    
    try:
        import akshare as ak
        df = ak.stock_zh_a_spot_em()
        results = []
        fuzzy = df[df["名称"].str.contains(keyword, na=False)]
        for _, r in fuzzy.head(20).iterrows():
            results.append({"code": r["代码"], "name": r["名称"], "match": "fuzzy"})
        return results[:20]
    except:
        pass

    # Sina suggest API fallback (纯 HTTP，不依赖第三方库)
    try:
        import urllib.request
        import urllib.parse
        import re

        encoded = urllib.parse.quote(keyword)
        url = f"https://suggest3.sinajs.cn/suggest/type=11&key={encoded}"
        req = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0",
            "Referer": "https://finance.sina.com.cn",
        })
        with urllib.request.urlopen(req, timeout=5) as resp:
            raw = resp.read().decode("gbk", errors="ignore")

        # Parse: var suggestvalue="name,type,code,full_code,name2,...";
        m = re.search(r'"([^"]*)"', raw)
        if m:
            parts = m.group(1).split(",")
            results = []
            i = 0
            while i + 3 < len(parts):
                name = parts[i]
                typ = parts[i + 1]
                code = parts[i + 2]
                if typ == "11" and code and code.isdigit():  # A股
                    results.append({
                        "code": code,
                        "name": name,
                        "match": "exact" if name == keyword else "fuzzy",
                    })
                i += 4  # each record is 4 fields
            if results:
                return results[:20]
    except Exception:
        pass

    return []
