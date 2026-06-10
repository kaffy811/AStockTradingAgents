"""
全量申万一级行业映射 CSV 生成脚本
====================================
生成 data/industry/sw_industry_map_full_l1.csv，供 import_industry_map.py 导入。

输出 CSV 字段（与 import_industry_map.py 完全兼容）：
    market, symbol, stock_name, industry_code, industry_name,
    industry_level, source, is_primary

支持两种模式：

模式 A：自动生成（从 swsresearch.com 申万指数成分股接口抓取）
    uv run python scripts/generate_sw_l1_industry_map_csv.py \\
        --output data/industry/sw_industry_map_full_l1.csv

模式 B：转换外部 CSV（任意字段映射→标准格式）
    uv run python scripts/generate_sw_l1_industry_map_csv.py \\
        --input  data/industry/raw_sw_industry.csv \\
        --output data/industry/sw_industry_map_full_l1.csv

外部 CSV（模式 B）至少包含以下三列之一（列名大小写不敏感）：
    - 股票代码（或 symbol / code）
    - 申万一级（或 sw_l1_name / industry_name / 行业名称）
    - 申万代码（或 sw_l1_code / industry_code）

限制（模式 A）：
    - 数据来源：AkShare index_component_sw → swsresearch.com 官方接口
    - 同一股票如归属多个行业（极少数），只保留第一次出现（最小编号行业优先）
    - 部分已退市/暂停股票可能出现在成分列表中，均正常写入

运行方式：
    uv run python scripts/generate_sw_l1_industry_map_csv.py [options]
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

# 确保 backend/ 在 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── SW 2021 L1 行业代码表（31 个）──────────────────────────────────────────────
SW_L1 = {
    "801010": "农林牧渔",
    "801030": "基础化工",
    "801040": "钢铁",
    "801050": "有色金属",
    "801080": "电子",
    "801110": "家用电器",
    "801120": "食品饮料",
    "801130": "纺织服饰",
    "801140": "轻工制造",
    "801150": "医药生物",
    "801160": "公用事业",
    "801170": "交通运输",
    "801180": "房地产",
    "801200": "商贸零售",
    "801210": "社会服务",
    "801230": "综合",
    "801710": "建筑材料",
    "801720": "建筑装饰",
    "801730": "电力设备",
    "801740": "国防军工",
    "801750": "计算机",
    "801760": "传媒",
    "801770": "通信",
    "801780": "银行",
    "801790": "非银金融",
    "801850": "美容护理",
    "801880": "汽车",
    "801890": "机械设备",
    "801960": "煤炭",
    "801970": "石油石化",
    "801980": "环保",
}

OUTPUT_COLUMNS = [
    "market", "symbol", "stock_name",
    "industry_code", "industry_name",
    "industry_level", "source", "is_primary",
]

_FETCH_DELAY = 0.3   # seconds between requests


# ── Direct API call to swsresearch.com (bypasses AkShare's empty-result bug) ─

def _fetch_index_component(code: str):
    """Fetch SW index constituents directly from swsresearch.com API.
    Returns a DataFrame with columns ['证券代码', '证券名称'] or None on failure."""
    import pandas as pd, requests, urllib3
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    url = "https://www.swsresearch.com/institute-sw/api/index_publish/details/component_stocks/"
    params = {"swindexcode": code, "page": "1", "page_size": "10000"}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    }
    r = requests.get(url, params=params, headers=headers, verify=False, timeout=20)
    r.raise_for_status()
    data = r.json()
    results = data.get("data", {}).get("results", [])
    if not results:
        return None
    df = _pd().DataFrame(results)
    df = df.rename(columns={"stockcode": "证券代码", "stockname": "证券名称"})
    return df[["证券代码", "证券名称"]]


def _pd():
    import pandas as pd
    return pd


# ── Mode A: Auto-generate from swsresearch.com via AkShare ───────────────────

def _auto_generate(output_path: Path) -> int:
    """Fetch all SW L1 constituents and write CSV. Returns row count written."""
    try:
        import akshare as ak
    except ImportError:
        print("[ERR] akshare 未安装，请先运行: uv add akshare")
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)

    rows: list[dict] = []
    seen_symbols: set[str] = set()   # dedup: first industry wins

    total = len(SW_L1)
    ok_count = 0
    skip_count = 0

    print(f"\n[模式 A] 从 swsresearch.com 抓取申万一级成分股（共 {total} 个行业）")
    print("-" * 60)

    for idx, (code, name) in enumerate(SW_L1.items(), 1):
        print(f"  [{idx:02d}/{total}] {code} {name} ...", end="", flush=True)
        try:
            df = _fetch_index_component(code)
            # expected columns: 证券代码, 证券名称
            if df is None or df.empty:
                print(f" 空（跳过）")
                skip_count += 1
                continue

            added = 0
            for _, row in df.iterrows():
                symbol = str(row.get("证券代码", "")).strip().zfill(6)
                stock_name = str(row.get("证券名称", "")).strip()
                if not symbol or symbol == "000000":
                    continue
                if symbol in seen_symbols:
                    continue
                seen_symbols.add(symbol)
                rows.append({
                    "market":         "CN",
                    "symbol":         symbol,
                    "stock_name":     stock_name,
                    "industry_code":  code,
                    "industry_name":  name,
                    "industry_level": "1",
                    "source":         "sw_2021_swsresearch",
                    "is_primary":     "true",
                })
                added += 1

            print(f" {added} 只股票")
            ok_count += 1

        except Exception as e:
            print(f" ERR: {e}")
            skip_count += 1

        if idx < total:
            time.sleep(_FETCH_DELAY)

    print(f"\n  完成：{ok_count} 个行业成功，{skip_count} 个跳过，共 {len(rows)} 条记录")

    if not rows:
        return 0

    _write_csv(rows, output_path)
    return len(rows)


# ── Mode B: Convert external CSV ─────────────────────────────────────────────

# Column alias maps (lowercase stripped)
_SYMBOL_ALIASES   = {"股票代码", "symbol", "code", "证券代码", "股票", "stock_code"}
_NAME_ALIASES     = {"股票名称", "股票简称", "stock_name", "name", "证券名称", "简称"}
_IND_NAME_ALIASES = {"申万一级", "行业名称", "industry_name", "sw_l1_name",
                     "sw_l1", "申万行业", "一级行业", "行业"}
_IND_CODE_ALIASES = {"申万代码", "行业代码", "industry_code", "sw_l1_code",
                     "sw_code", "申万一级代码"}


def _find_col(df_cols: list[str], aliases: set[str]) -> str | None:
    for col in df_cols:
        if col.strip().lower() in aliases:
            return col
    return None


def _convert_external_csv(input_path: Path, output_path: Path) -> int:
    """Convert an external CSV to the standard format. Returns row count."""
    import pandas as pd

    print(f"\n[模式 B] 转换外部 CSV: {input_path}")
    if not input_path.exists():
        print(f"[ERR] 文件不存在: {input_path}")
        return 0

    df = pd.read_csv(input_path, dtype=str).fillna("")
    cols_lower = {c.strip().lower(): c for c in df.columns}
    cols_list = list(df.columns)

    sym_col   = _find_col(cols_list, _SYMBOL_ALIASES)
    name_col  = _find_col(cols_list, _NAME_ALIASES)
    iname_col = _find_col(cols_list, _IND_NAME_ALIASES)
    icode_col = _find_col(cols_list, _IND_CODE_ALIASES)

    if sym_col is None:
        print(f"[ERR] 找不到股票代码列。当前列：{cols_list}")
        print(f"      支持的列名：{sorted(_SYMBOL_ALIASES)}")
        return 0
    if iname_col is None and icode_col is None:
        print(f"[ERR] 找不到行业名称列或行业代码列。当前列：{cols_list}")
        return 0

    # Build an industry name → code map from SW_L1 (for code inference)
    name_to_code = {v: k for k, v in SW_L1.items()}

    rows: list[dict] = []
    skipped = 0
    for _, row in df.iterrows():
        symbol = str(row[sym_col]).strip().zfill(6)
        if not symbol or symbol == "000000":
            skipped += 1
            continue

        stock_name = str(row[name_col]).strip() if name_col else ""
        ind_name   = str(row[iname_col]).strip() if iname_col else ""
        ind_code   = str(row[icode_col]).strip() if icode_col else ""

        # Infer missing code from name, or missing name from code
        if not ind_code and ind_name:
            ind_code = name_to_code.get(ind_name, "")
        if not ind_name and ind_code:
            ind_name = SW_L1.get(ind_code, "")
        if not ind_name and not ind_code:
            skipped += 1
            continue

        rows.append({
            "market":         "CN",
            "symbol":         symbol,
            "stock_name":     stock_name,
            "industry_code":  ind_code,
            "industry_name":  ind_name,
            "industry_level": "1",
            "source":         "sw_2021_csv",
            "is_primary":     "true",
        })

    print(f"  输入 {len(df)} 行，写出 {len(rows)} 行，跳过 {skipped} 行")

    if not rows:
        return 0

    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(rows, output_path)
    return len(rows)


# ── Shared helpers ────────────────────────────────────────────────────────────

def _write_csv(rows: list[dict], path: Path) -> None:
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=OUTPUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"\n  已写入 {len(rows)} 行 → {path}")


def _print_summary(path: Path) -> None:
    import pandas as pd
    df = pd.read_csv(path, dtype=str)
    print("\n" + "=" * 60)
    print(f"CSV 摘要: {path}")
    print(f"  总股票数:   {len(df)}")
    print(f"  覆盖行业数: {df['industry_name'].nunique()}")
    print(f"  行业列表:   {sorted(df['industry_name'].unique())[:10]} ...")

    # Key stocks
    key = df[df["symbol"].isin(["600519", "000001", "300750"])]
    if not key.empty:
        print(f"\n  关键股票映射:")
        for _, r in key.iterrows():
            print(f"    {r['symbol']} {r['stock_name']} → {r['industry_code']} {r['industry_name']}")
    else:
        print("  [WARN] 关键股票 600519/000001/300750 未全部覆盖")
    print("=" * 60)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    global _FETCH_DELAY
    parser = argparse.ArgumentParser(
        description="生成全量申万一级行业映射 CSV",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--output", "-o",
        default="data/industry/sw_industry_map_full_l1.csv",
        help="输出 CSV 路径（默认 data/industry/sw_industry_map_full_l1.csv）",
    )
    parser.add_argument(
        "--input", "-i",
        default=None,
        help="外部 CSV 路径（提供时使用模式 B：转换外部 CSV）",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=_FETCH_DELAY,
        help=f"模式 A：每次请求间隔秒数（默认 {_FETCH_DELAY}）",
    )
    parser.add_argument(
        "--no-summary",
        action="store_true",
        help="生成后不打印摘要",
    )
    args = parser.parse_args()

    _FETCH_DELAY = args.delay
    output_path = Path(args.output)

    print(f"\n申万一级行业映射 CSV 生成器")
    print(f"输出路径: {output_path.resolve()}")

    if args.input:
        n = _convert_external_csv(Path(args.input), output_path)
    else:
        n = _auto_generate(output_path)

    if n > 0 and not args.no_summary:
        _print_summary(output_path)
    elif n == 0:
        print("\n[ERR] 未生成任何数据。请检查：")
        print("  1. 网络可以访问 swsresearch.com（模式 A）")
        print("  2. 外部 CSV 格式正确（模式 B）")
        print("  外部 CSV 示例格式：")
        print("    stock_code,stock_name,sw_l1_code,sw_l1_name")
        print("    600519,贵州茅台,801120,食品饮料")
        print("    000001,平安银行,801780,银行")
        print("    300750,宁德时代,801730,电力设备")
        sys.exit(1)


if __name__ == "__main__":
    main()
