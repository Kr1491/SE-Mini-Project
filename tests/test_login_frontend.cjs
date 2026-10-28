'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../static/login.js'), 'utf8');
const flush = () => new Promise(resolve => setImmediate(resolve));
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return {promise, resolve}; }
function response(status, data = {}) { return {ok: status >= 200 && status < 300, status, json: async () => data}; }
class Element {
  constructor(id = '', dataset = {}) {
    this.id = id; this.dataset = dataset; this.handlers = {}; this.value = ''; this.textContent = '';
    this.hidden = id === 'demo-panel'; this.disabled = id === 'login-fields'; this.type = id === 'password' ? 'password' : '';
    this.attributes = {}; const values = new Set();
    this.classList = {toggle: (value, on) => on ? values.add(value) : values.delete(value), contains: value => values.has(value)};
  }
  addEventListener(name, fn) { this.handlers[name] = fn; }
  setAttribute(name, value) { this.attributes[name] = value; }
  querySelectorAll() { return this.buttons || []; }
  reportValidity() { return this.valid !== false; }
  closest(selector) { return selector === '[data-account]' && this.dataset.account ? this : null; }
}
function harness(custom = () => undefined, demo = false) {
  const elements = new Map(); const calls = []; const navigations = [];
  const element = id => { if (!elements.has(id)) elements.set(id, new Element(id)); return elements.get(id); };
  const buttons = [1,2,3,4].map(id => new Element('', {account: String(id)})); element('demo-accounts').buttons = buttons;
  const fetch = async (url, options = {}) => {
    calls.push({url,options}); const result = custom(url, options); if (result !== undefined) return result;
    if (url === '/api/health') return response(200, {demo});
    if (url === '/api/session') return response(401, {error: 'Sign in'});
    if (url === '/api/login' || url === '/api/demo/session') return response(200);
    throw new Error(`Unexpected route ${url}`);
  };
  const document = {getElementById: element};
  vm.runInNewContext(source, {document, fetch, location: {replace: url => navigations.push(url)}}, {filename:'login.js'});
  return {element, buttons, calls, navigations,
    submit: () => element('login-form').handlers.submit({preventDefault() {}}),
    choose: id => element('demo-accounts').handlers.click({target: buttons.find(button => button.dataset.account === String(id))}),
    fill: (email = 'student@example.test', password = 'A test password 42!') => { element('email').value = email; element('password').value = password; }};
}

test('initial session detection prevents an early login or sample selection', async () => {
  const session = deferred(); const ui = harness(url => url === '/api/session' ? session.promise : undefined, true);
  await flush(); ui.fill(); await ui.submit(); await ui.choose(2);
  assert.equal(ui.element('login-fields').disabled, true);
  assert.equal(ui.calls.some(call => ['/api/login','/api/demo/session'].includes(call.url)), false);
  session.resolve(response(401, {error:'Sign in'})); await flush();
  assert.equal(ui.element('login-fields').disabled, false); assert.equal(ui.element('demo-panel').hidden, false);
});

test('a valid existing session goes directly to the dashboard', async () => {
  const ui = harness(url => url === '/api/session' ? response(200,{user:{id:2}}) : undefined);
  await flush(); assert.deepEqual(ui.navigations,['/dashboard']);
  assert.equal(ui.element('demo-panel').hidden,true);
});

test('normal login sends only email/password and clears password before navigation', async () => {
  const ui = harness(); await flush(); ui.fill(' student@example.test ',' secret password ');
  await ui.submit(); const login = ui.calls.find(call => call.url === '/api/login');
  assert.deepEqual(JSON.parse(login.options.body),{email:'student@example.test',password:' secret password '});
  assert.equal(login.options.credentials,'same-origin');
  assert.equal(login.options.headers['Content-Type'],'application/json');
  assert.deepEqual(ui.navigations,['/dashboard']); assert.equal(ui.element('password').value,'');
});

test('wrong credentials show a literal error and re-enable the form', async () => {
  const ui = harness(url => url === '/api/login' ? response(401,{error:'Invalid email or password.'}) : undefined);
  await flush(); ui.fill(); await ui.submit();
  assert.equal(ui.element('login-status').textContent,'Invalid email or password.');
  assert.equal(ui.element('login-status').classList.contains('error'),true);
  assert.equal(ui.element('login-fields').disabled,false); assert.deepEqual(ui.navigations,[]);
});

test('native validation stops malformed form submission', async () => {
  const ui = harness(); await flush(); ui.element('login-form').valid=false; await ui.submit();
  assert.equal(ui.calls.some(call => call.url === '/api/login'),false);
});

test('a pending login blocks duplicate submissions and sample account races', async () => {
  const login = deferred(); const ui = harness(url => url === '/api/login' ? login.promise : undefined,true);
  await flush(); ui.fill(); const pending = ui.submit(); await ui.submit(); await ui.choose(3);
  assert.equal(ui.calls.filter(call => call.url === '/api/login').length,1);
  assert.equal(ui.calls.some(call => call.url === '/api/demo/session'),false);
  assert.ok(ui.buttons.every(button => button.disabled));
  login.resolve(response(401,{error:'Invalid email or password.'})); await pending;
  assert.ok(ui.buttons.every(button => !button.disabled));
});

test('the sample selector appears only in demo mode and uses the existing endpoint', async () => {
  const normal = harness(); await flush(); await normal.choose(3);
  assert.equal(normal.element('demo-panel').hidden,true);
  assert.equal(normal.calls.some(call => call.url === '/api/demo/session'),false);
  const demo = harness(() => undefined,true); await flush(); await demo.choose(3);
  const chosen = demo.calls.find(call => call.url === '/api/demo/session');
  assert.deepEqual(JSON.parse(chosen.options.body),{user_id:3});
  assert.deepEqual(demo.navigations,['/dashboard']);
});

test('sample selector failures are recoverable without redirecting', async () => {
  const ui = harness(url => url === '/api/demo/session' ? response(409,{error:'Demo fixture conflict.'}) : undefined,true);
  await flush(); await ui.choose(2);
  assert.equal(ui.element('login-status').textContent,'Demo fixture conflict.');
  assert.equal(ui.element('login-fields').disabled,false); assert.deepEqual(ui.navigations,[]);
});

test('password visibility toggle updates the input and accessible pressed state', async () => {
  const ui = harness(); await flush(); const button = ui.element('toggle-password');
  button.handlers.click(); assert.equal(ui.element('password').type,'text'); assert.equal(button.attributes['aria-pressed'],'true');
  button.handlers.click(); assert.equal(ui.element('password').type,'password'); assert.equal(button.attributes['aria-pressed'],'false');
});

test('server connection failure leaves controls unavailable with useful feedback', async () => {
  const ui = harness(() => Promise.reject(new Error('Offline'))); await flush(); await ui.choose(2);
  assert.match(ui.element('login-status').textContent,/Cannot reach/);
  assert.equal(ui.element('login-fields').disabled,true); assert.deepEqual(ui.navigations,[]);
});
