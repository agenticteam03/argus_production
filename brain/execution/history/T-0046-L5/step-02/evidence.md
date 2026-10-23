# T-0046 L5 step 02 — evidence: SC-03, SC-07 and SC-01 with link recording on (2026-10-21 UTC, conantkd)

Goal: ACR-0025 / T-0046 L5 asks to run SC-03 and SC-07 once each and see the link transitions against the errors.
SC-01 was added to see a model strategy's hypotheses on a live run (T-0047 H1, log-only): `dependency_unavailable`
runs the deterministic `baseline` (D-003), so SC-03 and SC-07 have no model call and no hypotheses. Commands:
[`code.bash`](code.bash). No key, address, token or password is written here.

| Run | Observed | Result |
|---|---|---|
| S.1 SC-03 by hand | cache stopped 18:34:57, gate reached 18:35:27, reset 18:35:25-27 (about 30 s down); recorded `api → cache` **`slow` 2503.5 ms at 18:35:43** (the cache coming back), `ok` 18:36:43; no `broken` row; `NO INTERFERENCE` on both VMs | as expected, see note 1 |
| S.2 SC-03 runner | **PASS** (`inc_fe2ab91bebc9`, 29 s): `dependency_unavailable`, root cause `argus-lab-cache` (baseline); incident opened 18:42:37, closed 18:42:40; recorded `api → cache` **`broken` (name not resolved) at 18:42:47**, `ok` at 18:43:48; the incident's chart shows `link_broken` and `link_recovered` (and the S.1 `link_slow` / `link_recovered`, inside its 30 min range) | PASS, see note 2 |
| S.2 SC-07 runner | **PASS** (`inc_e30d920d4383`, 30 s): `dependency_unavailable`, root cause `argus-lab-backend` (baseline); incident 18:43:08-18:43:09; **no `link_event` row** for `client → backend` | PASS, see note 1 |
| S.2 SC-01 runner | **PASS** (`inc_0e4efb393a0c`, 71 s): `container_restart_loop` (model strategy), root cause `argus-lab-worker`, confidence high; **three hypotheses**: h1 supported (self, 2 for) chosen; h2 ruled out (host, 1 against); h3 untested (self, 1 against); **no `hypothesis.invalid`** | PASS, see note 3 |
| S.4 | the runner's `nonint-check` after each run: `NO INTERFERENCE`; both leases released | OK |

## Notes

1. **A fault shorter than the recorder's tick can be missed.** The recorder runs on the reconcile tick (60 s): SC-07's
   client was broken for about 30 s between two ticks and left no row; S.1's 30 s outage left only the `slow` of its
   recovery. Correct by the rule (the recorder writes what it sees), but `network.link_states`' history (L6) will not
   show a fault that came and went between ticks.
2. **A row's time is when the recorder wrote it, not the probe sample's time.** SC-03's `broken` is 10 s after the
   incident opened, although the probe failed before the gate (18:42:2x). With a 60 s tick the lag can reach a
   minute, enough to put a link event after the errors it caused on the incident chart. **Follow-up for T-0046
   before L6:** write the probe sample's own time (`ProbeSample` carries it) and decide whether the tick is short
   enough for the history, or measure it with L6's evaluation batch.
3. **H1 on a live run:** the model listed hypotheses, `chosen` matches the root cause, and every §11.3 check passed.
   h3 is `untested` although it cites evidence against it (it could be `ruled_out`); a note for H4's labels.
