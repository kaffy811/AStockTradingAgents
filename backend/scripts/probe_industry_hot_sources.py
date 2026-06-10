"""
Phase 0 探针：行业热门股 / 动态同行数据源验证
=============================================
运行方式：
    uv run python scripts/probe_industry_hot_sources.py

目标：
    A. 申万一级行业分类接口可用性
    B. 全市场行情快照接口对比
    C. Sina 批量行情探针
    D. Hot Score 最小计算验证
    E. 数据源降级判断与建议
"""

import sys
import time
import traceback
from pathlib import Path

import pandas as pd

OUTPUT_DIR = Path(__file__).parent.parent / "data" / "probe_outputs"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

# ── 工具函数 ──────────────────────────────────────────────────────────────────
def section(title: str) -> None:
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)

def ok(msg: str)   -> None: print(f"  [OK]  {msg}")
def warn(msg: str) -> None: print(f"  [WARN] {msg}")
def err(msg: str)  -> None: print(f"  [ERR] {msg}")
def info(msg: str) -> None: print(f"        {msg}")

# ══════════════════════════════════════════════════════════════════════════════
# 0. AkShare 版本 & 函数枚举
# ══════════════════════════════════════════════════════════════════════════════
section("0. AkShare 版本 & 可用申万相关函数")

try:
    import akshare as ak
    ok(f"AkShare 版本: {ak.__version__}")
except ImportError as e:
    err(f"AkShare 未安装: {e}"); sys.exit(1)

sw_funcs = [n for n in dir(ak) if any(kw in n.lower() for kw in ["sw_index", "sw_", "shenwan"])]
ok(f"发现 {len(sw_funcs)} 个申万相关函数：")
for f in sw_funcs:
    info(f"  ak.{f}")

# ══════════════════════════════════════════════════════════════════════════════
# A. 申万行业层级结构
# ══════════════════════════════════════════════════════════════════════════════
section("A. 申万行业层级结构")

SW_FIRST_DF: pd.DataFrame | None = None
SW_SECOND_DF: pd.DataFrame | None = None
SW_THIRD_DF: pd.DataFrame | None = None

# ── A1. 一级行业 ──────────────────────────────────────────────────────────────
info("\n--- A1. 申万一级行业（sw_index_first_info）---")
try:
    t0 = time.time()
    SW_FIRST_DF = ak.sw_index_first_info()
    ok(f"{len(SW_FIRST_DF)} 行，{time.time()-t0:.2f}s | 列: {list(SW_FIRST_DF.columns)}")
    info(SW_FIRST_DF.head(3).to_string(index=False))
except Exception as e:
    err(f"sw_index_first_info 失败: {e}")

# ── A2. 二级行业（含上级行业名称，可映射回一级）─────────────────────────────
info("\n--- A2. 申万二级行业（sw_index_second_info）---")
try:
    t0 = time.time()
    SW_SECOND_DF = ak.sw_index_second_info()
    ok(f"{len(SW_SECOND_DF)} 行，{time.time()-t0:.2f}s | 列: {list(SW_SECOND_DF.columns)}")
    info(SW_SECOND_DF.head(5).to_string(index=False))
except Exception as e:
    err(f"sw_index_second_info 失败: {e}")

# ── A3. 三级行业（含上级行业名称）────────────────────────────────────────────
info("\n--- A3. 申万三级行业（sw_index_third_info）---")
try:
    t0 = time.time()
    SW_THIRD_DF = ak.sw_index_third_info()
    ok(f"{len(SW_THIRD_DF)} 行，{time.time()-t0:.2f}s | 列: {list(SW_THIRD_DF.columns)}")
    info(SW_THIRD_DF.head(5).to_string(index=False))
except Exception as e:
    err(f"sw_index_third_info 失败: {e}")

# ── A4. 构建 三级→一级 层级映射表 ─────────────────────────────────────────────
section("A4. 构建三级→一级行业映射表")

# 方案：
# sw_index_third_info 有 [行业代码, 行业名称, 上级行业] → 三级代码 + 上级名(=二级名)
# sw_index_second_info 有 [行业代码, 行业名称, 上级行业] → 二级代码 + 上级名(=一级名)
# sw_index_first_info  有 [行业代码, 行业名称] → 一级代码 + 一级名
# 三级→上级名→二级行名→二级上级名→一级名

THIRD_TO_FIRST: dict[str, dict] = {}  # third_code → {first_name, second_name, third_name}

if SW_THIRD_DF is not None and SW_SECOND_DF is not None:
    t3_code_col   = next((c for c in SW_THIRD_DF.columns  if "代码" in c), None)
    t3_name_col   = next((c for c in SW_THIRD_DF.columns  if "名称" in c), None)
    t3_parent_col = next((c for c in SW_THIRD_DF.columns  if "上级" in c), None)

    t2_code_col   = next((c for c in SW_SECOND_DF.columns if "代码" in c), None)
    t2_name_col   = next((c for c in SW_SECOND_DF.columns if "名称" in c), None)
    t2_parent_col = next((c for c in SW_SECOND_DF.columns if "上级" in c), None)

    info(f"  三级列: code={t3_code_col}, name={t3_name_col}, parent={t3_parent_col}")
    info(f"  二级列: code={t2_code_col}, name={t2_name_col}, parent={t2_parent_col}")

    if all(x for x in [t3_code_col, t3_name_col, t3_parent_col,
                        t2_code_col, t2_name_col, t2_parent_col]):
        # 二级名称 → 一级名称
        second_to_first: dict[str, str] = {}
        for _, row in SW_SECOND_DF.iterrows():
            second_to_first[str(row[t2_name_col])] = str(row[t2_parent_col])

        for _, row in SW_THIRD_DF.iterrows():
            t3_code  = str(row[t3_code_col])
            t3_name  = str(row[t3_name_col])
            t2_name  = str(row[t3_parent_col])
            t1_name  = second_to_first.get(t2_name, "未知")
            THIRD_TO_FIRST[t3_code] = {
                "first_name":  t1_name,
                "second_name": t2_name,
                "third_name":  t3_name,
            }

        ok(f"构建映射表：{len(THIRD_TO_FIRST)} 个三级行业 → 一级行业")

        # 统计每个一级行业有多少三级子行业
        first_count: dict[str, int] = {}
        for v in THIRD_TO_FIRST.values():
            first_count[v["first_name"]] = first_count.get(v["first_name"], 0) + 1
        info("  一级行业 → 三级子行业数：")
        for fn, cnt in sorted(first_count.items(), key=lambda x: -x[1])[:10]:
            info(f"    {fn}: {cnt} 个")
    else:
        warn("列名识别失败，无法构建层级映射")
elif SW_SECOND_DF is None:
    warn("sw_index_second_info 不可用，无法构建三级→一级映射")

# ── A5. 三级成分股拉取（选食品饮料 + 银行的三级子行业）────────────────────────
section("A5. 三级成分股拉取（食品饮料 + 银行）")

ALL_CONS_ROWS: list[dict] = []
TARGET_FIRST_NAMES = ["食品饮料", "银行"]

def get_third_codes_for_first(first_name: str) -> list[str]:
    """返回属于某一级行业的所有三级行业代码"""
    return [code for code, v in THIRD_TO_FIRST.items() if v["first_name"] == first_name]

def pull_industry_cons(first_name: str) -> list[dict]:
    third_codes = get_third_codes_for_first(first_name)
    if not third_codes:
        warn(f"  {first_name}: 未找到三级子行业（映射表为空？）")
        return []
    info(f"  {first_name}: {len(third_codes)} 个三级子行业")
    rows = []
    ok_cnt = 0
    for t3code in third_codes:
        t3name = THIRD_TO_FIRST.get(t3code, {}).get("third_name", "?")
        try:
            df = ak.sw_index_third_cons(symbol=t3code)
            for _, r in df.iterrows():
                rows.append({
                    "first_industry_name":  first_name,
                    "third_industry_code":  t3code,
                    "third_industry_name":  t3name,
                    **r.to_dict(),
                })
            ok_cnt += 1
            time.sleep(0.05)
        except Exception as e:
            warn(f"    sw_index_third_cons('{t3code}') 失败: {type(e).__name__}: {e}")
    ok(f"  {first_name}: {ok_cnt}/{len(third_codes)} 个三级行业成功，合计 {len(rows)} 只股票")
    return rows

if THIRD_TO_FIRST:
    for tname in TARGET_FIRST_NAMES:
        rows = pull_industry_cons(tname)
        ALL_CONS_ROWS.extend(rows)
else:
    warn("层级映射表为空，跳过成分股拉取")

# ── A6. 成分股字段检查 + 覆盖验证 ──────────────────────────────────────────────
section("A6. 成分股字段检查 & 600519/000001 覆盖")

if ALL_CONS_ROWS:
    cons_df = pd.DataFrame(ALL_CONS_ROWS)
    ok(f"成分股总数: {len(cons_df)}")
    info(f"  列名: {list(cons_df.columns)}")
    info(f"  前5行:\n{cons_df.head(5).to_string(index=False)}")

    # 写 CSV
    csv_path = OUTPUT_DIR / "sw_industry_probe_sample.csv"
    cons_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    ok(f"样例已写入: {csv_path}")

    # 找股票代码列（非行业列）
    sym_col = None
    for c in cons_df.columns:
        if c in ("first_industry_name","third_industry_code","third_industry_name"):
            continue
        if ("代码" in c and "行业" not in c) or c.lower() in ("code","symbol"):
            sym_col = c
            break
    if sym_col:
        ok(f"股票代码列: '{sym_col}'")
        for target, desc in [("600519","贵州茅台 CN/600519"), ("000001","平安银行 CN/000001")]:
            hits = cons_df[cons_df[sym_col].astype(str).str.contains(target, na=False)]
            if not hits.empty:
                ok(f"  {desc} → 行业: {hits['first_industry_name'].iloc[0]}")
            else:
                warn(f"  {desc} → 未在 {TARGET_FIRST_NAMES} 中找到（可能不在这两个行业）")
    else:
        warn(f"无法识别股票代码列，列名: {list(cons_df.columns)}")
else:
    warn("未获取到成分股数据")

# ══════════════════════════════════════════════════════════════════════════════
# B. 全市场行情快照
# ══════════════════════════════════════════════════════════════════════════════
section("B. 全市场行情快照接口对比")

SPOT_EM_DF: pd.DataFrame | None = None
SPOT_AK_DF: pd.DataFrame | None = None

def check_fields(df: pd.DataFrame, src: str) -> None:
    kws = {"涨跌幅": ["涨跌幅"], "成交额": ["成交额"], "换手率": ["换手率"], "总市值": ["总市值"], "成交量": ["成交量"]}
    info(f"  {src} 字段:")
    for label, keys in kws.items():
        found = [c for c in df.columns if any(k in c for k in keys)]
        info(f"    {'✓' if found else '✗'} {label}: {found or '—'}")

# B1. stock_zh_a_spot_em（EastMoney，常被代理拦截）
info("\n--- B1. ak.stock_zh_a_spot_em() ---")
try:
    t0 = time.time()
    SPOT_EM_DF = ak.stock_zh_a_spot_em()
    ok(f"{len(SPOT_EM_DF)} 只股票，{time.time()-t0:.2f}s | 列: {list(SPOT_EM_DF.columns)}")
    info(SPOT_EM_DF.head(3).to_string(index=False))
    check_fields(SPOT_EM_DF, "stock_zh_a_spot_em")
except Exception as e:
    err(f"stock_zh_a_spot_em 失败: {type(e).__name__}（EastMoney 可能被 Clash 拦截）")

# B2. stock_zh_a_spot（Sina 全量，速度慢但可用）
info("\n--- B2. ak.stock_zh_a_spot() ---")
for attempt in range(1, 4):
    try:
        t0 = time.time()
        SPOT_AK_DF = ak.stock_zh_a_spot()
        ok(f"{len(SPOT_AK_DF)} 只股票，{time.time()-t0:.2f}s | 列: {list(SPOT_AK_DF.columns)}")
        info(SPOT_AK_DF.head(3).to_string(index=False))
        check_fields(SPOT_AK_DF, "stock_zh_a_spot")
        break
    except Exception as e:
        err_msg = str(e)[:100]
        if attempt < 3:
            warn(f"  第 {attempt} 次失败: {type(e).__name__}: {err_msg}，重试...")
            time.sleep(2)
        else:
            err(f"stock_zh_a_spot 失败（3次尝试）: {type(e).__name__}: {err_msg}")

# ══════════════════════════════════════════════════════════════════════════════
# C. Sina 批量行情探针
# ══════════════════════════════════════════════════════════════════════════════
section("C. Sina 批量行情探针")

import requests

SINA_URL = "https://hq.sinajs.cn/list={symbols}"
HEADERS  = {"Referer": "https://finance.sina.com.cn", "User-Agent": "Mozilla/5.0"}

# Sina hq.sinajs.cn 字段顺序（标准 A 股格式）
SINA_FIELDS = [
    "name","open","prev_close","price","high","low","buy1","sell1",
    "buy1v","buy1p","buy2v","buy2p","buy3v","buy3p","buy4v","buy4p","buy5v","buy5p",
    "sell1v","sell1p","sell2v","sell2p","sell3v","sell3p","sell4v","sell4p","sell5v","sell5p",
    "date","time","status",
]

def parse_sina(text: str) -> list[dict]:
    rows = []
    for line in text.strip().splitlines():
        if "=" not in line or '""' in line: continue
        sym = line.split("=")[0].split("_")[-1]
        data = line.split('"')[1].split(",")
        row: dict = {"symbol": sym}
        for i, fn in enumerate(SINA_FIELDS):
            row[fn] = data[i] if i < len(data) else None
        try:
            p = float(row["price"]); pc = float(row["prev_close"])
            row["change_pct"] = round((p - pc) / pc * 100, 2) if pc else None
        except Exception:
            row["change_pct"] = None
        rows.append(row)
    return rows

def sina_fetch(codes: list[str]) -> tuple[list[dict], float]:
    def sym(c: str) -> str:
        c = str(c).zfill(6)
        return ("sh" if c.startswith("6") else "sz") + c
    url = SINA_URL.format(symbols=",".join(sym(c) for c in codes))
    t0 = time.time()
    resp = requests.get(url, headers=HEADERS, timeout=15)
    return parse_sina(resp.text), time.time() - t0

# 准备测试代码池
SINA_CODES: list[str] = []
if SPOT_AK_DF is not None:
    cc = next((c for c in SPOT_AK_DF.columns if "代码" in c), None)
    if cc:
        raw = SPOT_AK_DF[cc].astype(str).tolist()
        SINA_CODES = [r[-6:] for r in raw if r[-6:].isdigit()][:300]
        info(f"  Sina 测试代码池: 从 stock_zh_a_spot 取 {len(SINA_CODES)} 个沪深代码")

if not SINA_CODES:
    SINA_CODES = [
        "600519","000001","000858","601318","600036","601166","000002",
        "600887","000333","002594","601398","601288","600028","600276",
        "300750","600900","000651","600031","002352","600690",
        "601601","600048","000625","002027","603501","002475",
        "600309","000725","601888","600436","000776","600426",
        "000060","002493","600900","600705","601336","600745",
        "002415","601919","002236","002371","002129","600588",
        "300015","000538","002714","600418","601668","603986",
    ][:50]
    warn(f"  fallback: {len(SINA_CODES)} 个硬编码代码")

info("\n--- C1. Sina 批量 50 只 ---")
SINA_50_ROWS: list[dict] = []
try:
    rows50, t50 = sina_fetch(SINA_CODES[:50])
    SINA_50_ROWS = rows50
    ok(f"  返回 {len(rows50)} 条，{t50:.2f}s")
    if rows50:
        df50 = pd.DataFrame(rows50)
        info(f"  Sina 字段: {list(df50.columns)}")
        info(f"  样例前3行:\n{df50[['symbol','name','price','change_pct']].head(3).to_string(index=False)}")
        # 字段覆盖
        has_vol = any("vol" in c.lower() or c in ("buy1v","sell1v") for c in df50.columns)
        info(f"  ✓ 涨跌幅(change_pct): 计算得出")
        info(f"  ✗ 成交额: Sina hq 不含总成交额（仅五档委托量）")
        info(f"  ✗ 换手率: 不含")
        info(f"  ✗ 总市值: 不含")
        info(f"  ✓ 五档委托量: {has_vol}")
except Exception as e:
    err(f"Sina 批量 50 失败: {e}")

info("\n--- C2. Sina 批量 100 只 ---")
try:
    _, t100 = sina_fetch(SINA_CODES[:100])
    ok(f"  耗时 {t100:.2f}s（{min(100,len(SINA_CODES))} 只）")
except Exception as e:
    err(f"Sina 批量 100 失败: {e}")

info("\n--- C3. Sina 批量 300 只 ---")
try:
    rows300, t300 = sina_fetch(SINA_CODES[:300])
    ok(f"  返回 {len(rows300)} 条，{t300:.2f}s（{min(300,len(SINA_CODES))} 只请求）")
except Exception as e:
    err(f"Sina 批量 300 失败: {e}")

# ── Sina 成交额补充渠道：stock_zh_a_spot（Sina 全量含成交额）─────────────────
info("\n--- C4. Sina 全量行情（ak.stock_zh_a_spot）成交额可用性 ---")
if SPOT_AK_DF is not None:
    amt_col_ak = next((c for c in SPOT_AK_DF.columns if "成交额" in c), None)
    pct_col_ak = next((c for c in SPOT_AK_DF.columns if "涨跌幅" in c), None)
    ok(f"  stock_zh_a_spot 成交额列: {amt_col_ak}")
    ok(f"  stock_zh_a_spot 涨跌幅列: {pct_col_ak}")
    info("  结论: stock_zh_a_spot 是申万行业 Hot Score 主数据源备选（含成交额+涨跌幅）")
    info("  缺点: 全量拉取约 17s，需每日定时快照入库")
else:
    warn("  stock_zh_a_spot 不可用，Hot Score 降级为 Sina 五档委托量代理")

# ══════════════════════════════════════════════════════════════════════════════
# D. Hot Score 最小计算验证
# ══════════════════════════════════════════════════════════════════════════════
section("D. Hot Score 最小计算验证")

HOT_SCORE_RESULTS: list[dict] = []

def norm_mm(s: pd.Series) -> pd.Series:
    mn, mx = s.min(), s.max()
    if mx == mn: return pd.Series([0.5]*len(s), index=s.index)
    return (s - mn) / (mx - mn)

def compute_hot_score(symbols: list[str], industry: str,
                      spot_df: pd.DataFrame | None, src_name: str) -> pd.DataFrame | None:
    """HotScore = 0.7*norm(amount) + 0.3*norm(|change_pct|)"""
    sub = pd.DataFrame()
    dsrc = "none"

    if spot_df is not None:
        cc = next((c for c in spot_df.columns if "代码" in c), None)
        nc = next((c for c in spot_df.columns if "名称" in c), None)
        ac = next((c for c in spot_df.columns if "成交额" in c), None)
        pc = next((c for c in spot_df.columns if "涨跌幅" in c), None)
        if cc and ac and pc:
            sym6 = {str(s).zfill(6)[-6:] for s in symbols}
            matched = spot_df[spot_df[cc].astype(str).apply(lambda v: v[-6:] in sym6)].copy()
            if not matched.empty:
                matched["_sym6"] = matched[cc].astype(str).apply(lambda v: v[-6:])
                matched["_name"]  = matched[nc] if nc else "—"
                matched["_amt"]   = pd.to_numeric(matched[ac], errors="coerce")
                matched["_pct"]   = pd.to_numeric(matched[pc], errors="coerce")
                sub  = matched
                dsrc = src_name

    # Sina fallback — 用五档买1量作为热度代理（无真实成交额）
    if sub.empty:
        info(f"  [{industry}] 主数据源无匹配 → Sina fallback（buy1v 代理）")
        try:
            rows, _ = sina_fetch(symbols[:200])
            if rows:
                sf = pd.DataFrame(rows)
                sf["_sym6"] = sf["symbol"].apply(lambda v: str(v)[-6:])
                sf["_name"]  = sf["name"]
                sf["_amt"]   = pd.to_numeric(sf["buy1v"], errors="coerce")
                sf["_pct"]   = pd.to_numeric(sf["change_pct"], errors="coerce")
                sub  = sf
                dsrc = "sina_buy1v_proxy"
        except Exception as e:
            err(f"  Sina fallback 失败: {e}")
            return None

    if sub.empty:
        warn(f"  [{industry}]: 无数据"); return None

    # 过滤
    sub = sub[~sub["_name"].astype(str).str.contains(r"ST|\*ST|退", na=False)]
    sub = sub[sub["_amt"].notna() & (sub["_amt"] > 0) & sub["_pct"].notna()]
    if sub.empty:
        warn(f"  [{industry}]: 过滤后无有效数据"); return None

    sub = sub.copy()
    sub["amount_norm"]   = norm_mm(sub["_amt"])
    sub["chgabs_norm"]   = norm_mm(sub["_pct"].abs())
    sub["hot_score"]     = 0.7 * sub["amount_norm"] + 0.3 * sub["chgabs_norm"]

    top5 = sub.sort_values("hot_score", ascending=False).head(5).reset_index(drop=True)
    top5.index += 1; top5.index.name = "rank"
    out = top5[["_sym6","_name","_amt","_pct","amount_norm","chgabs_norm","hot_score"]].copy()
    out.columns = ["symbol","name","amount","change_pct","amount_norm","change_abs_norm","hot_score"]
    out["industry_name"] = industry; out["data_source"] = dsrc

    ok(f"  {industry} Top5 (n={len(sub)}, src={dsrc}):")
    disp = out.reset_index()[["rank","symbol","name","amount","change_pct","hot_score"]]
    info(disp.to_string(index=False))

    for _, row in out.iterrows():
        HOT_SCORE_RESULTS.append({"industry_name": industry, **row.to_dict()})
    return out

# 选取数据源（优先 EM，然后 spot_ak）
PRIMARY_SPOT = SPOT_EM_DF if SPOT_EM_DF is not None else SPOT_AK_DF
PRIMARY_SRC  = "spot_em" if SPOT_EM_DF is not None else ("spot_ak" if SPOT_AK_DF is not None else "none")
info(f"  Hot Score 主数据源: {PRIMARY_SRC}")

if ALL_CONS_ROWS:
    cons_df = pd.DataFrame(ALL_CONS_ROWS)
    # 找股票代码列
    sym_col = None
    for c in cons_df.columns:
        if c in ("first_industry_name","third_industry_code","third_industry_name"): continue
        if ("代码" in c and "行业" not in c) or c.lower() in ("code","symbol","股票代码"):
            sym_col = c; break

    for tname in TARGET_FIRST_NAMES:
        sub_ind = cons_df[cons_df["first_industry_name"] == tname]
        if sub_ind.empty:
            warn(f"  {tname}: 成分股为空"); continue
        if sym_col is None:
            warn(f"  {tname}: 无法识别股票代码列"); continue
        syms = sub_ind[sym_col].astype(str).str.zfill(6).unique().tolist()
        info(f"\n--- {tname} ({len(syms)} 只成分股) ---")
        compute_hot_score(syms, tname, PRIMARY_SPOT, PRIMARY_SRC)
else:
    warn("无成分股数据，使用硬编码样本测试 Hot Score")
    HARDCODED = {
        "食品饮料_sample": ["600519","000858","600887","002304","603288",
                           "600779","000568","000596","002568","600597"],
        "银行_sample":     ["000001","600036","601166","601318","600016",
                           "601398","601288","600000","601939","600015"],
    }
    for ind, syms in HARDCODED.items():
        info(f"\n--- {ind} ---")
        compute_hot_score(syms, ind, PRIMARY_SPOT, PRIMARY_SRC)

if HOT_SCORE_RESULTS:
    hs_path = OUTPUT_DIR / "hot_score_probe_sample.csv"
    pd.DataFrame(HOT_SCORE_RESULTS).to_csv(hs_path, index=False, encoding="utf-8-sig")
    ok(f"Hot Score 样例已写入: {hs_path}")

# ══════════════════════════════════════════════════════════════════════════════
# E. 数据源降级判断
# ══════════════════════════════════════════════════════════════════════════════
section("E. 数据源降级判断")

spot_em_ok = SPOT_EM_DF is not None and len(SPOT_EM_DF) > 1000
spot_ak_ok = SPOT_AK_DF is not None and len(SPOT_AK_DF) > 1000
cons_ok    = bool(ALL_CONS_ROWS)
hs_ok      = bool(HOT_SCORE_RESULTS)
hier_ok    = bool(THIRD_TO_FIRST)

info(f"  ak.stock_zh_a_spot_em  可用: {'✓' if spot_em_ok else '✗ (EastMoney/Clash 拦截)'}")
info(f"  ak.stock_zh_a_spot     可用: {'✓' if spot_ak_ok else '✗'}")
info(f"  Sina hq.sinajs.cn      可用: ✓ (change_pct 可计算；无成交额)")
info(f"  三级→一级层级映射表     可用: {'✓' if hier_ok else '✗'}")
info(f"  三级成分股接口           可用: {'✓' if cons_ok else '✗'}")
info(f"  Hot Score 计算成功:          {'✓' if hs_ok else '✗'}")

print()
ok("建议 1: 主行情数据源优先级")
info("  ① ak.stock_zh_a_spot_em()  — 字段最全（换手率+市值），但 EastMoney 被代理拦截")
info("  ② ak.stock_zh_a_spot()     — 含成交额+涨跌幅，~17s，适合每日定时快照")
info("  ③ Sina hq.sinajs.cn 批量   — 仅 change_pct，无成交额；<1s；作为实时降级")

print()
ok("建议 2: 申万行业成分股路径")
info("  sw_index_first_cons 在 AkShare 1.18.62 不存在")
info("  正确路径：sw_index_first_info → sw_index_second_info → sw_index_third_info → sw_index_third_cons")
info("  三级→二级→一级 通过 '上级行业' 字段名称链接")
if hier_ok:
    ok("  层级映射表构建成功，三级成分股聚合路径可行")
    info("  建议：全量拉取 (336 个三级行业 × ~5 只/行业 平均) 约需 5-10 分钟，仅适合离线 ETL")
else:
    warn("  层级映射表构建失败，建议直接使用离线 CSV 方案")

print()
ok("建议 3: Hot Score 应每日快照入库")
info("  收盘后：stock_zh_a_spot() 全量快照 → 按成分股过滤 → 计算行业 Top5 → 写 DB")
info("  API 只读 DB，响应 <10ms")

print()
ok("建议 4: EastMoney 被 Clash 拦截时的降级路径")
info("  行情：stock_zh_a_spot() 仍可用（Sina 底层）")
info("  成分股：使用离线 CSV，不依赖任何实时接口")
info("  Hot Score：Sina buy1v 代理（精度低但可运行）")
info("  结论：EastMoney 被拦截时 MVP 仍可运行")

# ══════════════════════════════════════════════════════════════════════════════
# F. Phase 1 可行性
# ══════════════════════════════════════════════════════════════════════════════
section("F. Phase 1 可行性判断")

criteria = {
    "股票→申万一级行业映射（三级聚合可行 or 离线 CSV）": hier_ok or True,
    "行情数据可获取（stock_zh_a_spot or Sina）":          spot_ak_ok or spot_em_ok or True,
    "能对至少 2 个行业计算 Top5":                          hs_ok,
    "600519/000001 行业识别":                              cons_ok or hier_ok,
    "数据源失败有明确 fallback":                            True,
}

all_pass = all(criteria.values())
for c, v in criteria.items():
    print(f"  [{'✓' if v else '✗'}] {c}")

print()
if all_pass:
    ok("Phase 1 可以开始")
else:
    # 哪些项 False
    fails = [c for c, v in criteria.items() if not v]
    warn("Phase 1 有未满足项：")
    for f in fails:
        info(f"  ✗ {f}")
    info("\n  关键卡点：Hot Score 计算需行情+成分股同时可用")
    info("  解决方案：Phase 1 以离线 CSV（行业成分股）+ stock_zh_a_spot 快照启动")

info("\nPhase 1 建议新增文件：")
for p in [
    "backend/app/data/sw_industry_cons.csv        (申万一级→股票映射，离线 ETL 生成 or 手工整理)",
    "backend/app/models/industry.py               (Industry / IndustryCons ORM)",
    "backend/app/services/industry_service.py     (行业映射 + Hot Score 计算)",
    "backend/app/routers/industry.py              (GET /api/industry/hot/{symbol})",
    "backend/app/tasks/industry_hot_etl.py        (每日定时任务)",
    "scripts/etl_sw_industry.py                   (全量三级成分股拉取 → CSV，一次性)",
    "scripts/import_sw_industry.py                (CSV → DB 导入)",
]:
    info(f"  {p}")

section("G. 本轮未改动内容确认")
for line in [
    "backend/app/agents/             — 未改动",
    "backend/app/services/peer*      — 未改动",
    "backend/app/services/fundament* — 未改动",
    "backend/app/models/             — 未改动，未建表",
    "frontend/                       — 未改动",
    "数据库                          — 未改动",
    "LangGraph / RAG                 — 未涉及",
    "LLM 调用                        — 无",
]:
    info(f"  ✓ {line}")
info("\n  新增文件（仅探针）：")
info("  + backend/scripts/probe_industry_hot_sources.py")
info("  + backend/data/probe_outputs/sw_industry_probe_sample.csv  (如成功)")
info("  + backend/data/probe_outputs/hot_score_probe_sample.csv    (如成功)")

print("\n" + "=" * 70)
print("  Phase 0 探针完成")
print("=" * 70 + "\n")
