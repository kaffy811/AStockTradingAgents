# Phase 7D-P0.7 Report RAG Mock Attribution

## Classification

`PRE_EXISTING_TEST_INFRA`

Mechanism: `FIXTURE_CONTRACT_DRIFT` inside the pre-existing test infrastructure.

## Reproduction matrix

The same command was run with `DEEPSEEK_API_KEY`, `OPENAI_API_KEY`, and `TUSHARE_TOKEN` explicitly unset:

```text
pytest -q backend/tests/test_phase6w_r1_2_numeric_pipeline.py
```

Results were identical:

- `5dad7228...`: 7 failed, 15 passed.
- P0.5 `c812d4d2...`: 7 failed, 15 passed.
- A `4434fc60...`: 7 failed, 15 passed.

Because the failure exists unchanged at the release baseline, it was not introduced by P0.5, P0.6, or A.

## Patch target and actual call path

The test patches:

```text
app.llm.deepseek_client.DeepSeekClient
```

The production code dynamically imports the same object inside `ReportChatCopilotAgent._do_chat`, so the class patch target is not stale. However, the production call order is:

1. import `settings` and `DeepSeekClient`;
2. check `settings.ai_enabled`;
3. check `settings.ai_api_key`;
4. only then instantiate `DeepSeekClient()` and call `client.chat(...)`.

The fixture patches the client class but does not supply an enabled, non-empty `settings.ai_api_key`. Execution raises `RuntimeError("AI API Key 未配置")` before client construction. The mocked `chat` response is therefore never reached, and the deterministic synthesis-failure response lacks the numeric-validation shape expected by seven assertions.

Observed log in all three baselines:

```text
ReportChatCopilot LLM error category=provider_error type=RuntimeError
```

## Provider safety

No live LLM was called: the configuration guard raised before `DeepSeekClient()` construction. No Tushare or other market/news Provider is involved in this test path. No production code or assertion was modified during B.

## Owner action

Any remediation requires separate authorization to update test infrastructure/fixture configuration. It should not change the global numeric validator, allow-set, Report RAG business logic, or assertions merely to hide the pre-existing fixture failure.
