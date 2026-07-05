#!/usr/bin/env python
"""
scripts/generate_frontend_mocks.py — 从 docs/api_examples/ 同步到 frontend/mock/fundamentals/

用法：
  python scripts/generate_frontend_mocks.py

功能：
  1. 读取 docs/api_examples/{key}.json (19个可用模块)
  2. 复制到 frontend/mock/fundamentals/{key}.json
  3. 构造 modules.json (从 backend MODULE_CATALOG)
  4. 构造 overview.json (snapshot + financial_summary 的 envelope)
"""
import sys
import os
import json
import shutil
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
API_EXAMPLES = ROOT / "docs" / "api_examples"
MOCK_DIR = ROOT / "frontend" / "mock" / "fundamentals"

sys.path.insert(0, str(ROOT / "backend"))


def main() -> None:
    MOCK_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Copy api_examples → frontend mock (non-partial files only)
    copied = 0
    for src in sorted(API_EXAMPLES.glob("*.json")):
        if "_partial" in src.name:
            continue
        dst = MOCK_DIR / src.name
        shutil.copy2(src, dst)
        copied += 1
    print(f"Copied {copied} example files to {MOCK_DIR}")

    # 2. Generate modules.json
    from app.tools.fundamental import MODULE_CATALOG, TOOL_REGISTRY

    modules = [
        {
            **m,
            "available": m["key"] in TOOL_REGISTRY or m.get("status") in ("available", "legacy"),
        }
        for m in MODULE_CATALOG
        if m.get("display", True) and m.get("status") != "hidden"
    ]
    modules_path = MOCK_DIR / "modules.json"
    with open(modules_path, "w", encoding="utf-8") as f:
        json.dump(modules, f, ensure_ascii=False, indent=2)
    print(f"Generated modules.json ({len(modules)} modules) → {modules_path}")

    # 3. Generate overview.json
    snap_file = API_EXAMPLES / "snapshot.json"
    fin_file = API_EXAMPLES / "financial_summary.json"
    if snap_file.exists() and fin_file.exists():
        overview = {
            "snapshot": json.loads(snap_file.read_text(encoding="utf-8")),
            "financial_summary": json.loads(fin_file.read_text(encoding="utf-8")),
        }
        overview_path = MOCK_DIR / "overview.json"
        with open(overview_path, "w", encoding="utf-8") as f:
            json.dump(overview, f, ensure_ascii=False, indent=2)
        print(f"Generated overview.json → {overview_path}")
    else:
        print("WARNING: snapshot.json or financial_summary.json not found, skipping overview.json")

    print("Done.")


if __name__ == "__main__":
    main()
