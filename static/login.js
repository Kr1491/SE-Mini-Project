"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let ready = false;
  let demo = false;
  let busy = false;
  function message(text, error = false) {
    byId('login-status').textContent = text;
    byId('login-status').classList.toggle('error', error);
  }
  function pending(value) {
    busy = value;
    byId('login-fields').disabled = value || !ready;
    byId('sign-in').textContent = value ? 'Opening your workspace…' : 'Sign in ↗';
    byId('login-form').setAttribute('aria-busy', String(value));
    for (const button of byId('demo-accounts').querySelectorAll('button')) button.disabled = value;
  }
  async function request(path, options = {}) {
    const response = await fetch(path, {...options, credentials: 'same-origin', headers: {...options.headers, ...(options.body !== undefined ? {'Content-Type': 'application/json'} : {})}});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || 'Could not sign in. Please try again.'); error.status = response.status; throw error; }
    return data;
  }
  function openWorkspace() { byId('password').value = ''; globalThis.location.replace('/dashboard'); }
  byId('login-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!ready || busy || !byId('login-form').reportValidity()) return;
    const email = byId('email').value.trim();
    const password = byId('password').value;
    pending(true); message('Signing in…');
    try {
      await request('/api/login', {method: 'POST', body: JSON.stringify({email, password})});
      openWorkspace();
    } catch (error) { message(error.message || 'Cannot reach the application. Please try again.', true); pending(false); }
  });
  byId('toggle-password').addEventListener('click', () => {
    if (busy) return;
    const show = byId('password').type === 'password';
    byId('password').type = show ? 'text' : 'password';
    byId('toggle-password').textContent = show ? 'Hide' : 'Show';
    byId('toggle-password').setAttribute('aria-pressed', String(show));
  });
  byId('demo-accounts').addEventListener('click', async event => {
    const button = event.target.closest('[data-account]');
    if (!button || !ready || !demo || busy) return;
    pending(true); message('Opening the sample workspace…');
    try {
      await request('/api/demo/session', {method: 'POST', body: JSON.stringify({user_id: Number(button.dataset.account)})});
      openWorkspace();
    } catch (error) { message(error.message || 'Cannot open this sample account. Please try again.', true); pending(false); }
  });
  (async () => {
    try {
      const health = await request('/api/health');
      demo = health.demo === true;
      try { await request('/api/session'); openWorkspace(); return; }
      catch (error) { if (error.status !== 401) throw error; }
      ready = true; pending(false);
      byId('demo-panel').hidden = !demo;
      message('');
    } catch { message('Cannot reach the application. Refresh the page to try again.', true); }
  })();
})();
