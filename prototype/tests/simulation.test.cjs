const { test } = require('node:test');
const assert = require('node:assert/strict');
const { Simulation, sha256 } = require('../src/simulation.js');

function ready(kind = 'cache', options = {}) {
  const sim = new Simulation({ seed: false });
  const incident = sim.inject(kind, options);
  sim.tick(16);
  return { sim, incident };
}

test('released restart pauses for an authenticated human and verifies with fresh samples', () => {
  const { sim, incident } = ready();
  assert.equal(incident.status, 'awaiting_approval');
  assert.equal(sim.actions.length, 0);
  assert.equal(sim.answer(incident.id, 'approved').ok, true);
  sim.tick(3);
  assert.equal(incident.status, 'verifying');
  assert.equal(sim.actions.length, 1);
  assert.equal(sim.actions[0].state, 'confirmed');
  sim.tick(6);
  assert.equal(incident.outcome, 'remediated');
  assert.equal(incident.samples.length, 3);
  assert.ok(incident.samples.every(s => s.at > sim.actions[0].attemptedAt));
});

test('viewer, operator, service, expired and wrong-host sessions cannot approve', () => {
  for (const role of ['viewer', 'operator', 'service', 'expired', 'wrong_scope']) {
    const { sim, incident } = ready();
    sim.setPrincipal(role);
    assert.equal(sim.answer(incident.id, 'approved').ok, false, role);
    assert.equal(incident.status, 'awaiting_approval');
    assert.equal(sim.actions.length, 0);
  }
});

test('read-only profile and target holds create no approval or write', () => {
  for (const cause of ['profile', 'hold']) {
    const sim = new Simulation({ seed: false });
    if (cause === 'profile') sim.setProfile('read_only');
    else sim.toggleHold('vm-166/container:argus-lab-cache');
    const incident = sim.inject('cache');
    sim.tick(20);
    assert.equal(incident.outcome, 'policy_blocked');
    assert.equal(incident.proposal, null);
    assert.equal(sim.actions.length, 0);
  }
});

test('denial and approval expiry never dispatch a write', () => {
  const a = ready();
  a.sim.answer(a.incident.id, 'denied', 'Preserve the workload for inspection');
  assert.equal(a.incident.outcome, 'approval_denied');
  a.sim.tick(10);
  assert.equal(a.sim.actions.length, 0);
  const b = ready();
  b.sim.tick(301);
  assert.equal(b.incident.outcome, 'approval_expired');
  assert.equal(b.sim.actions.length, 0);
});

test('precheck invalidates approvals when identity, policy, evidence or hold changes', () => {
  for (const change of ['identity', 'policy', 'evidence', 'hold']) {
    const { sim, incident } = ready();
    sim.answer(incident.id, 'approved');
    if (change === 'identity') sim.replaceTarget(incident.proposal.target);
    if (change === 'policy') sim.setProfile('read_only');
    if (change === 'evidence') sim.invalidateEvidence(incident.id);
    if (change === 'hold') sim.toggleHold(incident.proposal.target);
    sim.tick(12);
    assert.equal(incident.outcome, 'proposal_invalidated', change);
    assert.equal(sim.actions.length, 0);
  }
});

test('same-target alerts correlate but identical container names on different hosts do not', () => {
  const sim = new Simulation({ seed: false });
  const a = sim.inject('oom', { host: 'vm-166' });
  const duplicate = sim.inject('oom', { host: 'vm-166' });
  const b = sim.inject('oom', { host: 'vm-095' });
  assert.equal(a.id, duplicate.id);
  assert.equal(a.occurrences.length, 2);
  assert.notEqual(a.id, b.id);
  assert.equal(sim.incidents.length, 2);
});

test('unsupported and stale signals escalate without a model diagnosis', () => {
  for (const kind of ['unsupported', 'stale']) {
    const { sim, incident } = ready(kind);
    assert.equal(incident.status, 'escalated');
    assert.equal(incident.modelCalls, 0);
    assert.equal(incident.diagnosis, null);
    assert.ok(incident.evidence.length > 0);
    assert.equal(sim.actions.length, 0);
  }
});

test('failed and indeterminate actions escalate once; success is not recovery', () => {
  for (const result of ['failed', 'indeterminate', 'verification_failed']) {
    const { sim, incident } = ready('cache', { actionResult: result });
    sim.answer(incident.id, 'approved');
    sim.tick(40);
    assert.equal(incident.status, 'escalated', result);
    assert.equal(sim.actions.length, 1);
    assert.notEqual(incident.outcome, 'remediated');
    sim.tick(100);
    assert.equal(sim.actions.length, 1);
  }
});

test('external recovery cancels a pending proposal and prevents dispatch', () => {
  const { sim, incident } = ready();
  sim.restore(incident.id);
  assert.equal(incident.outcome, 'resolved_externally');
  assert.equal(sim.answer(incident.id, 'approved').ok, false);
  sim.tick(20);
  assert.equal(sim.actions.length, 0);
});

test('console is simulated and bounded; mutation and prompt injection are refused', () => {
  const sim = new Simulation({ seed: false });
  assert.match(sim.console('docker ps', 'vm-166').text, /argus-lab-api/);
  assert.equal(sim.console('docker restart argus-lab-api', 'vm-166').ok, false);
  assert.equal(sim.console('docker ps; rm -rf /', 'vm-166').ok, false);
  const incident = sim.inject('injection');
  sim.tick(20);
  assert.ok(incident.evidence.some(e => e.body.includes('[REDACTED]')));
  assert.ok(sim.audit.some(e => e.type === 'security.injection_refused'));
  assert.equal(sim.actions.length, 0);
});

test('all scenario definitions complete a bounded investigation', () => {
  const sim = new Simulation({ seed: false });
  for (const kind of Object.keys(sim.scenarios)) {
    const i = sim.inject(kind);
    sim.tick(20);
    assert.ok(['awaiting_approval', 'diagnosed', 'escalated', 'closed'].includes(i.status), kind);
    assert.ok(i.evidence.length >= 3, kind);
  }
});

test('evidence digests match SHA-256 and nested proposal values are immutable', () => {
  const { createHash } = require('node:crypto');
  for (const text of ['', 'abc', 'Argus evidence: vm-166 → cache', 'a'.repeat(300)]) {
    assert.equal(sha256(text), createHash('sha256').update(text).digest('hex'));
  }
  const { incident } = ready();
  assert.ok(Object.isFrozen(incident.proposal.arguments));
  assert.ok(Object.isFrozen(incident.proposal.evidenceIds));
  assert.ok(Object.isFrozen(incident.proposal.evidenceIds[0]));
});

test('an answer for a different frozen proposal digest is refused and audited', () => {
  const { sim, incident } = ready();
  const response = sim.answer(incident.id, 'approved', '', '0'.repeat(64));
  assert.equal(response.ok, false);
  assert.equal(incident.approval.state, 'pending');
  assert.equal(sim.actions.length, 0);
  assert.ok(sim.audit.some(a => a.type === 'approval.refused' && a.message.includes('digest mismatch')));
});
