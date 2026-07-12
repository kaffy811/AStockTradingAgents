# CompanyV2 601686 AI Verification Phase 6T-C3

## Before

- final_status: conflict
- human_review_queue_count: 10

## After

- report_id: 1
- report_year: 2024
- report_type: annual
- pdf_url: https://static.cninfo.com.cn/finalpage/2025-04-25/1223277982.PDF
- download_status: verified
- parse_status: parsed
- page_count: 265
- parsed_page_sidecar_exists: true
- final_status: needs_human_review
- true_conflict_count: 0
- human_review_queue_count: 3
- non_blocking_findings_count: 6
- local_path_leaked: false
- full_pdf_text_returned: false
- semantic_calibration_input: phase6tc2_real_ai_output_replay

## status_breakdown

- definition_mismatch: 3
- official_field_not_found: 1
- period_basis_mismatch: 1
- structured_field_missing: 4
- verified: 1

## human_review_queue

- field=revenue; status=definition_mismatch; reason=structured value appears to be main business revenue, not operating revenue; confidence=1.0; page=6
- field=net_profit_parent; status=definition_mismatch; reason=structured value appears to be net profit, not parent-company net profit; confidence=1.0; page=6
- field=roe_weighted; status=definition_mismatch; reason=field definition text indicates a different financial concept; confidence=1.0; page=6

## non_blocking_findings

- field=operating_cashflow; status=structured_field_missing; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=14
- field=total_assets; status=structured_field_missing; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=107
- field=equity_parent; status=structured_field_missing; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=6
- field=eps_basic; status=structured_field_missing; reason=结构化未找到该字段，但年报明确披露。; confidence=1.0; page=6
- field=total_share; status=period_basis_mismatch; reason=年报未直接提供2024-12-31总股本，证据中仅有2024-12-12的总股本1,432,296,037股，无法确认期末准确数值，需人工核实。; confidence=0.3; page=None
- field=float_share; status=official_field_not_found; reason=未在年报摘要中找到流通股数相关证据，无法校核。; confidence=0.0; page=None
