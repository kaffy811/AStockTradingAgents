"""Hermetic regressions for market I/O, Redis bridging and truthful fallback."""
import asyncio
import os
import threading
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import FastAPI

# Import settings without relying on a developer's .env or real database.
os.environ.setdefault('DATABASE_URL', 'postgresql+asyncpg://unit:unit@127.0.0.1:1/unit')
os.environ.setdefault('SECRET_KEY', 'unit-test-only-market-resilience-key')

import app.services.cache_service as bridge
from app.services import stock_cache_service as cache
from app.services.stock_data_service import StockDataService, QuoteResult, KlineResult
from app.data.providers import eastmoney_provider as em


@pytest.fixture(autouse=True)
def isolated(monkeypatch):
    monkeypatch.setattr(bridge, '_loop', None)
    monkeypatch.setattr(bridge, '_cb_fail_count', 0)
    monkeypatch.setattr(bridge, '_cb_open_until', 0)
    monkeypatch.setattr(bridge, 'get_redis', lambda: None)
    monkeypatch.setattr(em, '_OPEN_UNTIL', {})
    monkeypatch.setattr(em, '_MAX_INFLIGHT', threading.BoundedSemaphore(4))
    cache.clear_all()
    yield
    cache.clear_all()


@pytest.mark.parametrize('method,args,expected', [
    ('sync_get_json', ('k',), {'price': 10}),
    ('sync_set_json', ('k', {'price': 10}, 60), True),
    ('sync_exists', ('k',), True),
])
async def test_bridge_worker_and_loop_misuse(monkeypatch, method, args, expected):
    redis = SimpleNamespace(get=AsyncMock(return_value='{"price":10}'),
                            setex=AsyncMock(), exists=AsyncMock(return_value=1))
    monkeypatch.setattr(bridge, 'get_redis', lambda: redis)
    bridge.set_event_loop(asyncio.get_running_loop())
    call = getattr(bridge.cache_service, method)
    started = time.monotonic()
    assert call(*args, timeout=0.5) in (None, False)
    assert time.monotonic() - started < 0.1
    assert bridge._cb_fail_count == 0  # misuse is not a Redis outage
    redis.get.assert_not_awaited()
    redis.setex.assert_not_awaited()
    redis.exists.assert_not_awaited()
    assert await asyncio.to_thread(call, *args) == expected


@pytest.mark.parametrize('method,args,async_method,default', [
    ('sync_get_json', ('k',), 'get_json', None),
    ('sync_set_json', ('k', {}, 1), 'set_json', False),
    ('sync_exists', ('k',), 'exists', False),
])
async def test_bridge_timeout_cancels_pending_task(monkeypatch, method, args, async_method, default):
    entered, cleaned = asyncio.Event(), asyncio.Event()
    async def slow(*_args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    monkeypatch.setattr(bridge.cache_service, async_method, slow)
    bridge.set_event_loop(asyncio.get_running_loop())
    for _ in range(3):
        entered.clear()
        cleaned.clear()
        assert await asyncio.to_thread(getattr(bridge.cache_service, method), *args, timeout=0.03) is default
        assert entered.is_set()
        await asyncio.wait_for(cleaned.wait(), 0.5)
    assert not [t for t in asyncio.all_tasks() if getattr(t.get_coro(), '__name__', '') == 'slow']


async def test_bridge_redis_failure_is_optional(monkeypatch):
    monkeypatch.setattr(bridge, 'get_redis', lambda: SimpleNamespace(get=AsyncMock(side_effect=ConnectionError('offline'))))
    bridge.set_event_loop(asyncio.get_running_loop())
    assert await asyncio.to_thread(bridge.cache_service.sync_get_json, 'k') is None


@pytest.mark.parametrize('kind', ['quote', 'kline', 'news'])
async def test_slow_stock_route_does_not_block_other_requests(monkeypatch, kind):
    from app.routers import stocks
    from app.dependencies import get_current_user
    app = FastAPI()
    app.include_router(stocks.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    @app.get('/probe')
    async def probe():
        return {'ok': True}
    entered, release = threading.Event(), threading.Event()
    def slow(*args):
        entered.set()
        assert release.wait(1.5), 'other async request was blocked'
        if kind == 'quote':
            return QuoteResult({'price': 10}, 'fake')
        if kind == 'kline':
            return KlineResult([{'close': 10}], 'fake')
        return {'market': 'CN', 'symbol': '600519', 'items': [], 'count': 0, 'data_quality': {}}
    service = stocks.news_data_service if kind == 'news' else stocks.stock_data_service
    monkeypatch.setattr(service, 'get_stock_news' if kind == 'news' else f'get_{kind}', slow)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        task = asyncio.create_task(client.get(f'/stocks/CN/600519/{kind}'))
        try:
            for _ in range(100):
                if entered.is_set():
                    break
                await asyncio.sleep(0.005)
            assert entered.is_set()
            assert not task.done()
            assert (await asyncio.wait_for(client.get('/probe'), 0.3)).json() == {'ok': True}
        finally:
            release.set()
        assert (await task).status_code == 200


@pytest.mark.parametrize('kind', ['quote', 'kline'])
@pytest.mark.parametrize('market', ['CN', 'HK'])
@pytest.mark.parametrize('outcome', ['backup', 'stale', 'unavailable'])
def test_provider_fallback_contract(kind, market, outcome):
    svc = StockDataService()
    providers = [svc._eastmoney, svc._sina, svc._tencent_quote] if kind == 'quote' and market == 'CN' else (
        [svc._tencent_quote, svc._akshare] if kind == 'quote' else (
            [svc._eastmoney_kline, svc._tencent_kline, svc._akshare] if market == 'CN' else [svc._tencent_kline, svc._akshare]))
    value = {'price': 10} if kind == 'quote' else [{'date': '2026-10-23', 'close': 10}]
    for p in providers:
        setattr(p, f'get_{kind}', MagicMock(side_effect=RuntimeError('502 / remote closed')))
    if outcome == 'backup':
        setattr(providers[1], f'get_{kind}', MagicMock(return_value=value))
    if outcome == 'stale':
        if kind == 'quote':
            cache.set_quote_cache(market, '600519', value, 'original_source', [])
        else:
            cache.set_kline_cache(market, '600519', 'daily', '', 120, value, 'original_source', [])
        for key, (payload, _) in list(cache._store.items()):
            cache._store[key] = (payload, 0)
    r = getattr(svc, f'get_{kind}')(market, '600519')
    assert r.http_status == (503 if outcome == 'unavailable' else 200)
    assert r.stale == (outcome == 'stale')
    assert r.cached == (outcome == 'stale')
    assert r.provider == ('none' if outcome == 'unavailable' else 'original_source' if outcome == 'stale' else r.provider)
    assert 'error' in r.fallback_chain[0]
    if outcome == 'stale':
        assert r.message and '缓存' in r.message
    if outcome == 'unavailable':
        assert r.message
        assert not (r.data.get('price') if kind == 'quote' else r.bars)


def test_shared_cache_hit_remains_available_as_stale(monkeypatch):
    payload = {'data': {'price': 10}, 'provider': 'sina'}
    monkeypatch.setattr(bridge.cache_service, 'sync_get_json', lambda _: payload)
    assert cache.get_quote_cache('CN', '600519') == (payload, True)
    assert cache.get_quote_stale('CN', '600519') == (payload, True)


def test_kline_proxy_has_quote_price_and_non_realtime_label():
    cache.set_kline_cache('CN', '600519', 'daily', '', 120, [{'close': 10}], 'tencent_kline', [])
    r = StockDataService()._stale_or_503_quote('CN', '600519', [], [])
    assert r.data['price'] == 10
    assert r.stale and r.provider == 'kline_proxy' and r.data['is_realtime'] is False


@pytest.mark.parametrize('provider,method,args', [
    (em.EastmoneyDirectProvider, 'get_quote', ('CN', '600519')),
    (em.EastmoneyKlineProvider, 'get_kline', ('CN', '600519')),
])
def test_eastmoney_one_attempt_cooldown_and_cleanup(monkeypatch, provider, method, args):
    session, response = MagicMock(), MagicMock()
    session.__enter__.return_value = session
    session.get.return_value = response
    response.raise_for_status.side_effect = httpx.HTTPError('502 Bad Gateway')
    monkeypatch.setattr(em, '_make_session', lambda: session)
    with pytest.raises(RuntimeError, match='502'):
        getattr(provider(), method)(*args)
    response.close.assert_called_once()
    session.__exit__.assert_called_once()
    assert session.get.call_count == 1
    options = session.get.call_args.kwargs
    assert options['allow_redirects'] is False
    assert options['timeout'].total <= 8
    assert options['timeout'].connect_timeout == 2
    with pytest.raises(RuntimeError, match='cooldown'):
        getattr(provider(), method)(*args)
    assert session.get.call_count == 1
    monkeypatch.setattr(em.time, 'monotonic', lambda: max(em._OPEN_UNTIL.values()) + 1)
    with pytest.raises(RuntimeError, match='502'):
        getattr(provider(), method)(*args)
    assert session.get.call_count == 2


def test_eastmoney_bulkhead_fails_without_queueing(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(em, '_make_session', session)
    for _ in range(4):
        assert em._MAX_INFLIGHT.acquire(False)
    try:
        with pytest.raises(RuntimeError, match='capacity'):
            em._fetch_json(em._QUOTE_URL, {}, 6)
        session.assert_not_called()
    finally:
        for _ in range(4):
            em._MAX_INFLIGHT.release()


async def test_redis_pool_has_bounded_io_and_cleans_failed_startup(monkeypatch):
    from app.core import database
    redis = SimpleNamespace(ping=AsyncMock(side_effect=ConnectionError('offline')), aclose=AsyncMock())
    factory = MagicMock(return_value=redis)
    monkeypatch.setattr(database, 'from_url', factory)
    monkeypatch.setattr(database, '_redis_client', None)
    await database.connect_redis()
    redis.aclose.assert_awaited_once()
    assert database.get_redis() is None
    opts = factory.call_args.kwargs
    assert opts['max_connections'] == 32
    assert opts['socket_timeout'] == opts['socket_connect_timeout'] == 1.0


async def test_profile_preserves_stale_metadata(monkeypatch):
    from app.routers import stocks
    result = QuoteResult({'price': 10}, 'sina', cached=True, stale=True, message='过期缓存')
    monkeypatch.setattr(stocks.stock_data_service, 'get_quote', lambda *_: result)
    monkeypatch.setattr(stocks.industry_classification_service, 'get_stock_industry', AsyncMock(return_value=None))
    monkeypatch.setattr(stocks.industry_classification_service, 'search_stocks', AsyncMock(return_value=[]))
    db = SimpleNamespace(execute=AsyncMock(return_value=MagicMock()))
    db.execute.return_value.scalar_one_or_none.return_value = None
    db.execute.return_value.mappings.return_value.first.return_value = None
    r = await stocks.get_stock_profile('CN', '600519', SimpleNamespace(id='user'), db)
    assert r.quote.stale and r.quote.cached and r.quote.provider == 'sina'
    assert r.quote.message == '过期缓存' and r.data_quality.quote_status == 'stale'


async def test_watchlist_preserves_stale_metadata(monkeypatch):
    from datetime import datetime, timezone
    from uuid import uuid4
    from app.routers import watchlist
    result = QuoteResult({'price': 10}, 'sina', cached=True, stale=True, message='过期缓存')
    monkeypatch.setattr(watchlist._stock_data_svc, 'get_quote', lambda *_: result)
    row = SimpleNamespace(id=uuid4(), market='CN', symbol='600519', name='test', note=None,
                          sort_order=0, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
    count, listing, reports, industries = (MagicMock() for _ in range(4))
    count.scalar_one.return_value = 1
    listing.scalars.return_value.all.return_value = [row]
    reports.mappings.return_value.all.return_value = []
    industries.mappings.return_value.all.return_value = []
    db = SimpleNamespace(execute=AsyncMock(side_effect=[count, listing, reports, industries]))
    r = await watchlist.get_watchlist_enriched(SimpleNamespace(id=uuid4()), db)
    assert r.items[0].quote_stale and r.items[0].quote_cached
    assert r.items[0].quote_provider == 'sina' and r.items[0].quote_message == '过期缓存'


@pytest.mark.parametrize('kind', ['quote', 'kline', 'news'])
async def test_async_chat_tools_offload_sync_io(monkeypatch, kind):
    from app.agents.chat_tools import stock_tools
    loop_thread = threading.get_ident()
    def fake(*args, **kwargs):
        assert threading.get_ident() != loop_thread
        if kind == 'quote':
            return {'price': 10}
        if kind == 'kline':
            return [{'close': 10, 'high': 11, 'low': 9}]
        return {'items': [], 'count': 0}
    svc = stock_tools.news_data_service if kind == 'news' else stock_tools.stock_data_service
    attr = {'quote': 'get_quote_optional', 'kline': 'get_kline_for_agent', 'news': 'get_stock_news'}[kind]
    monkeypatch.setattr(svc, attr, fake)
    cls = {'quote': stock_tools.GetQuoteTool, 'kline': stock_tools.GetKlineSummaryTool, 'news': stock_tools.GetLatestNewsTool}[kind]
    assert (await cls().run(None, market='CN', symbol='600519')).ok


async def test_unexpected_backend_error_is_safe_json():
    from app.main import _unexpected_exception_handler
    app = FastAPI(debug=False)
    app.add_exception_handler(Exception, _unexpected_exception_handler)
    @app.get('/broken')
    async def broken():
        raise RuntimeError('secret traceback details')
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, raise_app_exceptions=False), base_url='http://test') as client:
        response = await client.get('/broken')
    assert response.status_code == 500
    assert response.json()['error_code'] == 'INTERNAL_ERROR'
    assert 'secret' not in response.text and 'Traceback' not in response.text


async def test_redis_errors_open_bridge_circuit_without_blocking(monkeypatch):
    redis = SimpleNamespace(get=AsyncMock(side_effect=ConnectionError('offline')))
    monkeypatch.setattr(bridge, 'get_redis', lambda: redis)
    bridge.set_event_loop(asyncio.get_running_loop())
    for _ in range(bridge._CB_FAIL_THRESHOLD + 2):
        assert await asyncio.to_thread(bridge.cache_service.sync_get_json, 'quote:k') is None
    assert redis.get.await_count == bridge._CB_FAIL_THRESHOLD
    assert bridge.cache_status() == 'unavailable'


async def test_sync_cache_loader_runs_in_worker():
    loop_thread = threading.get_ident()
    def loader():
        assert threading.get_ident() != loop_thread
        return {'ok': True}
    assert await bridge.cache_service.get_or_set_json('k', 1, loader) == {'ok': True}


async def test_financial_runtime_quote_offloads_sync_io(monkeypatch):
    from app.agents.financial_runtime.tool_runtime import FinancialToolRegistry
    from app.agents.financial_runtime.contracts import ToolRequest, FinancialSessionContext
    from app.services.stock_data_service import stock_data_service
    loop_thread = threading.get_ident()
    def fake(*args):
        assert threading.get_ident() != loop_thread
        return {'price': 10}
    monkeypatch.setattr(stock_data_service, 'get_quote_optional', fake)
    req = ToolRequest(trace_id='test', parameters={'entity': {'market': 'CN', 'symbol': '600519'}})
    r = await FinancialToolRegistry().get_quote_snapshot(req, FinancialSessionContext(trace_id='test'))
    assert r.data['quote']['price'] == 10


@pytest.mark.parametrize('kind', ['quote', 'kline'])
@pytest.mark.parametrize('stale,status', [(False, 200), (True, 200), (False, 503)])
async def test_market_route_keeps_http_and_json_contract(monkeypatch, kind, stale, status):
    from app.routers import stocks
    from app.dependencies import get_current_user
    result = (QuoteResult({'price': 10} if status == 200 else {'reason_code': 'NETWORK_UNAVAILABLE'}, 'sina' if status == 200 else 'none')
              if kind == 'quote' else KlineResult([{'close': 10}] if status == 200 else [], 'tencent_kline' if status == 200 else 'none'))
    result.stale, result.cached, result.http_status = stale, stale, status
    monkeypatch.setattr(stocks.stock_data_service, f'get_{kind}', lambda *_: result)
    app = FastAPI()
    app.include_router(stocks.router)
    app.dependency_overrides[get_current_user] = lambda: object()
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get(f'/stocks/CN/600519/{kind}')
    assert response.status_code == status
    body = response.json()
    assert body['stale'] == stale and body['cached'] == stale
    assert body['provider'] == result.provider
    assert isinstance(body['data'], dict if kind == 'quote' else list)
