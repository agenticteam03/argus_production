// Dependency-free browser QA with installed Chrome and Node's built-in CDP client.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { spawn } = require('node:child_process');
const { pathToFileURL } = require('node:url');

const root = path.resolve(__dirname, '..');
const output = path.join(root, '.qa');
const profile = path.join(output, 'browser-' + Date.now());
fs.mkdirSync(profile, { recursive: true });
const chrome = [process.env.ARGUS_QA_BROWSER, 'C:/Program Files/Google/Chrome/Application/chrome.exe', 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'].find(p => p && fs.existsSync(p));
if (!chrome) throw new Error('An installed Chrome or Edge is required for browser QA.');
const browser = spawn(chrome, ['--headless=new', '--disable-gpu', '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0', '--user-data-dir=' + profile, 'about:blank'], { windowsHide: true, stdio: 'ignore' });
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket, seq = 0;
const pending = new Map(), errors = [], requests = [];

async function send(method, params = {}) {
  const id = ++seq;
  const promise = new Promise((resolve, reject) => pending.set(id, { resolve, reject }));
  socket.send(JSON.stringify({ id, method, params }));
  return promise;
}
async function evaluate(expression) {
  const r = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
  if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result.value;
}
async function click(selector) {
  const ok = await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el || el.disabled) return false; el.click(); return true; })()`);
  assert.equal(ok, true, 'Clickable element: ' + selector);
  await sleep(80);
}
async function setValue(selector, value) {
  await evaluate(`(() => { const el = document.querySelector(${JSON.stringify(selector)}); if (!el) throw Error('Missing input'); el.value = ${JSON.stringify(value)}; el.dispatchEvent(new Event('input', {bubbles:true})); el.dispatchEvent(new Event('change', {bubbles:true})); })()`);
}
async function navigate(view, id) { await evaluate(`ArgusPrototype.navigate(${JSON.stringify(view)}, ${JSON.stringify(id || null)})`); await sleep(80); }
async function tick(n) { await evaluate(`ArgusPrototype.simulation.tick(${n}); ArgusPrototype.render();`); }
async function screenshot(name, width = 1440, height = 1140) {
  await send('Emulation.setDeviceMetricsOverride', { width, height, deviceScaleFactor: 1, mobile: width < 600 });
  await sleep(100);
  const { data } = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: true });
  fs.writeFileSync(path.join(output, name + '.png'), Buffer.from(data, 'base64'));
}
let checks = 0;
function pass(name) { checks++; process.stdout.write('PASS ' + name + '\n'); }

(async () => {
  const portFile = path.join(profile, 'DevToolsActivePort');
  for (let tries = 0; tries < 100 && !fs.existsSync(portFile); tries++) await sleep(100);
  if (!fs.existsSync(portFile)) throw new Error('Browser did not expose a local debugging port.');
  const port = fs.readFileSync(portFile, 'utf8').split('\n')[0];
  const targets = await (await fetch('http://127.0.0.1:' + port + '/json/list')).json();
  const target = targets.find(t => t.type === 'page');
  socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { socket.addEventListener('open', resolve); socket.addEventListener('error', reject); });
  socket.addEventListener('message', event => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) { const item = pending.get(msg.id); pending.delete(msg.id); if (msg.error) item.reject(new Error(JSON.stringify(msg.error))); else item.resolve(msg.result); }
    if (msg.method === 'Runtime.exceptionThrown') errors.push(msg.params.exceptionDetails.exception?.description || msg.params.exceptionDetails.text);
    if (msg.method === 'Network.requestWillBeSent') requests.push(msg.params.request.url);
  });
  await send('Runtime.enable'); await send('Page.enable'); await send('Network.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1140, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: pathToFileURL(path.join(root, 'index.html')).href });
  for (let tries = 0; tries < 100; tries++) { if (await evaluate('!!window.ArgusPrototype')) break; await sleep(100); }
  await evaluate('ArgusPrototype.ui.paused = true; ArgusPrototype.render();');
  assert.equal(await evaluate('ArgusPrototype.simulation.pending.length'), 1);
  assert.match(await evaluate('document.body.innerText'), /Operations overview/);
  assert.equal(await evaluate('document.querySelectorAll(".host-card").length'), 2);
  await screenshot('overview'); pass('offline startup with two hosts and a guided pending incident');

  await click('[data-action="review"]');
  assert.match(await evaluate('document.querySelector("[role=dialog]").innerText'), /SHA-256/);
  await screenshot('approval');
  await setValue('#approval-note', 'Restart the stopped root-cause cache once.');
  await click('[data-action="approve"]');
  await tick(10);
  assert.equal(await evaluate('ArgusPrototype.simulation.incidents[0].outcome'), 'remediated');
  assert.equal(await evaluate('ArgusPrototype.simulation.actions.length'), 1);
  pass('human review, approved dispatch, and three fresh recovery observations');

  await navigate('incidents', await evaluate('ArgusPrototype.simulation.incidents[0].id'));
  await click('[data-action="tab"][data-tab="evidence"]');
  await click('.evidence-card summary');
  assert.equal(await evaluate('!!document.querySelector("details[open] pre")'), true);
  await tick(2);
  assert.equal(await evaluate('!!document.querySelector("details[open] pre")'), true, 'Evidence remains expanded across live refresh');
  assert.match(await evaluate('document.body.innerText'), /SHA-256/);
  await screenshot('evidence');
  await click('[data-action="tab"][data-tab="actions"]');
  assert.match(await evaluate('document.body.innerText'), /Sample 3/);
  await click('[data-action="tab"][data-tab="audit"]');
  assert.match(await evaluate('document.body.innerText'), /approval.answered/);
  pass('evidence expansion, action ledger, and append-only audit views');
  const downloads = path.join(output, 'downloads'); fs.mkdirSync(downloads, { recursive: true });
  await send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: downloads });
  const exportedId = await evaluate('ArgusPrototype.simulation.incidents[0].id');
  await click('[data-action="export"]');
  const exportedFile = path.join(downloads, 'argus-' + exportedId + '-evidence.json');
  for (let tries = 0; tries < 100 && !fs.existsSync(exportedFile); tries++) await sleep(50);
  const exported = JSON.parse(fs.readFileSync(exportedFile, 'utf8'));
  assert.equal(exported.simulation, true);
  assert.equal(exported.incident.samples.length, 3);
  assert.equal(exported.actions.length, 1);
  pass('downloaded incident export contains evidence, approval, action and verification');

  await click('[data-action="navigate"][data-view="overview"]');
  await click('[data-action="simulate"]');
  await click('[data-action="select-scenario"][data-kind="oom"]');
  await click('[data-action="inject"]');
  await tick(16);
  assert.equal(await evaluate('ArgusPrototype.simulation.incidents[0].kind'), 'oom');
  assert.match(await evaluate('document.body.innerText'), /Retained allocations/);
  assert.equal(await evaluate('ArgusPrototype.simulation.actions.length'), 1);
  pass('failure injection through UI and diagnosis without inappropriate restart');

  await click('[data-action="restore"]'); await click('[data-action="confirm-restore"]');
  assert.equal(await evaluate('ArgusPrototype.simulation.incidents[0].outcome'), 'resolved_externally');
  pass('external lab restoration produces a verified external-recovery outcome');

  await evaluate('ArgusPrototype.simulation.inject("cache");'); await tick(16);
  await navigate('approvals');
  await click('[data-action="identity"]'); await click('[data-action="login-role"][data-role="viewer"]');
  await setValue('#login-password', 'wrong'); await click('[data-action="login"]');
  assert.match(await evaluate('document.getElementById("login-error").innerText'), /argus-demo/);
  await setValue('#login-password', 'argus-demo'); await click('[data-action="login"]');
  await click('[data-action="review"]');
  assert.equal(await evaluate('document.querySelector("[data-action=approve]").disabled'), true);
  await click('[data-action="close-modal"]');
  await click('[data-action="identity"]'); await click('[data-action="special-login"][data-role="service"]');
  await click('[data-action="review"]');
  assert.equal(await evaluate('document.querySelector("[data-action=approve]").disabled'), true);
  await click('[data-action="close-modal"]');
  await click('[data-action="identity"]'); await click('[data-action="special-login"][data-role="wrong_scope"]');
  const restrictedId = await evaluate('ArgusPrototype.simulation.incidents[0].id');
  await navigate('incidents', restrictedId);
  assert.match(await evaluate('document.body.innerText'), /Incident not found in your scope/);
  assert.equal(await evaluate('document.querySelectorAll(".evidence-card").length'), 0);
  await click('[data-action="identity"]'); await click('[data-action="special-login"][data-role="expired"]');
  assert.match(await evaluate('document.body.innerText'), /Authentication required/);
  assert.equal(await evaluate('document.querySelectorAll(".host-card, .evidence-card").length'), 0);
  await click('[data-action="identity"]'); await click('[data-action="login-role"][data-role="approver"]');
  await setValue('#login-password', 'argus-demo'); await click('[data-action="login"]');
  await navigate('approvals');
  pass('invalid mock login rejected; viewer and service cannot approve');
  pass('host scope hides unrelated incidents; expired session hides operational data');

  await click('[data-action="review"]'); await setValue('#approval-note', 'Preserve evidence for review.'); await click('[data-action="deny"]');
  assert.equal(await evaluate('ArgusPrototype.simulation.incidents[0].outcome'), 'approval_denied');
  assert.equal(await evaluate('ArgusPrototype.simulation.actions.length'), 1);
  pass('denial preserves evidence and causes zero additional writes');

  await navigate('policies'); await click('[data-action="profile"]');
  assert.equal(await evaluate('ArgusPrototype.simulation.profile'), 'read_only');
  await click('[data-action="hold"]');
  assert.equal(await evaluate('ArgusPrototype.simulation.holds.length'), 1);
  pass('policy profile switch and forensic target hold');

  await navigate('console'); await setValue('#console-command', 'docker ps');
  await evaluate('document.getElementById("console-form").requestSubmit()');
  assert.match(await evaluate('document.getElementById("console-output").innerText'), /argus-lab-api/);
  await setValue('#console-command', 'docker restart argus-lab-api');
  await evaluate('document.getElementById("console-form").requestSubmit()');
  assert.match(await evaluate('document.getElementById("console-output").innerText'), /REFUSED/);
  await screenshot('console'); pass('console accepts bounded reads and refuses mutation');

  await navigate('access'); await click('[data-action="token"]');
  await setValue('#token-name', '<script>hostile label</script>'); await click('[data-action="token-create"]');
  assert.equal(await evaluate('document.querySelectorAll("#main script").length'), 0);
  assert.match(await evaluate('document.body.innerText'), /hostile label/);
  const tokenId = await evaluate('ArgusPrototype.simulation.tokens.at(-1).id');
  await click('[data-action="revoke"][data-token="' + tokenId + '"]');
  assert.equal(await evaluate('ArgusPrototype.simulation.tokens.at(-1).revoked'), true);
  assert.equal(await evaluate('localStorage.length + sessionStorage.length'), 0);
  pass('scoped demo token creation, escaped labels, revocation, and no stored session');

  await navigate('runbooks'); assert.equal(await evaluate('document.querySelectorAll(".runbook-card").length'), 21);
  await setValue('#book-search', 'RB-004'); assert.equal(await evaluate('document.querySelectorAll(".runbook-card").length'), 1);
  await click('[data-action="book"][data-book="RB-004"]');
  assert.match(await evaluate('document.querySelector("[role=dialog]").innerText'), /connection exhaustion/i);
  await click('[data-action="close-modal"]'); pass('all 21 real runbooks searchable and readable offline');

  await click('[data-action="search"]'); await setValue('#global-search', 'argus-lab-db');
  assert.ok(await evaluate('document.querySelectorAll(".search-result").length') > 0);
  await click('.search-result');
  await click('[data-action="close-modal"]'); pass('workspace search opens a matching target');

  await navigate('overview');
  await sleep(4500);
  await screenshot('mobile', 390, 844);
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
  await click('[data-action="menu"]'); assert.equal(await evaluate('document.querySelector(".sidebar").classList.contains("open")'), true);
  await click('[data-action="navigate"][data-view="infrastructure"]');
  assert.equal(await evaluate('document.documentElement.scrollWidth <= innerWidth'), true);
  pass('mobile overview and infrastructure fit viewport; navigation works');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1140, deviceScaleFactor: 1, mobile: false });

  await navigate('overview'); await click('[data-action="reset"]'); await click('[data-action="confirm-reset"]');
  await evaluate('ArgusPrototype.ui.paused = true; ArgusPrototype.render();');
  assert.equal(await evaluate('ArgusPrototype.simulation.pending.length'), 1);
  assert.equal(await evaluate('ArgusPrototype.simulation.actions.length'), 0);
  await screenshot('overview-final'); pass('reset restores a clean guided lab');
  await sleep(4500);
  await screenshot('mobile-final', 390, 844);
  assert.deepEqual(errors, [], 'No browser runtime errors');
  assert.ok(requests.every(url => url.startsWith('file:') || url.startsWith('data:') || url.startsWith('blob:')), 'No external request from standalone artifact');
  pass('zero browser errors and zero external network requests');
  process.stdout.write('\n' + checks + ' browser checks passed. Screenshots: prototype/.qa/\n');
})().catch(error => { process.stderr.write(error.stack + '\n'); process.exitCode = 1; }).finally(async () => {
  if (socket?.readyState === WebSocket.OPEN) { try { await send('Browser.close'); } catch (_) {} socket.close(); }
  if (!browser.killed) browser.kill();
});
