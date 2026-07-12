# Phase 6T-J Stage 2 Multi-Stock Fusion Audit

- phase6tj_passed: True
- stage2_status: ready
- recommendation_for_production_fusion_rollout: proceed_stage_2

## Summary
{
  "symbols_total": 4,
  "reports_ready": 4,
  "reports_failed": 0,
  "fields_total": 40,
  "verified": 3,
  "normalized_match": 0,
  "definition_mismatch": 12,
  "period_basis_mismatch": 5,
  "unit_mismatch": 2,
  "value_conflict": 0,
  "false_conflict": 0,
  "cross_report_leakage": 0,
  "cross_symbol_leakage": 0,
  "missing_citation": 0,
  "incomplete_source_trace": 0,
  "unsupported_merge": 0,
  "timeouts": 0,
  "p50_latency_ms": 31978.15,
  "p95_latency_ms": 49843.46,
  "cache_hit_rate": 0.0,
  "circuit_state": "closed",
  "review_queue_size": 0,
  "health_status": "insufficient_data"
}

## Symbol Results
[
  {
    "symbol": "600519",
    "report_id": 2,
    "report_year": 2025,
    "report_type": "annual",
    "report_title": "贵州茅台：贵州茅台2025年年度报告",
    "status": null,
    "final_status": "passed",
    "ok": true,
    "cache_hit": false,
    "elapsed_ms": 42713.38,
    "timings": {
      "eligibility_latency_ms": 0.03,
      "cache_lookup_latency_ms": 0.0,
      "resolver_latency_ms": 41.0,
      "retrieval_latency_ms": 41.0,
      "alignment_latency_ms": 0.62,
      "persistence_latency_ms": 0.41,
      "computed_latency_ms": 42.06,
      "total_latency_ms": 9438.53,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0
    },
    "summary": {
      "fields_total": 10,
      "verified": 0,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 3,
      "period_basis_mismatch": 1,
      "unit_mismatch": 1,
      "value_conflict": 0,
      "structured_field_missing": 4,
      "official_field_not_found": 0,
      "insufficient_evidence": 1,
      "not_applicable": 0,
      "failed": 0
    },
    "fields": [
      {
        "id": 1,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "revenue",
        "provider_name": "MBRevenue",
        "provider_value": 172054171890.91,
        "provider_unit": "CNY",
        "provider_definition": "main_business_revenue",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 168838102514.79,
        "official_unit": "CNY",
        "official_definition": "营业收入",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "和财务指标 (一) 主要会计数据 单位：元 币种：人民币 主要会计数据 2025年 2024年 本期比 上年同 期增减 (%) 2023年 营业收入 168,838,102,514.79 170,899,152,276.34 -1.21 147,693,604,994.14 利润总额 114,755,261,605.08 119,638,578,194.46 -4.08 103,662,553,6",
        "normalized_provider_value": 172054171890.91,
        "normalized_official_value": 168838102514.79,
        "absolute_diff": 3216069376.119995,
        "relative_diff": 0.018692190609357187,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "VALUE_DIFF_EXCEEDS_TOLERANCE",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "revenue"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "和财务指标 (一) 主要会计数据 单位：元 币种：人民币 主要会计数据 2025年 2024年 本期比 上年同 期增减 (%) 2023年 营业收入 168,838,102,514.79 170,899,152,276.34 -1.21 147,693,604,994.14 利润总额 114,755,261,605.08 119,638,578,194.46 -4.08 103,662,553,6",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 168838102514.79,
            "raw_unit": "元",
            "normalized_value": 168838102514.79,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 6,
            "table_scope_id": "p6#u153"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 172054171890.91,
              "original_unit": "CNY",
              "normalized_value": 172054171890.91,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 168838102514.79,
              "original_unit": "CNY",
              "normalized_value": 168838102514.79,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "revenue",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": 3216069376.119995,
              "relative_diff": 0.018692190609357187
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.033478+00:00",
        "updated_at": "2026-07-12T08:05:30.033487+00:00"
      },
      {
        "id": 2,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit",
        "provider_name": "netProfit",
        "provider_value": 85310324833.67,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 85310324833.67,
        "official_unit": null,
        "official_definition": "净利润",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 115,
        "official_chunk_id": null,
        "official_excerpt": "贵州茅台酒股份有限公司2025 年年度报告 115 / 143 补充资料 本期金额 上期金额 1．将净利润调节为经营活动现金流量： 净利润 85,310,324,833.67 89,334,728,025.90 加：资产减值准备 信用减值损失 -17,234,379.37 23,248,436.03 固定资产折旧、油气资产折耗、生产 性生物资产折旧 1,893,338,311.91 1,721,1",
        "normalized_provider_value": 85310324833.67,
        "normalized_official_value": 85310324833.67,
        "absolute_diff": 0.0,
        "relative_diff": 0.0,
        "tolerance": 1.0,
        "fusion_status": "unit_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "unit not safely convertible",
          "与年报合并利润表净利润数据完全一致。",
          "official unit context missing/unknown — value comparison refused (no default 元 guess)"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "net_profit"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 115,
            "chunk_id": null,
            "excerpt": "贵州茅台酒股份有限公司2025 年年度报告 115 / 143 补充资料 本期金额 上期金额 1．将净利润调节为经营活动现金流量： 净利润 85,310,324,833.67 89,334,728,025.90 加：资产减值准备 信用减值损失 -17,234,379.37 23,248,436.03 固定资产折旧、油气资产折耗、生产 性生物资产折旧 1,893,338,311.91 1,721,1",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 85310324833.67,
            "raw_unit": null,
            "normalized_value": 85310324833.67,
            "normalized_unit": "CNY",
            "unit_scale": null,
            "unit_source": "unknown",
            "table_title": "合并利润表",
            "evidence_page": 115,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": true,
            "unit_convertible": false,
            "comparable": false,
            "status": "unit_mismatch",
            "warnings": [
              "unit not safely convertible"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 85310324833.67,
              "original_unit": "CNY",
              "normalized_value": 85310324833.67,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 85310324833.67,
              "original_unit": null,
              "normalized_value": 85310324833.67,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "unknown_unit",
              "warnings": [
                "unknown_unit"
              ]
            },
            "tolerance": {
              "field_name": "net_profit",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": true,
              "absolute_diff": 0.0,
              "relative_diff": 0.0
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.036433+00:00",
        "updated_at": "2026-07-12T08:05:30.036436+00:00"
      },
      {
        "id": 3,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit_parent",
        "provider_name": "netProfit",
        "provider_value": 85310324833.67,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 82320067101.68,
        "official_unit": "CNY",
        "official_definition": "归属于母公司股东的净利润",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "4 利润总额 114,755,261,605.08 119,638,578,194.46 -4.08 103,662,553,689.81 归属于上市公司股东的净利润 82,320,067,101.68 86,228,146,421.62 -4.53 74,734,071,550.75 归属于上市公司股东的扣除非 经常性损益的净利润 82,293,107,655.25 86,240,905,977",
        "normalized_provider_value": 85310324833.67,
        "normalized_official_value": 82320067101.68,
        "absolute_diff": 2990257731.9900055,
        "relative_diff": 0.03505153377179289,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "net_profit_parent"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "4 利润总额 114,755,261,605.08 119,638,578,194.46 -4.08 103,662,553,689.81 归属于上市公司股东的净利润 82,320,067,101.68 86,228,146,421.62 -4.53 74,734,071,550.75 归属于上市公司股东的扣除非 经常性损益的净利润 82,293,107,655.25 86,240,905,977",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 82320067101.68,
            "raw_unit": "元",
            "normalized_value": 82320067101.68,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 6,
            "table_scope_id": "p6#u153"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 85310324833.67,
              "original_unit": "CNY",
              "normalized_value": 85310324833.67,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 82320067101.68,
              "original_unit": "CNY",
              "normalized_value": 82320067101.68,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "net_profit_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": 2990257731.9900055,
              "relative_diff": 0.03505153377179289
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.039558+00:00",
        "updated_at": "2026-07-12T08:05:30.039563+00:00"
      },
      {
        "id": 4,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "cashflow_quality",
        "field_name": "operating_cashflow",
        "provider_name": "operating_cashflow",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "operating_cashflow",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 61522204989.35,
        "official_unit": "CNY",
        "official_definition": "经营活动产生的现金流量净额",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "经常性损益的净利润 82,293,107,655.25 86,240,905,977.42 -4.58 74,752,564,425.52 经营活动产生的现金流量净额 61,522,204,989.35 92,463,692,168.43 -33.46 66,593,247,721.09 2025年末 2024年末 本期末 比上年 同期末 增减（% ） 2023年末 归属于上市公司股东的净资产 2",
        "normalized_provider_value": null,
        "normalized_official_value": 61522204989.35,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "年报中有明确数据，但结构化数据缺失（null）。"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "operating_cashflow"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "经常性损益的净利润 82,293,107,655.25 86,240,905,977.42 -4.58 74,752,564,425.52 经营活动产生的现金流量净额 61,522,204,989.35 92,463,692,168.43 -33.46 66,593,247,721.09 2025年末 2024年末 本期末 比上年 同期末 增减（% ） 2023年末 归属于上市公司股东的净资产 2",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 61522204989.35,
            "raw_unit": "元",
            "normalized_value": 61522204989.35,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "合并现金流量表 / 主要会计数据",
            "evidence_page": 6,
            "table_scope_id": "p6#u153"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 61522204989.35,
              "original_unit": "CNY",
              "normalized_value": 61522204989.35,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "operating_cashflow",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.043835+00:00",
        "updated_at": "2026-07-12T08:05:30.043848+00:00"
      },
      {
        "id": 5,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_assets",
        "provider_name": "total_assets",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "total_assets",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 303834844021.44,
        "official_unit": "CNY",
        "official_definition": "总资产",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "司股东的净资产 244,637,811,032.18 233,105,984,399.47 4.95 215,668,571,607.43 总资产 303,834,844,021.44 298,944,579,918.70 1.64 272,699,660,092.25 股本 1,252,270,215.00 1,256,197,800.00 -0.31 1,256,197,800.00 (二) ",
        "normalized_provider_value": null,
        "normalized_official_value": 303834844021.44,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "年报中有明确数据，但结构化数据缺失（null）。"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "total_assets"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "司股东的净资产 244,637,811,032.18 233,105,984,399.47 4.95 215,668,571,607.43 总资产 303,834,844,021.44 298,944,579,918.70 1.64 272,699,660,092.25 股本 1,252,270,215.00 1,256,197,800.00 -0.31 1,256,197,800.00 (二) ",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 303834844021.44,
            "raw_unit": "元",
            "normalized_value": 303834844021.44,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "资产负债表 / 主要会计数据",
            "evidence_page": 6,
            "table_scope_id": "p6#u153"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 303834844021.44,
              "original_unit": "CNY",
              "normalized_value": 303834844021.44,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "total_assets",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.047287+00:00",
        "updated_at": "2026-07-12T08:05:30.047296+00:00"
      },
      {
        "id": 6,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "equity_parent",
        "provider_name": "equity_parent",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "equity_parent",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 244637811032.18,
        "official_unit": "CNY",
        "official_definition": "归属于母公司股东权益",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "8.43 -33.46 66,593,247,721.09 2025年末 2024年末 本期末 比上年 同期末 增减（% ） 2023年末 归属于上市公司股东的净资产 244,637,811,032.18 233,105,984,399.47 4.95 215,668,571,607.43 总资产 303,834,844,021.44 298,944,579,918.70 1.64 272,699",
        "normalized_provider_value": null,
        "normalized_official_value": 244637811032.18,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "年报中有明确数据，但结构化数据缺失（null）。"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "equity_parent"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "8.43 -33.46 66,593,247,721.09 2025年末 2024年末 本期末 比上年 同期末 增减（% ） 2023年末 归属于上市公司股东的净资产 244,637,811,032.18 233,105,984,399.47 4.95 215,668,571,607.43 总资产 303,834,844,021.44 298,944,579,918.70 1.64 272,699",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 244637811032.18,
            "raw_unit": "元",
            "normalized_value": 244637811032.18,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "资产负债表 / 主要会计数据",
            "evidence_page": 6,
            "table_scope_id": "p6#u153"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 244637811032.18,
              "original_unit": "CNY",
              "normalized_value": 244637811032.18,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "equity_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.050213+00:00",
        "updated_at": "2026-07-12T08:05:30.050219+00:00"
      },
      {
        "id": 7,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "eps_basic",
        "provider_name": "eps_basic",
        "provider_value": null,
        "provider_unit": "CNY/share",
        "provider_definition": "eps_basic",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 65.66,
        "official_unit": "CNY/share",
        "official_definition": "基本每股收益",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "31 1,256,197,800.00 (二) 主要财务指标 主要财务指标 2025年 2024年 本期比上年同期增 减(%) 2023年 基本每股收益（元／股） 65.66 68.64 -4.34 59.49 稀释每股收益（元／股） 65.66 68.64 -4.34 59.49 扣除非经常性损益后的基本每股 收益（元／股） 65.64 68.65 -4.38 59.51 加权平均净资产收益率（",
        "normalized_provider_value": null,
        "normalized_official_value": 65.66,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 0.01,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "年报中有明确数据，但结构化数据缺失（null）。"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "eps_basic"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "31 1,256,197,800.00 (二) 主要财务指标 主要财务指标 2025年 2024年 本期比上年同期增 减(%) 2023年 基本每股收益（元／股） 65.66 68.64 -4.34 59.49 稀释每股收益（元／股） 65.66 68.64 -4.34 59.49 扣除非经常性损益后的基本每股 收益（元／股） 65.64 68.65 -4.38 59.51 加权平均净资产收益率（",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 65.66,
            "raw_unit": null,
            "normalized_value": 65.66,
            "normalized_unit": "CNY/share",
            "unit_scale": 1.0,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 6,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY/share",
              "normalized_value": null,
              "normalized_unit": "CNY/share",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 65.66,
              "original_unit": "CNY/share",
              "normalized_value": 65.66,
              "normalized_unit": "CNY/share",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY/share→CNY/share",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "eps_basic",
              "absolute_tolerance": 0.01,
              "relative_tolerance": 0.005,
              "unit": "CNY/share",
              "basis": "eps",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.052932+00:00",
        "updated_at": "2026-07-12T08:05:30.052936+00:00"
      },
      {
        "id": 8,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "roe_weighted",
        "provider_name": "roeAvg",
        "provider_value": 34.462,
        "provider_unit": "%",
        "provider_definition": "roe",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 0.32530000000000003,
        "official_unit": "%",
        "official_definition": "加权平均净资产收益率",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "5.66 68.64 -4.34 59.49 扣除非经常性损益后的基本每股 收益（元／股） 65.64 68.65 -4.38 59.51 加权平均净资产收益率（%） 32.53 36.02 减少3.49个百分点 34.19 扣除非经常性损益后的加权平均 净资产收益率（%） 32.52 36.03 减少3.51个百分点 34.20 报告期末公司前三年主要会计数据和财务指标的说明 √适用 □不适用 ",
        "normalized_provider_value": 34.462,
        "normalized_official_value": 0.32530000000000003,
        "absolute_diff": 34.136700000000005,
        "relative_diff": 0.9905606174917301,
        "tolerance": 0.0005,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "roe_weighted"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "5.66 68.64 -4.34 59.49 扣除非经常性损益后的基本每股 收益（元／股） 65.64 68.65 -4.38 59.51 加权平均净资产收益率（%） 32.53 36.02 减少3.49个百分点 34.19 扣除非经常性损益后的加权平均 净资产收益率（%） 32.52 36.03 减少3.51个百分点 34.20 报告期末公司前三年主要会计数据和财务指标的说明 √适用 □不适用 ",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 32.53,
            "raw_unit": null,
            "normalized_value": 0.32530000000000003,
            "normalized_unit": "%",
            "unit_scale": 0.01,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 6,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 34.462,
              "original_unit": "%",
              "normalized_value": 34.462,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 0.32530000000000003,
              "original_unit": "%",
              "normalized_value": 0.32530000000000003,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "roe_weighted",
              "absolute_tolerance": 0.0005,
              "relative_tolerance": 0.005,
              "unit": "%",
              "basis": "percentage",
              "within_tolerance": false,
              "absolute_diff": 34.136700000000005,
              "relative_diff": 0.9905606174917301
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.055993+00:00",
        "updated_at": "2026-07-12T08:05:30.056000+00:00"
      },
      {
        "id": 9,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_share",
        "provider_name": "totalShare",
        "provider_value": 1252270215,
        "provider_unit": "shares",
        "provider_definition": "total_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 2025.0,
        "official_unit": "shares",
        "official_definition": "总股本",
        "official_period": "2026-03-31",
        "official_value_basis": "point_in_time",
        "official_page": 2,
        "official_chunk_id": null,
        "official_excerpt": "）蔡聪应\n声明：保证年度报告中财务报告的真实、准确、完整。\n五、 董事会决议通过的本报告期利润分配预案或公积金转增股本预案\n公司拟以实施权益分派股权登记日登记的总股本扣除回购专用账户中的股份为基数，实施\n2025年年度利润分配。2025年年度利润分配拟向全体股东每股派发现金红利27.993元（含税），\n截至2026年3月31日，公司总股本为1,252,270,215股，回购专用证券账户中的股份数为794,176\n股，总股本扣除回购专用证券账户中的股份数为1,251,476,039股，以此",
        "normalized_provider_value": 1252270215.0,
        "normalized_official_value": 2025.0,
        "absolute_diff": 1252268190.0,
        "relative_diff": 0.9999983829368648,
        "tolerance": 1.0,
        "fusion_status": "period_basis_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "与年报股本数据完全一致。",
          "period mismatch: provider=2025-12-31 official=2026-03-31"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "total_share"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "keyword",
            "page": 2,
            "chunk_id": null,
            "excerpt": "）蔡聪应\n声明：保证年度报告中财务报告的真实、准确、完整。\n五、 董事会决议通过的本报告期利润分配预案或公积金转增股本预案\n公司拟以实施权益分派股权登记日登记的总股本扣除回购专用账户中的股份为基数，实施\n2025年年度利润分配。2025年年度利润分配拟向全体股东每股派发现金红利27.993元（含税），\n截至2026年3月31日，公司总股本为1,252,270,215股，回购专用证券账户中的股份数为794,176\n股，总股本扣除回购专用证券账户中的股份数为1,251,476,039股，以此",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-17/1225114741.PDF",
            "raw_value": 2025.0,
            "raw_unit": "shares",
            "normalized_value": 2025.0,
            "normalized_unit": "shares",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": 2,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 1252270215,
              "original_unit": "shares",
              "normalized_value": 1252270215.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 2025.0,
              "original_unit": "shares",
              "normalized_value": 2025.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "total_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": false,
              "absolute_diff": 1252268190.0,
              "relative_diff": 0.9999983829368648
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.059310+00:00",
        "updated_at": "2026-07-12T08:05:30.059317+00:00"
      },
      {
        "id": 10,
        "market": "CN",
        "symbol": "600519",
        "report_id": 2,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "float_share",
        "provider_name": "liqaShare",
        "provider_value": 1252270215,
        "provider_unit": "shares",
        "provider_definition": "float_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": null,
        "official_unit": null,
        "official_definition": "流通股本",
        "official_period": null,
        "official_value_basis": "point_in_time",
        "official_page": null,
        "official_chunk_id": null,
        "official_excerpt": null,
        "normalized_provider_value": 1252270215.0,
        "normalized_official_value": null,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "insufficient_evidence",
        "confidence": 0.5,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "unit not safely convertible",
          "年报摘录中未找到明确流通股本数据，结构化值为1,252,270,215，与总股本相同，需人工确认是否全流通。",
          "official field not found in selected report",
          "official evidence not sufficient"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_600519_ai_official_verification_phase6tj.json",
            "field_name": "float_share"
          },
          "official": {
            "status": "insufficient_evidence",
            "retrieval_mode": "keyword",
            "page": null,
            "chunk_id": null,
            "excerpt": null,
            "source_url": null,
            "raw_value": null,
            "raw_unit": null,
            "normalized_value": null,
            "normalized_unit": "shares",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": null,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": false,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence",
              "unit not safely convertible"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 1252270215,
              "original_unit": "shares",
              "normalized_value": 1252270215.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": null,
              "original_unit": null,
              "normalized_value": null,
              "normalized_unit": "shares",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "tolerance": {
              "field_name": "float_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:30.064740+00:00",
        "updated_at": "2026-07-12T08:05:30.064747+00:00"
      }
    ],
    "warnings": [],
    "timeout": false,
    "blocking_issues": [],
    "citation_complete": true,
    "source_trace_complete": true
  },
  {
    "symbol": "300750",
    "report_id": 3,
    "report_year": 2025,
    "report_type": "annual",
    "report_title": "宁德时代：2025年年度报告",
    "status": null,
    "final_status": "passed",
    "ok": true,
    "cache_hit": false,
    "elapsed_ms": 29367.08,
    "timings": {
      "eligibility_latency_ms": 0.05,
      "cache_lookup_latency_ms": 0.0,
      "resolver_latency_ms": 68.53,
      "retrieval_latency_ms": 68.53,
      "alignment_latency_ms": 0.56,
      "persistence_latency_ms": 0.37,
      "computed_latency_ms": 69.48,
      "total_latency_ms": 12823.07,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0
    },
    "summary": {
      "fields_total": 10,
      "verified": 1,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 3,
      "period_basis_mismatch": 1,
      "unit_mismatch": 0,
      "value_conflict": 0,
      "structured_field_missing": 4,
      "official_field_not_found": 0,
      "insufficient_evidence": 1,
      "not_applicable": 0,
      "failed": 0
    },
    "fields": [
      {
        "id": 1,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "revenue",
        "provider_name": "MBRevenue",
        "provider_value": 423701834000,
        "provider_unit": "CNY",
        "provider_definition": "main_business_revenue",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 423701834000.0,
        "official_unit": "CNY",
        "official_definition": "营业收入",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 11,
        "official_chunk_id": null,
        "official_excerpt": "标 公司是否需追溯调整或重述以前年度会计数据 □是 否 单位：千元 项目 2025年 2024年 本年比上年增减 2023年 营业收入 423,701,834 362,012,554 17.04% 400,917,045 归属于上市公司股东 的净利润 72,201,282 50,744,682 42.28% 44,121,248 归属于上市公司股东 的扣除非经常性损益 的净利润 64,507,8",
        "normalized_provider_value": 423701834000.0,
        "normalized_official_value": 423701834000.0,
        "absolute_diff": 0.0,
        "relative_diff": 0.0,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "Structured revenue matches official 2025 annual revenue of 423,701,834 thousand yuan.",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "revenue"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 11,
            "chunk_id": null,
            "excerpt": "标 公司是否需追溯调整或重述以前年度会计数据 □是 否 单位：千元 项目 2025年 2024年 本年比上年增减 2023年 营业收入 423,701,834 362,012,554 17.04% 400,917,045 归属于上市公司股东 的净利润 72,201,282 50,744,682 42.28% 44,121,248 归属于上市公司股东 的扣除非经常性损益 的净利润 64,507,8",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 423701834.0,
            "raw_unit": "千元",
            "normalized_value": 423701834000.0,
            "normalized_unit": "CNY",
            "unit_scale": 1000.0,
            "unit_source": "table_level",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 11,
            "table_scope_id": "p11#u230"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 423701834000,
              "original_unit": "CNY",
              "normalized_value": 423701834000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 423701834000.0,
              "original_unit": "CNY",
              "normalized_value": 423701834000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "revenue",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": true,
              "absolute_diff": 0.0,
              "relative_diff": 0.0
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.922849+00:00",
        "updated_at": "2026-07-12T08:05:59.922861+00:00"
      },
      {
        "id": 2,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit",
        "provider_name": "netProfit",
        "provider_value": 76786309000,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 76786309000.0,
        "official_unit": "CNY",
        "official_definition": "净利润",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 200,
        "official_chunk_id": null,
        "official_excerpt": "、现金流量表补充资料 （1）现金流量表补充资料 单位：千元 补充资料 本期金额 上期金额 1.将净利润调节为经营活动现金流量 净利润 76,786,309 54,006,794 加：资产减值准备 8,660,164 8,423,325",
        "normalized_provider_value": 76786309000.0,
        "normalized_official_value": 76786309000.0,
        "absolute_diff": 0.0,
        "relative_diff": 0.0,
        "tolerance": 1.0,
        "fusion_status": "verified",
        "confidence": 1.0,
        "warnings_json": [
          "Official net profit matches structured value exactly."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "net_profit"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 200,
            "chunk_id": null,
            "excerpt": "、现金流量表补充资料 （1）现金流量表补充资料 单位：千元 补充资料 本期金额 上期金额 1.将净利润调节为经营活动现金流量 净利润 76,786,309 54,006,794 加：资产减值准备 8,660,164 8,423,325",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 76786309.0,
            "raw_unit": "千元",
            "normalized_value": 76786309000.0,
            "normalized_unit": "CNY",
            "unit_scale": 1000.0,
            "unit_source": "table_level",
            "table_title": "合并利润表",
            "evidence_page": 200,
            "table_scope_id": "p200#u738"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": true,
            "status": "comparable",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 76786309000,
              "original_unit": "CNY",
              "normalized_value": 76786309000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 76786309000.0,
              "original_unit": "CNY",
              "normalized_value": 76786309000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "net_profit",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": true,
              "absolute_diff": 0.0,
              "relative_diff": 0.0
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.931392+00:00",
        "updated_at": "2026-07-12T08:05:59.931400+00:00"
      },
      {
        "id": 3,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit_parent",
        "provider_name": "netProfit",
        "provider_value": 76786309000,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 72201282000.0,
        "official_unit": "CNY",
        "official_definition": "归属于母公司股东的净利润",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 11,
        "official_chunk_id": null,
        "official_excerpt": "营业收入 423,701,834 362,012,554 17.04% 400,917,045 归属于上市公司股东 的净利润 72,201,282 50,744,682 42.28% 44,121,248 归属于上市公司股东 的扣除非经常性损益 的净利润 64,507,864 44,992,919 43.37% 40,091,674 经营活动产生的现金 流量净额 133,219,982",
        "normalized_provider_value": 76786309000.0,
        "normalized_official_value": 72201282000.0,
        "absolute_diff": 4585027000.0,
        "relative_diff": 0.05971151706224087,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.3,
        "warnings_json": [
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "net_profit_parent"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 11,
            "chunk_id": null,
            "excerpt": "营业收入 423,701,834 362,012,554 17.04% 400,917,045 归属于上市公司股东 的净利润 72,201,282 50,744,682 42.28% 44,121,248 归属于上市公司股东 的扣除非经常性损益 的净利润 64,507,864 44,992,919 43.37% 40,091,674 经营活动产生的现金 流量净额 133,219,982",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 72201282.0,
            "raw_unit": "千元",
            "normalized_value": 72201282000.0,
            "normalized_unit": "CNY",
            "unit_scale": 1000.0,
            "unit_source": "table_level",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 11,
            "table_scope_id": "p11#u230"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 76786309000,
              "original_unit": "CNY",
              "normalized_value": 76786309000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 72201282000.0,
              "original_unit": "CNY",
              "normalized_value": 72201282000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "net_profit_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": 4585027000.0,
              "relative_diff": 0.05971151706224087
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.938545+00:00",
        "updated_at": "2026-07-12T08:05:59.938549+00:00"
      },
      {
        "id": 4,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "cashflow_quality",
        "field_name": "operating_cashflow",
        "provider_name": "operating_cashflow",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "operating_cashflow",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 133219982000.0,
        "official_unit": "CNY",
        "official_definition": "经营活动产生的现金流量净额",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 11,
        "official_chunk_id": null,
        "official_excerpt": "归属于上市公司股东 的扣除非经常性损益 的净利润 64,507,864 44,992,919 43.37% 40,091,674 经营活动产生的现金 流量净额 133,219,982 96,990,345 37.35% 92,826,124 基本每股收益（元/ 股） 16.14 11.58 39.38% 10.06 稀释每股收益（元/ 股） 16.14 11.58 39.38% 10.05 加权平",
        "normalized_provider_value": null,
        "normalized_official_value": 133219982000.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "Official value 133,219,982 thousand yuan is present in annual report but structured field is missing (STRUCTURED_ANNUAL_ROW_NOT_FOUND)."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "operating_cashflow"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 11,
            "chunk_id": null,
            "excerpt": "归属于上市公司股东 的扣除非经常性损益 的净利润 64,507,864 44,992,919 43.37% 40,091,674 经营活动产生的现金 流量净额 133,219,982 96,990,345 37.35% 92,826,124 基本每股收益（元/ 股） 16.14 11.58 39.38% 10.06 稀释每股收益（元/ 股） 16.14 11.58 39.38% 10.05 加权平",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 133219982.0,
            "raw_unit": "千元",
            "normalized_value": 133219982000.0,
            "normalized_unit": "CNY",
            "unit_scale": 1000.0,
            "unit_source": "table_level",
            "table_title": "合并现金流量表 / 主要会计数据",
            "evidence_page": 11,
            "table_scope_id": "p11#u230"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 133219982000.0,
              "original_unit": "CNY",
              "normalized_value": 133219982000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "operating_cashflow",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.944903+00:00",
        "updated_at": "2026-07-12T08:05:59.944906+00:00"
      },
      {
        "id": 5,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_assets",
        "provider_name": "total_assets",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "total_assets",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 974827544000.0,
        "official_unit": "CNY",
        "official_definition": "总资产",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 11,
        "official_chunk_id": null,
        "official_excerpt": "资产收益 率 24.91% 24.13% 0.78% 24.04% 项目 2025年末 2024年末 本年末比上年末增减 2023年末 资产总额 974,827,544 786,658,123 23.92% 717,168,041 归属于上市公司股东 的净资产 337,107,747 246,930,033 36.52% 197,708,052 公司最近三个会计年度扣除非经常性损益前后净利润孰低者",
        "normalized_provider_value": null,
        "normalized_official_value": 974827544000.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "Official value 974,827,544 thousand yuan is present in annual report but structured field is missing."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "total_assets"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 11,
            "chunk_id": null,
            "excerpt": "资产收益 率 24.91% 24.13% 0.78% 24.04% 项目 2025年末 2024年末 本年末比上年末增减 2023年末 资产总额 974,827,544 786,658,123 23.92% 717,168,041 归属于上市公司股东 的净资产 337,107,747 246,930,033 36.52% 197,708,052 公司最近三个会计年度扣除非经常性损益前后净利润孰低者",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 974827544.0,
            "raw_unit": "千元",
            "normalized_value": 974827544000.0,
            "normalized_unit": "CNY",
            "unit_scale": 1000.0,
            "unit_source": "table_level",
            "table_title": "资产负债表 / 主要会计数据",
            "evidence_page": 11,
            "table_scope_id": "p11#u230"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 974827544000.0,
              "original_unit": "CNY",
              "normalized_value": 974827544000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "total_assets",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.950548+00:00",
        "updated_at": "2026-07-12T08:05:59.950551+00:00"
      },
      {
        "id": 6,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "equity_parent",
        "provider_name": "equity_parent",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "equity_parent",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 337107747000.0,
        "official_unit": "CNY",
        "official_definition": "归属于母公司股东权益",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 11,
        "official_chunk_id": null,
        "official_excerpt": "本年末比上年末增减 2023年末 资产总额 974,827,544 786,658,123 23.92% 717,168,041 归属于上市公司股东 的净资产 337,107,747 246,930,033 36.52% 197,708,052 公司最近三个会计年度扣除非经常性损益前后净利润孰低者均为负值，且最近一年审计报告显示公司持续经营能力存在不 确定性 □是 否 公司报告期内经审计利润总额",
        "normalized_provider_value": null,
        "normalized_official_value": 337107747000.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.0,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "no comparable official or structured value"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "equity_parent"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 11,
            "chunk_id": null,
            "excerpt": "本年末比上年末增减 2023年末 资产总额 974,827,544 786,658,123 23.92% 717,168,041 归属于上市公司股东 的净资产 337,107,747 246,930,033 36.52% 197,708,052 公司最近三个会计年度扣除非经常性损益前后净利润孰低者均为负值，且最近一年审计报告显示公司持续经营能力存在不 确定性 □是 否 公司报告期内经审计利润总额",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 337107747.0,
            "raw_unit": "千元",
            "normalized_value": 337107747000.0,
            "normalized_unit": "CNY",
            "unit_scale": 1000.0,
            "unit_source": "table_level",
            "table_title": "资产负债表 / 主要会计数据",
            "evidence_page": 11,
            "table_scope_id": "p11#u230"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 337107747000.0,
              "original_unit": "CNY",
              "normalized_value": 337107747000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "equity_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.955995+00:00",
        "updated_at": "2026-07-12T08:05:59.956000+00:00"
      },
      {
        "id": 7,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "eps_basic",
        "provider_name": "eps_basic",
        "provider_value": null,
        "provider_unit": "CNY/share",
        "provider_definition": "eps_basic",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 16.14,
        "official_unit": "CNY/share",
        "official_definition": "基本每股收益",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 11,
        "official_chunk_id": null,
        "official_excerpt": "091,674 经营活动产生的现金 流量净额 133,219,982 96,990,345 37.35% 92,826,124 基本每股收益（元/ 股） 16.14 11.58 39.38% 10.06 稀释每股收益（元/ 股） 16.14 11.58 39.38% 10.05 加权平均净资产收益 率 24.91% 24.13% 0.78% 24.04% 项目 2025年末 2024年末 本年末比",
        "normalized_provider_value": null,
        "normalized_official_value": 16.14,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 0.01,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "Official basic EPS is 16.14 yuan per share but structured field is missing (STRUCTURED_ANNUAL_ROW_NOT_FOUND)."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "eps_basic"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 11,
            "chunk_id": null,
            "excerpt": "091,674 经营活动产生的现金 流量净额 133,219,982 96,990,345 37.35% 92,826,124 基本每股收益（元/ 股） 16.14 11.58 39.38% 10.06 稀释每股收益（元/ 股） 16.14 11.58 39.38% 10.05 加权平均净资产收益 率 24.91% 24.13% 0.78% 24.04% 项目 2025年末 2024年末 本年末比",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 16.14,
            "raw_unit": null,
            "normalized_value": 16.14,
            "normalized_unit": "CNY/share",
            "unit_scale": 1.0,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 11,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY/share",
              "normalized_value": null,
              "normalized_unit": "CNY/share",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 16.14,
              "original_unit": "CNY/share",
              "normalized_value": 16.14,
              "normalized_unit": "CNY/share",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY/share→CNY/share",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "eps_basic",
              "absolute_tolerance": 0.01,
              "relative_tolerance": 0.005,
              "unit": "CNY/share",
              "basis": "eps",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.961404+00:00",
        "updated_at": "2026-07-12T08:05:59.961407+00:00"
      },
      {
        "id": 8,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "roe_weighted",
        "provider_name": "roeAvg",
        "provider_value": 0.247249,
        "provider_unit": "%",
        "provider_definition": "roe",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 0.24910000000000002,
        "official_unit": "%",
        "official_definition": "加权平均净资产收益率",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 11,
        "official_chunk_id": null,
        "official_excerpt": "16.14 11.58 39.38% 10.06 稀释每股收益（元/ 股） 16.14 11.58 39.38% 10.05 加权平均净资产收益 率 24.91% 24.13% 0.78% 24.04% 项目 2025年末 2024年末 本年末比上年末增减 2023年末 资产总额 974,827,544 786,658,123 23.92% 717,168,041 归属于上市公司股东 的净资产 3",
        "normalized_provider_value": 0.247249,
        "normalized_official_value": 0.24910000000000002,
        "absolute_diff": 0.0018510000000000193,
        "relative_diff": 0.007430750702529181,
        "tolerance": 0.0005,
        "fusion_status": "definition_mismatch",
        "confidence": 0.5,
        "warnings_json": [
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "roe_weighted"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 11,
            "chunk_id": null,
            "excerpt": "16.14 11.58 39.38% 10.06 稀释每股收益（元/ 股） 16.14 11.58 39.38% 10.05 加权平均净资产收益 率 24.91% 24.13% 0.78% 24.04% 项目 2025年末 2024年末 本年末比上年末增减 2023年末 资产总额 974,827,544 786,658,123 23.92% 717,168,041 归属于上市公司股东 的净资产 3",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 24.91,
            "raw_unit": null,
            "normalized_value": 0.24910000000000002,
            "normalized_unit": "%",
            "unit_scale": 0.01,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 11,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 0.247249,
              "original_unit": "%",
              "normalized_value": 0.247249,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 0.24910000000000002,
              "original_unit": "%",
              "normalized_value": 0.24910000000000002,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "roe_weighted",
              "absolute_tolerance": 0.0005,
              "relative_tolerance": 0.005,
              "unit": "%",
              "basis": "percentage",
              "within_tolerance": false,
              "absolute_diff": 0.0018510000000000193,
              "relative_diff": 0.007430750702529181
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.966309+00:00",
        "updated_at": "2026-07-12T08:05:59.966311+00:00"
      },
      {
        "id": 9,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_share",
        "provider_name": "totalShare",
        "provider_value": 4563803488,
        "provider_unit": "shares",
        "provider_definition": "total_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 15991524.0,
        "official_unit": "股",
        "official_definition": "总股本",
        "official_period": "2025-03-13",
        "official_value_basis": "point_in_time",
        "official_page": 57,
        "official_chunk_id": null,
        "official_excerpt": "2024年年度\n股东会审议通过了《关于<2024年度利润分配预案>的议案》 ，并于2025年 4月 15日披露《2024年\n年度权益分派实施公告》 ，以公司当时总股本剔除已回购股份15,991,524股后的 4,387,403,387股为\n基数，向全体股东每 10股派发现金分红 45.53元（含税） 。 ",
        "normalized_provider_value": 4563803488.0,
        "normalized_official_value": 15991524.0,
        "absolute_diff": 4547811964.0,
        "relative_diff": 0.996496009514422,
        "tolerance": 1.0,
        "fusion_status": "period_basis_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "Official total shares 4,563,803,488 matches structured value exactly.",
          "period mismatch: provider=2025-12-31 official=2025-03-13"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "total_share"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "keyword",
            "page": 57,
            "chunk_id": null,
            "excerpt": "2024年年度\n股东会审议通过了《关于<2024年度利润分配预案>的议案》 ，并于2025年 4月 15日披露《2024年\n年度权益分派实施公告》 ，以公司当时总股本剔除已回购股份15,991,524股后的 4,387,403,387股为\n基数，向全体股东每 10股派发现金分红 45.53元（含税） 。 ",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-10/1225002214.PDF",
            "raw_value": 15991524.0,
            "raw_unit": "股",
            "normalized_value": 15991524.0,
            "normalized_unit": "shares",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": 57,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 4563803488,
              "original_unit": "shares",
              "normalized_value": 4563803488.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 15991524.0,
              "original_unit": "股",
              "normalized_value": 15991524.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "股→shares",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "total_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": false,
              "absolute_diff": 4547811964.0,
              "relative_diff": 0.996496009514422
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.971955+00:00",
        "updated_at": "2026-07-12T08:05:59.971957+00:00"
      },
      {
        "id": 10,
        "market": "CN",
        "symbol": "300750",
        "report_id": 3,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "float_share",
        "provider_name": "liqaShare",
        "provider_value": 4256573358,
        "provider_unit": "shares",
        "provider_definition": "float_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": null,
        "official_unit": null,
        "official_definition": "流通股本",
        "official_period": null,
        "official_value_basis": "point_in_time",
        "official_page": null,
        "official_chunk_id": null,
        "official_excerpt": null,
        "normalized_provider_value": 4256573358.0,
        "normalized_official_value": null,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "insufficient_evidence",
        "confidence": 0.0,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "unit not safely convertible",
          "No candidate excerpt provided for float_share; official value cannot be verified. Structured value exists but cannot be confirmed.",
          "official field not found in selected report",
          "official evidence not sufficient"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_300750_ai_official_verification_phase6tj.json",
            "field_name": "float_share"
          },
          "official": {
            "status": "insufficient_evidence",
            "retrieval_mode": "keyword",
            "page": null,
            "chunk_id": null,
            "excerpt": null,
            "source_url": null,
            "raw_value": null,
            "raw_unit": null,
            "normalized_value": null,
            "normalized_unit": "shares",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": null,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": false,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence",
              "unit not safely convertible"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 4256573358,
              "original_unit": "shares",
              "normalized_value": 4256573358.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": null,
              "original_unit": null,
              "normalized_value": null,
              "normalized_unit": "shares",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "tolerance": {
              "field_name": "float_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:05:59.979937+00:00",
        "updated_at": "2026-07-12T08:05:59.979939+00:00"
      }
    ],
    "warnings": [],
    "timeout": false,
    "blocking_issues": [],
    "citation_complete": true,
    "source_trace_complete": true
  },
  {
    "symbol": "000725",
    "report_id": 4,
    "report_year": 2025,
    "report_type": "annual",
    "report_title": "京东方Ａ：2025年年度报告",
    "status": null,
    "final_status": "passed",
    "ok": true,
    "cache_hit": false,
    "elapsed_ms": 30749.7,
    "timings": {
      "eligibility_latency_ms": 0.04,
      "cache_lookup_latency_ms": 0.0,
      "resolver_latency_ms": 87.05,
      "retrieval_latency_ms": 87.05,
      "alignment_latency_ms": 0.48,
      "persistence_latency_ms": 0.38,
      "computed_latency_ms": 87.93,
      "total_latency_ms": 11523.81,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0
    },
    "summary": {
      "fields_total": 10,
      "verified": 0,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 3,
      "period_basis_mismatch": 2,
      "unit_mismatch": 1,
      "value_conflict": 0,
      "structured_field_missing": 4,
      "official_field_not_found": 0,
      "insufficient_evidence": 0,
      "not_applicable": 0,
      "failed": 0
    },
    "fields": [
      {
        "id": 1,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "revenue",
        "provider_name": "MBRevenue",
        "provider_value": 204590222888.0,
        "provider_unit": "CNY",
        "provider_definition": "main_business_revenue",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 50598933939.0,
        "official_unit": "CNY",
        "official_definition": "营业收入",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 13,
        "official_chunk_id": null,
        "official_excerpt": "与按照中国会计准则披露的财务报告中净利润和净资产差异情况。 八、分季度主要财务指标 单位：元 项目 第一季度 第二季度 第三季度 第四季度 营业收入 50,598,933,939.00 50,679,248,196.00 53,269,817,390.00 50,042,223,363.00 归属于上市公司股东的净利润 1,613,999,380.00 1,632,886,399.00 1,354",
        "normalized_provider_value": 204590222888.0,
        "normalized_official_value": 50598933939.0,
        "absolute_diff": 153991288949.0,
        "relative_diff": 0.7526815640320229,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "within tolerance",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "revenue"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 13,
            "chunk_id": null,
            "excerpt": "与按照中国会计准则披露的财务报告中净利润和净资产差异情况。 八、分季度主要财务指标 单位：元 项目 第一季度 第二季度 第三季度 第四季度 营业收入 50,598,933,939.00 50,679,248,196.00 53,269,817,390.00 50,042,223,363.00 归属于上市公司股东的净利润 1,613,999,380.00 1,632,886,399.00 1,354",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 50598933939.0,
            "raw_unit": "元",
            "normalized_value": 50598933939.0,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 13,
            "table_scope_id": "p13#u138"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 204590222888.0,
              "original_unit": "CNY",
              "normalized_value": 204590222888.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 50598933939.0,
              "original_unit": "CNY",
              "normalized_value": 50598933939.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "revenue",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": 153991288949.0,
              "relative_diff": 0.7526815640320229
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.557147+00:00",
        "updated_at": "2026-07-12T08:06:30.557156+00:00"
      },
      {
        "id": 2,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit",
        "provider_name": "netProfit",
        "provider_value": 5027373569.0,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 5027373569.0,
        "official_unit": null,
        "official_definition": "净利润",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 100,
        "official_chunk_id": null,
        "official_excerpt": "利润总额 7,034,201,130 5,085,653,633 减：所得税费用 61 2,006,827,561 940,379,751 净利润 5,027,373,569 4,145,273,882 按经营持续性分类 持续经营净利润 5,027,373,569 4,145,273,882 后附财务报表附注为本财务报表的组成部分",
        "normalized_provider_value": 5027373569.0,
        "normalized_official_value": 5027373569.0,
        "absolute_diff": 0.0,
        "relative_diff": 0.0,
        "tolerance": 1.0,
        "fusion_status": "unit_mismatch",
        "confidence": 0.0,
        "warnings_json": [
          "unit not safely convertible",
          "no explicit net profit figure found in excerpts; cannot verify directly",
          "official unit context missing/unknown — value comparison refused (no default 元 guess)"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "net_profit"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 100,
            "chunk_id": null,
            "excerpt": "利润总额 7,034,201,130 5,085,653,633 减：所得税费用 61 2,006,827,561 940,379,751 净利润 5,027,373,569 4,145,273,882 按经营持续性分类 持续经营净利润 5,027,373,569 4,145,273,882 后附财务报表附注为本财务报表的组成部分",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 5027373569.0,
            "raw_unit": null,
            "normalized_value": 5027373569.0,
            "normalized_unit": "CNY",
            "unit_scale": null,
            "unit_source": "unknown",
            "table_title": "合并利润表",
            "evidence_page": 100,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": true,
            "unit_convertible": false,
            "comparable": false,
            "status": "unit_mismatch",
            "warnings": [
              "unit not safely convertible"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 5027373569.0,
              "original_unit": "CNY",
              "normalized_value": 5027373569.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 5027373569.0,
              "original_unit": null,
              "normalized_value": 5027373569.0,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "unknown_unit",
              "warnings": [
                "unknown_unit"
              ]
            },
            "tolerance": {
              "field_name": "net_profit",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": true,
              "absolute_diff": 0.0,
              "relative_diff": 0.0
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.568105+00:00",
        "updated_at": "2026-07-12T08:06:30.568112+00:00"
      },
      {
        "id": 3,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit_parent",
        "provider_name": "netProfit",
        "provider_value": 5027373569.0,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 1613999380.0,
        "official_unit": "CNY",
        "official_definition": "归属于母公司股东的净利润",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 13,
        "official_chunk_id": null,
        "official_excerpt": ",598,933,939.00 50,679,248,196.00 53,269,817,390.00 50,042,223,363.00 归属于上市公司股东的净利润 1,613,999,380.00 1,632,886,399.00 1,354,611,315.00 1,255,469,660.00 归属于上市公司股东的扣除非 经常性损益的净利润 1,351,864,713.00 930,371",
        "normalized_provider_value": 5027373569.0,
        "normalized_official_value": 1613999380.0,
        "absolute_diff": 3413374189.0,
        "relative_diff": 0.6789577384994204,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.3,
        "warnings_json": [
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "net_profit_parent"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 13,
            "chunk_id": null,
            "excerpt": ",598,933,939.00 50,679,248,196.00 53,269,817,390.00 50,042,223,363.00 归属于上市公司股东的净利润 1,613,999,380.00 1,632,886,399.00 1,354,611,315.00 1,255,469,660.00 归属于上市公司股东的扣除非 经常性损益的净利润 1,351,864,713.00 930,371",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 1613999380.0,
            "raw_unit": "元",
            "normalized_value": 1613999380.0,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 13,
            "table_scope_id": "p13#u138"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 5027373569.0,
              "original_unit": "CNY",
              "normalized_value": 5027373569.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 1613999380.0,
              "original_unit": "CNY",
              "normalized_value": 1613999380.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "net_profit_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": 3413374189.0,
              "relative_diff": 0.6789577384994204
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.577519+00:00",
        "updated_at": "2026-07-12T08:06:30.577522+00:00"
      },
      {
        "id": 4,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "cashflow_quality",
        "field_name": "operating_cashflow",
        "provider_name": "operating_cashflow",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "operating_cashflow",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 13743795736.0,
        "official_unit": "CNY",
        "official_definition": "经营活动产生的现金流量净额",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 13,
        "official_chunk_id": null,
        "official_excerpt": "益的净利润 1,351,864,713.00 930,371,818.00 896,919,685.00 1,051,183,309.00 经营活动产生的现金流量净额 13,743,795,736.00 8,992,511,350.00 14,038,311,177.00 12,049,937,411.00 上述财务指标或其加总数是否与公司已披露季度报告、半年度报告相关财务指标存在重大差异 □是 ",
        "normalized_provider_value": null,
        "normalized_official_value": 13743795736.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "structured field not found in company_v2_annual_history"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "operating_cashflow"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 13,
            "chunk_id": null,
            "excerpt": "益的净利润 1,351,864,713.00 930,371,818.00 896,919,685.00 1,051,183,309.00 经营活动产生的现金流量净额 13,743,795,736.00 8,992,511,350.00 14,038,311,177.00 12,049,937,411.00 上述财务指标或其加总数是否与公司已披露季度报告、半年度报告相关财务指标存在重大差异 □是 ",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 13743795736.0,
            "raw_unit": "元",
            "normalized_value": 13743795736.0,
            "normalized_unit": "CNY",
            "unit_scale": 1.0,
            "unit_source": "table_level",
            "table_title": "合并现金流量表 / 主要会计数据",
            "evidence_page": 13,
            "table_scope_id": "p13#u138"
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 13743795736.0,
              "original_unit": "CNY",
              "normalized_value": 13743795736.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "operating_cashflow",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.585949+00:00",
        "updated_at": "2026-07-12T08:06:30.585951+00:00"
      },
      {
        "id": 5,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_assets",
        "provider_name": "total_assets",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "total_assets",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 436378322803.0,
        "official_unit": null,
        "official_definition": "总资产",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 97,
        "official_chunk_id": null,
        "official_excerpt": "15,231,258,913 18,991,222,545 非流动资产合计 294,502,505,023 286,590,766,167 资产总计 436,378,322,803 429,978,221,541 后附财务报表附注为本财务报表的组成部分",
        "normalized_provider_value": null,
        "normalized_official_value": 436378322803.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "unit not safely convertible",
          "structured field not found in any source"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "total_assets"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 97,
            "chunk_id": null,
            "excerpt": "15,231,258,913 18,991,222,545 非流动资产合计 294,502,505,023 286,590,766,167 资产总计 436,378,322,803 429,978,221,541 后附财务报表附注为本财务报表的组成部分",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 436378322803.0,
            "raw_unit": null,
            "normalized_value": 436378322803.0,
            "normalized_unit": "CNY",
            "unit_scale": null,
            "unit_source": "unknown",
            "table_title": "资产负债表 / 主要会计数据",
            "evidence_page": 97,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": false,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence",
              "unit not safely convertible"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 436378322803.0,
              "original_unit": null,
              "normalized_value": 436378322803.0,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "unknown_unit",
              "warnings": [
                "unknown_unit"
              ]
            },
            "tolerance": {
              "field_name": "total_assets",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.593618+00:00",
        "updated_at": "2026-07-12T08:06:30.593620+00:00"
      },
      {
        "id": 6,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "equity_parent",
        "provider_name": "equity_parent",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "equity_parent",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 37645016203.0,
        "official_unit": null,
        "official_definition": "归属于上市公司股东的净资产",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 102,
        "official_chunk_id": null,
        "official_excerpt": "京东方科技集团股份有限公司\n合并股东权益变动表\n2025年度 人民币元\n102\n2025年度\n归属于母公司股东权益 少数股东权益 股东权益合计\n股本 其他权益工具 资本公积 减：库存股 其他综合收益 专项储备 盈余公积 未分配利润 小计\n一、 本年年初余额 37,645,016,203 2,043,402,946 52,207,573,706 1,216,490,683 (1,171,823,864) 139,227,664 3,879,754,479 39,410,894,857 132,937,555,308 71,6",
        "normalized_provider_value": null,
        "normalized_official_value": 37645016203.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "unit not safely convertible",
          "structured field not found in any source"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "equity_parent"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "keyword",
            "page": 102,
            "chunk_id": null,
            "excerpt": "京东方科技集团股份有限公司\n合并股东权益变动表\n2025年度 人民币元\n102\n2025年度\n归属于母公司股东权益 少数股东权益 股东权益合计\n股本 其他权益工具 资本公积 减：库存股 其他综合收益 专项储备 盈余公积 未分配利润 小计\n一、 本年年初余额 37,645,016,203 2,043,402,946 52,207,573,706 1,216,490,683 (1,171,823,864) 139,227,664 3,879,754,479 39,410,894,857 132,937,555,308 71,6",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 37645016203.0,
            "raw_unit": null,
            "normalized_value": 37645016203.0,
            "normalized_unit": "CNY",
            "unit_scale": null,
            "unit_source": "unknown",
            "table_title": null,
            "evidence_page": 102,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": false,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence",
              "unit not safely convertible"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 37645016203.0,
              "original_unit": null,
              "normalized_value": 37645016203.0,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "unknown_unit",
              "warnings": [
                "unknown_unit"
              ]
            },
            "tolerance": {
              "field_name": "equity_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.601643+00:00",
        "updated_at": "2026-07-12T08:06:30.601647+00:00"
      },
      {
        "id": 7,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "eps_basic",
        "provider_name": "eps_basic",
        "provider_value": null,
        "provider_unit": "CNY/share",
        "provider_definition": "eps_basic",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 0.16,
        "official_unit": "CNY/share",
        "official_definition": "基本每股收益",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 12,
        "official_chunk_id": null,
        "official_excerpt": "现金流量净额（元） 48,824,555,674.00 47,737,577,379.00 2.28% 38,301,826,884.00 基本每股收益（元/股） 0.16 0.14 14.29% 0.06 稀释每股收益（元/股） 0.16 0.14 14.29% 0.06 加权平均净资产收益率 4.39% 4.05% 0.34% 1.89% 项目 2025 年末 2024 年末 本年末比上 年末",
        "normalized_provider_value": null,
        "normalized_official_value": 0.16,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 0.01,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "structured field not found in company_v2_annual_history"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "eps_basic"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 12,
            "chunk_id": null,
            "excerpt": "现金流量净额（元） 48,824,555,674.00 47,737,577,379.00 2.28% 38,301,826,884.00 基本每股收益（元/股） 0.16 0.14 14.29% 0.06 稀释每股收益（元/股） 0.16 0.14 14.29% 0.06 加权平均净资产收益率 4.39% 4.05% 0.34% 1.89% 项目 2025 年末 2024 年末 本年末比上 年末",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 0.16,
            "raw_unit": null,
            "normalized_value": 0.16,
            "normalized_unit": "CNY/share",
            "unit_scale": 1.0,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 12,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY/share",
              "normalized_value": null,
              "normalized_unit": "CNY/share",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 0.16,
              "original_unit": "CNY/share",
              "normalized_value": 0.16,
              "normalized_unit": "CNY/share",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY/share→CNY/share",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "eps_basic",
              "absolute_tolerance": 0.01,
              "relative_tolerance": 0.005,
              "unit": "CNY/share",
              "basis": "eps",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.608941+00:00",
        "updated_at": "2026-07-12T08:06:30.608944+00:00"
      },
      {
        "id": 8,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "roe_weighted",
        "provider_name": "roeAvg",
        "provider_value": 0.043804,
        "provider_unit": "%",
        "provider_definition": "roe",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 0.043899999999999995,
        "official_unit": "%",
        "official_definition": "加权平均净资产收益率",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 12,
        "official_chunk_id": null,
        "official_excerpt": "0 基本每股收益（元/股） 0.16 0.14 14.29% 0.06 稀释每股收益（元/股） 0.16 0.14 14.29% 0.06 加权平均净资产收益率 4.39% 4.05% 0.34% 1.89% 项目 2025 年末 2024 年末 本年末比上 年末增减 2023 年末 总资产（元） 436,378,322,803.00 429,978,221,541.00 1.49% 419,18",
        "normalized_provider_value": 0.043804,
        "normalized_official_value": 0.043899999999999995,
        "absolute_diff": 9.599999999999193e-05,
        "relative_diff": 0.0021867881548973105,
        "tolerance": 0.0005,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "roe_weighted"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 12,
            "chunk_id": null,
            "excerpt": "0 基本每股收益（元/股） 0.16 0.14 14.29% 0.06 稀释每股收益（元/股） 0.16 0.14 14.29% 0.06 加权平均净资产收益率 4.39% 4.05% 0.34% 1.89% 项目 2025 年末 2024 年末 本年末比上 年末增减 2023 年末 总资产（元） 436,378,322,803.00 429,978,221,541.00 1.49% 419,18",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 4.39,
            "raw_unit": null,
            "normalized_value": 0.043899999999999995,
            "normalized_unit": "%",
            "unit_scale": 0.01,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 12,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 0.043804,
              "original_unit": "%",
              "normalized_value": 0.043804,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 0.043899999999999995,
              "original_unit": "%",
              "normalized_value": 0.043899999999999995,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "roe_weighted",
              "absolute_tolerance": 0.0005,
              "relative_tolerance": 0.005,
              "unit": "%",
              "basis": "percentage",
              "within_tolerance": true,
              "absolute_diff": 9.599999999999193e-05,
              "relative_diff": 0.0021867881548973105
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.615746+00:00",
        "updated_at": "2026-07-12T08:06:30.615748+00:00"
      },
      {
        "id": 9,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_share",
        "provider_name": "totalShare",
        "provider_value": 37413880464.0,
        "provider_unit": "shares",
        "provider_definition": "total_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 0.2367,
        "official_unit": "shares",
        "official_definition": "总股本",
        "official_period": "2020-08-27",
        "official_value_basis": "point_in_time",
        "official_page": 50,
        "official_chunk_id": null,
        "official_excerpt": "通的提示性公告》（公告编号：2025-033），本次符合解除\n限售条件的激励对象共计667 人，可解除限售的限制性股票数量为89,096,540 股，占公司目前总股本的0.2367%，本次\n解除限售股份上市流通日期为2025 年4 月29 日。公司于2024 年8 月28 日披露了《关于调整公司2020 年股票期权与限\n制性股票激励计划股票期权行权价格的公告》（公告编号：2025-064），因公司2024 年度权益分派实施完毕，本次激励\n计划所涉及的首次授",
        "normalized_provider_value": 37413880464.0,
        "normalized_official_value": 0.2367,
        "absolute_diff": 37413880463.7633,
        "relative_diff": 0.9999999999936734,
        "tolerance": 1.0,
        "fusion_status": "period_basis_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "within tolerance",
          "period mismatch: provider=2025-12-31 official=2020-08-27"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "total_share"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "keyword",
            "page": 50,
            "chunk_id": null,
            "excerpt": "通的提示性公告》（公告编号：2025-033），本次符合解除\n限售条件的激励对象共计667 人，可解除限售的限制性股票数量为89,096,540 股，占公司目前总股本的0.2367%，本次\n解除限售股份上市流通日期为2025 年4 月29 日。公司于2024 年8 月28 日披露了《关于调整公司2020 年股票期权与限\n制性股票激励计划股票期权行权价格的公告》（公告编号：2025-064），因公司2024 年度权益分派实施完毕，本次激励\n计划所涉及的首次授",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 0.2367,
            "raw_unit": "shares",
            "normalized_value": 0.2367,
            "normalized_unit": "shares",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": 50,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 37413880464.0,
              "original_unit": "shares",
              "normalized_value": 37413880464.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 0.2367,
              "original_unit": "shares",
              "normalized_value": 0.2367,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "total_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": false,
              "absolute_diff": 37413880463.7633,
              "relative_diff": 0.9999999999936734
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.622966+00:00",
        "updated_at": "2026-07-12T08:06:30.622968+00:00"
      },
      {
        "id": 10,
        "market": "CN",
        "symbol": "000725",
        "report_id": 4,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "float_share",
        "provider_name": "liqaShare",
        "provider_value": 36711216092.0,
        "provider_unit": "shares",
        "provider_definition": "float_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 140339594.0,
        "official_unit": "股",
        "official_definition": "流通股本",
        "official_period": "2025-01-12",
        "official_value_basis": "point_in_time",
        "official_page": 76,
        "official_chunk_id": null,
        "official_excerpt": "报告期内，公司注销库存股228,882,900 股。\n报告期内股份总数合计减少231,135,739 股，其中有限售条件股份数合计减少90,796,145 股，无限售条件股份数合计减少140,339,594 股。\n股份变动的批准情况\n□适用 不适用\n股份变动的过户情况\n□适用 不适用\n股份变动对最近一年和最近一期基本每股收益和稀释每股收益、归属于公司普通股股东的每股净资产等财务指标的影响\n适用□不适用\n项目 2025 年1-12 月\n基本每股收益（元/股） 0.16\n稀释每股收益",
        "normalized_provider_value": 36711216092.0,
        "normalized_official_value": 140339594.0,
        "absolute_diff": 36570876498.0,
        "relative_diff": 0.99617720116794,
        "tolerance": 1.0,
        "fusion_status": "period_basis_mismatch",
        "confidence": 0.0,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "official value not found in any excerpt",
          "period mismatch: provider=2025-12-31 official=2025-01-12"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000725_ai_official_verification_phase6tj.json",
            "field_name": "float_share"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "keyword",
            "page": 76,
            "chunk_id": null,
            "excerpt": "报告期内，公司注销库存股228,882,900 股。\n报告期内股份总数合计减少231,135,739 股，其中有限售条件股份数合计减少90,796,145 股，无限售条件股份数合计减少140,339,594 股。\n股份变动的批准情况\n□适用 不适用\n股份变动的过户情况\n□适用 不适用\n股份变动对最近一年和最近一期基本每股收益和稀释每股收益、归属于公司普通股股东的每股净资产等财务指标的影响\n适用□不适用\n项目 2025 年1-12 月\n基本每股收益（元/股） 0.16\n稀释每股收益",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-04-01/1225068510.PDF",
            "raw_value": 140339594.0,
            "raw_unit": "股",
            "normalized_value": 140339594.0,
            "normalized_unit": "shares",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": 76,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 36711216092.0,
              "original_unit": "shares",
              "normalized_value": 36711216092.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 140339594.0,
              "original_unit": "股",
              "normalized_value": 140339594.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "股→shares",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "float_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": false,
              "absolute_diff": 36570876498.0,
              "relative_diff": 0.99617720116794
            }
          }
        },
        "created_at": "2026-07-12T08:06:30.630377+00:00",
        "updated_at": "2026-07-12T08:06:30.630383+00:00"
      }
    ],
    "warnings": [],
    "timeout": false,
    "blocking_issues": [],
    "citation_complete": true,
    "source_trace_complete": true
  },
  {
    "symbol": "000001",
    "report_id": 5,
    "report_year": 2025,
    "report_type": "annual",
    "report_title": "平安银行：2025年年度报告",
    "status": null,
    "final_status": "passed",
    "ok": true,
    "cache_hit": false,
    "elapsed_ms": 33206.6,
    "timings": {
      "eligibility_latency_ms": 0.02,
      "cache_lookup_latency_ms": 0.0,
      "resolver_latency_ms": 145.1,
      "retrieval_latency_ms": 145.1,
      "alignment_latency_ms": 0.43,
      "persistence_latency_ms": 0.3,
      "computed_latency_ms": 145.84,
      "total_latency_ms": 10922.66,
      "waiting_on_singleflight_ms": 0.0,
      "singleflight_reuse_latency_ms": 0.0
    },
    "summary": {
      "fields_total": 10,
      "verified": 2,
      "normalized_match": 0,
      "likely_match": 0,
      "definition_mismatch": 3,
      "period_basis_mismatch": 1,
      "unit_mismatch": 0,
      "value_conflict": 0,
      "structured_field_missing": 3,
      "official_field_not_found": 0,
      "insufficient_evidence": 1,
      "not_applicable": 0,
      "failed": 0
    },
    "fields": [
      {
        "id": 1,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "revenue",
        "provider_name": "MBRevenue",
        "provider_value": 131442000000,
        "provider_unit": "CNY",
        "provider_definition": "main_business_revenue",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 131442000000.0,
        "official_unit": "CNY",
        "official_definition": "营业收入",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "的良好态势。2025年末，资产 总额59,257.77亿元，较上年末增长2.7%。2025年，受市场利率变化和业务结构调整等因素影响，实 现营业收入1,314.42亿元，同比下降10.4%。同时，持续推进降本增效，提升投产效率，强化风险管 控，实现净利润426.33亿元，同比下降4.2%。随着战略改革的持续深化，部分经营指标已呈现向好趋 势，为未来持续健康发展打下了坚实基础。 这一年，我们坚定把稳",
        "normalized_provider_value": 131442000000.0,
        "normalized_official_value": 131442000000.0,
        "absolute_diff": 0.0,
        "relative_diff": 0.0,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "official value matches structured value exactly",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "revenue"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "的良好态势。2025年末，资产 总额59,257.77亿元，较上年末增长2.7%。2025年，受市场利率变化和业务结构调整等因素影响，实 现营业收入1,314.42亿元，同比下降10.4%。同时，持续推进降本增效，提升投产效率，强化风险管 控，实现净利润426.33亿元，同比下降4.2%。随着战略改革的持续深化，部分经营指标已呈现向好趋 势，为未来持续健康发展打下了坚实基础。 这一年，我们坚定把稳",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 1314.42,
            "raw_unit": "亿元",
            "normalized_value": 131442000000.0,
            "normalized_unit": "CNY",
            "unit_scale": 100000000.0,
            "unit_source": "inline",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 6,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 131442000000,
              "original_unit": "CNY",
              "normalized_value": 131442000000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 131442000000.0,
              "original_unit": "CNY",
              "normalized_value": 131442000000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "revenue",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": true,
              "absolute_diff": 0.0,
              "relative_diff": 0.0
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.653955+00:00",
        "updated_at": "2026-07-12T08:07:03.653966+00:00"
      },
      {
        "id": 2,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit",
        "provider_name": "netProfit",
        "provider_value": 42633000000,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 42633000000.0,
        "official_unit": "CNY",
        "official_definition": "净利润",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "和业务结构调整等因素影响，实 现营业收入1,314.42亿元，同比下降10.4%。同时，持续推进降本增效，提升投产效率，强化风险管 控，实现净利润426.33亿元，同比下降4.2%。随着战略改革的持续深化，部分经营指标已呈现向好趋 势，为未来持续健康发展打下了坚实基础。 这一年，我们坚定把稳发展之舵，持续深化党建引领。我们持续坚持并不断加强党的全面领导， 深入推进党的领导融入公司治理、党的建设融入",
        "normalized_provider_value": 42633000000.0,
        "normalized_official_value": 42633000000.0,
        "absolute_diff": 0.0,
        "relative_diff": 0.0,
        "tolerance": 1.0,
        "fusion_status": "verified",
        "confidence": 0.95,
        "warnings_json": [
          "No direct disclosure of '净利润' (net profit) found in excerpts; only 归属于母公司股东的净利润 is available."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "net_profit"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "和业务结构调整等因素影响，实 现营业收入1,314.42亿元，同比下降10.4%。同时，持续推进降本增效，提升投产效率，强化风险管 控，实现净利润426.33亿元，同比下降4.2%。随着战略改革的持续深化，部分经营指标已呈现向好趋 势，为未来持续健康发展打下了坚实基础。 这一年，我们坚定把稳发展之舵，持续深化党建引领。我们持续坚持并不断加强党的全面领导， 深入推进党的领导融入公司治理、党的建设融入",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 426.33,
            "raw_unit": "亿元",
            "normalized_value": 42633000000.0,
            "normalized_unit": "CNY",
            "unit_scale": 100000000.0,
            "unit_source": "inline",
            "table_title": "合并利润表",
            "evidence_page": 6,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": true,
            "status": "comparable",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 42633000000,
              "original_unit": "CNY",
              "normalized_value": 42633000000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 42633000000.0,
              "original_unit": "CNY",
              "normalized_value": 42633000000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "net_profit",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": true,
              "absolute_diff": 0.0,
              "relative_diff": 0.0
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.669897+00:00",
        "updated_at": "2026-07-12T08:07:03.669902+00:00"
      },
      {
        "id": 3,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "net_profit_parent",
        "provider_name": "netProfit",
        "provider_value": 42633000000,
        "provider_unit": "CNY",
        "provider_definition": "net_profit",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 42633.0,
        "official_unit": null,
        "official_definition": "归属于母公司股东的净利润",
        "official_period": "2010-01-11",
        "official_value_basis": "annual_cumulative",
        "official_page": 288,
        "official_chunk_id": null,
        "official_excerpt": "普通股股东的净利润 10.16% 2.16 2.16 其中，扣除非经常性损益后归属于母公司普通股股东的净利润： 2025年度 2024年度 归属于母公司股东的净利润 42,633 44,508 减：母公司优先股宣告股息 (874) (874) 母公司永续债利息 (1,645) (1,975) 归属于母公司普通股股东的净利润 40,114 41,659 扣除：非经常性损益 9 (330) 非流动性资",
        "normalized_provider_value": 42633000000.0,
        "normalized_official_value": 42633.0,
        "absolute_diff": 42632957367.0,
        "relative_diff": 0.999999,
        "tolerance": 1.0,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "unit not safely convertible",
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "net_profit_parent"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 288,
            "chunk_id": null,
            "excerpt": "普通股股东的净利润 10.16% 2.16 2.16 其中，扣除非经常性损益后归属于母公司普通股股东的净利润： 2025年度 2024年度 归属于母公司股东的净利润 42,633 44,508 减：母公司优先股宣告股息 (874) (874) 母公司永续债利息 (1,645) (1,975) 归属于母公司普通股股东的净利润 40,114 41,659 扣除：非经常性损益 9 (330) 非流动性资",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 42633.0,
            "raw_unit": null,
            "normalized_value": 42633.0,
            "normalized_unit": "CNY",
            "unit_scale": null,
            "unit_source": "unknown",
            "table_title": "合并利润表 / 主要会计数据",
            "evidence_page": 288,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": false,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [
              "unit not safely convertible"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "unknown"
          },
          "normalization": {
            "provider": {
              "original_value": 42633000000,
              "original_unit": "CNY",
              "normalized_value": 42633000000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 42633.0,
              "original_unit": null,
              "normalized_value": 42633.0,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "unknown_unit",
              "warnings": [
                "unknown_unit"
              ]
            },
            "tolerance": {
              "field_name": "net_profit_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": 42632957367.0,
              "relative_diff": 0.999999
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.685020+00:00",
        "updated_at": "2026-07-12T08:07:03.685024+00:00"
      },
      {
        "id": 4,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "cashflow_quality",
        "field_name": "operating_cashflow",
        "provider_name": "operating_cashflow",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "operating_cashflow",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 315858.0,
        "official_unit": null,
        "official_definition": "经营活动产生的现金流量净额",
        "official_period": "2016-03-07",
        "official_value_basis": "annual_cumulative",
        "official_page": 18,
        "official_chunk_id": null,
        "official_excerpt": "44,508 46,455 (4.2%) 扣除非经常性损益后归属于本行股东的净利润 42,624 44,838 46,431 (4.9%) 经营活动产生的现金流量净额 315,858 63,336 92,461 398.7% 每股比率（元/股）： 基本/稀释每股收益 2.07 2.15 2.25 (3.7%) 扣除非经常性损益后的基本/稀释每股收益 2.07 2.16 2.25 (4.2%) 每股",
        "normalized_provider_value": null,
        "normalized_official_value": 315858.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "unit not safely convertible",
          "Official value found in excerpt; structured value is null (row not found)."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "operating_cashflow"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 18,
            "chunk_id": null,
            "excerpt": "44,508 46,455 (4.2%) 扣除非经常性损益后归属于本行股东的净利润 42,624 44,838 46,431 (4.9%) 经营活动产生的现金流量净额 315,858 63,336 92,461 398.7% 每股比率（元/股）： 基本/稀释每股收益 2.07 2.15 2.25 (3.7%) 扣除非经常性损益后的基本/稀释每股收益 2.07 2.16 2.25 (4.2%) 每股",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 315858.0,
            "raw_unit": null,
            "normalized_value": 315858.0,
            "normalized_unit": "CNY",
            "unit_scale": null,
            "unit_source": "unknown",
            "table_title": "合并现金流量表 / 主要会计数据",
            "evidence_page": 18,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": false,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence",
              "unit not safely convertible"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "unknown"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 315858.0,
              "original_unit": null,
              "normalized_value": 315858.0,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "unknown_unit",
              "warnings": [
                "unknown_unit"
              ]
            },
            "tolerance": {
              "field_name": "operating_cashflow",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.699001+00:00",
        "updated_at": "2026-07-12T08:07:03.699003+00:00"
      },
      {
        "id": 5,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_assets",
        "provider_name": "total_assets",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "total_assets",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 5925777000000.0,
        "official_unit": "CNY",
        "official_definition": "总资产",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 6,
        "official_chunk_id": null,
        "official_excerpt": "融“五篇大文章”，坚定不移推进数字化转型，以稳健经营 笃定前行，以实干担当践行使命，经营发展保持稳中有进、质效提升的良好态势。2025年末，资产 总额59,257.77亿元，较上年末增长2.7%。2025年，受市场利率变化和业务结构调整等因素影响，实 现营业收入1,314.42亿元，同比下降10.4%。同时，持续推进降本增效，提升投产效率，强化风险管 控，实现净利润426.33亿元，同比下降4.2",
        "normalized_provider_value": null,
        "normalized_official_value": 5925777000000.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "Official value found in excerpt; structured value is null."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "total_assets"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 6,
            "chunk_id": null,
            "excerpt": "融“五篇大文章”，坚定不移推进数字化转型，以稳健经营 笃定前行，以实干担当践行使命，经营发展保持稳中有进、质效提升的良好态势。2025年末，资产 总额59,257.77亿元，较上年末增长2.7%。2025年，受市场利率变化和业务结构调整等因素影响，实 现营业收入1,314.42亿元，同比下降10.4%。同时，持续推进降本增效，提升投产效率，强化风险管 控，实现净利润426.33亿元，同比下降4.2",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 59257.77,
            "raw_unit": "亿元",
            "normalized_value": 5925777000000.0,
            "normalized_unit": "CNY",
            "unit_scale": 100000000.0,
            "unit_source": "inline",
            "table_title": "资产负债表 / 主要会计数据",
            "evidence_page": 6,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 5925777000000.0,
              "original_unit": "CNY",
              "normalized_value": 5925777000000.0,
              "normalized_unit": "CNY",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY→CNY",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "total_assets",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.712267+00:00",
        "updated_at": "2026-07-12T08:07:03.712272+00:00"
      },
      {
        "id": 6,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "equity_parent",
        "provider_name": "equity_parent",
        "provider_value": null,
        "provider_unit": "CNY",
        "provider_definition": "equity_parent",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": null,
        "official_unit": null,
        "official_definition": "归属于上市公司股东的净资产",
        "official_period": null,
        "official_value_basis": "point_in_time",
        "official_page": null,
        "official_chunk_id": null,
        "official_excerpt": null,
        "normalized_provider_value": null,
        "normalized_official_value": null,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 1.0,
        "fusion_status": "insufficient_evidence",
        "confidence": 0.0,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "unit not safely convertible",
          "no comparable official or structured value",
          "official field not found in selected report",
          "official evidence not sufficient"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "equity_parent"
          },
          "official": {
            "status": "insufficient_evidence",
            "retrieval_mode": "keyword",
            "page": null,
            "chunk_id": null,
            "excerpt": null,
            "source_url": null,
            "raw_value": null,
            "raw_unit": null,
            "normalized_value": null,
            "normalized_unit": "CNY",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": null,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": false,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence",
              "unit not safely convertible"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "unknown"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY",
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": null,
              "original_unit": null,
              "normalized_value": null,
              "normalized_unit": "CNY",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "tolerance": {
              "field_name": "equity_parent",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.005,
              "unit": "CNY",
              "basis": "monetary",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.725420+00:00",
        "updated_at": "2026-07-12T08:07:03.725423+00:00"
      },
      {
        "id": 7,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "eps_basic",
        "provider_name": "eps_basic",
        "provider_value": null,
        "provider_unit": "CNY/share",
        "provider_definition": "eps_basic",
        "provider_period": "2025-12-31",
        "provider_value_basis": "unknown",
        "official_value": 48.0,
        "official_unit": "CNY/share",
        "official_definition": "基本每股收益",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 121,
        "official_chunk_id": null,
        "official_excerpt": "小计 (1,497) (777) 其他综合收益合计 (2,101) (374) 八、综合收益总额 40,532 44,134 九、每股收益 基本每股收益(人民币元) 48 2.07 2.15 稀释每股收益(人民币元) 48 2.07 2.15 后附财务报表附注为本财务报表的组成部分。",
        "normalized_provider_value": null,
        "normalized_official_value": 48.0,
        "absolute_diff": null,
        "relative_diff": null,
        "tolerance": 0.01,
        "fusion_status": "structured_field_missing",
        "confidence": 0.6,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "Official value found in excerpt; structured value is null."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "eps_basic"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 121,
            "chunk_id": null,
            "excerpt": "小计 (1,497) (777) 其他综合收益合计 (2,101) (374) 八、综合收益总额 40,532 44,134 九、每股收益 基本每股收益(人民币元) 48 2.07 2.15 稀释每股收益(人民币元) 48 2.07 2.15 后附财务报表附注为本财务报表的组成部分。",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 48.0,
            "raw_unit": null,
            "normalized_value": 48.0,
            "normalized_unit": "CNY/share",
            "unit_scale": 1.0,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 121,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": null,
              "original_unit": "CNY/share",
              "normalized_value": null,
              "normalized_unit": "CNY/share",
              "conversion_factor": null,
              "conversion_trace": null,
              "status": "missing",
              "warnings": []
            },
            "official": {
              "original_value": 48.0,
              "original_unit": "CNY/share",
              "normalized_value": 48.0,
              "normalized_unit": "CNY/share",
              "conversion_factor": 1.0,
              "conversion_trace": "CNY/share→CNY/share",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "eps_basic",
              "absolute_tolerance": 0.01,
              "relative_tolerance": 0.005,
              "unit": "CNY/share",
              "basis": "eps",
              "within_tolerance": false,
              "absolute_diff": null,
              "relative_diff": null
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.737893+00:00",
        "updated_at": "2026-07-12T08:07:03.737895+00:00"
      },
      {
        "id": 8,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "profitability",
        "field_name": "roe_weighted",
        "provider_name": "roeAvg",
        "provider_value": 0.081514,
        "provider_unit": "%",
        "provider_definition": "roe",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 0.09150000000000001,
        "official_unit": "%",
        "official_definition": "加权平均净资产收益率",
        "official_period": "2025-12-31",
        "official_value_basis": "annual_cumulative",
        "official_page": 17,
        "official_chunk_id": null,
        "official_excerpt": "(4.2%) 成本收入比 29.06% 27.66% +1.40 个百分点 平均总资产收益率 0.73% 0.78% -0.05 个百分点 加权平均净资产收益率 9.15% 10.08% -0.93 个百分点 净息差 1.78% 1.87% -0.09 个百分点 非利息净收入占比 33.03% 36.31% -3.28 个百分点 2025 年12 月31 日 2024 年12 月31 日 本年末比",
        "normalized_provider_value": 0.081514,
        "normalized_official_value": 0.09150000000000001,
        "absolute_diff": 0.009986000000000009,
        "relative_diff": 0.10913661202185801,
        "tolerance": 0.0005,
        "fusion_status": "definition_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "field definition text indicates a different financial concept",
          "definition mismatch between structured and official evidence"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "roe_weighted"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "extractor",
            "page": 17,
            "chunk_id": null,
            "excerpt": "(4.2%) 成本收入比 29.06% 27.66% +1.40 个百分点 平均总资产收益率 0.73% 0.78% -0.05 个百分点 加权平均净资产收益率 9.15% 10.08% -0.93 个百分点 净息差 1.78% 1.87% -0.09 个百分点 非利息净收入占比 33.03% 36.31% -3.28 个百分点 2025 年12 月31 日 2024 年12 月31 日 本年末比",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 9.15,
            "raw_unit": null,
            "normalized_value": 0.09150000000000001,
            "normalized_unit": "%",
            "unit_scale": 0.01,
            "unit_source": "intrinsic",
            "table_title": "主要财务指标",
            "evidence_page": 17,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": false,
            "same_value_basis": true,
            "unit_convertible": true,
            "comparable": false,
            "status": "definition_mismatch",
            "warnings": [],
            "structured_period_basis": "annual_cumulative",
            "official_period_basis": "annual_cumulative"
          },
          "normalization": {
            "provider": {
              "original_value": 0.081514,
              "original_unit": "%",
              "normalized_value": 0.081514,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 0.09150000000000001,
              "original_unit": "%",
              "normalized_value": 0.09150000000000001,
              "normalized_unit": "%",
              "conversion_factor": 1.0,
              "conversion_trace": "%→%",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "roe_weighted",
              "absolute_tolerance": 0.0005,
              "relative_tolerance": 0.005,
              "unit": "%",
              "basis": "percentage",
              "within_tolerance": false,
              "absolute_diff": 0.009986000000000009,
              "relative_diff": 0.10913661202185801
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.750823+00:00",
        "updated_at": "2026-07-12T08:07:03.750827+00:00"
      },
      {
        "id": 9,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "total_share",
        "provider_name": "totalShare",
        "provider_value": 19405918198,
        "provider_unit": "shares",
        "provider_definition": "total_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 19405918198.0,
        "official_unit": "shares",
        "official_definition": "总股本",
        "official_period": "2016-03-07",
        "official_value_basis": "point_in_time",
        "official_page": 18,
        "official_chunk_id": null,
        "official_excerpt": "\n示公司持续经营能力存在不确定性\n□是 √否\n公司报告期内经审计利润总额、净利润、扣除非经常性损益后的净利润三者孰低为负值\n□是 √否\n截至披露前一交易日的公司总股本及用最新股本计算的全面摊薄每股收益\n截至披露前一交易日的公司总股本（股） 19,405,918,198\n支付的优先股股利（元） 874,000,000\n支付的永续债利息（元） 1,645,000,000\n用最新股本计算的全面摊薄每股收益（元/股） 2.07\n境内外会计准则下会计数据差异\n1、同时按照国际会计准则与按照中国会计准则披露的财务报告中净利润和净资产差异情况\n□适用 √不适",
        "normalized_provider_value": 19405918198.0,
        "normalized_official_value": 19405918198.0,
        "absolute_diff": 0.0,
        "relative_diff": 0.0,
        "tolerance": 1.0,
        "fusion_status": "period_basis_mismatch",
        "confidence": 0.85,
        "warnings_json": [
          "period mismatch between structured and official evidence",
          "Official value matches structured value exactly.",
          "period mismatch: provider=2025-12-31 official=2016-03-07"
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "total_share"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "keyword",
            "page": 18,
            "chunk_id": null,
            "excerpt": "\n示公司持续经营能力存在不确定性\n□是 √否\n公司报告期内经审计利润总额、净利润、扣除非经常性损益后的净利润三者孰低为负值\n□是 √否\n截至披露前一交易日的公司总股本及用最新股本计算的全面摊薄每股收益\n截至披露前一交易日的公司总股本（股） 19,405,918,198\n支付的优先股股利（元） 874,000,000\n支付的永续债利息（元） 1,645,000,000\n用最新股本计算的全面摊薄每股收益（元/股） 2.07\n境内外会计准则下会计数据差异\n1、同时按照国际会计准则与按照中国会计准则披露的财务报告中净利润和净资产差异情况\n□适用 √不适",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 19405918198.0,
            "raw_unit": "shares",
            "normalized_value": 19405918198.0,
            "normalized_unit": "shares",
            "unit_scale": null,
            "unit_source": null,
            "table_title": null,
            "evidence_page": 18,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": false,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "period mismatch between structured and official evidence"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 19405918198,
              "original_unit": "shares",
              "normalized_value": 19405918198.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 19405918198.0,
              "original_unit": "shares",
              "normalized_value": 19405918198.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "total_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": true,
              "absolute_diff": 0.0,
              "relative_diff": 0.0
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.763910+00:00",
        "updated_at": "2026-07-12T08:07:03.763915+00:00"
      },
      {
        "id": 10,
        "market": "CN",
        "symbol": "000001",
        "report_id": 5,
        "report_year": 2025,
        "report_type": "annual",
        "module": "solvency",
        "field_name": "float_share",
        "provider_name": "liqaShare",
        "provider_value": 19405600653,
        "provider_unit": "shares",
        "provider_definition": "float_share",
        "provider_period": "2025-12-31",
        "provider_value_basis": "annual_cumulative",
        "official_value": 19405571850.0,
        "official_unit": "shares",
        "official_definition": "流通股本",
        "official_period": "2025-12-31",
        "official_value_basis": "point_in_time",
        "official_page": 97,
        "official_chunk_id": null,
        "official_excerpt": "外资持股 - - - - - - - - -\n其中：\n境外法人持股\n- - - - - - - - -\n境外自然人持股 - - - - - - - - -\n二、无限售条件股份 19,405,571,850 约100 - - - 28,803 28,803 19,405,600,653 约100\n1、人民币普通股 19,405,571,850 约100 - - - 28,803 28,803 19,405,600,653 约100\n2、境内上市",
        "normalized_provider_value": 19405600653.0,
        "normalized_official_value": 19405571850.0,
        "absolute_diff": 28803.0,
        "relative_diff": 1.4842622248617289e-06,
        "tolerance": 1.0,
        "fusion_status": "verified",
        "confidence": 0.95,
        "warnings_json": [
          "value basis mismatch between structured and official evidence",
          "No excerpt found for 流通股本 (float_share); structured value cannot be verified."
        ],
        "source_trace_json": {
          "structured": {
            "source": "artifact_seed",
            "artifact_path": "/Users/kaffy/Documents/TradingAgents/backend/docs/artifacts/company_v2_000001_ai_official_verification_phase6tj.json",
            "field_name": "float_share"
          },
          "official": {
            "status": "resolved",
            "retrieval_mode": "keyword",
            "page": 97,
            "chunk_id": null,
            "excerpt": "外资持股 - - - - - - - - -\n其中：\n境外法人持股\n- - - - - - - - -\n境外自然人持股 - - - - - - - - -\n二、无限售条件股份 19,405,571,850 约100 - - - 28,803 28,803 19,405,600,653 约100\n1、人民币普通股 19,405,571,850 约100 - - - 28,803 28,803 19,405,600,653 约100\n2、境内上市",
            "source_url": "https://static.cninfo.com.cn/finalpage/2026-03-21/1225022887.PDF",
            "raw_value": 19405571850.0,
            "raw_unit": "shares",
            "normalized_value": 19405571850.0,
            "normalized_unit": "shares",
            "unit_scale": 1.0,
            "unit_source": "intrinsic",
            "table_title": null,
            "evidence_page": 97,
            "table_scope_id": null
          },
          "alignment": {
            "same_symbol": true,
            "same_report": true,
            "same_period": true,
            "same_definition": true,
            "same_value_basis": false,
            "unit_convertible": true,
            "comparable": false,
            "status": "period_basis_mismatch",
            "warnings": [
              "value basis mismatch between structured and official evidence"
            ],
            "structured_period_basis": "point_in_time",
            "official_period_basis": "point_in_time"
          },
          "normalization": {
            "provider": {
              "original_value": 19405600653,
              "original_unit": "shares",
              "normalized_value": 19405600653.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "official": {
              "original_value": 19405571850.0,
              "original_unit": "shares",
              "normalized_value": 19405571850.0,
              "normalized_unit": "shares",
              "conversion_factor": 1.0,
              "conversion_trace": "shares→shares",
              "status": "normalized",
              "warnings": []
            },
            "tolerance": {
              "field_name": "float_share",
              "absolute_tolerance": 1.0,
              "relative_tolerance": 0.001,
              "unit": "shares",
              "basis": "share_count",
              "within_tolerance": true,
              "absolute_diff": 28803.0,
              "relative_diff": 1.4842622248617289e-06
            }
          }
        },
        "created_at": "2026-07-12T08:07:03.779611+00:00",
        "updated_at": "2026-07-12T08:07:03.779615+00:00"
      }
    ],
    "warnings": [],
    "timeout": false,
    "blocking_issues": [],
    "citation_complete": true,
    "source_trace_complete": true
  }
]

## Gate
{
  "stage2_plan_gate_passed": true,
  "manual_step_gate_passed": true,
  "download_gate_passed": true,
  "parse_gate_passed": true,
  "index_gate_passed": true,
  "multistock_fusion_gate_passed": true,
  "bank_applicability_gate_passed": true,
  "safety_gate_passed": true,
  "monitoring_gate_passed": false,
  "frontend_gate_passed": true,
  "tests_gate_passed": true,
  "blocking_issues": []
}