# P1.6.8 Browser Regression (B01/B02/B04/B05 + B03 fix)

| Case | Loading | Assistant | ClarCard | Links | OfficialDomain | ConsoleErr | Note |
| --- | --- | --- | --- | --- | --- | --- | --- |
| B03 | True | 1 | 1 | - | - | 0 | candidates rendered incl. index-driven 平安电工; click→中国平安 resolved; refresh restored |
| B01 | True | 2 | 0 | 1 | True | 0 | multi-turn context kept; no clarification card in non-ambiguous flow |
| B02 | True | 1 | 0 | 1 | True | 0 | 2025 annual official PDF |
| B04 | True | 1 | 0 | 0 | True | 0 | unsupported semi refused, no annual leak |
| B05 | True | 1 | 0 | 0 | True | 0 | no fabricated URL/company |

- raw500/raw503: `{'500': 0, '503': 0}`
- No clarification component appeared in any non-ambiguous case.
- No tokens/user ids/screenshots stored.
