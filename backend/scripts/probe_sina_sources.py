"""
scripts/probe_sina_sources.py — 新浪财经接口可用性探索脚本。

用途：手动运行，评估新浪源能否稳定提供 A股/港股 行情、估值、财务数据。
不接入任何业务链路，不写数据库，纯探索/报告用途。

运行方式：
    cd backend
    uv run python scripts/probe_sina_sources.py
"""

from __future__ import annotations

import re
import sys
import json

import requests

# ── Session 设置 ──────────────────────────────────────────────────────────────

session = requests.Session()
session.trust_env = False   # 禁用系统/环境代理

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
}

TIMEOUT = 8

# ── A股 symbol 转换 ────────────────────────────────────────────────────────────

def _to_sina_cn(symbol: str) -> str:
    return f"sh{symbol}" if symbol.startswith("6") else f"sz{symbol}"


# ── 工具函数 ──────────────────────────────────────────────────────────────────

def _fetch_text(url: str) -> tuple[int, str]:
    """返回 (status_code, text)，失败时返回 (-1, error_msg)。"""
    try:
        r = session.get(url, headers=HEADERS, timeout=TIMEOUT)
        try:
            text = r.content.decode("gb18030", errors="replace")
        except Exception:
            text = r.content.decode("utf-8", errors="replace")
        return r.status_code, text
    except Exception as exc:
        return -1, str(exc)


def _safe_float(fields: list[str], idx: int) -> float | None:
    try:
        v = fields[idx].strip()
        return float(v) if v else None
    except (IndexError, ValueError):
        return None


def _safe_str(fields: list[str], idx: int) -> str | None:
    try:
        v = fields[idx].strip()
        return v if v else None
    except IndexError:
        return None


def section(title: str) -> None:
    print()
    print("=" * 60)
    print(f"  {title}")
    print("=" * 60)


def subsection(title: str) -> None:
    print(f"\n--- {title} ---")


# ── 探索 1：A股实时行情 ───────────────────────────────────────────────────────

def probe_cn_quote(symbol: str, name: str) -> dict | None:
    """探索 hq.sinajs.cn A股行情接口。"""
    subsection(f"A股 quote: {name}（{symbol}）")
    sina_sym = _to_sina_cn(symbol)
    url = f"https://hq.sinajs.cn/list={sina_sym}"

    status, text = _fetch_text(url)
    print(f"URL: {url}")
    print(f"Status: {status}")
    print(f"Raw (前500字): {text[:500]!r}")

    if status != 200:
        print("FAILED: 非 200 响应")
        return None

    m = re.search(r'"([^"]+)"', text)
    if not m:
        print("FAILED: 无法从响应中提取数据")
        return None

    raw = m.group(1).strip()
    if not raw:
        print("FAILED: 数据为空（可能停牌或代码错误）")
        return None

    fields = raw.split(",")
    print(f"\n解析后字段数: {len(fields)}")

    # CN A股字段映射（34字段格式）
    result = {
        "name":       _safe_str(fields, 0),
        "open":       _safe_float(fields, 1),
        "prev_close": _safe_float(fields, 2),
        "price":      _safe_float(fields, 3),
        "high":       _safe_float(fields, 4),
        "low":        _safe_float(fields, 5),
        # [6] buy, [7] sell — 最新买卖报价
        "vol_raw_hand": _safe_float(fields, 8),   # 手（lot），×100 = 股
        "amount_yuan":  _safe_float(fields, 9),   # 元
        "trade_date": _safe_str(fields, 30),
        "trade_time": _safe_str(fields, 31),
    }
    vol_raw = result["vol_raw_hand"]
    result["volume_shares"] = int(vol_raw * 100) if vol_raw else None

    print("\n解析结果：")
    for k, v in result.items():
        print(f"  {k}: {v}")

    # 单位验证
    price = result["price"]
    amount = result["amount_yuan"]
    vol = result["volume_shares"]
    print("\n单位验证：")
    print(f"  价格 {price} 元 × 成交量 {vol} 股 ≈ 估算额 {price * vol:.0f} 元" if price and vol else "  无法验证（数据缺失）")
    print(f"  新浪报告额 {amount} 元")
    if price and vol and amount:
        ratio = (price * vol) / amount
        print(f"  比值（应接近 1.0）: {ratio:.3f}")

    return result


# ── 探索 2：港股实时行情 ───────────────────────────────────────────────────────

def probe_hk_quote(symbol: str, name: str) -> dict | None:
    """探索 hq.sinajs.cn 港股行情接口。"""
    subsection(f"港股 quote: {name}（{symbol}）")
    # 港股格式：hk + 5位代码（不足5位补0）
    hk_sym = f"hk{symbol.zfill(5)}"
    url = f"https://hq.sinajs.cn/list={hk_sym}"

    status, text = _fetch_text(url)
    print(f"URL: {url}")
    print(f"Status: {status}")
    print(f"Raw (前500字): {text[:500]!r}")

    if status != 200:
        print("FAILED: 非 200 响应")
        return None

    m = re.search(r'"([^"]*)"', text)
    if not m:
        print("FAILED: 无法提取数据")
        return None

    raw = m.group(1).strip()
    if not raw:
        print("FAILED: 数据为空（港股可能不支持或代码错误）")
        return None

    fields = raw.split(",")
    print(f"\n解析后字段数: {len(fields)}")
    print("原始字段:")
    for i, f in enumerate(fields):
        print(f"  [{i}]: {f!r}")

    # HK 字段格式（19字段）：
    # [0] 英文名, [1] 中文名, [2] prev_close, [3] price, [4] high, [5] low
    # [6] bid?, [7] change, [8] change_pct, [9] buy, [10] sell
    # [11] volume, [12] amount, [13-14] 0?, [15] ?, [16] 52w_low?
    # [17] date (YYYY/MM/DD), [18] time (HH:MM)
    result = {
        "name_en":    _safe_str(fields, 0),
        "name_cn":    _safe_str(fields, 1),
        "prev_close": _safe_float(fields, 2),
        "price":      _safe_float(fields, 3),
        "high":       _safe_float(fields, 4),
        "low":        _safe_float(fields, 5),
        "change":     _safe_float(fields, 7),
        "change_pct": _safe_float(fields, 8),
        "volume":     _safe_float(fields, 11),   # 股
        "amount":     _safe_float(fields, 12),   # HKD?
        "trade_date": _safe_str(fields, 17),
        "trade_time": _safe_str(fields, 18),
    }
    print("\n解析结果：")
    for k, v in result.items():
        print(f"  {k}: {v}")

    return result


# ── 探索 3：批量行情 ──────────────────────────────────────────────────────────

def probe_batch_quote(symbols: list[str]) -> None:
    """探索批量行情接口。"""
    subsection(f"批量 quote: {symbols}")
    sina_syms = ",".join(_to_sina_cn(s) for s in symbols)
    url = f"https://hq.sinajs.cn/list={sina_syms}"

    status, text = _fetch_text(url)
    print(f"URL: {url}")
    print(f"Status: {status}")
    # 找出所有变量
    vars_found = re.findall(r"var hq_str_(\w+)=", text)
    print(f"响应中包含的股票代码: {vars_found}")
    print(f"原始前300字: {text[:300]!r}")


# ── 探索 4：估值/财务 JSON 接口 ───────────────────────────────────────────────

def probe_fundamentals() -> None:
    """探索新浪是否有可用的 JSON/JS 估值或财务接口。"""
    subsection("估值/财务接口探索")

    tests = [
        # 已知有数据的 JSON-like 接口
        ("https://finance.sina.com.cn/realstock/company/sh600519/nc.shtml",
         "Sina 股票详情页（HTML）"),
        ("https://vip.stock.finance.sina.com.cn/corp/go.php/vFD_FinanceSummary/stockid/600519.phtml",
         "Sina 财务摘要页（HTML）"),
        ("https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
         "?symbol=sh600519&scale=240&ma=no&datalen=1",
         "Sina KLine JSON API"),
        ("https://hq.sinajs.cn/list=ff_sh600519",
         "hq.sinajs ff_前缀（财务相关？）"),
        ("https://hq.sinajs.cn/list=fx_sh600519",
         "hq.sinajs fx_前缀"),
    ]

    for url, label in tests:
        status, text = _fetch_text(url)
        print(f"\n  [{label}]")
        print(f"  URL: {url}")
        print(f"  Status: {status}")
        snippet = text[:400].replace("\n", " ").replace("\r", "")
        print(f"  Raw: {snippet!r}")

        # 尝试 JSON 解析
        try:
            data = json.loads(text)
            print(f"  JSON解析成功，类型: {type(data).__name__}, 键: {list(data.keys()) if isinstance(data, dict) else '(list)'}")
        except Exception:
            # 检查是否有 JS 变量数据
            if re.search(r"var\s+\w+\s*=", text):
                print("  包含 JS 变量（非纯 JSON）")
            elif text.strip().startswith("<"):
                print("  HTML 页面（无稳定 JSON 接口）")
            else:
                print("  未知格式")


# ── 主函数 ────────────────────────────────────────────────────────────────────

def main() -> None:
    print("新浪财经接口可用性探索")
    print("探索时间:", __import__("datetime").datetime.now().isoformat())

    # ── A股实时行情 ──────────────────────────────────────────────────────────
    section("1. A股实时行情接口（hq.sinajs.cn）")
    probe_cn_quote("600519", "贵州茅台")
    probe_cn_quote("000001", "平安银行")

    # ── 港股实时行情 ─────────────────────────────────────────────────────────
    section("2. 港股实时行情接口")
    probe_hk_quote("700", "腾讯控股")
    probe_hk_quote("9988", "阿里巴巴")

    # ── 批量行情 ─────────────────────────────────────────────────────────────
    section("3. 批量行情接口")
    probe_batch_quote(["600519", "000858", "000568"])

    # ── 估值/财务接口 ────────────────────────────────────────────────────────
    section("4. 估值/财务接口探索")
    probe_fundamentals()

    # ── 汇总报告 ─────────────────────────────────────────────────────────────
    section("5. 探索结论汇总")
    print("""
  ✅ CN A股实时行情（hq.sinajs.cn）：
     - 支持 sh/sz 前缀
     - 34 字段，结构稳定
     - gb18030 编码
     - 已有 SinaQuoteProvider 封装，可信赖
     - 支持批量（逗号分隔多个 symbol）

  ✅ HK 港股实时行情（hq.sinajs.cn/list=hk00700）：
     - 支持 hk 前缀，5位代码（不足补0）
     - 19 字段，结构与 A股不同
     - 含中英文名、价格、涨跌、成交量
     - 当前 SinaQuoteProvider 不支持 HK，需要新 parser
     - 可作为 TencentHKQuoteProvider 的备用

  ❌ 新浪 PE / PB / 市值 / 行业 / 财务摘要（JSON/JS 接口）：
     - 无稳定 JSON 接口
     - 只有 HTML 页面（需要复杂 HTML 解析）
     - ff_/fx_ 前缀返回空字符串
     - 不建议接入生产逻辑

  📋 综合建议：
     - 新浪 CN 行情：作为 EastMoney 的可靠备用（当前已是 fallback chain 一环）
     - 新浪 HK 行情：可补充 TencentHK，但需新建 HK 字段 parser
     - 新浪基本面数据：不建议接入，无稳定 JSON 接口
     - AkShare 替代建议：hq.sinajs.cn 可替代 stock_zh_a_spot_em()（name/pe/pb 除外）
    """)


if __name__ == "__main__":
    main()
