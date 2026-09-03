"""
app/datasource/tushare_client.py — Tushare Pro 客户端

功能：
- 令牌桶速率限制（默认 500 积分/分钟，可通过配置调整）
- 自动 ts_code 转换（市场代码 + symbol → Tushare ts_code 格式）
- 统一异常类型（TushareError / TushareRateLimitError / TushareAuthError）
- 同步 Tushare SDK 调用通过 asyncio.to_thread 转为异步

Tushare Pro 接口调用均通过 `tushare_client` 单例。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import pandas as pd

log = logging.getLogger(__name__)


# ── 异常类型 ────────────────────────────────────────────────────────────────

class TushareError(RuntimeError):
    """Tushare 调用失败的基类"""

class TushareAuthError(TushareError):
    """Token 无效或权限不足"""

class TushareRateLimitError(TushareError):
    """速率限制：令牌桶耗尽且超时"""


# ── 令牌桶速率限制器 ─────────────────────────────────────────────────────────

class _TokenBucket:
    """
    令牌桶速率限制器（asyncio 原生，无第三方依赖）。

    参数：
        rate_per_min: 每分钟最大令牌数（对应 Tushare 积分限额）
        burst:        允许的短时突发数量（令牌桶容量）
        acquire_timeout: acquire() 最长等待时间（秒），超时抛出 TushareRateLimitError
    """

    def __init__(
        self,
        rate_per_min: int = 500,
        burst: int = 20,
        acquire_timeout: float = 10.0,
    ) -> None:
        self._rate: float = rate_per_min / 60.0          # tokens/sec
        self._capacity: float = float(min(burst, 50))    # 桶容量上限 50
        self._tokens: float = self._capacity              # 初始满桶
        self._last_refill: float = time.monotonic()
        self._lock = asyncio.Lock()
        self._acquire_timeout = acquire_timeout

    def _refill(self) -> None:
        """根据经过的时间补充令牌（在 _lock 内调用）。"""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._tokens = min(self._capacity, self._tokens + elapsed * self._rate)
        self._last_refill = now

    async def acquire(self) -> None:
        """
        获取一个令牌（阻塞直到可用或超时）。
        超时时抛出 TushareRateLimitError。
        """
        deadline = time.monotonic() + self._acquire_timeout
        async with self._lock:
            while True:
                self._refill()
                if self._tokens >= 1.0:
                    self._tokens -= 1.0
                    return
                # 计算需等待时间
                deficit = 1.0 - self._tokens
                wait = deficit / self._rate
                if time.monotonic() + wait > deadline:
                    raise TushareRateLimitError(
                        f"Tushare 速率限制：令牌桶耗尽，等待超过 {self._acquire_timeout}s"
                    )
                await asyncio.sleep(min(wait, 0.05))


# ── ts_code 转换工具 ─────────────────────────────────────────────────────────

def _to_ts_code(market: str, symbol: str) -> str:
    """
    将 (market, symbol) 转换为 Tushare ts_code 格式。

    规则：
        CN + 6XXXXX → 600000.SH (沪市) 或 000001.SZ (深市)
        CN + 688XXX → 688001.SH (科创板)
        HK + 数字   → 00700.HK
        US + ticker → AAPL（原样）
    """
    m = market.upper()
    s = symbol.strip()

    if m == "CN":
        # 按首位数字判断交易所
        if s.startswith(("6", "9")):
            return f"{s}.SH"
        elif s.startswith(("0", "3", "2")):
            return f"{s}.SZ"
        elif s.startswith("8") or s.startswith("4"):
            # 北交所
            return f"{s}.BJ"
        else:
            # fallback：按长度猜测
            return f"{s}.SH" if len(s) == 6 else s
    elif m == "HK":
        # 港股：确保 5 位数字，不足则补零
        digits = s.lstrip("0") or "0"
        return f"{digits.zfill(5)}.HK"
    else:
        # 美股：直接使用 ticker
        return s


# ── Tushare Pro 客户端 ───────────────────────────────────────────────────────

class TushareClient:
    """
    Tushare Pro API 封装，支持异步调用。

    所有 Tushare SDK 方法（同步）通过 asyncio.to_thread 转为协程，
    避免阻塞 FastAPI 事件循环。

    速率限制通过 _TokenBucket 实现，所有 _call() 调用前自动 acquire。
    """

    def __init__(self) -> None:
        self._pro: Any = None      # tushare.pro_api instance（懒加载）
        self._bucket: _TokenBucket | None = None
        self._init_lock = asyncio.Lock()
        self._timeout: float = 15.0

    # ── 初始化 ────────────────────────────────────────────────────────────────

    def _ensure_initialized(self, token: str, rate_per_min: int, timeout: float) -> None:
        """同步初始化（在 to_thread 中调用）。"""
        import tushare as ts
        ts.set_token(token)
        self._pro = ts.pro_api()
        log.info(
            "TushareClient 初始化完成：credential configured, rate=%d/min",
            rate_per_min,
        )

    async def initialize(self, token: str, rate_per_min: int = 500, timeout: float = 15.0) -> None:
        """异步初始化。仅调用一次（由应用启动时触发）。"""
        async with self._init_lock:
            if self._pro is not None:
                return
            self._timeout = timeout
            self._bucket = _TokenBucket(rate_per_min=rate_per_min, burst=20)
            await asyncio.to_thread(self._ensure_initialized, token, rate_per_min, timeout)

    @property
    def is_available(self) -> bool:
        return self._pro is not None

    # ── 核心调用 ──────────────────────────────────────────────────────────────

    async def _call(self, func_name: str, **kwargs: Any) -> pd.DataFrame:
        """
        调用 Tushare Pro 接口。

        - 先 acquire 令牌（速率限制）
        - 通过 asyncio.to_thread 异步执行同步 SDK 调用
        - 处理常见错误：权限不足（40001）、数据为空
        """
        if not self.is_available:
            raise TushareError("TushareClient 未初始化（TUSHARE_TOKEN 未配置）")

        if self._bucket:
            await self._bucket.acquire()

        func = getattr(self._pro, func_name)

        t0 = time.monotonic()
        try:
            df: pd.DataFrame = await asyncio.wait_for(
                asyncio.to_thread(func, **kwargs),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            raise TushareError(
                f"Tushare {func_name} 调用超时（{self._timeout}s）"
            )
        except Exception as exc:
            err_msg = str(exc)
            if "40001" in err_msg or "权限" in err_msg or "token" in err_msg.lower():
                raise TushareAuthError(f"Tushare 权限不足或 Token 无效: {exc}") from exc
            raise TushareError(f"Tushare {func_name} 调用失败: {exc}") from exc

        elapsed_ms = (time.monotonic() - t0) * 1000
        log.info(
            "tushare call=%s kwargs=%s elapsed=%.0fms rows=%s",
            func_name,
            {k: v for k, v in kwargs.items() if k not in ("token",)},
            elapsed_ms,
            len(df) if df is not None else "None",
        )

        if df is None or df.empty:
            raise TushareError(f"Tushare {func_name} 返回空数据，参数: {kwargs}")

        return df

    # ── 业务方法 ──────────────────────────────────────────────────────────────

    async def get_daily(self, ts_code: str, trade_date: str | None = None) -> pd.DataFrame:
        """Latest or specified EOD daily bar. Values are never real-time."""
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
        }
        if trade_date:
            kwargs["trade_date"] = trade_date
        return await self._call("daily", **kwargs)

    async def get_index_daily(self, ts_code: str, trade_date: str | None = None) -> pd.DataFrame:
        """Latest or specified index EOD bar for an explicitly mapped index."""
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": "ts_code,trade_date,open,high,low,close,pre_close,change,pct_chg,vol,amount",
        }
        if trade_date:
            kwargs["trade_date"] = trade_date
        return await self._call("index_daily", **kwargs)

    async def get_daily_basic_range(
        self,
        ts_code: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """
        daily_basic 区间接口：用于估值历史分位计算。
        start_date / end_date 格式：YYYYMMDD。
        返回 trade_date, pe_ttm, pb, ps_ttm, dv_ttm, close 等列。
        """
        return await self._call(
            "daily_basic",
            ts_code=ts_code,
            start_date=start_date,
            end_date=end_date,
            fields="ts_code,trade_date,close,pe,pe_ttm,pb,ps,ps_ttm,dv_ratio,dv_ttm",
        )

    async def get_daily_basic(self, ts_code: str, trade_date: str | None = None) -> pd.DataFrame:
        """
        daily_basic 接口：PE / PB / 市值 / 换手率等日频指标。
        trade_date 格式：YYYYMMDD，不传则取最新交易日。
        """
        kwargs: dict[str, Any] = {"ts_code": ts_code, "fields": ",".join([
            "ts_code", "trade_date", "close", "pe", "pe_ttm", "pb",
            "ps", "ps_ttm", "dv_ratio", "dv_ttm", "total_mv", "circ_mv",
            "turnover_rate", "turnover_rate_f", "volume_ratio",
        ])}
        if trade_date:
            kwargs["trade_date"] = trade_date
        return await self._call("daily_basic", **kwargs)

    async def get_fina_indicator(self, ts_code: str, period: str | None = None) -> pd.DataFrame:
        """
        fina_indicator 接口：ROE / ROA / 毛利率 / 净利率 / 资产负债率等财务指标。
        period 格式：YYYYMMDD（报告期末日）。
        """
        kwargs: dict[str, Any] = {"ts_code": ts_code, "fields": ",".join([
            "ts_code", "ann_date", "end_date", "eps", "bps",
            "roe", "roe_waa", "roa", "npta", "roic",
            "grossprofit_margin", "netprofit_margin", "expense_of_sales",
            "profit_dedt", "current_ratio", "quick_ratio", "cash_ratio",
            "debt_to_assets", "op_income", "ebit", "ebitda",
            "revenue_ps", "capital_rese_ps", "undist_profit_ps",
            "extra_item", "profit_dedt", "gross_margin", "current_ratio",
            "quick_ratio", "cash_ratio", "ar_turn", "inv_turn",
            "assets_turn", "op_cycle", "beps", "ocfps", "retainedps",
            "cfps", "ebit_ps", "fcff_ps", "fcfe_ps",
            "netprofit_yoy", "tr_yoy", "or_yoy",
            "equity_yoy", "rd_exp",
        ])}
        if period:
            kwargs["period"] = period
        return await self._call("fina_indicator", **kwargs)

    async def get_income(self, ts_code: str, period: str | None = None, limit: int = 8) -> pd.DataFrame:
        """
        income 接口：利润表（营收/净利润/毛利等）。
        返回最近 `limit` 期数据。
        """
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": ",".join([
                "ts_code", "ann_date", "f_ann_date", "end_date", "report_type",
                "comp_type", "total_revenue", "revenue", "int_income",
                "prem_earned", "comm_income", "n_commis_income",
                "n_oth_income", "n_oth_b_income", "prem_income",
                "out_prem", "une_prem_reser", "reins_income",
                "n_sec_tb_income", "n_sec_ubal_income", "n_deriv_income",
                "n_forex_gain", "n_other_bus_income", "total_cogs",
                "oper_cost", "int_exp", "comm_exp", "biz_tax_surchg",
                "sell_exp", "admin_exp", "fin_exp", "assets_impair_loss",
                "prem_refund", "compens_payout", "reser_insur_liab",
                "div_payt", "reins_exp", "oper_exp", "compens_payout_refu",
                "insur_reser_refu", "reins_cost_refund",
                "other_bus_cost", "operate_profit", "non_oper_income",
                "non_oper_exp", "nca_disploss", "total_profit",
                "income_tax", "n_income", "n_income_attr_p",
                "minority_gain", "oth_compr_income", "t_compr_income",
                "compr_inc_attr_p", "compr_inc_attr_m_s",
                "ebit", "ebitda", "insurance_exp", "undist_profit",
                "distable_profit",
            ]),
            "limit": limit,
        }
        if period:
            kwargs["period"] = period
        return await self._call("income", **kwargs)

    async def get_balancesheet(self, ts_code: str, period: str | None = None, limit: int = 8) -> pd.DataFrame:
        """
        balancesheet 接口：资产负债表关键指标。
        """
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": ",".join([
                "ts_code", "ann_date", "f_ann_date", "end_date", "report_type",
                "comp_type", "total_assets", "total_liab", "total_hldr_eqy_exc_min_int",
                "total_hldr_eqy_inc_min_int", "money_cap", "trad_asset",
                "notes_receiv", "accounts_receiv", "oth_receiv", "prepayment",
                "div_receiv", "int_receiv", "inventories", "amor_exp",
                "nca_within_1y", "sett_rsrv", "loanto_oth_bank_fi",
                "premium_receiv", "reinsur_receiv", "reinsur_res_receiv",
                "pur_resale_fa", "oth_cur_assets", "total_cur_assets",
                "fa_avail_for_sale", "htm_invest", "lt_eqt_invest",
                "invest_real_estate", "time_deposits", "oth_assets",
                "lt_rec", "fix_assets", "cip", "const_materials",
                "fixed_assets_disp", "produc_bio_assets", "oil_and_gas_assets",
                "intan_assets", "r_and_d", "goodwill", "lt_amor_exp",
                "defer_tax_assets", "decr_in_disbur", "oth_nca", "total_nca",
                "cash_reser_cb", "depos_in_oth_bfi", "prec_metals",
                "deriv_assets", "rr_reins_une_prem", "rr_reins_outstd_cla",
                "rr_reins_lins_liab", "rr_reins_lthins_liab",
                "refund_depos", "ph_pledge_loans", "refund_cap_depos",
                "indep_acct_assets", "client_depos", "client_prov",
                "transac_seat_fee", "invest_as_receiv", "total_assets",
                "lt_borr", "st_borr", "cb_borr", "depos_ib_deposits",
                "loan_oth_bank", "trading_fl", "notes_payable",
                "acct_payable", "adv_receipts", "sold_for_repur_fa",
                "comm_payable", "payroll_payable", "taxes_payable",
                "int_payable", "div_payable", "oth_payable", "acc_exp",
                "deferred_inc", "st_bonds_payable", "payable_to_reinsurer",
                "rsrv_insur_cont", "acting_trading_sec",
                "acting_uw_sec", "non_cur_liab_due_1y", "oth_cur_liab",
                "total_cur_liab", "bond_payable", "lt_payable",
                "specific_payables", "estimated_liab", "defer_tax_liab",
                "defer_inc_non_cur_liab", "oth_ncl", "total_ncl",
                "depos_oth_bfi", "deriv_liab", "depos", "agency_bus_liab",
                "oth_liab", "prem_receiv_adva", "depos_received",
                "ph_invest", "reser_une_prem", "reser_outstd_claims",
                "reser_lins_liab", "reser_lthins_liab",
                "indep_acct_liab", "pledge_borr", "indem_payable",
                "policy_div_payable", "total_liab",
                "treasury_share", "ordin_risk_reser", "forex_differ",
                "invest_loss_unconf", "minority_int", "total_hldr_eqy_exc_min_int",
                "total_hldr_eqy_inc_min_int", "total_liab_hldr_eqy",
                "lt_payroll_payable", "oth_comp_income", "oth_eqt_tools",
                "oth_eqt_tools_p_shr", "lending_funds",
                "acc_invest", "mngt_fee_payable", "rcv_prem_for_insur",
                "summ_payable_to_reinsurer", "exp_payable",
                "grnt_assets", "insur_exp_reserve", "undist_profit",
                "distable_profit", "update_flag",
            ]),
            "limit": limit,
        }
        if period:
            kwargs["period"] = period
        return await self._call("balancesheet", **kwargs)

    async def get_cashflow(self, ts_code: str, period: str | None = None, limit: int = 8) -> pd.DataFrame:
        """
        cashflow 接口：现金流量表。
        """
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": ",".join([
                "ts_code", "ann_date", "f_ann_date", "end_date", "report_type",
                "comp_type", "net_profit", "finan_exp", "c_fr_sale_sg",
                "recp_tax_rends", "n_depos_incr_fi", "n_incr_loans_cb",
                "n_inc_borr_oth_fi", "prem_fr_orig_contr",
                "n_incr_insured_dep", "n_reinsur_prem",
                "n_incr_disp_tfa", "ifc_cash_incr",
                "n_incr_disp_faas", "n_incr_loans_oth_bank",
                "n_cap_incr_repur", "c_fr_oth_operate_a",
                "c_inf_fr_operate_a", "c_paid_goods_s",
                "c_paid_to_employ_s", "c_paid_for_taxes",
                "n_incr_clt_loan_adv", "n_incr_dep_cbob",
                "c_pay_claims_orig_inco", "pay_handling_chrg",
                "pay_comm_insur_plcy", "oth_cash_pay_oper_act",
                "st_cash_out_act", "n_cashflow_act",
                "oth_recp_ral_inv_act", "c_disp_withdrwl_invest",
                "c_recp_return_invest", "n_recp_disp_fiolta",
                "n_recp_disp_sobu", "stot_inflows_inv_act",
                "c_pay_acq_const_fiolta", "c_paid_invest",
                "n_disp_subs_oth_biz", "oth_pay_ral_inv_act",
                "n_incr_pledge_loan", "stot_out_inv_act",
                "n_cashflow_inv_act", "c_recp_borrow",
                "proc_issue_bonds", "oth_cash_recp_ral_fnc_act",
                "stot_cash_in_fnc_act", "free_cashflow",
                "c_prepay_amt_borr", "c_pay_dist_dpcp_int_exp",
                "incl_dvd_profit_paid_sc_ms", "oth_cashpay_ral_fnc_act",
                "stot_cashout_fnc_act", "n_cash_flows_fnc_act",
                "eff_fx_flu_cash", "n_incr_cash_cash_equ",
                "c_cash_equ_beg_period", "c_cash_equ_end_period",
                "c_recp_cap_contrib", "incl_cash_rec_saims",
                "uncon_invest_loss", "prov_depr_assets",
                "depr_fa_coga_dpba", "amort_intang_assets",
                "lt_amort_deferred_exp", "decr_deferred_exp",
                "incr_acc_exp", "loss_disp_fiolta",
                "loss_scr_fa", "loss_fv_chg", "invest_loss",
                "decr_def_inc_tax_assets", "incr_def_inc_tax_liab",
                "decr_inventories", "decr_oper_payable",
                "incr_oper_payable", "others",
                "im_n_cashflow_act", "conv_debt_into_cap",
                "conv_copyrrightings_into_assets", "fa_fnc_leases",
                "end_bal_cash", "beg_bal_cash",
                "end_bal_cash_equ", "beg_bal_cash_equ",
                "p_end_bal_cash",
            ]),
            "limit": limit,
        }
        if period:
            kwargs["period"] = period
        return await self._call("cashflow", **kwargs)

    async def get_daily_basic_by_trade_date(self, trade_date: str) -> pd.DataFrame:
        """
        daily_basic 全市场批量接口：按 trade_date 获取所有上市股票的日频估值/市值数据。

        trade_date 格式：YYYYMMDD。
        不按 ts_code 循环，一次拉取全市场。

        返回字段：ts_code, trade_date, close, turnover_rate, volume_ratio,
                  pe, pe_ttm, pb, ps, ps_ttm, dv_ratio, dv_ttm,
                  total_share, float_share, free_share, total_mv, circ_mv
        """
        return await self._call(
            "daily_basic",
            trade_date=trade_date,
            fields=",".join([
                "ts_code", "trade_date", "close", "turnover_rate", "turnover_rate_f",
                "volume_ratio", "pe", "pe_ttm", "pb", "ps", "ps_ttm",
                "dv_ratio", "dv_ttm", "total_share", "float_share", "free_share",
                "total_mv", "circ_mv",
            ]),
        )

    async def get_fina_indicator_by_period(
        self,
        period: str | None = None,
        ann_date: str | None = None,
    ) -> pd.DataFrame:
        """
        fina_indicator 全市场批量接口：按 period（报告期末）或 ann_date（披露日）批量拉取。

        period 格式：YYYYMMDD（如 20251231 代表 2025 年年报）。
        ann_date 格式：YYYYMMDD。
        period 和 ann_date 至少传一个。

        不按 ts_code 循环，一次拉取全市场指定期间数据。
        """
        if not period and not ann_date:
            raise TushareError("get_fina_indicator_by_period 需要传入 period 或 ann_date")
        kwargs: dict[str, Any] = {
            "fields": ",".join([
                "ts_code", "ann_date", "end_date",
                "roe", "roa", "roic",
                "grossprofit_margin", "netprofit_margin",
                "netprofit_yoy", "or_yoy", "tr_yoy", "dt_netprofit_yoy",
                "assets_turn", "inv_turn", "ar_turn",
                "current_ratio", "quick_ratio", "debt_to_assets",
                "beps", "ocfps",
            ]),
        }
        if period:
            kwargs["period"] = period
        if ann_date:
            kwargs["ann_date"] = ann_date
        return await self._call("fina_indicator", **kwargs)

    async def get_stock_basic(self, ts_code: str | None = None, market: str | None = None) -> pd.DataFrame:
        """
        stock_basic 接口：股票基本信息（名称/行业/上市日期等）。
        """
        kwargs: dict[str, Any] = {
            "fields": "ts_code,symbol,name,area,industry,fullname,enname,cnspell,market,exchange,curr_type,list_status,list_date,delist_date,is_hs",
        }
        if ts_code:
            kwargs["ts_code"] = ts_code
        if market:
            kwargs["market"] = market
        return await self._call("stock_basic", **kwargs)

    async def get_fina_mainbz(self, ts_code: str, period: str | None = None) -> pd.DataFrame:
        """主营业务构成（fina_mainbz）。period 格式 YYYYMMDD（如 20251231）。"""
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "type": "P",  # P=按产品, D=按地区
            "fields": "ts_code,end_date,bz_item,bz_sales,bz_profit,bz_cost,curr_type,update_flag",
        }
        if period:
            kwargs["period"] = period
        return await self._call("fina_mainbz", **kwargs)

    async def get_dividend(self, ts_code: str) -> pd.DataFrame:
        """分红送股历史（dividend）。"""
        return await self._call(
            "dividend",
            ts_code=ts_code,
            fields="ts_code,end_date,ann_date,div_proc,stk_div,stk_bo_rate,stk_co_rate,cash_div,cash_div_tax,record_date,ex_date,pay_date,div_listdate,imp_ann_date,base_date,base_share",
        )

    async def get_stk_holdernumber(
        self,
        ts_code: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        """股东户数趋势（stk_holdernumber）。"""
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": "ts_code,ann_date,end_date,holder_num,holder_num_change",
        }
        if start_date:
            kwargs["start_date"] = start_date
        if end_date:
            kwargs["end_date"] = end_date
        return await self._call("stk_holdernumber", **kwargs)

    async def get_top10_floatholders(self, ts_code: str, period: str | None = None) -> pd.DataFrame:
        """十大流通股东（top10_floatholders）。"""
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": "ts_code,ann_date,end_date,holder_name,hold_amount,hold_ratio",
        }
        if period:
            kwargs["period"] = period
        return await self._call("top10_floatholders", **kwargs)

    async def get_forecast(self, ts_code: str, period: str | None = None) -> pd.DataFrame:
        """业绩预告（forecast）。"""
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": "ts_code,ann_date,end_date,type,p_change_min,p_change_max,net_profit_min,net_profit_max,last_parent_net,first_ann_date,summary,change_reason",
        }
        if period:
            kwargs["period"] = period
        return await self._call("forecast", **kwargs)

    async def get_express(self, ts_code: str, period: str | None = None) -> pd.DataFrame:
        """业绩快报（express）。"""
        kwargs: dict[str, Any] = {
            "ts_code": ts_code,
            "fields": "ts_code,ann_date,end_date,revenue,operate_profit,total_profit,n_income,total_assets,total_hldr_eqy_exc_min_int,diluted_eps,diluted_roe,yoy_net_profit,bps,yoy_sales,yoy_op,cfps,roe,gross_margin,op_income,ebit_ps,fcfe_ps,netprofit_margin,dt_netprofit,yoy_equity,total_revenue,operate_income",
        }
        if period:
            kwargs["period"] = period
        return await self._call("express", **kwargs)


# ── 模块级单例（懒初始化，由应用启动时触发） ─────────────────────────────────

tushare_client = TushareClient()


async def init_tushare_client() -> None:
    """
    在 FastAPI lifespan 中调用，初始化 Tushare 客户端。
    如果 TUSHARE_TOKEN 未配置则跳过（服务不可用时各工具返回 err_envelope）。
    """
    from app.core.config import settings

    token = settings.tushare_token
    if not token:
        log.warning(
            "TUSHARE_TOKEN 未配置 — Tushare 数据源不可用。"
            "请在 .env 中设置 TUSHARE_TOKEN=<your_token>"
        )
        return

    await tushare_client.initialize(
        token=token,
        rate_per_min=settings.tushare_rate_limit_per_min,
        timeout=settings.tushare_timeout_seconds,
    )
