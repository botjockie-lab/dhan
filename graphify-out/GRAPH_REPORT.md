# Graph Report - dhan  (2026-10-08)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 104 nodes · 158 edges · 7 communities (2 shown, 5 thin omitted)
- Extraction: 89% EXTRACTED · 11% INFERRED · 0% AMBIGUOUS · INFERRED: 18 edges (avg confidence: 0.86)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `7fd52ba0`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- Community 0
- Community 1
- Community 2
- Community 3
- Community 4
- Community 5

## God Nodes (most connected - your core abstractions)
1. `DhanRiskManager` - 16 edges
2. `TelegramNotifier` - 10 edges
3. `SimplifiedDhanRiskManager` - 9 edges
4. `TestTrailingStoploss` - 8 edges
5. `main()` - 8 edges
6. `TestKillSwitchFeature` - 7 edges
7. `SimpleDhanRiskManager` - 6 edges
8. `monitor_risk()` - 6 edges
9. `send_periodic_pnl()` - 6 edges
10. `main()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `DhanRiskManager`  [EXTRACTED]
  dry_run.py → dhan_risk_manager.py
- `TelegramPositionsTest` --uses--> `DhanRiskManager`  [INFERRED]
  telegram_positions_test.py → dhan_risk_manager.py

## Import Cycles
- None detected.

## Communities (7 total, 5 thin omitted)

### Community 0 - "Community 0"
Cohesion: 0.11
Nodes (7): is_market_hours(), main(), monitor_risk(), send_periodic_pnl(), setup_logging(), TelegramNotifier, validate_config()

### Community 5 - "Community 5"
Cohesion: 0.33
Nodes (3): FakeResponse, main(), fake_post()

## Knowledge Gaps
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `DhanRiskManager` connect `Community 1` to `Community 0`, `Community 3`, `Community 5`, `Community 6`?**
  _High betweenness centrality (0.352) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `main()` (e.g. with `send_periodic_pnl()` and `.send_startup_message()`) actually correct?**
  _`main()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Community 0` be split into smaller, more focused modules?**
  _Cohesion score 0.11231884057971014 - nodes in this community are weakly interconnected._
- **Why does `TestTrailingStoploss` connect `Community 2` to `Community 6`?**
  _High betweenness centrality (0.189) - this node is a cross-community bridge._
- **Should `Community 1` be split into smaller, more focused modules?**
  _Cohesion score 0.14210526315789473 - nodes in this community are weakly interconnected._
- **Why does `TelegramNotifier` connect `Community 0` to `Community 3`?**
  _High betweenness centrality (0.177) - this node is a cross-community bridge._