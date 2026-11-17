"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let ready = false;
  let busy = false;
  function message(text, error = false) {
    byId('register-status').textContent = text;
    byId('register-status').classList.toggle('error', error);
  }
  function pending(value) {
    busy = value;
    byId('register-fields').disabled = value || !ready;
    byId('create-account').textContent = value ? 'Creating your account…' : 'Create account ↗';
    byId('register-form').setAttribute('aria-busy', String(value));
  }
  async function request(path, options = {}) {
    const response = await fetch(path, {...options, credentials: 'same-origin', headers: {...options.headers, ...(options.body !== undefined ? {'Content-Type': 'application/json'} : {})}});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || 'Could not create the account. Please try again.'); error.status = response.status; throw error; }
    return data;
  }
  function openWorkspace() { byId('password').value = ''; globalThis.location.replace('/dashboard'); }
  byId('register-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (!ready || busy || !byId('register-form').reportValidity()) return;
    const account = {name: byId('name').value.trim(), email: byId('email').value.trim(), password: byId('password').value};
    pending(true); message('Creating your account…');
    try {
      await request('/api/register', {method: 'POST', body: JSON.stringify(account)});
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
  (async () => {
    try {
      const health = await request('/api/health');
      try { await request('/api/session'); openWorkspace(); return; }
      catch (error) { if (error.status !== 401) throw error; }
      if (health.demo === true) {
        message('Registration is turned off in the local demo. Use a sample account on the sign-in page.', true);
        return;
      }
      ready = true; pending(false);
      message('');
    } catch { message('Cannot reach the application. Refresh the page to try again.', true); }
  })();
})();
