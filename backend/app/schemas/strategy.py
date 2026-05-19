from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class StrategyRuleResult(BaseModel):
    rule_name: str
    passed: bool
    details: str


class BreakoutEvaluation(BaseModel):
    symbol: str
    timeframe: str
    ts: datetime
    is_valid_setup: bool
    confidence_score: float
    reasoning: list[str]
    rejection_reasons: list[str]
    suggested_entry: Decimal | None = None
    suggested_stop: Decimal | None = None
    suggested_target: Decimal | None = None
    rules_checked: list[StrategyRuleResult]
