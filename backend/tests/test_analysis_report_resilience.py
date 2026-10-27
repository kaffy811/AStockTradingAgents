import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.agents.language_utils import build_output_language_instruction
from app.agents.realtime_analysis_runner import RealtimeAnalysisRunner, _public_failure_message
from app.core.config import settings
from app.llm.deepseek_client import DeepSeekClient, NormalizedProviderError, ProviderErrorRecord


@pytest.fixture(autouse=True)
def standard_report_contract(monkeypatch):
    # These regressions cover the retained standard report/fallback contract.
    # Beginner report behavior has its own end-to-end and evidence tests.
    monkeypatch.setattr(settings, 'report_reader_mode', 'standard')


def test_default_language_is_explicit_and_requires_localized_labels():
    instruction = build_output_language_instruction('zh-CN')
    assert '简体中文' in instruction
    assert '不得直接输出英文内部字段名' in instruction
    assert '不得自行换算单位' in instruction
    assert 'English (US)' in build_output_language_instruction('en-US')


def test_provider_timeout_is_not_reported_as_missing_kline():
    error = NormalizedProviderError(ProviderErrorRecord(
        category='connection', retryable=True, http_status=None, provider_code=None,
        safe_reason_code='PROVIDER_TIMEOUT', original_exception_type='APITimeoutError'))
    message = _public_failure_message(error)
    assert '响应超时' in message
    assert '不代表原始行情数据缺失' in message
    assert 'http_status' not in message


def test_unexpected_error_does_not_leak_provider_body():
    assert 'secret-value' not in _public_failure_message(RuntimeError('secret-value'))


def test_sdk_does_not_silently_multiply_timeout(monkeypatch):
    monkeypatch.setattr(settings, 'deepseek_api_key', 'fake-key')
    with patch('app.llm.deepseek_client.OpenAI') as sdk:
        DeepSeekClient()
    assert sdk.call_args.kwargs['max_retries'] == 0


@pytest.mark.asyncio
async def test_synthesis_has_deadline_and_cleans_async_work(monkeypatch):
    monkeypatch.setattr(settings, 'analysis_synthesis_timeout_seconds', 0.01)
    runner = object.__new__(RealtimeAnalysisRunner)
    cleaned = asyncio.Event()
    async def hanging():
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
    with pytest.raises(TimeoutError):
        await runner._await_synthesis(hanging())
    assert cleaned.is_set()


@pytest.mark.asyncio
async def test_synthesis_returns_success_without_fallback():
    runner = object.__new__(RealtimeAnalysisRunner)
    async def done():
        return '真实报告'
    assert await runner._await_synthesis(done()) == '真实报告'

@pytest.mark.asyncio
async def test_timed_out_synthesis_saves_partial_report_and_marks_degraded(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import app.agents.realtime_analysis_runner as module
    monkeypatch.setattr(settings, 'analysis_synthesis_timeout_seconds', 0.01)
    runner = RealtimeAnalysisRunner(MagicMock())
    async def hang(*args, **kwargs):
        await asyncio.Event().wait()
    runner._coordinator._synthesize_tech_fundamental = hang
    async def agent(name, *args):
        return name, ('## 数据限制\n本次证据有限。')
    runner._run_named_agent = agent
    monkeypatch.setattr(module.ComprehensiveAnalysisCoordinator, '_fetch_stock_name',
                        AsyncMock(return_value='贵州茅台'))
    saved = AsyncMock(return_value='saved-report')
    monkeypatch.setattr(module, 'save_generated_report', saved)
    registry = AsyncMock()
    registry.is_cancel_requested.return_value = False
    ref = SimpleNamespace(run_id='test', market='CN', symbol='600519',
                          analysis_scope='technical_fundamental', output_language='zh-CN')
    await runner._do_run(ref, registry, MagicMock())
    result = saved.call_args.args[1]
    assert result['metadata']['synthesis']['status'] == 'degraded'
    assert '响应超时' in result['report']
    assert result['sections']['technical']
    events = [call.args[1] for call in registry.push_event.call_args_list if call.args[1]]
    assert next(e for e in events if e['event'] == 'synthesis_completed')['degraded'] is True
    assert any(e['event'] == 'report_ready' for e in events)


@pytest.mark.asyncio
@pytest.mark.parametrize('scope', ['technical_fundamental', 'comprehensive'])
@pytest.mark.parametrize('error_kind', ['timeout', 'unexpected'])
async def test_immediate_model_failure_saves_degraded_synthesis(monkeypatch, scope, error_kind):
    """Use the real synthesis helper: it must not hide fallback from the runner."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import app.agents.realtime_analysis_runner as module

    error = (NormalizedProviderError(ProviderErrorRecord(
        category='connection', retryable=True, http_status=None, provider_code=None,
        safe_reason_code='PROVIDER_TIMEOUT', original_exception_type='APITimeoutError'))
        if error_kind == 'timeout' else RuntimeError('secret-provider-payload'))
    llm = MagicMock()
    llm.chat.side_effect = error
    runner = RealtimeAnalysisRunner(llm)
    async def agent(name, *args):
        return name, '## 分项报告\n这是本维度已生成的分析内容。'
    runner._run_named_agent = agent
    monkeypatch.setattr(module.ComprehensiveAnalysisCoordinator, '_fetch_stock_name',
                        AsyncMock(return_value='贵州茅台'))
    saved = AsyncMock(return_value='saved-report')
    monkeypatch.setattr(module, 'save_generated_report', saved)
    registry = AsyncMock()
    registry.is_cancel_requested.return_value = False
    ref = SimpleNamespace(run_id='test', market='CN', symbol='600519',
                          analysis_scope=scope, output_language='zh-CN')

    await runner._do_run(ref, registry, MagicMock())

    result = saved.call_args.args[1]
    assert result['metadata']['synthesis']['status'] == 'degraded'
    assert result['metadata']['partial'] is True
    assert any('综合摘要生成失败' in warning for warning in result['metadata']['warnings'])
    assert result['metadata']['agents']['technical']['status'] == 'success'
    assert result['sections']['technical'] == '## 分项报告\n这是本维度已生成的分析内容。'
    assert '**技术面分析**：正常生成' in result['report']
    assert 'secret-provider-payload' not in result['report']
    if error_kind == 'timeout':
        assert '响应超时' in result['metadata']['synthesis']['message']
    events = [call.args[1] for call in registry.push_event.call_args_list if call.args[1]]
    assert next(e for e in events if e['event'] == 'synthesis_completed')['degraded'] is True
    assert any(e['event'] == 'report_ready' for e in events)
    llm.chat.assert_called_once()


@pytest.mark.asyncio
async def test_legacy_tech_fundamental_synthesis_keeps_fallback_contract():
    from app.agents.comprehensive_analysis_coordinator import ComprehensiveAnalysisCoordinator
    llm = MagicMock()
    llm.chat.side_effect = RuntimeError('offline')
    coordinator = ComprehensiveAnalysisCoordinator(llm)
    report = await coordinator._synthesize_tech_fundamental(
        'CN', 'CN/600519', {'technical': '已完成技术面', 'fundamental': '已完成基本面'})
    assert report.startswith('# 技术面与基本面分析报告：CN/600519')
    assert '综合摘要生成失败' in report
    assert '**技术面分析**：正常生成' in report


@pytest.mark.parametrize('language', ['zh-CN', 'zh-TW', 'en-US', 'ja-JP', 'ko-KR', 'es-ES'])
def test_fallback_report_localizes_dimension_names_and_statuses(language):
    from app.agents.comprehensive_analysis_coordinator import _fallback_report
    from app.agents.language_utils import report_label
    report = _fallback_report('CN', '600519', {'technical': '已有分析', 'news': '[failed]'},
                              RuntimeError('offline'), output_language=language)
    assert f"**{report_label(language, 'section_technical')}**：{report_label(language, 'status_generated')}" in report
    assert f"**{report_label(language, 'section_news')}**：{report_label(language, 'status_unavailable')}" in report
    assert '**technical**' not in report and '**news**' not in report

@pytest.mark.asyncio
async def test_all_failed_dimensions_do_not_call_synthesis_or_claim_complete(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    import app.agents.realtime_analysis_runner as module
    llm = MagicMock()
    runner = RealtimeAnalysisRunner(llm)
    async def agent(name, *args):
        return name, TimeoutError('private error')
    runner._run_named_agent = agent
    monkeypatch.setattr(module.ComprehensiveAnalysisCoordinator, '_fetch_stock_name', AsyncMock(return_value='测试公司'))
    saved = AsyncMock(return_value='diagnostic-report')
    monkeypatch.setattr(module, 'save_generated_report', saved)
    registry = AsyncMock()
    registry.is_cancel_requested.return_value = False
    ref = SimpleNamespace(run_id='all-failed', market='CN', symbol='000001',
                          analysis_scope='comprehensive', output_language='zh-CN')
    await runner._do_run(ref, registry, MagicMock())
    result = saved.call_args.args[1]
    assert result['metadata']['report_status'] == 'unavailable'
    assert result['metadata']['partial'] is True
    assert result['metadata']['synthesis']['status'] == 'degraded'
    llm.chat.assert_not_called()


def test_concise_client_request_disables_hidden_thinking_and_bounds_output(monkeypatch):
    monkeypatch.setattr(settings, 'deepseek_api_key', 'fake-key')
    with patch('app.llm.deepseek_client.OpenAI') as sdk:
        sdk.return_value.chat.completions.create.return_value.choices[0].message.content = '报告'
        client = DeepSeekClient()
        assert client.chat([{'role': 'user', 'content': '测试'}]) == '报告'
    kwargs = sdk.return_value.chat.completions.create.call_args.kwargs
    assert kwargs['extra_body'] == {'thinking': {'type': 'disabled'}}
    assert kwargs['max_tokens'] == settings.deepseek_analysis_max_tokens
