# -*- coding: utf-8 -*-
"""
分析结果仓库
"""

import json
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from sqlalchemy import desc

from dsa_db.schema import DatabaseManager, AnalysisResult

logger = logging.getLogger(__name__)


class AnalysisRepository:
    """分析结果仓库"""

    def __init__(self, db: Optional[DatabaseManager] = None):
        self.db = db or DatabaseManager.get_instance()

    def save(self, code: str, name: str, strategy: str, result: Dict[str, Any]) -> AnalysisResult:
        """
        保存分析结果

        Args:
            code: 股票代码
            name: 股票名称
            strategy: 策略名称
            result: 分析结果字典，可包含:
                - sentiment_score: 情绪评分
                - operation_advice: 操作建议
                - trend_prediction: 趋势预测
                - confidence_level: 置信度
                - analysis_summary: 分析摘要
                - technical_indicators: 技术指标(dict)
                - risk_factors: 风险因素(list)
                - ideal_buy/secondary_buy/stop_loss/take_profit: 点位
                - raw_result: 完整原始结果
        """
        query_id = uuid.uuid4().hex[:12]

        with self.db.session() as session:
            record = AnalysisResult(
                query_id=query_id,
                code=code,
                name=name,
                strategy=strategy,
                report_type=result.get("report_type", "single"),
                sentiment_score=result.get("sentiment_score"),
                operation_advice=result.get("operation_advice"),
                trend_prediction=result.get("trend_prediction"),
                confidence_level=result.get("confidence_level"),
                analysis_summary=result.get("analysis_summary"),
                technical_indicators=json.dumps(result.get("technical_indicators", {}), ensure_ascii=False) if result.get("technical_indicators") else None,
                risk_factors=json.dumps(result.get("risk_factors", []), ensure_ascii=False) if result.get("risk_factors") else None,
                ideal_buy=result.get("ideal_buy"),
                secondary_buy=result.get("secondary_buy"),
                stop_loss=result.get("stop_loss"),
                take_profit=result.get("take_profit"),
                raw_result=json.dumps(result.get("raw_result", result), ensure_ascii=False),
                context_snapshot=json.dumps(result.get("context_snapshot", {}), ensure_ascii=False) if result.get("context_snapshot") else None,
            )
            session.add(record)
            session.flush()
            record_id = record.id

        logger.info(f"分析结果已保存: code={code}, strategy={strategy}, id={record_id}")
        return record

    def get_by_code(self, code: str, limit: int = 20) -> List[AnalysisResult]:
        """按股票代码查询历史分析"""
        with self.db.session() as session:
            return (
                session.query(AnalysisResult)
                .filter(AnalysisResult.code == code)
                .order_by(desc(AnalysisResult.created_at))
                .limit(limit)
                .all()
            )

    def get_by_strategy(self, code: str, strategy: str, limit: int = 10) -> List[AnalysisResult]:
        """按策略查询某股票历史分析"""
        with self.db.session() as session:
            return (
                session.query(AnalysisResult)
                .filter(AnalysisResult.code == code, AnalysisResult.strategy == strategy)
                .order_by(desc(AnalysisResult.created_at))
                .limit(limit)
                .all()
            )

    def get_latest(self, code: str) -> Optional[AnalysisResult]:
        """获取某股票最新分析结果"""
        with self.db.session() as session:
            return (
                session.query(AnalysisResult)
                .filter(AnalysisResult.code == code)
                .order_by(desc(AnalysisResult.created_at))
                .first()
            )

    def get_latest_by_strategy(self, code: str, strategy: str) -> Optional[AnalysisResult]:
        """获取某股票某策略最新分析"""
        with self.db.session() as session:
            return (
                session.query(AnalysisResult)
                .filter(AnalysisResult.code == code, AnalysisResult.strategy == strategy)
                .order_by(desc(AnalysisResult.created_at))
                .first()
            )

    def count_by_code(self, code: str) -> int:
        """统计某股票分析次数"""
        with self.db.session() as session:
            return session.query(AnalysisResult).filter(AnalysisResult.code == code).count()
