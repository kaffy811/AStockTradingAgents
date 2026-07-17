# Update 56 - Phase 6U-D6.4

## Summary
- Fixed market-wide security entity resolver coverage by rebuilding the index from StockMaster plus StockIndustryMap and rejecting stale/incomplete cache payloads.
- Added `security_entity_index:v3_d6_4` metadata, checksum validation, source counts, and a release-gate integrity script.
- Implemented compiled exact/code/name lookup plus trie-based continuous Chinese name matching with text-order and longest-match ranking.
- Verified real DB records for `CN/000858` and `CN/600519`; `五粮液最新财报表现如何` now resolves to `000858.SZ`.
- Fixed report comparison entity merge so `那它和五粮液比呢` produces `600519.SH` from context and `000858.SZ` from current query.
- Cleaned normal Chat display: internal source/chunk fields are hidden, disclaimer is owned by frontend footer, and trace text no longer exposes internal Agent/Skill names.
- Fixed safety postprocessor overreach that corrupted `面临一定业绩压力`.

## Validation
- Targeted backend: `38 passed`
- Failed-contract backend subset after updates: `51 passed`
- Security index integrity artifact: `backend/docs/artifacts/security_entity_index_integrity.json`
  - CN: `5166/5166` short names, full names, and codes resolvable
  - HK: `30/30` resolvable
  - US: `0` records in current security master
- Warm CN resolver lookup: 20/20 sampled names, avg `1.336ms`, p95 `1.431ms`
- Frontend targeted: `17 passed`
- Frontend full vitest: `678 passed`
- Frontend build: passed

## Notes
- Full backend first rerun after D6.4 contract changes exposed 5 old-contract test failures; those contracts were updated.
- Full backend second rerun reached `3236 passed`; 11 live DB persistence tests timed out in `company_v2_report_rag_db_repository` / `shadow_soak_live`, unrelated to D6.4 resolver or Chat display paths. A focused rerun reproduced the DB timeout in the same persistence helper.
- No migration added.
- Public API fields were not removed.
