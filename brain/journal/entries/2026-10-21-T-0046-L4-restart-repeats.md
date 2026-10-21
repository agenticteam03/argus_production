## 2026-10-21 — T-0046 L4 follow-up: a scheduler restart is not a link transition

Type: implementation
Who: juanbetancurm (+ agent)
Context: reviewing #227, `conantkd` noted that the recorder writes every link's state once at startup (ARCHITECTURE
§7.3), so each deploy repeated the states it already had: the map's `since` restarted at the deploy, and a link that
stayed broken showed a second `link_broken` on the incident charts. He also noted that the two stores picked the
latest row by different rules (Postgres by time then id, SQLite by id).
Decision / result:
- Fixed where the rows are read, not where they are written: the stores' `link_events` and `latest_link_events` skip
  a row whose state is its link's previous state (a window `LAG` over time, then id), so the map, the charts and
  `network.link_states` all read transitions only. The recorder keeps its startup row, as §7.3 says, so the table
  still shows when a scheduler started; seeding the recorder from the table would have changed §7.3.
- Both stores now order a link's rows by time, then id.
- The L3 test that checks the startup row reads the table directly.
Consequences: no architecture change; ARCHITECTURE §7.1 already defines `since` as the last recorded transition.
References: [T-0046](../../tasks/current/T-0046-live-dependency-graph.md), #227.
