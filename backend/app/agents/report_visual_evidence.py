"""Capture numeric chart evidence from the same input used by the analysts.

Context-local collectors avoid cross-request state and do not add data requests.
"""
from contextvars import ContextVar
from datetime import date, datetime
import math

_collector = ContextVar('report_visual_evidence', default=None)


class EvidenceText(str):
    def __new__(cls, text, visuals):
        value = super().__new__(cls, text)
        value.visuals = visuals
        return value


def run_with_visuals(call, *args):
    visuals = {}
    token = _collector.set(visuals)
    try:
        return EvidenceText(call(*args), visuals)
    finally:
        _collector.reset(token)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        n = float(value)
        return n if math.isfinite(n) else None
    except (ValueError, TypeError):
        return None


def capture_prices(bars):
    collector = _collector.get()
    if collector is None:
        return
    points = []
    for bar in bars[-30:]:
        value = _number(bar.get('close'))
        raw_date = bar.get('date') or bar.get('trade_date')
        if isinstance(raw_date, (datetime, date)):
            raw_date = raw_date.isoformat()[:10]
        if value is not None and value > 0 and raw_date:
            points.append({'date': str(raw_date)[:10], 'close': value})
    if len(points) >= 2:
        collector['prices'] = points


def capture_growth(snapshot):
    collector = _collector.get()
    if collector is None:
        return
    period = snapshot.get('data_quality', {}).get('latest_report_date')
    if isinstance(period, (datetime, date)):
        period = period.isoformat()[:10]
    if not period:
        return
    growth = snapshot.get('growth') or {}
    items = []
    for key, label in [('revenue_growth_yoy', '营业收入'), ('net_profit_growth_yoy', '净利润')]:
        n = _number(growth.get(key))
        if n is not None:
            items.append({'label': label, 'value': n, 'as_of': str(period), 'unit': '%'})
    if items:
        collector['growth'] = items
