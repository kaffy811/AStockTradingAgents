from __future__ import annotations

import pytest

from app.services.security_entity_resolver import (
    SecurityEntityResolver,
    normalize_security_text,
    normalize_symbol_for_market,
)


def _sample_master() -> list[dict]:
    rows: list[dict] = []
    for i in range(100):
        symbol = f"6{i:05d}"
        rows.append({
            "market": "CN",
            "symbol": symbol,
            "short_name": f"样本A股{i}",
            "full_name": f"样本A股{i}股份有限公司",
            "industry": "测试行业",
        })
    for i in range(30):
        symbol = str(700 + i).zfill(5)
        rows.append({
            "market": "HK",
            "symbol": symbol,
            "short_name": f"HK样本{i}",
            "full_name": f"HK Sample {i} Limited",
            "english_name": f"HK SAMPLE {i}",
        })
    for i in range(30):
        ticker = f"T{chr(65 + (i % 26))}{chr(65 + (i // 26))}"
        rows.append({
            "market": "US",
            "symbol": ticker,
            "short_name": f"US Sample {i}",
            "full_name": f"US Sample Corporation {i}",
        })
    rows.extend([
        {"market": "CN", "symbol": "601318", "short_name": "中国平安", "full_name": "中国平安保险(集团)股份有限公司"},
        {"market": "CN", "symbol": "000001", "short_name": "平安银行", "full_name": "平安银行股份有限公司"},
        {"market": "CN", "symbol": "000725", "short_name": "京东方A", "full_name": "京东方科技集团股份有限公司", "former_names": ["京东方"]},
    ])
    return rows


@pytest.mark.asyncio
@pytest.mark.parametrize("idx", [0, 1, 7, 19, 42, 88])
async def test_cn_short_name_full_name_and_code_round_trip(idx):
    row = _sample_master()[idx]
    resolver = SecurityEntityResolver(sample_rows=_sample_master())
    for query in (row["short_name"], row["full_name"], row["symbol"]):
        entity = await resolver.resolve_one(None, query, market_hint="CN")
        assert entity is not None
        assert entity.symbol == row["symbol"]
        assert entity.market == "CN"


@pytest.mark.asyncio
async def test_hk_leading_zero_and_market_isolation():
    resolver = SecurityEntityResolver(sample_rows=_sample_master())
    entity = await resolver.resolve_one(None, "700", market_hint="HK")
    assert entity is not None
    assert entity.market == "HK"
    assert entity.symbol == "00700"
    cn = await resolver.resolve_one(None, "700", market_hint="CN")
    assert cn is None


@pytest.mark.asyncio
async def test_us_ticker_and_company_name():
    resolver = SecurityEntityResolver(sample_rows=_sample_master())
    by_ticker = await resolver.resolve_one(None, "TFA", market_hint="US")
    by_name = await resolver.resolve_one(None, "US Sample Corporation 5", market_hint="US")
    assert by_ticker is not None and by_ticker.symbol == "TFA"
    assert by_name is not None and by_name.symbol == "TFA"


@pytest.mark.asyncio
async def test_ambiguous_short_name_returns_candidates():
    resolver = SecurityEntityResolver(sample_rows=_sample_master())
    result = await resolver.resolve(None, "平安", market_hint="CN", min_confidence=0.72)
    assert result["ambiguity"] is True
    assert {c["symbol"] for c in result["candidates"]} >= {"601318", "000001"}


def test_normalization_rules():
    assert normalize_security_text(" Ａ股（测试）有限公司 ") == "A(测试)"
    assert normalize_symbol_for_market("HK", "700") == "00700"
    assert normalize_symbol_for_market("US", "aapl") == "AAPL"


def test_no_new_hardcoded_sample_symbols_in_resolver_paths():
    checked = [
        "backend/app/services/security_entity_resolver.py",
        "backend/app/agents/chat_skills/base.py",
        "backend/app/agents/chat_skills/report_comparison_skill.py",
        "backend/app/agents/chat_skills/report_explanation_skill.py",
        "backend/app/agents/chat_orchestrator.py",
        "backend/app/agents/central_planning_agent.py",
    ]
    banned = {"600519", "000858", "300750", "000725"}
    for path in checked:
        text = open(path, encoding="utf-8").read()
        for token in banned:
            assert token not in text, f"{token} must not appear in production resolver path {path}"
