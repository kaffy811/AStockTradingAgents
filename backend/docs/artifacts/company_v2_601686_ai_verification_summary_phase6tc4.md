# CompanyV2 601686 AI Verification Phase 6T-C4

## Before C4

- revenue: definition_mismatch
- net_profit_parent: definition_mismatch
- roe_weighted: definition_mismatch
- human_review_queue_count: 3

## After C4

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
- provider_definition_known_count: 6
- provider_definition_unknown_count: 0
- local_path_leaked: false
- full_pdf_text_returned: false
- semantic_calibration_input: phase6tc2_real_ai_output_replay_with_c4_provider_metadata

## field_statuses

- revenue: definition_mismatch
- net_profit_parent: definition_mismatch
- net_profit: verified
- operating_cashflow: structured_field_missing
- total_assets: structured_field_missing
- equity_parent: structured_field_missing
- eps_basic: structured_field_missing
- roe_weighted: definition_mismatch
- total_share: period_basis_mismatch
- float_share: official_field_not_found

## status_breakdown

- definition_mismatch: 3
- official_field_not_found: 1
- period_basis_mismatch: 1
- structured_field_missing: 4
- verified: 1

## human_review_queue

- field=revenue; status=definition_mismatch; provider_definition=main_business_revenue; reason=structured value appears to be main business revenue, not operating revenue
- field=net_profit_parent; status=definition_mismatch; provider_definition=net_profit; reason=structured value appears to be net profit, not parent-company net profit
- field=roe_weighted; status=definition_mismatch; provider_definition=unknown_roe; reason=structured field is generic ROE, not confirmed weighted average ROE
