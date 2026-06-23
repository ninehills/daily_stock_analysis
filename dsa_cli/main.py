#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dsa - Daily Stock Analysis CLI 工具

Hermes Agent 可通过 terminal() 调用此工具获取股票数据。
所有命令支持 --json 输出结构化数据。

Usage:
    dsa quote 600519                    # 实时行情
    dsa history 600519 --days 60        # 历史日线
    dsa indicators 600519               # 技术指标
    dsa resolve 茅台                     # 名称→代码
    dsa index sh                        # 大盘指数
    dsa position list                   # 持仓列表
    dsa position add 600519 --shares 100 --cost 1850.00  # 添加持仓
"""

import json
import logging
import sys
import os
import time
from datetime import date, datetime
from typing import Optional

import click
import pandas as pd

# 确保项目根目录在 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dsa_db.schema import DatabaseManager
from dsa_db.stock_repo import StockRepository
from dsa_db.analysis_repo import AnalysisRepository
from dsa_db.position_repo import PositionRepository
from dsa_cli.cache import _cache as cache
from dsa_cli.indicators import calculate_all_indicators, get_latest_indicators
from dsa_cli.multi_fetcher import fetch_quote, fetch_history, fetch_resolve

logger = logging.getLogger(__name__)


# ============================================================
# Helpers
# ============================================================

def _fmt_json(data, indent=2):
    """格式化 JSON 输出"""
    return json.dumps(data, ensure_ascii=False, indent=indent, default=str)


def _output(data, as_json=False):
    """统一输出"""
    if as_json:
        click.echo(_fmt_json(data))
    else:
        if isinstance(data, dict):
            click.echo(_fmt_json(data))
        elif isinstance(data, list):
            click.echo(_fmt_json(data))
        else:
            click.echo(str(data))


# ============================================================
# fetch helpers
# ============================================================

def _fetch_quote_akshare(code: str) -> dict:
    """通过 akshare 获取实时行情"""
    import akshare as ak
    try:
        # 尝试获取 A 股实时行情
        df = ak.stock_zh_a_spot_em()
        row = df[df["代码"] == code]
        if not row.empty:
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
                "pe": float(r["市盈率-动态"]) if r.get("市盈率-动态", "-") != "-" else None,
                "market_cap": float(r["总市值"]) if r["总市值"] != "-" else None,
            }
    except Exception as e:
        logger.warning(f"akshare 实时行情获取失败: {e}")

    return {"code": code, "error": "无法获取实时行情"}


def _fetch_history_akshare(code: str, days: int = 60) -> list:
    """通过 akshare 获取历史日线"""
    import akshare as ak
    try:
        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - pd.Timedelta(days=days + 30)).strftime("%Y%m%d")

        df = ak.stock_zh_a_hist(symbol=code, period="daily",
                                start_date=start_date, end_date=end_date,
                                adjust="qfq")

        if df is None or df.empty:
            return []

        # 标准化列名
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
        logger.warning(f"akshare 历史日线获取失败: {e}")
        return []


def _resolve_name(name: str) -> list:
    """通过名称/拼音查找股票代码"""
    import akshare as ak
    try:
        df = ak.stock_zh_a_spot_em()
        results = []

        # 精确匹配名称
        exact = df[df["名称"] == name]
        for _, r in exact.iterrows():
            results.append({"code": r["代码"], "name": r["名称"], "match_type": "精确"})

        # 模糊匹配名称
        if len(results) < 10:
            fuzzy = df[df["名称"].str.contains(name, na=False)]
            for _, r in fuzzy.iterrows():
                if len(results) >= 10:
                    break
                if r["代码"] not in [x["code"] for x in results]:
                    results.append({"code": r["代码"], "name": r["名称"], "match_type": "模糊"})

        return results[:20]
    except Exception as e:
        logger.warning(f"名称解析失败: {e}")
        return []


def _fetch_index_akshare(market: str) -> dict:
    """获取大盘指数"""
    import akshare as ak
    try:
        df = ak.stock_zh_index_spot_em()
        if df is None or df.empty:
            return {"error": "无法获取指数数据"}

        index_map = {
            "sh": "上证指数", "sz": "深证成指", "cy": "创业板指",
            "hs300": "沪深300", "sz50": "上证50", "kc50": "科创50",
        }
        target_name = index_map.get(market, market)

        row = df[df["名称"] == target_name]
        if row.empty:
            # 模糊查找
            row = df[df["名称"].str.contains(target_name, na=False)]

        if not row.empty:
            r = row.iloc[0]
            return {
                "code": str(r["代码"]),
                "name": str(r["名称"]),
                "price": float(r["最新价"]),
                "change_pct": float(r["涨跌幅"]),
                "change_amount": float(r["涨跌额"]),
                "volume": float(r["成交量"]) if "成交量" in r else None,
                "amount": float(r["成交额"]) if "成交额" in r else None,
            }
    except Exception as e:
        logger.warning(f"指数获取失败: {e}")

    return {"error": f"未找到指数: {market}"}


# ============================================================
# CLI Commands
# ============================================================

@click.group()
@click.option("--json", "as_json", is_flag=True, help="JSON 输出")
@click.option("--db", "db_path", default=None, help="数据库路径")
@click.pass_context
def cli(ctx, as_json, db_path):
    """dsa - Daily Stock Analysis CLI 工具"""
    ctx.ensure_object(dict)
    ctx.obj["json"] = as_json
    ctx.obj["db"] = DatabaseManager(db_path) if db_path else DatabaseManager.get_instance()


@cli.command()
@click.argument("code")
@click.option("--force", is_flag=True, help="强制刷新，忽略缓存")
@click.pass_context
def quote(ctx, code, force):
    """获取股票实时行情

    CODE: 股票代码，如 600519, 000001
    """
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]

    # 检查缓存
    if not force:
        cached = cache.get(code, "quote")
        if cached:
            _output(cached, as_json)
            return

    # 获取实时行情（多源并行）
    result = fetch_quote(code)

    if "error" not in result:
        cache.set(code, "quote", result)

        # 同时尝试保存到 SQLite（仅保存当前快照）
        try:
            repo = StockRepository(db)
            records = [{
                "date": date.today(),
                "open": result.get("open"),
                "high": result.get("high"),
                "low": result.get("low"),
                "close": result.get("price"),
                "volume": result.get("volume"),
                "amount": result.get("amount"),
                "pct_chg": result.get("change_pct"),
            }]
            repo.save_daily(code, result.get("name", ""), records, source="akshare")
        except Exception as e:
            logger.debug(f"保存到 SQLite 失败: {e}")

    _output(result, as_json)


@cli.command()
@click.argument("code")
@click.option("--days", default=60, help="获取天数 (默认: 60)")
@click.option("--force", is_flag=True, help="强制刷新")
@click.pass_context
def history(ctx, code, days, force):
    """获取历史日线数据

    CODE: 股票代码
    """
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]

    if not force:
        cached = cache.get(code, "history")
        if cached:
            _output(cached, as_json)
            return

    records = fetch_history(code, days)

    if records:
        cache.set(code, "history", {"code": code, "count": len(records), "records": records})

        # 保存到 SQLite
        try:
            repo = StockRepository(db)
            repo.save_daily(code, "", records, source="akshare")
        except Exception as e:
            logger.debug(f"保存到 SQLite 失败: {e}")

    _output({"code": code, "count": len(records), "records": records}, as_json)


@cli.command()
@click.argument("code")
@click.option("--force", is_flag=True, help="强制刷新")
@click.pass_context
def indicators(ctx, code, force):
    """计算技术指标 (MA/MACD/RSI/KDJ/BOLL)

    CODE: 股票代码
    """
    as_json = ctx.obj["json"]

    if not force:
        cached = cache.get(code, "indicators")
        if cached:
            _output(cached, as_json)
            return

    # 先获取历史数据（多源 fallback）
    records = fetch_history(code, 120)
    if not records:
        _output({"error": "无法获取历史数据"}, as_json)
        return

    df = pd.DataFrame(records)
    if df.empty:
        _output({"error": "数据为空"}, as_json)
        return

    # 计算指标
    df = calculate_all_indicators(df)
    result = get_latest_indicators(df)
    result["code"] = code

    # 也加入最近几天的指标
    recent = df.tail(5)[["date", "close", "MA5", "MA10", "MA20", "DIF", "DEA", "MACD",
                          "RSI6", "RSI12", "RSI24", "K", "D", "J"]].to_dict(orient="records")
    result["recent_5d"] = recent

    cache.set(code, "indicators", result)
    _output(result, as_json)


@cli.command()
@click.argument("name")
@click.pass_context
def resolve(ctx, name):
    """通过名称或拼音查找股票代码

    NAME: 股票名称或拼音 (如 '茅台', 'guizhoumaotai', 'tencent')
    """
    as_json = ctx.obj["json"]
    results = fetch_resolve(name)
    _output({"query": name, "count": len(results), "results": results}, as_json)


@cli.command("source-status")
@click.pass_context
def source_status(ctx):
    """查看数据源健康状态（熔断器）"""
    as_json = ctx.obj["json"]
    from dsa_cli.circuit_breaker import CircuitBreaker
    breaker = CircuitBreaker()
    status = breaker.list_all_status()
    _output({"sources": status}, as_json)


@cli.command("search-news")
@click.argument("query")
@click.pass_context
def search_news(ctx, query):
    """搜索金融资讯（东方财富妙想）"""
    as_json = ctx.obj["json"]
    from dsa_cli.multi_fetcher import _fetch_news_miaoxiang
    results = _fetch_news_miaoxiang(query)
    if results:
        _output({"query": query, "count": len(results), "results": results}, as_json)
    else:
        _output({"query": query, "error": "无结果" if results is not None else "API 不可用（需 MX_APIKEY）"}, as_json)


@cli.command()
@click.argument("market", default="sh")
@click.pass_context
def index(ctx, market):
    """获取大盘指数

    MARKET: sh(上证), sz(深证), cy(创业板), hs300(沪深300), sz50(上证50)
    """
    as_json = ctx.obj["json"]
    result = _fetch_index_akshare(market)
    _output(result, as_json)


# ============================================================
# Position 持仓管理
# ============================================================

@cli.group()
def position():
    """持仓管理"""
    pass


@position.command("list")
@click.option("--all", "show_all", is_flag=True, help="显示全部(包括已卖出)")
@click.pass_context
def position_list(ctx, show_all):
    """列出当前持仓"""
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]
    repo = PositionRepository(db)
    positions = repo.list_all(held_only=not show_all)

    items = []
    for p in positions:
        d = p.to_dict()
        d["profit_pct"] = p.profit_pct
        d["profit_amount"] = p.profit_amount
        items.append(d)

    summary = repo.get_portfolio_summary()
    _output({"count": len(items), "summary": summary, "positions": items}, as_json)


@position.command("add")
@click.argument("code")
@click.option("--shares", type=int, required=True, help="持仓数量（股）")
@click.option("--cost", "cost_price", type=float, required=True, help="成本价")
@click.option("--name", default="", help="股票名称")
@click.option("--market", default="cn", help="市场: cn/hk/us")
@click.option("--date", "first_buy_date", default=None, help="首次买入日期 YYYY-MM-DD")
@click.option("--notes", default="", help="备注")
@click.pass_context
def position_add(ctx, code, shares, cost_price, name, market, first_buy_date, notes):
    """添加/更新持仓

    CODE: 股票代码
    """
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]
    repo = PositionRepository(db)

    buy_date = None
    if first_buy_date:
        buy_date = date.fromisoformat(first_buy_date)

    pos = repo.upsert(code=code, name=name, market=market,
                      shares=shares, cost_price=cost_price,
                      first_buy_date=buy_date, notes=notes)
    _output({"status": "ok", "position": pos.to_dict()}, as_json)


@position.command("get")
@click.argument("code")
@click.pass_context
def position_get(ctx, code):
    """查询单只股票持仓"""
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]
    repo = PositionRepository(db)
    pos = repo.get(code)
    if pos:
        d = pos.to_dict()
        d["profit_pct"] = pos.profit_pct
        d["profit_amount"] = pos.profit_amount
        _output(d, as_json)
    else:
        _output({"error": f"未找到持仓: {code}"}, as_json)


@position.command("close")
@click.argument("code")
@click.pass_context
def position_close(ctx, code):
    """标记卖出（不再持有）"""
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]
    repo = PositionRepository(db)
    ok = repo.close_position(code)
    _output({"status": "ok" if ok else "not_found", "code": code}, as_json)


@position.command("update-price")
@click.argument("code")
@click.argument("price", type=float)
@click.pass_context
def position_update_price(ctx, code, price):
    """更新当前价格缓存"""
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]
    repo = PositionRepository(db)
    ok = repo.update_price(code, price)
    _output({"status": "ok" if ok else "not_found", "code": code, "price": price}, as_json)


# ============================================================
# Analysis 分析历史查询
# ============================================================

@cli.group()
def analysis():
    """分析历史查询"""
    pass


@analysis.command("history")
@click.argument("code")
@click.option("--limit", default=20, help="返回数量")
@click.option("--strategy", default=None, help="按策略筛选")
@click.pass_context
def analysis_history(ctx, code, limit, strategy):
    """查询股票的历史分析记录"""
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]
    repo = AnalysisRepository(db)

    if strategy:
        records = repo.get_by_strategy(code, strategy, limit)
    else:
        records = repo.get_by_code(code, limit)

    items = [r.to_dict() for r in records]
    _output({"code": code, "count": len(items), "records": items}, as_json)


@analysis.command("latest")
@click.argument("code")
@click.option("--strategy", default=None, help="按策略筛选")
@click.pass_context
def analysis_latest(ctx, code, strategy):
    """查询股票最新分析结果"""
    as_json = ctx.obj["json"]
    db = ctx.obj["db"]
    repo = AnalysisRepository(db)

    if strategy:
        record = repo.get_latest_by_strategy(code, strategy)
    else:
        record = repo.get_latest(code)

    if record:
        _output(record.to_dict(), as_json)
    else:
        _output({"code": code, "error": "无历史分析记录"}, as_json)


# ============================================================
# Main
# ============================================================

def main():
    """Entry point"""
    cli()


if __name__ == "__main__":
    main()
