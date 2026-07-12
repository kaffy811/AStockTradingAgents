# Phase 6T-J2 Official Extractor Unit Context

- generated_at: 2026-07-12T08:10:16.195600+00:00
- official_extractor_version: official-extractor-unit-context-v2
- real_execution: true
- mock: false
- repository_backend: database
- persistent: true

## 300750 net_profit
- classification: verified
- raw official value: 76786309.0 千元
- unit_scale: 1000.0
- normalized official value: 76786309000.0 CNY
- structured value: 76786309000 CNY
- evidence_page: 200
- table_scope_id: p200#u738

## 600519 revenue
- classification: definition_mismatch
- structured_definition: main_business_revenue
- official_definition: 营业收入

## Review Queue Resolution
- original_classification: value_conflict
- corrected_classification: verified
- resolution: resolved_false_positive
- resolution_reason: table_level_unit_context_restored
- active_queue_contains_item: false
