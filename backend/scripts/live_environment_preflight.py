"""Live acceptance environment preflight for Phase 6U-E1.3.

The script records whether the current machine is suitable for real layered
runtime shadow acceptance. It never writes secrets, full DB URLs, API keys, or
complete resolved IP addresses to artifacts.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import platform
import socket
import ssl
import struct
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402


ARTIFACT_PATH = Path("backend/docs/artifacts/live_environment_preflight.json")


def _status(status: str, *, latency_ms: int | None = None, error_code: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "latency_ms": latency_ms,
        "error_code": error_code,
        "details": details or {},
    }


def _masked_addresses(infos: list[Any]) -> list[str]:
    masked: list[str] = []
    for family, _socktype, _proto, _canonname, sockaddr in infos[:5]:
        label = "ipv6" if family == socket.AF_INET6 else "ipv4"
        port = sockaddr[1] if len(sockaddr) > 1 else None
        masked.append(f"{label}:masked:{port}")
    return masked


def _db_target() -> tuple[str | None, int | None, str]:
    url = make_url(settings.database_url)
    host = url.host
    port = int(url.port or 5432)
    host_class = "supabase_pooler" if host and "pooler.supabase.com" in host else "database_host"
    return host, port, host_class


def _dns_check(host: str | None, port: int | None) -> tuple[dict[str, Any], list[Any]]:
    if not host or not port:
        return _status("failed", error_code="DATABASE_HOST_MISSING"), []
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return _status("passed", latency_ms=int((time.perf_counter() - started) * 1000), details={"resolved_addresses": _masked_addresses(infos)}), infos
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=int((time.perf_counter() - started) * 1000), error_code=type(exc).__name__, details={"message": str(exc)[:180]}), []


def _tcp_check(host: str | None, port: int | None, timeout: float) -> dict[str, Any]:
    if not host or not port:
        return _status("failed", error_code="DATABASE_HOST_MISSING")
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return _status("passed", latency_ms=int((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=int((time.perf_counter() - started) * 1000), error_code=type(exc).__name__, details={"message": str(exc)[:180]})


def _tls_check(host: str | None, port: int | None, timeout: float) -> dict[str, Any]:
    """Verify PostgreSQL TLS using the PostgreSQL SSLRequest handshake.

    PostgreSQL does not speak raw TLS on the TCP port. Clients first send an
    SSLRequest packet, wait for ``S``, then wrap the socket with TLS. A generic
    ``ssl.wrap_socket`` immediately after TCP connect misclassifies healthy
    PostgreSQL endpoints as TLS failures.
    """
    if not host or not port:
        return _status("failed", error_code="DATABASE_HOST_MISSING")
    started = time.perf_counter()
    try:
        context = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(struct.pack("!II", 8, 80877103))
            response = sock.recv(1)
            if response != b"S":
                return _status(
                    "failed",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    error_code="POSTGRES_SSL_NOT_SUPPORTED",
                    details={"server_response": response.decode("ascii", errors="replace") if response else "empty"},
                )
            with context.wrap_socket(sock, server_hostname=host):
                return _status(
                    "passed",
                    latency_ms=int((time.perf_counter() - started) * 1000),
                    details={"protocol": "postgres_ssl_request"},
                )
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=int((time.perf_counter() - started) * 1000), error_code=type(exc).__name__, details={"message": str(exc)[:180]})


async def _postgres_check(timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async def _query() -> None:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))

        await asyncio.wait_for(_query(), timeout=timeout)
        return _status("passed", latency_ms=int((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=int((time.perf_counter() - started) * 1000), error_code=type(exc).__name__, details={"message": str(exc)[:180]})


async def _redis_check(timeout: float) -> dict[str, Any]:
    if not settings.redis_url:
        return _status("skipped", error_code="REDIS_URL_NOT_CONFIGURED")
    started = time.perf_counter()
    try:
        from redis.asyncio import from_url

        client = from_url(settings.redis_url, decode_responses=True)
        try:
            await asyncio.wait_for(client.ping(), timeout=timeout)
        finally:
            await client.aclose()
        return _status("passed", latency_ms=int((time.perf_counter() - started) * 1000))
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=int((time.perf_counter() - started) * 1000), error_code=type(exc).__name__, details={"message": str(exc)[:180]})


def _http_check(url: str, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "TradingAgents-live-preflight"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 - explicit preflight target
            return _status("passed", latency_ms=int((time.perf_counter() - started) * 1000), details={"http_status": int(resp.status)})
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=int((time.perf_counter() - started) * 1000), error_code=type(exc).__name__, details={"message": str(exc)[:180]})


def _host_dns_check(host: str, port: int) -> dict[str, Any]:
    result, _infos = _dns_check(host, port)
    return result


async def run_preflight(*, timeout: float = 4.0, check_llm: bool = False) -> dict[str, Any]:
    host, port, host_class = _db_target()
    dns_result, _infos = _dns_check(host, port)
    tcp_result = _tcp_check(host, port, timeout) if dns_result["status"] == "passed" else _status("skipped", error_code="DNS_FAILED")
    tls_result = _tls_check(host, port, timeout) if tcp_result["status"] == "passed" else _status("skipped", error_code="TCP_FAILED")
    postgres_result = await _postgres_check(timeout) if tls_result["status"] == "passed" else _status("skipped", error_code="TLS_FAILED")
    redis_result = await _redis_check(timeout)
    cninfo_result = _http_check("https://www.cninfo.com.cn/new/index", timeout)
    baostock_result = _host_dns_check("www.baostock.com", 443)
    rag_result = _status("skipped", error_code="POSTGRES_NOT_READY") if postgres_result["status"] != "passed" else _status("passed", details={"minimal_query": "postgres_select_1_only"})
    llm_result = _status("skipped", error_code="LLM_PREFLIGHT_DISABLED")
    if check_llm:
        llm_result = _http_check(settings.deepseek_base_url, timeout) if settings.deepseek_api_key else _status("skipped", error_code="LLM_KEY_NOT_CONFIGURED")
    blockers = []
    checks = {
        "dns": dns_result,
        "tcp": tcp_result,
        "tls": tls_result,
        "postgres": postgres_result,
        "redis": redis_result,
        "cninfo": cninfo_result,
        "baostock": baostock_result,
        "rag": rag_result,
        "llm": llm_result,
    }
    required = ["dns", "tcp", "tls", "postgres", "cninfo", "baostock", "rag"]
    for name in required:
        if checks[name]["status"] != "passed":
            blockers.append(f"{name.upper()}_{checks[name].get('error_code') or 'NOT_PASSED'}")
    return {
        "schema_version": "live_environment_preflight.v1",
        "environment": {
            "environment_id": os.getenv("LIVE_ACCEPTANCE_ENVIRONMENT_ID", "local_unverified"),
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "region": os.getenv("LIVE_ACCEPTANCE_REGION", "unknown"),
            "database_mode": settings.database_connection_mode,
            "database_host_class": host_class,
            "dns_provider": os.getenv("LIVE_ACCEPTANCE_DNS_PROVIDER", "unknown"),
            "ipv4_available": any("ipv4" in item for item in dns_result.get("details", {}).get("resolved_addresses", [])),
            "ipv6_available": any("ipv6" in item for item in dns_result.get("details", {}).get("resolved_addresses", [])),
        },
        "dns": {"supabase_pooler": dns_result},
        "tcp": {"supabase_pooler": tcp_result},
        "tls": {"supabase_pooler": tls_result},
        "postgres": postgres_result,
        "redis": redis_result,
        "cninfo": cninfo_result,
        "baostock": baostock_result,
        "rag": rag_result,
        "llm": llm_result,
        "environment_ready": not blockers,
        "blockers": blockers,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ARTIFACT_PATH))
    parser.add_argument("--timeout", type=float, default=4.0)
    parser.add_argument("--check-llm", action="store_true")
    args = parser.parse_args()
    payload = asyncio.run(run_preflight(timeout=args.timeout, check_llm=args.check_llm))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"artifact": str(out), "environment_ready": payload["environment_ready"], "blockers": payload["blockers"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
