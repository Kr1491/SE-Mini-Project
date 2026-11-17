#!/usr/bin/env node
'use strict';
/*
 * ISO 9126 usability + portability check in a real (headless) Chrome browser.
 *
 *   node scripts/browser_quality_check.cjs --out /tmp/studyspace-browser
 *
 * Starts two throwaway StudySpace servers (normal mode for registration, demo
 * mode for the quiz/material flows) on temporary databases, then for each
 * device profile:
 *   - runs the main student tasks with real mouse clicks and keyboard input,
 *     counting the clicks each task needs (usability), and
 *   - opens every page and checks nothing is wider than the screen (portability).
 *
 * Needs Python 3.11+, Node 22+ and Google Chrome/Chromium (set CHROME_PATH if
 * it is not in a standard location). No npm packages are required.
 */
const {spawn} = require('node:child_process');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const ROOT = path.resolve(__dirname, '..');
const PASSWORD = 'correct horse battery staple';
const DEVICES = {
  'Desktop 1440x900': {width: 1440, height: 900, mobile: false, scale: 1},
  'iPhone 14 (390x844)': {width: 390, height: 844, mobile: true, scale: 3,
    ua: 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'},
  'Android Pixel 7 (412x915)': {width: 412, height: 915, mobile: true, scale: 2.625,
    ua: 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'},
  'Small Android (360x640)': {width: 360, height: 640, mobile: true, scale: 2,
    ua: 'Mozilla/5.0 (Linux; Android 12; SM-A125F) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36'},
  'iPad (768x1024)': {width: 768, height: 1024, mobile: true, scale: 2,
    ua: 'Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1'},
};
const STUDENT_PAGES = ['/dashboard', '/quizzes', '/results', '/materials', '/access'];

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function option(name, fallback) {
  const index = process.argv.indexOf(`--${name}`);
  return index > 0 ? process.argv[index + 1] : fallback;
}
function findChrome() {
  const candidates = [process.env.CHROME_PATH,
    '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
    '/Applications/Chromium.app/Contents/MacOS/Chromium',
    '/usr/bin/google-chrome', '/usr/bin/google-chrome-stable', '/usr/bin/chromium', '/usr/bin/chromium-browser'];
  const found = candidates.find(candidate => candidate && fs.existsSync(candidate));
  if (!found) throw new Error('Chrome/Chromium not found. Set CHROME_PATH.');
  return found;
}

function startServer(temp, name, demo) {
  const dir = path.join(temp, name);
  fs.mkdirSync(dir, {mode: 0o700});
  const args = ['server.py', '--port', '0', '--database', path.join(dir, 'study.db'), '--storage', path.join(dir, 'materials')];
  if (demo) args.splice(1, 0, '--demo');
  const child = spawn('python3', args, {cwd: ROOT, stdio: ['ignore', 'pipe', 'pipe']});
  return new Promise((resolve, reject) => {
    let output = '';
    child.stdout.on('data', chunk => {
      output += chunk;
      const match = output.match(/http:\/\/127\.0\.0\.1:(\d+)/);
      if (match) resolve({child, url: `http://127.0.0.1:${match[1]}`});
    });
    child.on('exit', code => reject(new Error(`${name} server exited (${code})`)));
    setTimeout(() => reject(new Error(`${name} server did not start`)), 15000);
  });
}

async function publishQuiz(url, questions) {
  const session = await fetch(`${url}/api/demo/session`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({user_id: 1})});
  const cookie = session.headers.get('set-cookie').split(';')[0];
  const {csrf_token: csrf} = await session.json();
  const headers = {'Content-Type': 'application/json', Cookie: cookie, 'X-CSRF-Token': csrf};
  const quiz = {title: 'Usability check quiz', questions: Array.from({length: questions}, (_, i) => ({
    question: `Question ${i + 1}: what does SQL stand for?`,
    options: [{text: 'Structured Query Language', is_correct: true}, {text: 'Simple Question Language', is_correct: false}]}))};
  const created = await (await fetch(`${url}/api/groups/1/quizzes`, {method: 'POST', headers, body: JSON.stringify(quiz)})).json();
  const published = await fetch(`${url}/api/quizzes/${created.quiz.id}/publish`, {method: 'POST', headers, body: '{}'});
  if (!published.ok) throw new Error('Could not publish the check quiz.');
}

class Connection {
  constructor(wsUrl) {
    this.nextId = 1; this.pending = new Map(); this.listeners = [];
    this.ws = new WebSocket(wsUrl);
    this.ready = new Promise((resolve, reject) => { this.ws.onopen = resolve; this.ws.onerror = reject; });
    this.ws.onmessage = event => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const {resolve, reject} = this.pending.get(message.id); this.pending.delete(message.id);
        message.error ? reject(new Error(message.error.message)) : resolve(message.result);
      } else if (message.method) this.listeners.forEach(listener => listener(message));
    };
  }
  send(method, params = {}) {
    const id = this.nextId++;
    this.ws.send(JSON.stringify({id, method, params}));
    return new Promise((resolve, reject) => this.pending.set(id, {resolve, reject}));
  }
  close() { this.ws.close(); }
}

class Page {
  constructor(connection, device) { this.cdp = connection; this.device = device; this.clicks = 0; this.errors = []; }
  async setup() {
    await this.cdp.ready;
    await this.cdp.send('Page.enable'); await this.cdp.send('Runtime.enable');
    this.cdp.listeners.push(message => {
      if (message.method === 'Runtime.exceptionThrown') this.errors.push(message.params.exceptionDetails.text);
    });
    const d = this.device;
    await this.cdp.send('Emulation.setDeviceMetricsOverride', {width: d.width, height: d.height, deviceScaleFactor: d.scale, mobile: d.mobile});
    if (d.ua) await this.cdp.send('Emulation.setUserAgentOverride', {userAgent: d.ua});
    if (d.mobile) await this.cdp.send('Emulation.setTouchEmulationEnabled', {enabled: true, maxTouchPoints: 5});
  }
  async eval(expression) {
    const result = await this.cdp.send('Runtime.evaluate', {expression, awaitPromise: true, returnByValue: true});
    if (result.exceptionDetails) throw new Error(result.exceptionDetails.text);
    return result.result.value;
  }
  async until(expression, label, timeout = 10000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      try { if (await this.eval(expression)) return; } catch { /* page is navigating */ }
      await sleep(50);
    }
    throw new Error(`Timed out waiting for: ${label}`);
  }
  async open(url) { await this.cdp.send('Page.navigate', {url}); await this.until('document.readyState === "complete"', `load ${url}`); }
  // Real mouse click at the centre of the first visible element matching the selector (and text).
  async click(selector, text = '') {
    const point = await this.eval(`(() => {
      const match = [...document.querySelectorAll(${JSON.stringify(selector)})].find(el =>
        el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden' && el.textContent.includes(${JSON.stringify(text)}));
      if (!match) return null;
      match.scrollIntoView({block: 'center', inline: 'center'});
      const r = match.getBoundingClientRect();
      return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height};
    })()`);
    if (!point) throw new Error(`No visible element: ${selector} ${text}`);
    for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased']) {
      await this.cdp.send('Input.dispatchMouseEvent', {type, x: point.x, y: point.y, button: 'left', clickCount: 1});
    }
    this.clicks += 1;
    return point;
  }
  async type(selector, text) {
    await this.eval(`document.querySelector(${JSON.stringify(selector)}).focus()`);
    await this.cdp.send('Input.insertText', {text});
  }
  async layout() {
    return this.eval(`(() => {
      const width = document.documentElement.clientWidth;
      const offenders = [...document.querySelectorAll('body *')].filter(el => {
        if (!el.getClientRects().length) return false;
        for (let p = el.parentElement; p && p !== document.body; p = p.parentElement) {
          const o = getComputedStyle(p).overflowX; if (o === 'auto' || o === 'scroll' || o === 'hidden') return false;
        }
        const r = el.getBoundingClientRect(); return r.width > 0 && (r.right > width + 1 || r.left < -1);
      }).slice(0, 5).map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : ''));
      // WCAG 2.2 target size: 24px minimum. A radio/checkbox inside a larger label uses the label as its target.
      const small = [...document.querySelectorAll('button, a, input, select')].filter(el => {
        if (!el.getClientRects().length || el.closest('[hidden]')) return false;
        const target = el.matches('input[type=radio], input[type=checkbox]') && el.closest('label') ? el.closest('label') : el;
        const r = target.getBoundingClientRect(); return r.height > 0 && r.height < 24;
      }).map(el => el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ')[0] : '') + ' "' + el.textContent.trim().slice(0, 24) + '"');
      return {pageWidth: document.documentElement.scrollWidth, viewport: width, horizontalScroll: document.documentElement.scrollWidth > width + 1, offenders, smallTargets: small};
    })()`);
  }
  async screenshot(file) {
    const {data} = await this.cdp.send('Page.captureScreenshot', {format: 'png'});
    fs.writeFileSync(file, Buffer.from(data, 'base64'));
  }
}

async function launchChrome(temp) {
  const port = 9200 + Math.floor(Math.random() * 500);
  const child = spawn(findChrome(), ['--headless=new', `--remote-debugging-port=${port}`, `--user-data-dir=${path.join(temp, 'chrome')}`,
    '--no-first-run', '--no-default-browser-check', '--disable-extensions', 'about:blank'], {stdio: 'ignore'});
  for (let i = 0; i < 100; i += 1) {
    try {
      const info = await (await fetch(`http://127.0.0.1:${port}/json/version`)).json();
      return {child, port, version: info.Browser, browser: new Connection(info.webSocketDebuggerUrl)};
    } catch { await sleep(100); }
  }
  throw new Error('Chrome did not start');
}

async function newPage(chrome, device) {
  const {browserContextId} = await chrome.browser.send('Target.createBrowserContext');
  const {targetId} = await chrome.browser.send('Target.createTarget', {url: 'about:blank', browserContextId});
  const page = new Page(new Connection(`ws://127.0.0.1:${chrome.port}/devtools/page/${targetId}`), device);
  await page.setup();
  page.dispose = async () => { page.cdp.close(); await chrome.browser.send('Target.disposeBrowserContext', {browserContextId}); };
  return page;
}

async function task(results, name, run) {
  const started = Date.now();
  try {
    const details = await run();
    results.push({task: name, ok: true, ms: Date.now() - started, ...details});
  } catch (error) {
    results.push({task: name, ok: false, ms: Date.now() - started, error: error.message});
  }
}

async function checkDevice(chrome, servers, label, device, out, unique) {
  const tasks = [];
  const slug = label.replace(/[^a-z0-9]+/gi, '-').toLowerCase();

  await task(tasks, 'Register a new student account', async () => {
    const page = await newPage(chrome, device);
    try {
      await page.open(`${servers.normal}/login`);
      await page.until('!document.getElementById("login-fields").disabled', 'login form ready');
      await page.click('a', 'Create an account');
      await page.until('location.pathname === "/register" && !document.getElementById("register-fields").disabled', 'registration form');
      await page.type('#name', 'Usability Student');
      await page.type('#email', `student-${unique}-${slug}@example.test`);
      await page.type('#password', PASSWORD);
      await page.click('#create-account');
      await page.until('location.pathname === "/dashboard" && document.getElementById("dashboard-role")?.textContent.trim().toLowerCase() === "student"', 'student dashboard');
      return {clicks: page.clicks, fieldsTyped: 3, jsErrors: page.errors.length};
    } finally { await page.dispose(); }
  });

  await task(tasks, 'Sign in with the new account', async () => {
    const page = await newPage(chrome, device);
    try {
      await page.open(`${servers.normal}/login`);
      await page.until('!document.getElementById("login-fields").disabled', 'login form ready');
      await page.type('#email', `student-${unique}-${slug}@example.test`);
      await page.type('#password', PASSWORD);
      await page.click('#sign-in');
      await page.until('location.pathname === "/dashboard" && document.getElementById("dashboard-role")?.textContent.trim().length > 0', 'dashboard');
      return {clicks: page.clicks, fieldsTyped: 2, jsErrors: page.errors.length};
    } finally { await page.dispose(); }
  });

  const layouts = [];
  await task(tasks, 'Take and submit a 2-question quiz (from dashboard)', async () => {
    const page = await newPage(chrome, device);
    try {
      await page.open(`${servers.demo}/login`);
      await page.until('!document.getElementById("demo-panel").hidden', 'demo accounts');
      await page.click('#demo-accounts button', 'Student');
      await page.until('location.pathname === "/dashboard" && document.getElementById("dashboard-role")?.textContent.trim().toLowerCase() === "student"', 'student dashboard');
      page.clicks = 0; // count from the dashboard onwards
      await page.click('a[href="/quizzes"]');
      await page.until('[...document.querySelectorAll("#group-quizzes button")].some(b => b.textContent.includes("Start Quiz"))', 'quiz list');
      await page.click('#group-quizzes button', 'Start Quiz');
      await page.until('document.querySelectorAll("#attempt-questions input[type=radio]:not([disabled])").length >= 4', 'quiz questions');
      const answers = await page.eval('document.querySelectorAll("#attempt-questions fieldset").length');
      for (let i = 0; i < answers; i += 1) await page.click(`#attempt-questions fieldset:nth-of-type(${i + 1}) label.attempt-option`);
      const navigationClicks = page.clicks - answers;
      await page.click('#submit-quiz-attempt');
      await page.until('document.getElementById("attempt-confirmation").getClientRects().length > 0', 'confirmation');
      await page.click('#confirm-quiz-submit');
      await page.until('/\\d/.test(document.getElementById("attempt-score")?.textContent || "")', 'score');
      const score = await page.eval('document.getElementById("attempt-score").textContent.trim()');
      await page.screenshot(path.join(out, `${slug}-quiz-result.png`));
      return {clicks: page.clicks, answerClicks: answers, nonAnswerClicks: page.clicks - answers, navigationClicks, score, jsErrors: page.errors.length};
    } finally { await page.dispose(); }
  });

  await task(tasks, 'Open a study material preview (from dashboard)', async () => {
    const page = await newPage(chrome, device);
    try {
      await page.open(`${servers.demo}/login`);
      await page.until('!document.getElementById("demo-panel").hidden', 'demo accounts');
      await page.click('#demo-accounts button', 'Student');
      await page.until('location.pathname === "/dashboard" && document.getElementById("dashboard-role")?.textContent.trim().length > 0', 'dashboard');
      page.clicks = 0;
      await page.click('a[href="/materials"]');
      await page.until('document.querySelectorAll("#material-list [data-view]").length > 0', 'material list');
      await page.click('#material-list [data-view]');
      await page.until('document.getElementById("preview-dialog").open || document.getElementById("preview-dialog").getClientRects().length > 0', 'preview');
      return {clicks: page.clicks, jsErrors: page.errors.length};
    } finally { await page.dispose(); }
  });

  // Layout of every student page plus the public pages on this device.
  const page = await newPage(chrome, device);
  try {
    for (const route of ['/login', '/register']) {
      await page.open(`${servers.normal}${route}`); await sleep(300);
      layouts.push({page: route, ...(await page.layout())});
      await page.screenshot(path.join(out, `${slug}${route.replace(/\//g, '-')}.png`));
    }
    await page.open(`${servers.demo}/login`);
    await page.until('!document.getElementById("demo-panel").hidden', 'demo accounts');
    await page.click('#demo-accounts button', 'Student');
    await page.until('location.pathname === "/dashboard"', 'dashboard');
    for (const route of STUDENT_PAGES) {
      await page.open(`${servers.demo}${route}`); await sleep(600);
      layouts.push({page: route, ...(await page.layout())});
      await page.screenshot(path.join(out, `${slug}${route.replace(/\//g, '-')}.png`));
    }
    layouts.forEach(entry => { entry.jsErrors = page.errors.length; });
  } finally { await page.dispose(); }
  return {tasks, layouts};
}

async function main() {
  const out = path.resolve(option('out', path.join(os.tmpdir(), 'studyspace-browser-check')));
  fs.mkdirSync(out, {recursive: true});
  const temp = fs.mkdtempSync(path.join(os.tmpdir(), 'studyspace-check-'));
  fs.chmodSync(temp, 0o700);
  const processes = [];
  try {
    const normal = await startServer(temp, 'normal', false); processes.push(normal.child);
    const demo = await startServer(temp, 'demo', true); processes.push(demo.child);
    await publishQuiz(demo.url, 2);
    const chrome = await launchChrome(temp); processes.push(chrome.child);
    await chrome.browser.ready;
    const report = {browser: chrome.version, platform: `${os.type()} ${os.release()} ${os.arch()}`, date: new Date().toISOString(), devices: {}};
    const unique = Date.now().toString(36);
    for (const [label, device] of Object.entries(DEVICES)) {
      report.devices[label] = await checkDevice(chrome, {normal: normal.url, demo: demo.url}, label, device, out, unique);
      const {tasks, layouts} = report.devices[label];
      console.log(`\n${label}`);
      for (const t of tasks) console.log(`  ${t.ok ? 'PASS' : 'FAIL'} ${t.task}: ${t.ok ? `${t.clicks} clicks, ${t.ms} ms` : t.error}`);
      for (const l of layouts) console.log(`  ${l.horizontalScroll || l.offenders.length ? 'FAIL' : 'PASS'} ${l.page} fits ${l.viewport}px (page ${l.pageWidth}px)${l.offenders.length ? ' overflow: ' + l.offenders.join(', ') : ''}${l.smallTargets.length ? ' | targets <24px: ' + l.smallTargets.join(', ') : ''}`);
    }
    chrome.browser.close();
    fs.writeFileSync(path.join(out, 'browser-quality-results.json'), JSON.stringify(report, null, 2));
    const failed = Object.values(report.devices).some(({tasks, layouts}) =>
      tasks.some(t => !t.ok) || layouts.some(l => l.horizontalScroll || l.offenders.length || l.smallTargets.length));
    console.log(`\nBrowser: ${report.browser}\nResults and screenshots: ${out}`);
    process.exitCode = failed ? 1 : 0;
  } finally {
    await Promise.all(processes.map(child => new Promise(resolve => {
      if (child.exitCode !== null || child.signalCode !== null) return resolve();
      child.once('exit', resolve); child.kill();
    })));
    fs.rmSync(temp, {recursive: true, force: true, maxRetries: 5, retryDelay: 200});
  }
}

main().catch(error => { console.error(error); process.exit(1); });
