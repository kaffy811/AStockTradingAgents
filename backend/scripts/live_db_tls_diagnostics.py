"""Safe PostgreSQL/TLS diagnostics for live acceptance.

The script classifies DNS/TCP/PostgreSQL TLS/certificate/Postgres SELECT 1
without printing DATABASE_URL, password, JWT, API keys, or the complete host.
It intentionally keeps TLS verification enabled.
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
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import make_url

try:
    import certifi
except Exception:  # noqa: BLE001
    certifi = None

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings  # noqa: E402
from app.core.database import AsyncSessionLocal  # noqa: E402


def _elapsed(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _target() -> dict[str, Any]:
    url = make_url(settings.database_url)
    host = url.host or ""
    query = dict(url.query)
    return {
        "host": host,
        "port": int(url.port or 5432),
        "host_class": "supabase_pooler" if "pooler.supabase.com" in host else "database_host",
        "host_suffix": ".".join(host.split(".")[-3:]) if host else "",
        "driver": url.drivername,
        "query_keys": sorted(query.keys()),
        "sslmode": query.get("sslmode"),
    }


def _status(status: str, *, latency_ms: int | None = None, error_code: str | None = None, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "latency_ms": latency_ms,
        "error_code": error_code,
        "details": details or {},
    }


def _classify_tls_error(exc: BaseException) -> str:
    message = str(exc).lower()
    if isinstance(exc, ssl.SSLCertVerificationError):
        if "hostname" in message or "ip address mismatch" in message:
            return "hostname_mismatch"
        if "expired" in message:
            return "expired_certificate"
        if "self-signed" in message or "unable to get local issuer" in message or "certificate verify failed" in message:
            return "certificate_verification_failure"
        return "certificate_verification_failure"
    if isinstance(exc, ssl.SSLError):
        return "ssl_mode_or_protocol_error"
    if isinstance(exc, TimeoutError):
        return "tcp_or_tls_timeout"
    if isinstance(exc, OSError):
        return "tcp_failure"
    return type(exc).__name__


def _dns(host: str, port: int) -> tuple[dict[str, Any], list[Any]]:
    started = time.perf_counter()
    try:
        infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        return _status(
            "passed",
            latency_ms=_elapsed(started),
            details={
                "address_families": sorted({"ipv6" if item[0] == socket.AF_INET6 else "ipv4" for item in infos}),
                "address_count": len(infos),
            },
        ), infos
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=_elapsed(started), error_code=type(exc).__name__, details={"message": str(exc)[:180]}), []


def _tcp(host: str, port: int, timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return _status("passed", latency_ms=_elapsed(started))
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=_elapsed(started), error_code=type(exc).__name__, details={"message": str(exc)[:180]})


def _postgres_tls(host: str, port: int, timeout: float, *, cafile: str | None = None, label: str = "default") -> dict[str, Any]:
    started = time.perf_counter()
    context = ssl.create_default_context(cafile=cafile)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(struct.pack("!II", 8, 80877103))
            response = sock.recv(1)
            if response != b"S":
                return _status(
                    "failed",
                    latency_ms=_elapsed(started),
                    error_code="POSTGRES_SSL_NOT_SUPPORTED",
                    details={"server_response": response.decode("ascii", errors="replace") if response else "empty"},
                )
            with context.wrap_socket(sock, server_hostname=host) as tls:
                cert = tls.getpeercert() or {}
                return _status(
                    "passed",
                    latency_ms=_elapsed(started),
                    details={
                        "protocol": "postgres_ssl_request",
                        "ca_source": label,
                        "tls_version": tls.version(),
                        "cipher": tls.cipher()[0] if tls.cipher() else None,
                        "certificate_verified": True,
                        "hostname_verified": True,
                        "issuer_summary": _name_summary(cert.get("issuer")),
                        "subject_summary": _name_summary(cert.get("subject")),
                        "not_before": cert.get("notBefore"),
                        "not_after": cert.get("notAfter"),
                    },
                )
    except Exception as exc:  # noqa: BLE001
        return _status(
            "failed",
            latency_ms=_elapsed(started),
            error_code=type(exc).__name__,
            details={
                "ca_source": label,
                "classification": _classify_tls_error(exc),
                "message": str(exc)[:220],
                "certificate_verified": False,
                "hostname_verified": False,
            },
        )


def _name_summary(parts: Any) -> list[str]:
    summary: list[str] = []
    if not parts:
        return summary
    for group in parts:
        for key, value in group:
            if key in {"commonName", "organizationName"} and value:
                summary.append(f"{key}={value}")
    return summary[:4]


async def _postgres_select(timeout: float) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        async def _query() -> None:
            async with AsyncSessionLocal() as db:
                await db.execute(text("SELECT 1"))

        await asyncio.wait_for(_query(), timeout=timeout)
        return _status("passed", latency_ms=_elapsed(started))
    except Exception as exc:  # noqa: BLE001
        return _status("failed", latency_ms=_elapsed(started), error_code=type(exc).__name__, details={"message": str(exc)[:220]})


def _root_cause(dns: dict[str, Any], tcp: dict[str, Any], tls: dict[str, Any], postgres: dict[str, Any]) -> tuple[str, str]:
    if dns["status"] != "passed":
        return "dns_failure", "Fix DNS/network routing before retrying database validation."
    if tcp["status"] != "passed":
        return "tcp_failure", "Fix firewall/VPC/proxy connectivity before retrying database validation."
    if tls["status"] != "passed":
        classification = tls.get("details", {}).get("classification") or tls.get("error_code")
        if classification == "ssl_mode_or_protocol_error":
            return "ssl_mode_or_protocol_error", "Use PostgreSQL SSLRequest negotiation and keep certificate verification enabled."
        if classification in {"certificate_verification_failure", "hostname_mismatch", "expired_certificate"}:
            return classification, "Install/update CA bundle or correct the hostname/endpoint; do not disable TLS verification."
        return str(classification), "Inspect TLS classification; keep sslmode=require/verify-full equivalent behavior."
    if postgres["status"] != "passed":
        return "postgres_connection_failure_after_verified_tls", "TLS is verified; inspect credentials, pooler mode, database availability, or asyncpg settings."
    return "none", "No TLS/Postgres blocker detected."


async def run(*, timeout: float = 5.0) -> dict[str, Any]:
    target = _target()
    host = target.pop("host")
    port = int(target["port"])
    dns, _infos = _dns(host, port)
    tcp = _tcp(host, port, timeout) if dns["status"] == "passed" else _status("skipped", error_code="DNS_FAILED")
    tls = _postgres_tls(host, port, timeout) if tcp["status"] == "passed" else _status("skipped", error_code="TCP_FAILED")
    certifi_tls = (
        _postgres_tls(host, port, timeout, cafile=certifi.where(), label="certifi")
        if tcp["status"] == "passed" and certifi
        else _status("skipped", error_code="CERTIFI_UNAVAILABLE" if not certifi else "TCP_FAILED")
    )
    postgres = await _postgres_select(timeout) if tls["status"] == "passed" else _status("skipped", error_code="TLS_FAILED")
    root_cause, safe_fix = _root_cause(dns, tcp, tls, postgres)
    verify_paths = ssl.get_default_verify_paths()
    return {
        "schema_version": "live_db_tls_diagnostics.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": {
            "environment_id": os.getenv("LIVE_ACCEPTANCE_ENVIRONMENT_ID", "local_unverified"),
            "os": platform.platform(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "openssl_version": ssl.OPENSSL_VERSION,
            "system_time_utc": datetime.now(timezone.utc).isoformat(),
        },
        "target": target,
        "ca": {
            "default_verify_paths": {
                "cafile": verify_paths.cafile,
                "capath": verify_paths.capath,
                "openssl_cafile_env": verify_paths.openssl_cafile_env,
                "openssl_capath_env": verify_paths.openssl_capath_env,
            },
            "certifi_where": certifi.where() if certifi else None,
        },
        "dns": dns,
        "tcp": tcp,
        "tls_handshake": tls,
        "tls_handshake_certifi": certifi_tls,
        "postgres_select_1": postgres,
        "certificate_verified": bool(tls.get("details", {}).get("certificate_verified")),
        "hostname_verified": bool(tls.get("details", {}).get("hostname_verified")),
        "root_cause": root_cause,
        "safe_fix": safe_fix,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="backend/docs/artifacts/live_db_tls_diagnostics.json")
    parser.add_argument("--timeout", type=float, default=5.0)
    args = parser.parse_args()
    payload = asyncio.run(run(timeout=args.timeout))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(out),
        "root_cause": payload["root_cause"],
        "postgres": payload["postgres_select_1"]["status"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
