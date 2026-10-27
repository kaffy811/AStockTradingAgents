from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from app.agents.reader_report import beginner_messages, clean_evidence, peers_have_matching_periods
from app.agents.report_visual_evidence import run_with_visuals, capture_prices, capture_growth, EvidenceText
from app.core.config import settings

@pytest.fixture(autouse=True)
def beginner_mode(monkeypatch):
    monkeypatch.setattr(settings, 'report_reader_mode', 'beginner')


def test_missing_claims_and_incomparable_peer_rankings_are_not_used():
    messages = beginner_messages({
        'fundamental': '营业收入同比增长2.42%。\nPE数据缺失，不评价。\n市值为未提供数字亿元。',
        'peer_comparison': '报告期不一致，目标Q3，同行H1。ROE最高。',
        'news': '[news 模块暂时不可用：timeout]',
    }, '平安银行（CN/000001）', 'zh-CN')
    evidence = messages[-1]['content']
    assert '2.42%' in evidence
    assert 'PE' not in evidence
    assert '未提供数字' not in evidence
    assert 'ROE最高' not in evidence
    assert 'timeout' not in evidence
    assert '简体中文' in evidence
    assert beginner_messages({'news':'暂无相关新闻数据'}, 'test', 'zh-CN') == []


def test_invalid_numeric_claim_is_removed_as_a_whole_sentence():
    report = '利润增长2.21%。市值为未提供数字亿元。股价收盘11.30元。'
    result = clean_evidence(report)
    assert '2.21%' in result and '11.30' in result
    assert '市值' not in result


def test_visual_evidence_is_request_local_and_keeps_zero_and_reporting_dates():
    def work(price):
        def analyze():
            capture_prices([{'date':'2026-10-25','close':price}, {'date':'2026-10-26','close':price+1}])
            capture_growth({'growth': {'revenue_growth_yoy':0, 'net_profit_growth_yoy':None},
                            'data_quality':{'latest_report_date':'2026-09-30'}})
            return '已取得事实'
        return run_with_visuals(analyze)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(work, [10,100]))
    assert isinstance(first, str)
    assert first.visuals['prices'][0]['close'] == 10
    assert second.visuals['prices'][0]['close'] == 100
    assert first.visuals['growth'] == [{'label':'营业收入','value':0.0,'as_of':'2026-09-30','unit':'%'}]


def test_empty_fundamental_snapshot_does_not_call_model():
    from app.agents.fundamental_analyst import FundamentalAnalystAgent
    llm = MagicMock()
    agent = FundamentalAnalystAgent(llm, svc=SimpleNamespace(get_fundamentals=lambda *a: {'company':{'name':'测试'}, 'data_quality':{}}))
    assert agent.analyze('CN','000001') == ''
    llm.chat.assert_not_called()


def test_peer_dates_must_be_known_and_matching():
    assert not peers_have_matching_periods({'peers':[{}], 'data_quality':{'latest_report_dates':{'target':'2026-09-30','peer':'2026-06-30'}}})
    assert not peers_have_matching_periods({'peers':[{}], 'data_quality':{'latest_report_dates':{'target':'2026-09-30'}}})
    assert peers_have_matching_periods({'peers':[{}], 'data_quality':{'latest_report_dates':{'target':'2026-06-30','peer':'2026-06-30'}}})


def test_empty_news_does_not_call_model(monkeypatch):
    from app.agents.news_analyst import NewsAnalystAgent, news_data_service
    monkeypatch.setattr(news_data_service, 'get_stock_news', lambda **kw: {'items':[], 'count':0, 'data_quality':{}})
    llm = MagicMock()
    assert NewsAnalystAgent(llm).analyze('CN','000001') == ''
    llm.chat.assert_not_called()


@pytest.mark.asyncio
async def test_reader_visuals_are_saved_with_report_and_skipped_sections_stay_out(monkeypatch):
    import app.agents.realtime_analysis_runner as module
    llm = MagicMock()
    llm.chat.return_value = '## 先看懂这点\n最近收盘11.30元。'
    runner = module.RealtimeAnalysisRunner(llm)
    visuals = {'prices':[{'date':'2026-10-25','close':11.2},{'date':'2026-10-26','close':11.3}]}
    async def analyze(name,*args):
        return name, EvidenceText('收盘11.30元。',visuals) if name=='technical' else ''
    runner._run_named_agent = analyze
    monkeypatch.setattr(module.ComprehensiveAnalysisCoordinator,'_fetch_stock_name', AsyncMock(return_value='平安银行'))
    save = AsyncMock(return_value='report')
    monkeypatch.setattr(module,'save_generated_report',save)
    registry = AsyncMock()
    registry.is_cancel_requested.return_value=False
    ref=SimpleNamespace(run_id='test',market='CN',symbol='000001',analysis_scope='comprehensive',output_language='zh-CN')
    await runner._do_run(ref,registry,MagicMock())
    result=save.call_args.args[1]
    assert result['metadata']['reader_mode']=='beginner'
    assert result['metadata']['visuals']==visuals
    assert result['metadata']['agents']['fundamental']['status']=='skipped'
    assert 'fundamental' not in result['sections']
    assert '覆盖度' not in result['report']
    assert '11.30' in result['report']
    llm.chat.assert_called_once()


def test_reader_guard_keeps_equivalent_decline_without_accepting_wrong_direction():
    from app.agents.reader_report import supported_reader_report
    sections={'technical':'截至2026-10-26，5日涨跌-3%，20日涨跌-1.32%。'}
    result=supported_reader_report('截至2026年10月26日，5日下跌3%。20日下跌1.32%。上涨3%。预测涨幅99%。',sections)
    assert '2026年10月26日' in result
    assert '下跌3%' in result and '下跌1.32%' in result
    assert '上涨3%' not in result and '99' not in result
