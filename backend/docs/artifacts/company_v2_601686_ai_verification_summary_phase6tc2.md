# CompanyV2 601686 AI Verification Phase 6T-C2

- report_id: 1
- report_year: 2024
- report_type: annual
- pdf_url: https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF
- download_status: verified
- parse_status: parsed
- page_count: 265
- parsed_page_sidecar_exists: true
- fields_checked: 10
- verified_count: 1
- likely_match_count: 0
- mismatch_count: 3
- needs_human_review_count: 1
- insufficient_evidence_count: 5
- final_status: conflict
- local_path_leaked: false
- full_pdf_text_returned: false

## human_review_queue

- field=total_share; reason=年报未直接提供2024-12-31总股本，需人工确认期末总股本。; confidence=None; page=None
- field=revenue; reason=结构化值为主营业务收入50,227,475,991.67，而年报披露营业收入为54,822,111,649.52，两者不一致。; confidence=1.0; page=6
- field=net_profit_parent; reason=结构化值为净利润（含少数股东）482,101,037.78，而归母净利润应为424,777,342.95。; confidence=1.0; page=6
- field=operating_cashflow; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=14
- field=total_assets; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=107
- field=equity_parent; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=6
- field=eps_basic; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=6
- field=roe_weighted; reason=结构化值为6.3051%（0.063051），年报披露为6.54%，差异约3.59%。; confidence=1.0; page=6
- field=total_share; reason=年报未直接提供2024-12-31总股本，证据中仅有2024-12-12的总股本1,432,296,037股，无法确认期末准确数值，需人工核实。; confidence=0.3; page=None
- field=float_share; reason=未在年报摘要中找到流通股数相关证据，无法校核。; confidence=0.0; page=None
