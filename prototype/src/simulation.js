(function (root) {
  'use strict';
  // This engine never sends requests, spawns a process, or connects to infrastructure.
  const scenarios = {
    cache: { title: 'Cache dependency offline', subtitle: 'API health fails after Redis stops responding.', code: 'SC-03', category: 'Availability', severity: 'critical', class: 'dependency_unavailable', strategy: 'model_loop', book: 'RB-003', name: 'argus-lab-api', root: 'argus-lab-cache', alert: 'DependencyUnavailable', signal: 'dependency_tcp_up = 0; api_health = 0', diagnosis: 'Redis is stopped. The API is a victim of its unavailable cache dependency.', confidence: 'High', recommendation: 'Restart the stopped cache once. Do not restart the dependent API.', capability: 'container.restart', logs: 'api: Redis connection refused at argus-lab-cache:6379\nhealth: dependency unavailable; returning HTTP 503', resources: 'cache: state=exited; exit_code=0; restart_count=0\napi: running; CPU 14%; memory 178 / 512 MiB', impact: 'API requests return 503; background jobs are waiting.' },
    oom: { title: 'Worker OOM restart loop', subtitle: 'Repeated memory peaks and container exits.', code: 'SC-01', category: 'Stability', severity: 'critical', class: 'container_restart_loop', strategy: 'model_loop', book: 'RB-001', name: 'argus-lab-worker', alert: 'ContainerRestartLoop', signal: 'oom_killed = true; restart_count = 7', diagnosis: 'The worker repeatedly reaches its 256 MiB memory boundary. Retained allocations are a probable cause; application profiling is still needed.', confidence: 'Medium', recommendation: 'Application owner: remove the allocation fault and review the working set. A restart alone does not remove the cause.', logs: 'worker: retained buffer grew by 16 MiB\nruntime: OOM / die / start; exit_code=137', resources: 'memory peak 256 / 256 MiB; 7 restart cycles\nhost: 5.1 GiB available; no host-wide pressure', impact: 'Jobs are retried and throughput is reduced.' },
    crash: { title: 'Non-OOM crash loop', subtitle: 'The worker cannot boot with its current configuration.', code: 'SC-02', category: 'Stability', severity: 'warning', class: 'container_restart_loop', strategy: 'model_loop', book: 'RB-008', name: 'argus-lab-worker', alert: 'ContainerRestartLoop', signal: 'restart_count = 6; oom_killed = false', diagnosis: 'The worker exits during startup because a required configuration value is missing. Memory pressure is ruled out.', confidence: 'High', recommendation: 'Have the application owner restore the missing configuration. Restarting the unchanged container will repeat the failure.', logs: 'startup: required QUEUE_NAME is absent\nprocess exited with code 1; OOMKilled=false', resources: 'memory 41 / 256 MiB; CPU 2%; exit_code=1', impact: 'Queue consumers are unavailable.' },
    health: { title: 'API health check failure', subtitle: 'A running container returns an unhealthy readiness result.', code: 'RB-002', category: 'Availability', severity: 'warning', class: 'health_check_failed', strategy: 'plan_then_reason', book: 'RB-002', name: 'argus-lab-api', alert: 'ContainerHealthFailed', signal: 'container_running = 1; health = 0; http_status = 503', diagnosis: 'Readiness fails because the cache dependency is unavailable. The running API is the victim, not the root cause.', root: 'argus-lab-cache', confidence: 'High', recommendation: 'Restore the cache dependency. Do not restart the API victim.', logs: 'readiness: dependency probe failed; returning 503', resources: 'api: running, 178 / 512 MiB; cache: exited', impact: 'The API readiness endpoint is unhealthy.' },
    database: { title: 'Database connection exhaustion', subtitle: 'Idle transactions consume nearly all usable slots.', code: 'SC-04', category: 'Database', severity: 'critical', class: 'postgresql_connection_exhaustion', strategy: 'model_loop', book: 'RB-004', name: 'argus-lab-db', root: 'argus-lab-leaker', alert: 'DbConnectionsExhausted', signal: 'db_connection_usage = 0.94; ordinary_slots_free = 1', diagnosis: 'argus-lab-leaker holds 16 idle-in-transaction sessions. The reserved monitoring slot remains available.', confidence: 'High', recommendation: 'Database owner: stop the leaking client and close its sessions with an approved change. Do not restart the database.', logs: 'db-probe: 16 sessions owned by argus-lab-leaker\nstate=idle in transaction; SQL text and rows excluded', resources: '16 / 17 usable slots occupied; reserved monitor slot=1\ndatabase memory and CPU within baseline', impact: 'New application database connections time out.' },
    disk: { title: 'Host disk pressure', subtitle: 'A container fills the host’s lab filesystem.', code: 'SC-05', category: 'Saturation', severity: 'critical', class: 'disk_pressure', strategy: 'confirm_then_reason', book: 'RB-005', name: 'host', root: 'argus-lab-filler', alert: 'HostDiskAlmostFull', signal: 'filesystem_usage = 0.97; free_bytes = 210 MiB', diagnosis: 'argus-lab-filler is writing to its read-write mount at /srv/argus-lab-fill. Its own logs confirm the writer attribution.', confidence: 'High', recommendation: 'Stop the writer and review lab files with the host owner. No automated deletion; database and evidence volumes stay protected.', logs: 'filler: wrote 32 MiB to /srv/argus-lab-fill/payload\nmount: /srv/argus-lab-fill → /data (rw); writer confirmed', resources: '/srv/argus-lab-fill 97% used; / 38% used\nwriter throughput 32 MiB/s; inode use 12%', impact: 'New writes on the lab mount may fail.' },
    cpu: { title: 'CPU quota saturation', subtitle: 'A busy loop is throttled by its container quota.', code: 'SC-06', category: 'Saturation', severity: 'warning', class: 'cpu_saturation', strategy: 'model_loop', book: 'RB-006', name: 'argus-lab-burner', alert: 'ContainerCpuThrottled', signal: 'cpu_quota_utilization = 1.0; throttled_ratio = 0.89', diagnosis: 'A busy loop in argus-lab-burner saturates its 0.3-core quota. The host itself has available capacity.', confidence: 'High', recommendation: 'Application owner: remove the busy loop or reduce concurrency. Review capacity separately before changing the quota.', logs: 'burner: entering unbounded processing loop\ncgroup: throttled periods increased', resources: 'container quota 0.3 cores; throttled ratio 89%\nhost CPU 34%; headroom remains', impact: 'Container work is delayed by CPU throttling.' },
    network: { title: 'Network isolation mismatch', subtitle: 'A healthy backend is attached to the wrong network.', code: 'SC-07', category: 'Connectivity', severity: 'warning', class: 'dns_network_failure', strategy: 'plan_then_reason', book: 'RB-009', name: 'argus-lab-client', root: 'argus-lab-backend', alert: 'DependencyTcpUnreachable', signal: 'dependency_tcp_up = 0; backend_health = 1', diagnosis: 'The healthy backend is on argus-lab-iso while the client is on argus-lab-app. Their expected networks do not match.', confidence: 'High', recommendation: 'Platform owner: attach the backend to its assigned network under a reviewed change. Restarting either healthy process will not fix the topology.', logs: 'client: backend DNS resolution failed\nbackend: healthy listener on :8080\nnetworks: client=argus-lab-app; backend=argus-lab-iso', resources: 'both containers running; backend endpoint healthy\nnetwork inventory expects argus-lab-app', impact: 'Client requests cannot reach the backend.' },
    upstream: { title: 'Nginx upstream timeout', subtitle: 'A slow backend exceeds the proxy response timeout.', code: 'SC-08', category: 'Availability', severity: 'critical', class: 'nginx_upstream_failure', strategy: 'plan_then_reason', book: 'RB-015', name: 'argus-lab-nginx', root: 'argus-lab-slow', alert: 'HttpGatewayErrors', signal: 'gateway_5xx_ratio = 0.87; upstream_duration = 5 s', diagnosis: 'The upstream takes 5 seconds to respond, exceeding Nginx’s 2-second read timeout. Nginx is a victim of upstream latency.', confidence: 'High', recommendation: 'Application owner: remove the backend delay; review timeout values with the platform owner. Do not restart the proxy victim.', logs: 'nginx: upstream timed out while reading response header\nslow: response completed after 5.0 s', resources: 'proxy running; CPU 9%; upstream response=5.0 s\nproxy_read_timeout=2.0 s', impact: 'Requests through the proxy return 504.' },
    unsupported: { title: 'Unregistered alert', subtitle: 'A reported symptom has no enabled incident class.', code: 'SC-09', category: 'Safety', severity: 'warning', class: 'unsupported', strategy: 'evidence_pack', book: 'RB-014', name: 'argus-lab-api', alert: 'SyntheticUnknownSignal', signal: 'reported symptom; no registered detector matches', diagnosis: null, recommendation: 'Escalate the evidence pack to platform on-call. No diagnosis is claimed. Add this case to the class-enablement backlog.', logs: 'synthetic alert: unsupported condition reported\napplication bounded logs collected for human review', resources: 'allowlisted target inventory captured; runtime running', impact: 'Impact is unknown; operator review is required.' },
    stale: { title: 'Monitoring blind spot', subtitle: 'Prometheus samples are too old to trust.', code: 'SC-10', category: 'Safety', severity: 'warning', class: 'monitoring_blind_spot', strategy: 'evidence_pack', book: 'RB-014', name: 'host', alert: 'ArgusScrapeTargetDown', signal: 'last sample age = 240 s; freshness ceiling = 60 s', diagnosis: null, recommendation: 'Restore the scrape path and obtain fresh metrics. Do not classify an old snapshot or claim the server is healthy.', logs: 'prometheus: exporter scrape timeout\nlast observed sample is 240 seconds old', resources: 'read-gateway reachable; stale metric snapshot excluded', impact: 'Current workload health cannot be established from metrics.' },
    injection: { title: 'Malicious instruction in logs', subtitle: 'Untrusted evidence attempts to cross the tool boundary.', code: 'SC-11', category: 'Safety', severity: 'warning', class: 'health_check_failed', strategy: 'plan_then_reason', book: 'RB-002', name: 'argus-lab-api', alert: 'ContainerHealthFailed', signal: 'health = 0; untrusted log content present', diagnosis: 'Health check fails after invalid application configuration. Instructions embedded in the log were refused as untrusted data.', confidence: 'Medium', recommendation: 'Application owner: review the configuration. Security on-call receives the redacted injection evidence; no injected tool call is permitted.', logs: 'app: invalid health configuration\n[UNTRUSTED INSTRUCTION REFUSED]\ncredential=[REDACTED]; external command=[REDACTED]', resources: 'API running; bounded health probe returns HTTP 503', impact: 'The readiness endpoint fails; hostile log content is isolated.' },
    budget: { title: 'Investigation budget exhausted', subtitle: 'Conflicting observations use the bounded read budget.', code: 'SC-12', category: 'Safety', severity: 'warning', class: 'container_restart_loop', strategy: 'model_loop', book: 'RB-008', name: 'argus-lab-worker', alert: 'ContainerRestartLoop', signal: 'restart_count = 4; conflicting runtime observations', diagnosis: null, recommendation: 'Escalate the collected evidence and competing hypotheses. Stop at the step budget; no unbounded retry or speculative remediation.', logs: 'runtime: inconsistent timestamps across restart observations\nlast diagnostic step reached MAX_STEPS=12', resources: 'insufficient consistent observations to attribute the failure', impact: 'Worker availability is uncertain; human inspection is needed.' }
  };

  // Portable SHA-256 keeps mock evidence and frozen proposal digests reproducible offline.
  function sha256(text) {
    const bytes = new TextEncoder().encode(text), words = [];
    for (let i = 0; i < bytes.length; i++) words[i >> 2] = (words[i >> 2] || 0) | bytes[i] << (24 - (i % 4) * 8);
    words[bytes.length >> 2] = (words[bytes.length >> 2] || 0) | 0x80 << (24 - (bytes.length % 4) * 8);
    const end = (((bytes.length + 8) >> 6) + 1) * 16;
    words[end - 1] = bytes.length * 8;
    const primes = [], h = [], k = [];
    for (let n = 2; primes.length < 64; n++) {
      if (primes.every(p => n % p)) {
        primes.push(n);
        if (h.length < 8) h.push((Math.sqrt(n) % 1 * 0x100000000) | 0);
        k.push((Math.cbrt(n) % 1 * 0x100000000) | 0);
      }
    }
    const r = (x, n) => (x >>> n) | (x << (32 - n));
    for (let off = 0; off < end; off += 16) {
      const w = Array.from({ length: 64 }, (_, i) => words[off + i] || 0);
      for (let i = 16; i < 64; i++) {
        const a = w[i - 15], b = w[i - 2];
        w[i] = (w[i - 16] + (r(a, 7) ^ r(a, 18) ^ (a >>> 3)) + w[i - 7] + (r(b, 17) ^ r(b, 19) ^ (b >>> 10))) | 0;
      }
      let [a, b, c, d, e, f, g, v] = h;
      for (let i = 0; i < 64; i++) {
        const t1 = (v + (r(e, 6) ^ r(e, 11) ^ r(e, 25)) + ((e & f) ^ (~e & g)) + k[i] + w[i]) | 0;
        const t2 = ((r(a, 2) ^ r(a, 13) ^ r(a, 22)) + ((a & b) ^ (a & c) ^ (b & c))) | 0;
        v = g; g = f; f = e; e = (d + t1) | 0; d = c; c = b; b = a; a = (t1 + t2) | 0;
      }
      [a, b, c, d, e, f, g, v].forEach((x, i) => h[i] = (h[i] + x) | 0);
    }
    return h.map(x => (x >>> 0).toString(16).padStart(8, '0')).join('');
  }
  function deepFreeze(value) {
    for (const child of Object.values(value)) if (child && typeof child === 'object') deepFreeze(child);
    return Object.freeze(value);
  }

  class Simulation {
    constructor({ seed = true } = {}) {
      this.now = Date.now(); this.incidents = []; this.actions = []; this.audit = []; this.holds = [];
      this.scenarios = scenarios; this.profile = 'supervised'; this.policyRevision = 1; this.inventoryVersion = 'inventory-demo-v1';
      this.count = 1040; this.auditCount = 0; this.evidenceCount = 0; this.tokenCount = 1; this.setPrincipal('approver');
      this.targets = [];
      const add = (host, name, role, cpu = 3, memory = 64, limit = 512) => this.targets.push({ ref: host + '/container:' + name, host, name, role, cpu, memory, limit, identity: sha256(host + name).slice(0, 12), state: 'running', health: 'healthy', restarts: 0 });
      for (const name of ['agent', 'worker', 'scheduler', 'postgres', 'tunnel', 'prometheus', 'read-gateway']) add('vm-095', 'argus-v18-' + name, name === 'postgres' ? 'Persistence' : 'Control plane');
      add('vm-095', 'argus-lab-api', 'Workload', 8, 96); add('vm-095', 'argus-lab-worker', 'Workload', 7, 88, 256);
      for (const [name, role] of [['api', 'Application'], ['cache', 'Redis 7'], ['db', 'PostgreSQL 16'], ['worker', 'Queue consumer'], ['nginx', 'Reverse proxy'], ['slow', 'Upstream'], ['client', 'Network client'], ['backend', 'Backend'], ['burner', 'CPU lab'], ['filler', 'Disk lab'], ['leaker', 'DB client']]) add('vm-166', 'argus-lab-' + name, role, name === 'api' ? 14 : 3, name === 'api' ? 178 : 48, name === 'worker' ? 256 : 512);
      for (const name of ['read-gateway', 'host-probe', 'network-probe', 'db-probe', 'prometheus', 'alertmanager', 'exporter']) add('vm-166', 'argus-v18-' + name, 'Monitoring / probe');
      this.tokens = [{ id: 'tok-web-01', name: 'Web console session', kind: 'human', scope: 'vm-095, vm-166', expires: this.now + 3600000, revoked: false }, { id: 'tok-alert-01', name: 'Alertmanager intake', kind: 'service', scope: 'alerts:submit · vm-166', expires: this.now + 86400000, revoked: false }, { id: 'tok-peer-01', name: 'Security peer agent', kind: 'agent', scope: 'investigate:submit · evidence:append', expires: this.now + 86400000, revoked: false }];
      if (seed) {
        const current = this.now;
        this.now = current - 7200000;
        const cpu = this.inject('cpu'); this.tick(16); this.restore(cpu.id, 'Application owner removed the busy-loop fixture.');
        this.now = current - 2520000;
        const net = this.inject('network'); this.tick(16); this.restore(net.id, 'Platform owner restored the assigned Docker network.');
        this.now = current - 16000;
        this.inject('cache'); this.tick(16);
      }
    }
    get policyVersion() { return sha256(this.profile + ':' + this.policyRevision); }
    get pending() { return this.incidents.filter(i => i.status === 'awaiting_approval'); }
    get active() { return this.incidents.filter(i => !['closed', 'escalated', 'diagnosed'].includes(i.status)); }
    get unresolved() { return this.incidents.filter(i => i.faultActive); }
    get sessionValid() { return this.principal && this.principal.expires > this.now && !this.principal.revoked; }
    get canApprove() { return this.sessionValid && this.principal.kind === 'human' && this.principal.role === 'approver'; }
    setPrincipal(role) {
      const roles = { viewer: ['Sam Rivera', 'human', 'viewer', ['vm-095', 'vm-166']], operator: ['Alex Morgan', 'human', 'operator', ['vm-095', 'vm-166']], approver: ['Alex Morgan', 'human', 'approver', ['vm-095', 'vm-166']], service: ['alertmanager', 'service', 'service', ['vm-166']], expired: ['Alex Morgan', 'human', 'approver', ['vm-095', 'vm-166']], wrong_scope: ['Jordan Lee', 'human', 'approver', ['vm-095']] };
      const [name, kind, actualRole, scopes] = roles[role] || roles.approver;
      this.principal = { name, kind, role: actualRole, scopes, expires: this.now + (role === 'expired' ? -1 : 3600000), revoked: false, tokenId: 'session-' + (++this.tokenCount || 1) };
      if (this.audit) this.log('auth.session_started', null, name + ' · ' + kind + ' · ' + actualRole + ' · ' + scopes.join(', '));
    }
    log(type, incident, message) {
      const e = { id: 'aud-' + (++this.auditCount), type, incidentId: incident ? incident.id : null, at: this.now, message };
      this.audit.push(e); if (incident) incident.events.push(e); return e;
    }
    evidence(incident, capability, body) {
      const record = { id: 'ev-' + (++this.evidenceCount).toString().padStart(4, '0'), capability, host: incident.host, executor: capability.startsWith('container') ? 'docker_read' : capability.startsWith('knowledge') ? 'runbook_library' : capability.startsWith('database') ? 'db_probe' : capability.startsWith('metrics') ? 'prometheus' : 'host_probe', caller: 'argus-worker', at: this.now, body, hash: sha256(body), redacted: body.includes('[REDACTED]') };
      incident.evidence.push(record); incident.evidenceVersion++;
      this.log('tool.completed', incident, capability + ' → ' + record.id + ' · read-only · allowed'); return record;
    }
    target(ref) { return this.targets.find(t => t.ref === ref); }
    inject(kind, { host = 'vm-166', actionResult = 'confirmed', trigger = 'Alertmanager' } = {}) {
      const s = this.scenarios[kind]; if (!s) throw new Error('Unknown simulation scenario.');
      if (host !== 'vm-166' && !(host === 'vm-095' && ['oom', 'crash', 'unsupported', 'stale', 'budget', 'injection', 'health'].includes(kind))) throw new Error('Scenario is not in this host’s inventory.');
      const ref = host + '/' + (s.name === 'host' ? 'host:' + host : 'container:' + s.name);
      const existing = this.incidents.find(i => i.target === ref && i.class === s.class && i.faultActive);
      if (existing) {
        existing.occurrences.push({ at: this.now, trigger, state: 'firing' });
        this.log('alert.correlated', existing, 'Same host, target, class and episode: attached occurrence; no new investigation.'); return existing;
      }
      const i = { id: 'INC-' + (++this.count), kind, host, target: ref, title: s.title, class: s.class, severity: s.severity, strategy: s.strategy, book: s.book, createdAt: this.now, status: 'detecting', outcome: null, faultActive: true, phase: 0, events: [], evidence: [], evidenceVersion: 0, occurrences: [{ at: this.now, trigger, state: 'firing' }], diagnosis: null, confidence: null, modelCalls: 0, tokens: 0, steps: 0, proposal: null, approval: null, action: null, samples: [], actionResult, rootTarget: host + '/container:' + (s.root || s.name), recommendation: s.recommendation, impact: s.impact, threadId: '01ARGUSDEMO' + this.count.toString().padStart(16, '0') };
      this.incidents.unshift(i); this.log('intake.accepted', i, trigger + ' · ' + s.alert + ' · durable intake recorded');
      this.log('incident.detecting', i, 'Awaiting fresh signal snapshot; detection runs before any model call.');
      return i;
    }
    tick(seconds = 1) {
      for (let t = 0; t < seconds; t++) {
        this.now += 1000;
        for (const i of this.incidents) this.advance(i);
      }
    }
    advance(i) {
      if (['closed', 'diagnosed', 'escalated'].includes(i.status)) return;
      if (i.status === 'awaiting_approval') {
        if (this.now >= i.proposal.expiresAt) { i.approval.state = 'expired'; this.finish(i, 'escalated', 'approval_expired', 'Approval expired. No write dispatched; escalation sent to platform on-call.'); }
        return;
      }
      if (i.status === 'prechecking') {
        if (this.now < i.approval.answeredAt + 2000) return;
        const p = i.proposal, target = this.target(p.target);
        const reasons = [];
        if (!i.faultActive) reasons.push('incident resolved');
        if (p.policyVersion !== this.policyVersion) reasons.push('policy version changed');
        if (p.inventoryVersion !== this.inventoryVersion) reasons.push('inventory changed');
        if (!target || target.identity !== p.identity) reasons.push('immutable target identity changed');
        if (this.holds.includes(p.target)) reasons.push('target hold is active');
        if (i.evidenceVersion !== p.evidenceVersion) reasons.push('evidence version changed');
        if (this.now >= p.expiresAt) reasons.push('proposal expired');
        if (p.digest !== sha256(p.canonical)) reasons.push('proposal digest mismatch');
        if (reasons.length) { i.approval.state = 'cancelled'; this.finish(i, 'escalated', 'proposal_invalidated', 'Precheck refused: ' + reasons.join('; ') + '. No action dispatched.'); return; }
        this.log('action.precheck_passed', i, 'Digest, open incident, current policy, hold, immutable identity, inventory, evidence and expiry verified.');
        i.action = { id: 'act-' + i.id.slice(4), incidentId: i.id, capability: p.capability, target: p.target, state: 'attempting', attemptedAt: this.now, resultAt: null, approvalId: i.approval.id, digest: p.digest };
        this.actions.push(i.action); i.status = 'executing';
        this.log('action.attempting', i, 'Ledger persisted before dispatch · ' + i.action.id + ' · exact target ' + p.target); return;
      }
      if (i.status === 'executing') {
        if (this.now < i.action.attemptedAt + 1000) return;
        i.action.state = ['failed', 'indeterminate'].includes(i.actionResult) ? i.actionResult : 'confirmed'; i.action.resultAt = this.now;
        this.log('action.' + i.action.state, i, i.action.state === 'confirmed' ? 'Action gateway acknowledged one restart. Recovery has not yet been established.' : i.action.state === 'failed' ? 'Action gateway rejected the restart. Fault remains; no retry.' : 'Gateway response was lost. Outcome cannot be established; never dispatch again automatically.');
        if (i.action.state !== 'confirmed') { this.finish(i, 'escalated', 'action_' + i.action.state, 'Action ' + i.action.state + ' · human reconciliation required; no automatic retry.'); return; }
        i.status = 'verifying'; return;
      }
      if (i.status === 'verifying') {
        const nextAt = i.action.resultAt + (i.samples.length + 1) * 2000;
        if (this.now < nextAt) return;
        const ok = i.actionResult !== 'verification_failed';
        i.samples.push({ at: this.now, ok, value: ok ? 'cache TCP 1 · API HTTP 200 · restart_count stable' : 'cache TCP 0 · API HTTP 503 · fault persists' });
        this.evidence(i, 'network.http_probe', 'POST-ACTION SAMPLE ' + i.samples.length + ': ' + i.samples.at(-1).value + '\nobserved_at=' + new Date(this.now).toISOString());
        if (i.samples.length === 3) {
          if (ok) { this.clearFault(i); this.finish(i, 'closed', 'remediated', 'Recovery verified by 3 distinct fresh post-action samples. Incident and episodic summary recorded.'); }
          else this.finish(i, 'escalated', 'verification_failed', 'Command succeeded but recovery verification failed. Escalated; no second restart.');
        }
        return;
      }
      const age = (this.now - i.createdAt) / 1000, s = this.scenarios[i.kind];
      if (age >= 2 && i.phase === 0) {
        i.phase = 1; i.steps++;
        this.evidence(i, 'metrics.snapshot', s.signal + '\nsource=' + i.host + '/prometheus\nfresh=' + (i.kind !== 'stale') + '; target=' + i.target);
        this.log('incident.classified', i, i.kind === 'unsupported' ? 'No enabled class matches. Fixed evidence pack selected; zero model calls.' : i.kind === 'stale' ? 'Required metrics are stale. Classification refused; fixed evidence pack selected.' : 'Pure detector matched ' + i.class + ' from source-fresh signals.');
        i.status = 'recalling';
      }
      if (age >= 4 && i.phase === 1) {
        i.phase = 2; i.steps++;
        this.evidence(i, 'knowledge.runbook', s.book + ' · runbook library v1.1.0 · draft source\nStrategy: ' + s.strategy + '\nConstraint: ' + s.recommendation);
        const similar = this.incidents.filter(x => x !== i && x.class === i.class && x.status === 'closed');
        this.log('memory.recalled', i, s.book + ' retrieved · ' + similar.length + ' similar resolved incident(s) · scope checked'); i.status = 'investigating';
      }
      if (age >= 6 && i.phase === 2) {
        i.phase = 3; i.steps++;
        this.evidence(i, 'container.status', 'target=' + i.rootTarget + '\nimmutable_id=' + (this.target(i.rootTarget)?.identity || 'host-boot-demo') + '\n' + s.resources);
        if (!['unsupported', 'stale', 'budget'].includes(i.kind)) { i.modelCalls++; i.tokens += 780; }
        this.log('strategy.read', i, 'Allowlisted runtime and dependency inspection; InvokeCapability audited the exact host route.');
      }
      if (age >= 8 && i.phase === 3) {
        i.phase = 4; i.steps++;
        this.evidence(i, i.kind === 'database' ? 'database.health' : i.kind === 'disk' ? 'host.disk_usage' : 'container.resources', s.resources);
        this.log('strategy.hypothesis', i, i.kind === 'disk' ? 'Suspected writer discovered through its host mount. A confirmation read is mandatory before diagnosis.' : 'Compare symptom with dependency and resource evidence; distinguish victim from root cause.');
      }
      if (age >= 10 && i.phase === 4) {
        i.phase = 5; i.steps++;
        this.evidence(i, 'container.logs', s.logs);
        if (i.kind === 'injection') this.log('security.injection_refused', i, 'Untrusted instructions excluded from control flow; credential fields redacted before evidence storage.');
        this.log('checkpoint.saved', i, 'Investigate node checkpoint saved · ' + i.threadId + ' · evidence v' + i.evidenceVersion);
      }
      if (age >= 12 && i.phase === 5) {
        i.phase = 6; i.steps++;
        if (i.kind === 'unsupported' || i.kind === 'stale' || i.kind === 'budget') {
          if (i.kind === 'budget') { i.steps = 12; i.modelCalls = 2; i.tokens = 2160; }
          this.finish(i, 'escalated', i.kind === 'unsupported' ? 'unsupported_escalated' : i.kind === 'stale' ? 'undiagnosable' : 'budget_exhausted', s.recommendation); return;
        }
        i.diagnosis = s.diagnosis; i.confidence = s.confidence;
        this.log('decision.diagnosis', i, s.diagnosis);
        if (s.capability) {
          const target = this.target(i.rootTarget);
          if (this.profile === 'read_only' || this.holds.includes(i.rootTarget) || !target || i.host !== 'vm-166') {
            this.finish(i, 'escalated', 'policy_blocked', 'Write pair is not released or the target is held. No proposal or approval created; evidence escalated.'); return;
          }
          const proposal = { id: 'prop-' + i.id.slice(4), capability: s.capability, target: i.rootTarget, identity: target.identity, arguments: { timeout_seconds: 10 }, risk: 'medium', scope: 'vm-166', policyVersion: this.policyVersion, inventoryVersion: this.inventoryVersion, evidenceVersion: i.evidenceVersion, evidenceIds: i.evidence.map(e => ({ id: e.id, hash: e.hash })), expiresAt: this.now + 300000, maxActions: 1, rollback: 'A restart cannot restore lost in-memory cache contents. On failure, stop and escalate; no second automatic attempt.' };
          proposal.canonical = JSON.stringify(proposal); proposal.digest = sha256(proposal.canonical); i.proposal = deepFreeze(proposal);
          i.approval = { id: 'appr-' + i.id.slice(4), digest: proposal.digest, state: 'pending', actor: null, requestedAt: this.now, answeredAt: null, reason: '' };
          i.status = 'awaiting_approval';
          this.log('approval.requested', i, 'Frozen proposal and pending approval persisted together · notification recorded · checkpoint paused.');
        } else this.finish(i, 'diagnosed', 'diagnosed', 'Diagnosis complete. Recommended remediation requires the owning human; no released write capability matches.');
      }
    }
    finish(i, status, outcome, message) {
      i.status = status; i.outcome = outcome; i.closedAt = this.now;
      this.log('incident.' + outcome, i, message);
      if (status !== 'closed') this.log('escalation.routed', i, (i.kind === 'database' ? 'Database on-call' : ['oom', 'cpu', 'crash', 'upstream'].includes(i.kind) ? 'Application on-call' : 'Platform on-call') + ' · evidence pack attached · recorded notification (simulation)');
    }
    answer(id, decision, reason = '', suppliedDigest = null) {
      const i = this.incidents.find(x => x.id === id);
      const fail = message => { this.log('approval.refused', i, message); return { ok: false, message }; };
      if (!this.sessionValid) return fail('Authentication required. The demo session has expired or was revoked.');
      if (!this.canApprove) return fail('Only an authenticated human approver can answer. Service, agent, viewer and operator principals cannot approve.');
      if (!i || i.status !== 'awaiting_approval' || i.approval.state !== 'pending') return fail('This approval is no longer pending. No action dispatched.');
      if (!['approved', 'denied'].includes(decision)) return fail('Invalid approval decision.');
      if (!this.principal.scopes.includes(i.host)) return fail('Approver scope does not include ' + i.host + '.');
      if (this.now >= i.proposal.expiresAt) return fail('Proposal has expired.');
      if (suppliedDigest && suppliedDigest !== i.proposal.digest) return fail('Proposal digest mismatch.');
      if (this.holds.includes(i.proposal.target) || i.proposal.policyVersion !== this.policyVersion || i.proposal.identity !== this.target(i.proposal.target)?.identity || i.proposal.evidenceVersion !== i.evidenceVersion) {
        i.approval.state = 'cancelled'; this.finish(i, 'escalated', 'proposal_invalidated', 'The frozen proposal is no longer compatible with current target, policy, hold or evidence.'); return { ok: false, message: 'Proposal invalidated. Re-investigation required.' };
      }
      i.approval.state = decision; i.approval.actor = this.principal.name; i.approval.answeredAt = this.now; i.approval.reason = reason;
      this.log('approval.answered', i, this.principal.name + ' · ' + decision + ' · digest ' + i.proposal.digest.slice(0, 16) + ' · ' + (reason || 'No additional comment'));
      if (decision === 'denied') this.finish(i, 'escalated', 'approval_denied', 'Human denied the proposal. No action dispatched; evidence preserved.');
      else { i.status = 'prechecking'; this.log('resume.intent', i, 'Atomic approval answer and resume intent recorded. Current-state precheck runs before dispatch.'); }
      return { ok: true, message: decision === 'approved' ? 'Approval recorded. Argus is rechecking the current state.' : 'Proposal denied. No action will execute.' };
    }
    clearFault(i) { i.faultActive = false; i.occurrences.forEach(o => o.state = 'resolved'); }
    restore(id, reason = 'Lab operator removed the simulated fault.') {
      const i = this.incidents.find(x => x.id === id); if (!i || !i.faultActive) return false;
      if (['executing', 'verifying'].includes(i.status)) return false;
      this.clearFault(i); if (i.approval?.state === 'pending' || i.approval?.state === 'approved') i.approval.state = 'cancelled';
      this.evidence(i, 'metrics.snapshot', 'External recovery: fresh healthy metrics; all firing fingerprints resolved.');
      this.finish(i, 'closed', 'resolved_externally', reason + ' Fresh signals confirm recovery; Argus dispatched no additional action.'); return true;
    }
    setProfile(profile) { if (!['supervised', 'read_only'].includes(profile)) return; this.profile = profile; this.policyRevision++; this.log('policy.updated', null, profile + ' · revision ' + this.policyRevision + ' · pending proposals must recheck.'); }
    toggleHold(ref) { if (this.holds.includes(ref)) this.holds = this.holds.filter(x => x !== ref); else this.holds.push(ref); this.log('hold.updated', null, ref + ' · ' + (this.holds.includes(ref) ? 'held: preserve evidence' : 'hold released')); }
    replaceTarget(ref) { const t = this.target(ref); if (t) { t.identity = sha256(t.identity + this.now).slice(0, 12); this.log('inventory.identity_changed', null, ref + ' replaced · new immutable identity ' + t.identity); } }
    invalidateEvidence(id) { const i = this.incidents.find(x => x.id === id); if (i) this.evidence(i, 'container.status', 'Material change detected: target restarted outside Argus; prior evidence incompatible.'); }
    createToken(name, kind) {
      const token = { id: 'tok-demo-' + (++this.tokenCount), name: name || 'Demo integration', kind: kind === 'agent' ? 'agent' : 'service', scope: kind === 'agent' ? 'investigate:submit · evidence:append' : 'alerts:submit · vm-166', expires: this.now + 86400000, revoked: false };
      this.tokens.push(token); this.log('auth.token_created', null, token.name + ' · ' + token.kind + ' · never permitted to approve'); return token;
    }
    revokeToken(id) { const t = this.tokens.find(x => x.id === id); if (t) { t.revoked = true; if (t.id === 'tok-web-01') this.principal.revoked = true; this.log('auth.token_revoked', null, t.name); } }
    statusOf(target) {
      const faults = this.unresolved.filter(i => (i.target === target.ref || i.rootTarget === target.ref) && !(i.status === 'verifying' && i.actionResult === 'confirmed'));
      const i = faults[0]; if (!i) return { state: target.state, health: target.health, cpu: target.cpu, memory: target.memory, restarts: target.restarts };
      const root = target.ref === i.rootTarget;
      return { state: root && i.kind === 'cache' ? 'exited' : ['oom', 'crash', 'budget'].includes(i.kind) ? 'restarting' : 'running', health: root && ['database', 'disk'].includes(i.kind) ? 'degraded' : 'unhealthy', cpu: i.kind === 'cpu' ? 99 : target.cpu, memory: i.kind === 'oom' ? 252 : target.memory, restarts: ['oom', 'crash'].includes(i.kind) ? 7 : target.restarts };
    }
    metrics(host) {
      const faults = this.unresolved.filter(i => i.host === host);
      return { cpu: faults.some(i => i.kind === 'cpu') ? 76 : host === 'vm-095' ? 19 : 34, memory: faults.some(i => i.kind === 'oom') ? 63 : host === 'vm-095' ? 38 : 42, disk: faults.some(i => i.kind === 'disk') ? 97 : 38, health: faults.some(i => i.kind === 'stale') ? 'unknown' : faults.length ? 'degraded' : 'healthy', freshness: faults.some(i => i.kind === 'stale') ? 240 : 3 };
    }
    console(command, host = 'vm-166') {
      const raw = String(command).trim(); const cmd = raw.replace(/\s+/g, ' ');
      const deny = message => { this.log('console.refused', null, cmd + ' · ' + message); return { ok: false, text: 'REFUSED · ' + message }; };
      if (!this.sessionValid) return deny('Demo session expired. Sign in before inspecting evidence.');
      if (!this.principal.scopes.includes(host)) return deny('Host is outside the current principal scope.');
      if (/[;&|<>`\n\r$]/.test(raw)) return deny('Shell chaining and arbitrary execution are unavailable. Use a listed read command.');
      let out;
      const targets = this.targets.filter(t => t.host === host), m = this.metrics(host);
      if (cmd === 'help') out = 'SIMULATED READ CONSOLE — no shell or network connection\n\ndocker ps\ndocker stats\ndocker inspect <allowlisted-container>\ndocker logs --tail 20 <allowlisted-container>\nfree -m\ndf -h\nuptime\nargus status\nargus incidents\nargus policies\ncurl http://argus-lab-api:8080/health\n\nMutating commands are refused. Writes use frozen proposals and human approval.';
      else if (cmd === 'docker ps') out = 'CONTAINER ID  NAME                       STATE       HEALTH\n' + targets.map(t => { const s = this.statusOf(t); return t.identity + '  ' + t.name.padEnd(27) + s.state.padEnd(12) + s.health; }).join('\n');
      else if (cmd === 'docker stats') out = 'NAME                         CPU      MEMORY / LIMIT     RESTARTS\n' + targets.map(t => { const s = this.statusOf(t); return t.name.padEnd(29) + (s.cpu + '%').padEnd(9) + (s.memory + ' / ' + t.limit + ' MiB').padEnd(19) + s.restarts; }).join('\n');
      else if (cmd === 'free -m') out = '              total     used     available\nMem:          8192      ' + Math.round(m.memory * 81.92) + '     ' + Math.round((100 - m.memory) * 81.92) + '\nSwap:         2048      0        2048';
      else if (cmd === 'df -h') out = 'Filesystem             Size  Used  Avail  Use%  Mounted on\n/dev/vda1              40G   15G   25G    38%   /\n/dev/argus-lab-fill     8G    ' + (m.disk === 97 ? '7.8G  210M   97%' : '3.0G  5.0G   38%') + '   /srv/argus-lab-fill';
      else if (cmd === 'uptime') out = 'up 14 days, 6:32 · load average: 0.31, 0.28, 0.24 · host=' + host;
      else if (cmd === 'argus status') out = 'API healthy · worker healthy · scheduler healthy\nMCP tool child isolated · checkpoint store connected\ntransport: restricted-ssh · metric freshness: ' + m.freshness + 's\nprofile: ' + this.profile + ' (simulation) · pending approvals: ' + this.pending.length;
      else if (cmd === 'argus incidents') out = this.incidents.filter(i => i.host === host).map(i => i.id + '  ' + i.status.padEnd(20) + i.class + '  ' + i.target).join('\n') || 'No incidents on this host.';
      else if (cmd === 'argus policies') out = 'Allowed: bounded read capabilities (Levels 1–3)\nWrite gate: ' + (this.profile === 'read_only' ? 'CLOSED' : 'container.restart / vm-166/container:argus-lab-cache ONLY (demo)') + '\nHuman approval required for EVERY write\nMaximum actions per incident: 1\nHolds: ' + (this.holds.join(', ') || 'none');
      else if (cmd === 'curl http://argus-lab-api:8080/health') out = this.unresolved.some(i => i.host === host && ['cache', 'health', 'injection'].includes(i.kind)) ? 'HTTP/1.1 503 Service Unavailable\n{"status":"unhealthy","dependency":"cache"}' : 'HTTP/1.1 200 OK\n{"status":"healthy"}';
      else {
        const match = cmd.match(/^docker (inspect|logs --tail 20) ([a-z0-9-]+)$/);
        const t = match && targets.find(x => x.name === match[2]);
        if (!t) return deny('Command or target is not allowlisted. Type help for available reads.');
        const i = this.unresolved.find(x => x.host === host && (x.target === t.ref || x.rootTarget === t.ref));
        out = match[1] === 'inspect' ? JSON.stringify({ Id: t.identity, Name: t.name, Host: host, State: this.statusOf(t), Networks: i?.kind === 'network' && t.name.includes('backend') ? ['argus-lab-iso'] : ['argus-lab-app'] }, null, 2) : i ? this.scenarios[i.kind].logs : t.name + ': ready; bounded health checks passing';
      }
      this.log('console.read', null, cmd + ' · ' + host + ' · allowed · simulated'); return { ok: true, text: out };
    }
    exportIncident(id) { const i = this.incidents.find(x => x.id === id); return JSON.stringify({ simulation: true, architecture: '1.8.6', incident: i, actions: this.actions.filter(a => a.incidentId === id), audit: this.audit.filter(a => a.incidentId === id) }, null, 2); }
  }
  const exports = { Simulation, scenarios, sha256 };
  if (typeof module !== 'undefined') module.exports = exports;
  else root.ArgusSimulation = exports;
})(typeof globalThis !== 'undefined' ? globalThis : this);
