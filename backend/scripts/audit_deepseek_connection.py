#!/usr/bin/env python3
"""
C15 Audit: DeepSeek API Connection Verification.

Usage: uv run python scripts/audit_deepseek_connection.py

Outputs connection status without exposing API key.
"""
from __future__ import annotations

import sys
import time

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))


def main() -> None:
    try:
        from app.core.config import settings
    except Exception as e:
        print(f"[C15_AUDIT] CONFIG_ERROR: {e}")
        return

    key = settings.deepseek_api_key or ""
    url = settings.deepseek_base_url or ""
    model = settings.deepseek_default_model or ""
    pro_model = settings.deepseek_pro_model or ""
    provider = settings.llm_provider or ""

    print(f"[C15_AUDIT] llm_provider: {provider}")
    print(f"[C15_AUDIT] deepseek_api_key exists: {bool(key)}, length: {len(key)}")
    print(f"[C15_AUDIT] deepseek_base_url: {url}")
    print(f"[C15_AUDIT] deepseek_default_model: {model}")
    print(f"[C15_AUDIT] deepseek_pro_model: {pro_model}")

    if not key:
        print("[C15_AUDIT] RESULT: NOT_CONFIGURED — DEEPSEEK_API_KEY missing")
        return

    try:
        from openai import OpenAI, APIError, AuthenticationError
    except ImportError:
        print("[C15_AUDIT] ERROR: openai package not installed")
        return

    client = OpenAI(api_key=key, base_url=url)

    for test_model in [model, "deepseek-chat"]:
        t0 = time.time()
        try:
            resp = client.chat.completions.create(
                model=test_model,
                messages=[{"role": "user", "content": "Reply with the word OK only."}],
                temperature=0,
            )
            latency_ms = int((time.time() - t0) * 1000)
            content = resp.choices[0].message.content or ""
            finish = resp.choices[0].finish_reason
            print(f"[C15_AUDIT] model={test_model} → http=200 latency={latency_ms}ms "
                  f"finish={finish} response_chars={len(content)} "
                  f"preview={content[:40]!r}")
        except AuthenticationError as e:
            print(f"[C15_AUDIT] model={test_model} → AuthenticationError: {e}")
        except APIError as e:
            print(f"[C15_AUDIT] model={test_model} → APIError[{e.status_code}]: {e.message}")
        except Exception as e:
            print(f"[C15_AUDIT] model={test_model} → {type(e).__name__}: {e}")

    # Test the full LLM client via factory
    print("[C15_AUDIT] --- Testing via get_llm_client() factory ---")
    try:
        from app.llm.factory import get_llm_client
        llm = get_llm_client()
        t0 = time.time()
        answer = llm.chat_flash([{"role": "user", "content": "以一句话描述贵州茅台。"}], temperature=0)
        latency_ms = int((time.time() - t0) * 1000)
        print(f"[C15_AUDIT] chat_flash() → {latency_ms}ms, chars={len(answer)}, preview={answer[:60]!r}")
    except ValueError as e:
        print(f"[C15_AUDIT] chat_flash() → ValueError: {e}")
    except RuntimeError as e:
        print(f"[C15_AUDIT] chat_flash() → RuntimeError: {e}")
    except Exception as e:
        print(f"[C15_AUDIT] chat_flash() → {type(e).__name__}: {e}")


if __name__ == "__main__":
    main()
