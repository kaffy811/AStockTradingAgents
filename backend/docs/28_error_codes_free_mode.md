# Phase 6L — API Error Codes Reference

## Overview

All API error responses include a stable `error_code` string field.
Frontend code can branch on this field to display localised copy.
Python exception class names are **never** exposed in API responses.

Error codes are defined in `app/core/error_codes.py`.

---

## Error Code Reference

### Data Source Errors

| Code | HTTP Status | Meaning | Suggested UI copy |
|------|-------------|---------|-------------------|
| `FREE_SOURCE_LIMITED` | 200 (partial) | Requested metric not available in free-mode sources (BaoStock/AkShare) | 免费数据源暂不支持此指标 |
| `DATA_SOURCE_UNAVAILABLE` | 200 (partial) | All configured data sources failed or are offline | 数据服务暂时不可用，请稍后重试 |

### Report PDF Pipeline Errors

| Code | HTTP Status | Meaning | Suggested UI copy |
|------|-------------|---------|-------------------|
| `REPORT_PDF_NOT_FOUND` | 200 (partial) | No annual/semi-annual report found in discovery index | 未找到该股票的年报/半年报 |
| `REPORT_DISCOVERY_FAILED` | 200 (partial) | Discovery service failed to query CNINFO/SSE/SZSE | 财报发现服务暂时不可用 |
| `REPORT_DOWNLOAD_FAILED` | 200 (partial) | PDF download failed (network or domain not allowlisted) | 财报下载失败，请检查网络 |
| `REPORT_PARSE_FAILED` | 200 (partial) | PDF text extraction failed | 财报解析失败 |

### Report RAG / Embedding Errors

| Code | HTTP Status | Meaning | Suggested UI copy |
|------|-------------|---------|-------------------|
| `REPORT_RAG_NOT_READY` | 200 (partial) | No chunks indexed; RAG cannot answer | 该股票财报尚未建立索引 |
| `REPORT_EMBEDDING_UNAVAILABLE` | 200 (partial) | Embedding provider offline or misconfigured | 向量化服务不可用 |

### Report Chat Errors

| Code | HTTP Status | Meaning | Suggested UI copy |
|------|-------------|---------|-------------------|
| `REPORT_CHAT_RATE_LIMITED` | 429 | Rate limit exceeded | 请求过于频繁，请稍后再试 |
| `REPORT_CHAT_NO_EVIDENCE` | 200 (partial) | No relevant evidence found for the question | 未找到相关财报片段，无法回答 |

### Safety / Compliance Errors

| Code | HTTP Status | Meaning | Suggested UI copy |
|------|-------------|---------|-------------------|
| `INVESTMENT_ADVICE_BLOCKED` | 200 (partial) | Question requested investment advice (buy/sell/target price) | 本系统不提供投资建议，请调整问题 |
| `PROMPT_INJECTION_BLOCKED` | 200 (partial) | Prompt injection pattern detected | 输入包含非常规指令，系统已拒绝处理 |
| `SOURCE_CHUNK_INVALID` | 200 (partial) | Answer references chunks that failed Review Agent validation | 引用片段未通过合规校验 |

### Infrastructure Errors

| Code | HTTP Status | Meaning | Suggested UI copy |
|------|-------------|---------|-------------------|
| `CORS_NOT_CONFIGURED` | 403 | Request origin not on CORS allowlist | 跨域请求来源未配置，请联系管理员 |
| `INTERNAL_ERROR` | 200 (partial) | Unexpected internal error (check logs with request_id) | 服务内部错误，请稍后重试 |

---

## Usage

### Backend (Python)

```python
from app.core.error_codes import REPORT_CHAT_RATE_LIMITED, INVESTMENT_ADVICE_BLOCKED

return {
    "answer": "...",
    "error_code": REPORT_CHAT_RATE_LIMITED,
    "partial": True,
}
```

### Frontend (JavaScript)

```js
const body = await response.json();

if (response.status === 429) {
    showRateLimitNotice(body.rate_limit_meta?.retry_after_seconds);
} else if (body.error_code === 'INVESTMENT_ADVICE_BLOCKED') {
    showWarning(t('chat_advice_blocked'));
} else if (body.error_code === 'REPORT_RAG_NOT_READY') {
    showInfo(t('chat_no_index'));
}
```

---

## Stability Guarantee

Error codes are stable strings. Once defined, they will NOT be renamed or removed
without a deprecation period. New codes may be added in future phases.

The `partial: true` flag always accompanies non-HTTP-error codes, allowing generic
UI fallbacks to "partial result" copy without needing to enumerate all codes.

---

## Notes

- `local_path` is never included in API responses.
- Python exception type names are never included in API responses.
- Stack traces are written to server logs only (identified by `request_id`).
- Errors from external data sources record the source name and failure type in logs,
  not the raw exception message (which may contain internal URLs or credentials).
