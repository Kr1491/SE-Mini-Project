"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let session = null, revision = 0, sequence = 0, busy = false, readOnly = false, onJoined = null;
  const node = (tag, text) => { const item = document.createElement(tag); if (text !== undefined) item.textContent = text; return item; };
  function message(text, error = false) { byId('membership-status').textContent = text; byId('membership-status').classList.toggle('error', error); }
  function controls() {
    byId('request-group-id').disabled = busy || readOnly;
    byId('request-join-button').disabled = busy || readOnly;
    byId('refresh-memberships').disabled = busy;
    for (const button of byId('membership-requests').querySelectorAll('button')) button.disabled = busy || readOnly;
  }
  function reset() {
    ++revision; ++sequence; session = null; busy = false; readOnly = false; onJoined = null;
    byId('membership-panel').hidden = true; byId('request-join-form').hidden = true;
    byId('membership-requests').replaceChildren(); byId('request-group-id').value = '';
    message(''); controls();
  }
  async function request(path, options = {}) {
    const headers = {...options.headers};
    if (options.body !== undefined) { headers['Content-Type'] = 'application/json'; headers['X-CSRF-Token'] = session.csrf_token; }
    const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || 'The membership request could not be completed.'); error.status = response.status; throw error; }
    return data;
  }
  async function refresh(token = revision) {
    const requestNumber = ++sequence;
    try {
      const data = await request('/api/membership-requests');
      if (token !== revision || requestNumber !== sequence) return false;
      readOnly = data.read_only;
      byId('membership-demo-notice').hidden = !readOnly;
      byId('membership-heading').textContent = data.can_review ? 'Membership requests' : 'Your join requests';
      byId('request-join-form').hidden = session.user.role !== 'student';
      byId('membership-requests').replaceChildren();
      for (const item of data.requests) {
        const card = node('article'); card.className = 'membership-card';
        const info = node('div'); info.append(node('strong', item.group_name || `Group #${item.group_id}`));
        if (data.can_review) info.append(node('p', `${item.student_name} · ${item.student_email}`));
        else info.append(node('p', `Request ${item.id} · ${item.status}`));
        card.append(info);
        if (data.can_review) for (const decision of ['approve', 'reject']) {
          const button = node('button', decision === 'approve' ? 'Approve' : 'Decline'); button.type = 'button';
          button.dataset.reviewRequest = String(item.id); button.dataset.decision = decision; card.append(button);
        }
        byId('membership-requests').append(card);
      }
      if (!data.requests.length) byId('membership-requests').append(node('p', data.can_review ? 'No requests are waiting for review.' : 'No join requests yet. Enter the group ID shared by your instructor.'));
      controls(); return true;
    } catch (error) {
      if (token !== revision || requestNumber !== sequence) return false;
      if ([401, 403].includes(error.status)) { reset(); return false; }
      message(error.message || 'Cannot load requests. Refresh to try again.', true); return false;
    }
  }
  async function load(account, options = {}) {
    reset(); session = account; onJoined = options.onJoined || null;
    byId('membership-panel').hidden = false;
    await refresh(revision);
  }
  byId('request-join-form').addEventListener('submit', async event => {
    event.preventDefault(); if (!session || session.user.role !== 'student' || busy || readOnly) return;
    const id = byId('request-group-id').value.trim();
    if (!/^[1-9][0-9]{0,18}$/.test(id)) { message('Enter a valid group ID.', true); return; }
    const token = revision; busy = true; controls(); message('Sending join request…');
    try {
      const result = await request(`/api/groups/${id}/join`, {method: 'POST', body: '{}'});
      if (token !== revision) return;
      byId('request-group-id').value = '';
      if (result.joined && onJoined) { await onJoined(result); return; }
      if (await refresh(token)) message(result.message || 'You joined the group. Refresh overview to see it.');
    } catch (error) { if (token === revision) message(error.message || 'Could not join. Refresh before retrying.', true); }
    finally { if (token === revision) { busy = false; controls(); } }
  });
  byId('membership-requests').addEventListener('click', async event => {
    const button = event.target.closest('[data-review-request]');
    if (!button || button.disabled || !session || busy || readOnly) return;
    const token = revision; busy = true; controls(); message('Saving the decision…');
    try {
      const result = await request(`/api/membership-requests/${button.dataset.reviewRequest}/review`, {method: 'POST', body: JSON.stringify({decision: button.dataset.decision})});
      if (token !== revision) return;
      if (await refresh(token)) message(result.status === 'approved' ? 'Request approved. The student can now access this group.' : 'Request declined.');
    } catch (error) { if (token === revision) message(error.message || 'Could not save the decision. Refresh before retrying.', true); }
    finally { if (token === revision) { busy = false; controls(); } }
  });
  byId('refresh-memberships').addEventListener('click', () => { if (session && !busy) return refresh(); });
  globalThis.StudyMemberships = {load, reset};
})();
