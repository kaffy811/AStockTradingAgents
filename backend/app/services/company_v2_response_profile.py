"""
app/services/company_v2_response_profile.py — Phase 6T-E 响应 Profile（page|debug）

profile=page：轻量生产展示。普通 CompanyV2 页面默认使用。
profile=debug：完整诊断（现有行为，不变）。

page profile 移除（每模块）：
- raw / raw_sample
- field_trace
- validation_checks（保留 validation_summary）
- debug 元信息
- 完整 source_chain（压缩为 source badge：provider/success/error_code）
- errors 堆栈细节（保留 error_code + 短消息）
- diagnosis 细节（保留 primary_issue / tags）

保留：
- normalized fields（指标卡渲染需要）
- latest / history / period_type / chart_contract / history_coverage / history_quality
- chart_contract_validation / metric_applicability
- coverage / validation_summary / render

不破坏 debug API；不修改传入对象（返回新 dict）。
"""
from __future__ import annotations

from typing import Any

VALID_PROFILES = ("page", "debug")

_MODULE_DROP_KEYS = frozenset({
    "raw", "field_trace", "validation_checks", "debug", "raw_sample",
})
_SENSITIVE_KEYS = frozenset({"local_path", "token", "secret"})


def _condense_source_chain(source_chain: list[Any]) -> list[dict[str, Any]]:
    badges: list[dict[str, Any]] = []
    for s in source_chain or []:
        if not isinstance(s, dict):
            continue
        badges.append({
            "provider": s.get("provider"),
            "success": bool(s.get("success")),
            "error_code": s.get("error_code") or "",
        })
    return badges


def _condense_errors(errors: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in errors or []:
        if not isinstance(e, dict):
            continue
        out.append({
            "error_code": e.get("error_code") or "",
            "message": str(e.get("message") or "")[:120],
        })
    return out


def _strip_sensitive(obj: Any) -> Any:
    """递归移除敏感键（local_path/token/secret）。"""
    if isinstance(obj, dict):
        return {
            k: _strip_sensitive(v)
            for k, v in obj.items()
            if k not in _SENSITIVE_KEYS
        }
    if isinstance(obj, list):
        return [_strip_sensitive(v) for v in obj]
    return obj


def _page_module(module: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in module.items():
        if k in _MODULE_DROP_KEYS:
            continue
        if k == "source_chain":
            out[k] = _condense_source_chain(v if isinstance(v, list) else [])
            continue
        if k == "errors":
            out[k] = _condense_errors(v if isinstance(v, list) else [])
            continue
        if k == "diagnosis" and isinstance(v, dict):
            out[k] = {
                "primary_issue": v.get("primary_issue"),
                "tags": v.get("tags") or [],
            }
            continue
        if k == "normalized" and isinstance(v, dict):
            out[k] = {nk: nv for nk, nv in v.items() if nk != "raw_sample"}
            continue
        out[k] = v
    return out


def apply_response_profile(payload: dict[str, Any], profile: str) -> dict[str, Any]:
    """
    应用响应 profile。profile=debug 时原样返回（仅剥离敏感键）。
    """
    if profile != "page":
        return _strip_sensitive(payload)

    out: dict[str, Any] = {}
    for k, v in payload.items():
        if k in ("validation_checks",):
            continue
        if k == "modules" and isinstance(v, dict):
            out[k] = {mk: _page_module(m) if isinstance(m, dict) else m for mk, m in v.items()}
            continue
        out[k] = v
    out["response_profile"] = "page"
    return _strip_sensitive(out)
