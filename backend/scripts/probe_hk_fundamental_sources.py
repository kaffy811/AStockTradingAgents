"""
scripts/probe_hk_fundamental_sources.py — HK 港股基本面数据源可用性探索脚本。

探索结论（2026-05-21）：
  ─────────────────────────────────────────────────────────────────────────
  1. Yahoo Finance HTTP（v7/v8，不使用 yfinance 包，直接 requests）
     结果：HTTP 403 — 当前环境无 cookie/auth，全部被拒。
     结论：本轮不可用，不接入主链路。

  2. AkShare stock_hk_spot_em()（东方财富 HK 接口）
     结果：ProxyError（Clash 代理拦截 eastmoney.com）。
     字段：名称/最新价/涨跌幅/PE/PB/市值 均有，但需要绕过代理。
     结论：当前环境因 Clash 不可用，待代理配置直连后可重新评估。

  3. 新浪财经 hq.sinajs.cn/list=hk{code}（19 字段格式）
     结果：可用，延迟 < 1s，稳定。
     字段覆盖：
       [0]  英文名
       [1]  中文名           ← company.name 可从此读取
       [2]  昨收（HKD）
       [3]  当前价（HKD）
       [4]  今日最高（HKD）
       [5]  今日最低（HKD）
       [7]  涨跌额
       [8]  涨跌幅(%)
       [11] 成交量（股）
       [12] 成交笔数
       [15] 52周高
       [16] 52周低
       [17] 日期
       [18] 时间
     缺失：PE、PB、市值、行业、业务描述。
     结论：Sina HK 可补 company.name，但无法补 valuation 字段。

  综合结论（本轮）：
  ─────────────────────────────────────────────────────────────────────────
  - HK pe/pb/market_cap/industry 本轮无可靠数据源 → 保持 null。
  - HK company.name 可通过 Sina HK 或 quote_optional 获取。
  - yfinance 已在 FundamentalDataService 中对 HK 禁用（经常 429）。
  - 后续计划：等 AkShare HK stock_hk_spot_em 代理问题解决后可重新接入。

运行方式：
    cd backend
    uv run python scripts/probe_hk_fundamental_sources.py
"""

from __future__ import annotations

import re
import sys

import requests

# ── Session ───────────────────────────────────────────────────────────────────

session = requests.Session()
session.trust_env = False   # 禁用系统代理

HEADERS_BROWSER = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Referer": "https://finance.yahoo.com",
}

HEADERS_SINA = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://finance.sina.com.cn",
}

TIMEOUT = 8

HK_STOCKS = {
    "00700": ("腾讯控股", "0700.HK"),
    "09988": ("阿里巴巴", "9988.HK"),
    "03690": ("美团",     "3690.HK"),
    "09999": ("网易",     "9999.HK"),
    "09888": ("百度",     "9888.HK"),
}


def section(title: str) -> None:
    print()
    print("=" * 65)
    print(f"  {title}")
    print("=" * 65)


def subsection(title: str) -> None:
    print(f"\n--- {title} ---")


# ── 1. Yahoo Finance HTTP ─────────────────────────────────────────────────────

def probe_yahoo_http() -> None:
    section("1. Yahoo Finance HTTP（v7/v8，不使用 yfinance 包）")

    subsection("v8 quoteSummary")
    for code, (name, yf_sym) in HK_STOCKS.items():
        url = (
            f"https://query1.finance.yahoo.com/v8/finance/quoteSummary/{yf_sym}"
            "?modules=price,summaryDetail,assetProfile"
        )
        try:
            r = session.get(url, headers=HEADERS_BROWSER, timeout=TIMEOUT)
            print(f"  {name}({yf_sym}): HTTP {r.status_code}")
            if r.status_code == 200:
                d = r.json()
                result = (d.get("quoteSummary") or {}).get("result") or [{}]
                price_mod  = result[0].get("price", {})
                summary    = result[0].get("summaryDetail", {})
                profile    = result[0].get("assetProfile", {})
                print(f"    name:        {price_mod.get('longName') or price_mod.get('shortName')}")
                print(f"    market_cap:  {(price_mod.get('marketCap') or {}).get('raw')}")
                print(f"    pe:          {(summary.get('trailingPE') or {}).get('raw')}")
                print(f"    pb:          {(summary.get('priceToBook') or {}).get('raw')}")
                print(f"    div_yield:   {(summary.get('dividendYield') or {}).get('raw')}")
                print(f"    industry:    {profile.get('industry')}")
                print(f"    currency:    {price_mod.get('currency')}")
            elif r.status_code == 429:
                print(f"    429 — rate limited")
            elif r.status_code == 403:
                print(f"    403 — forbidden (no auth cookie)")
        except Exception as e:
            print(f"  {name}({yf_sym}): ERROR {e}")

    subsection("v7 batch quote")
    syms = ",".join(v[1] for v in HK_STOCKS.values())
    url2 = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}"
    try:
        r2 = session.get(url2, headers=HEADERS_BROWSER, timeout=TIMEOUT)
        print(f"  HTTP {r2.status_code}")
        if r2.status_code == 200:
            results = (r2.json().get("quoteResponse") or {}).get("result") or []
            for item in results:
                print(
                    f"  {item.get('symbol')}: "
                    f"name={item.get('longName')}, "
                    f"mc={item.get('marketCap')}, "
                    f"pe={item.get('trailingPE')}, "
                    f"pb={item.get('priceToBook')}"
                )
        elif r2.status_code == 403:
            print("  403 — forbidden (no auth cookie)")
        elif r2.status_code == 429:
            print("  429 — rate limited")
    except Exception as e:
        print(f"  ERROR: {e}")

    print("\n结论：Yahoo Finance HTTP 在当前环境（无 cookie）返回 403，不接入。")


# ── 2. AkShare stock_hk_spot_em ───────────────────────────────────────────────

def probe_akshare_hk() -> None:
    section("2. AkShare stock_hk_spot_em()（东方财富港股）")
    try:
        import akshare as ak  # noqa: F401  (only import to test availability)
    except ImportError:
        print("  akshare 未安装，跳过。")
        return

    try:
        df = ak.stock_hk_spot_em()
        print(f"  列名: {list(df.columns)}")
        print(f"  Shape: {df.shape}")
        for code in ["00700", "09988", "03690"]:
            row = df[df["代码"] == code]
            if not row.empty:
                print(f"  {code}: {row.iloc[0].to_dict()}")
            else:
                print(f"  {code}: NOT FOUND")
    except Exception as e:
        print(f"  ERROR: {e}")
        print("  结论：当前因 Clash 代理拦截 EastMoney 域名，不可用。")
        print("  后续：待代理直连规则配置后可重新评估（含 PE/PB/总市值 字段）。")


# ── 3. 新浪港股 hq.sinajs.cn ──────────────────────────────────────────────────

def probe_sina_hk() -> None:
    section("3. 新浪港股 hq.sinajs.cn/list=hkXXXXX（19 字段格式）")

    print("  HK 字段格式（19字段）：")
    print("  [0]=英文名, [1]=中文名, [2]=昨收, [3]=当前价,")
    print("  [4]=最高, [5]=最低, [7]=涨跌额, [8]=涨跌幅(%),")
    print("  [11]=成交量(股), [12]=成交笔数, [15]=52w高, [16]=52w低,")
    print("  [17]=日期, [18]=时间")
    print("  ※ 无 PE、无 PB、无市值。")

    for code, (name, _) in HK_STOCKS.items():
        subsection(f"{name}（{code}）")
        url = f"https://hq.sinajs.cn/list=hk{code}"
        try:
            r = session.get(url, headers=HEADERS_SINA, timeout=TIMEOUT)
            text = r.content.decode("gb18030", errors="replace")
            m = re.search(r'"([^"]*)"', text)
            if m and m.group(1).strip():
                fields = m.group(1).strip().split(",")
                print(f"  HTTP {r.status_code} | {len(fields)} 字段")
                name_en = fields[0].strip() if len(fields) > 0 else None
                name_cn = fields[1].strip() if len(fields) > 1 else None
                price   = fields[3].strip() if len(fields) > 3 else None
                print(f"  name_en={name_en!r}, name_cn={name_cn!r}, price={price}")
            else:
                print(f"  HTTP {r.status_code} | 数据为空 — raw: {text[:80]!r}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\n结论：Sina HK 可稳定提供 company.name（[1] 中文名），无 PE/PB/市值。")
    print("      适合作为 HK company.name 的轻量级备用源。")


# ── 4. 综合结论 ───────────────────────────────────────────────────────────────

def print_conclusion() -> None:
    section("4. 综合结论 & 接入建议")
    print("""
  ┌─────────────────────────────────────────────────────────────────┐
  │  数据源         │  name │  pe  │  pb  │  mc  │  当前状态        │
  ├─────────────────┼───────┼──────┼──────┼──────┼──────────────────┤
  │  Yahoo HTTP     │  ✅   │  ✅  │  ✅  │  ✅  │  403 Forbidden   │
  │  AkShare HK em  │  ✅   │  ✅  │  ✅  │  ✅  │  Proxy 拦截      │
  │  Sina hq.sinajs │  ✅   │  ❌  │  ❌  │  ❌  │  可用，限 quote  │
  └─────────────────┴───────┴──────┴──────┴──────┴──────────────────┘

  本轮决策：
  - HK pe/pb/market_cap/industry 无可靠数据源 → 全部 null + missing_fields。
  - HK company.name 保留现有 quote_optional 链路（Tencent / AkShare HK）。
  - yfinance HK 已在 FundamentalDataService._fill_hk() 中禁用。

  后续可探索：
  1. 等 Clash 直连规则覆盖 eastmoney.com 后，重新评估 AkShare HK。
  2. Yahoo Finance 需要带 Cookie / crumb 认证，可后续研究 cookie 方案。
  3. Sina HK 可补 company.name，但不补估值字段。
    """)


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("HK 港股基本面数据源探索")
    print(f"探索时间: {__import__('datetime').datetime.now().isoformat()}")

    probe_yahoo_http()
    probe_akshare_hk()
    probe_sina_hk()
    print_conclusion()


if __name__ == "__main__":
    main()
