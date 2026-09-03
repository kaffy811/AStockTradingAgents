"""Isolated R3.3I.2 acceptance harness with a four-condition serial gate."""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import urllib.request
import uuid
from pathlib import Path

import asyncpg


QUESTIONS = [
    "2024年贵州茅台净利率如何？请结合营收和归母净利润说明。",
    "请根据贵州茅台2024年营业收入和归母净利润计算并解释净利率。",
]


def serial_gate(*, api_terminal: bool, s8_persisted: bool,
                backend_completed: bool, health_ok: bool) -> bool:
    return api_terminal and s8_persisted and backend_completed and health_ok


def _http_json(url: str, *, payload: dict | None = None, timeout: int = 150) -> dict:
    data = json.dumps(payload, ensure_ascii=False).encode() if payload else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


async def _terminal_trace(connection: asyncpg.Connection, request_id: str) -> dict:
    row = await connection.fetchrow(
        """
        SELECT t.final_status, t.completed_at,
               EXISTS (SELECT 1 FROM report_analysis_trace_stages s
                       WHERE s.trace_id=t.trace_id AND s.stage_name='S8'
                         AND s.status='completed') AS s8_persisted
        FROM report_analysis_traces t WHERE t.request_id=$1
        """, request_id,
    )
    return dict(row) if row else {}


async def wait_for_gate(connection: asyncpg.Connection, base_url: str,
                        request_id: str, *, timeout_seconds: int = 30) -> dict:
    deadline = asyncio.get_running_loop().time() + timeout_seconds
    while asyncio.get_running_loop().time() < deadline:
        trace = await _terminal_trace(connection, request_id)
        health = await asyncio.to_thread(_http_json, f"{base_url}/api/v1/health", timeout=10)
        state = {
            "api_terminal": True,
            "s8_persisted": bool(trace.get("s8_persisted")),
            "backend_completed": trace.get("completed_at") is not None,
            "health_ok": health.get("status") == "ok",
        }
        if serial_gate(**state):
            return {**state, "final_status": trace.get("final_status")}
        await asyncio.sleep(1)
    raise TimeoutError(f"strict serial gate not reached for {request_id}")


async def run(base_url: str, output: Path, interval_seconds: int, *, q3_only: bool = False) -> None:
    database_url = os.environ["DATABASE_URL"].replace("postgresql+asyncpg://", "postgresql://", 1)
    connection = await asyncpg.connect(database_url)
    results = []
    try:
        questions = [QUESTIONS[1]] if q3_only else QUESTIONS
        run_id = uuid.uuid4().hex[:12]
        for index, question in enumerate(questions, start=1):
            if results:
                await asyncio.sleep(interval_seconds)
            payload = {
                "question": question, "years": [2024], "report_id": 1,
                "force_refresh": True, "session_id": f"r33i2-4-{run_id}-q{index}", "use_memory": False,
            }
            response = await asyncio.to_thread(
                _http_json, f"{base_url}/api/v1/stock/600519/report-chat",
                payload=payload, timeout=150,
            )
            request_id = str(response["request_id"])
            gate = await wait_for_gate(connection, base_url, request_id)
            results.append({"question": question, "response": response, "gate": gate})
        output.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    finally:
        await connection.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--interval-seconds", type=int, default=15)
    parser.add_argument("--q3-only", action="store_true")
    args = parser.parse_args()
    asyncio.run(run(args.base_url, args.output, args.interval_seconds, q3_only=args.q3_only))
