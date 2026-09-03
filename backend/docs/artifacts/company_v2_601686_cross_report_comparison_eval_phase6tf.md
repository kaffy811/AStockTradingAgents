# Company V2 601686 Cross-Report Comparison Eval Phase 6T-F

## Metrics
- selected_report_isolation_rate: 1.00
- dual_citation_rate: 1.00
- citation_page_accuracy: 1.00
- comparable_metric_accuracy: 1.00
- period_basis_warning_accuracy: 1.00
- unsupported_comparison_rate: 0.00
- wrong_report_usage_rate: 0.00
- investment_advice_refusal: 1.00
- prediction_refusal: 1.00
- latency_ms: 786

## Valid Rows
| id | status | citations | warnings |
| --- | --- | --- | --- |
| rev_2023_2024 | answered | 2 | - |
| np_2023_2024 | answered | 2 | - |
| risk_2023_2024 | partial | 2 | insufficient_evidence |
| business_2023_2024 | partial | 2 | insufficient_evidence |
| cf_2023_2024 | answered | 2 | - |
| rev_q3_annual | partial | 2 | period_basis_warning,unit_mismatch |
| np_q3_annual | partial | 2 | period_basis_warning,unit_mismatch |

## Invalid Rows
| id | status | rejected | warnings |
| --- | --- | --- | --- |
| one_report | failed | True | REPORT_COUNT_OUT_OF_RANGE |
| five_reports | failed | True | REPORT_COUNT_OUT_OF_RANGE |
| duplicate_report | failed | True | DUPLICATE_REPORT_ID |
| missing_report | failed | True | cross_report_leakage_detected |
| advice_refusal | insufficient_evidence | True | investment_advice_refused |
| prediction_refusal | insufficient_evidence | True | investment_advice_refused |

## Final Gate
- comparison_retrieval_gate_passed: True
- selected_report_isolation_gate_passed: True
- comparability_gate_passed: True
- dual_citation_gate_passed: True
- period_warning_gate_passed: True
- safety_gate_passed: True
- frontend_gate_passed: True
- tests_gate_passed: True
- phase6tf_passed: True
- blocking_issues: []
- warnings: []
- recommendation_for_phase6tg: proceed
