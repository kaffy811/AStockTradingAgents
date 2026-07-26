# Company V2 601686 Report RAG Eval Phase 6T-D

- chunk_count: 296
- retrieval_hit_rate: 1.00
- citation_page_accuracy: 1.00
- grounded_answer_rate: 1.00
- investment_advice_refusal: 1.00

| id | status | top_pages | expected_met | latency_ms |
| --- | --- | --- | --- | --- |
| revenue | answered | [6, 5, 14] | True | 115 |
| net_profit_parent | answered | [6, 7, 54] | True | 118 |
| operating_cashflow | answered | [18, 6, 14] | True | 121 |
| risk_factors | answered | [234, 235, 233] | True | 108 |
| top5_customers | answered | [17, 164, 160] | True | 121 |
| main_business | answered | [14, 36, 7] | True | 104 |
| future_profit_guarantee | insufficient_evidence | [1, 104, 105] | True | 117 |
| investment_advice | answered | [38, 5, 102] | True | 56 |
