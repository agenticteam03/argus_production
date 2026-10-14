export function summarizeRun(events = []) {
  const traceId = events.map((event) => event.data?.trace_id).find(Boolean) ?? null;
  const last = events.at(-1);
  return {
    traceId,
    node: last?.node ?? null,
    tools: events.filter((event) => event.phase === "step" && ["act", "evidence_pack"].includes(event.node)).length,
    decisions: events.filter((event) => event.node === "investigate" && event.phase === "exit").length,
    steps: events.length,
  };
}
