## 2026-10-21 - Frontend tests for the incident page's components; coverage floors raised

Type: tests
Who: conantkd (+ agent)
Context: OP-014 step 4 (#246) set the frontend's coverage floors at 33.9 % of lines; components, hooks and pages had
no unit test (no DOM in the test runner).
Decision / result:
- Components rendered with `react-dom/server`'s `renderToStaticMarkup` (Node, no new dependency, no jsdom); only new
  test files, no component changed.
- **SafeMarkdown** (renders runbooks and agent text): raw HTML never rendered, images dropped, only http(s) links
  clickable, with `noopener`. Red seen: allowing every link and images fails 3 tests (`javascript:` and `data:` links
  are also emptied by react-markdown itself: two layers).
- **MetricChart**: a missing sample is a gap, never a zero; samples outside the window left out; the incident band.
  Red seen: drawing null as 0 fails 2 tests.
- AnswerBlock, WhyCard, RunTimeline, EvidenceAudit (folded content, cited marks, audit links and Details), `format`
  and `clipboard` helpers. 136 to 175 tests.
- Coverage: lines 33.9 to 43.6 %, branches 26.6 to 40.9 %; floors 43 / 43 / 39 / 40.
Consequences: hooks and pages are still uncovered by unit tests (Playwright covers the pages); a DOM test setup
(jsdom, Testing Library) would be the frontend lane's call.
References: [OP-014](../../OPEN_PROBLEMS.md).
