"use strict";
(() => {
  const byId = id => document.getElementById(id);
  const state = {revision: 0, initialized: false, demo: false, switching: false, session: null, group: '', offset: 0, limit: 24, total: 0, items: new Map()};
  let previewSequence = 0;
  let previewController = null;
  let previewMaterial = null;
  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function message(id, text, error = false) {
    byId(id).textContent = text;
    byId(id).classList.toggle('error', error);
  }
  async function json(path, options = {}) {
    const headers = {...options.headers};
    if (options.body !== undefined) headers['Content-Type'] = 'application/json';
    const response = await fetch(path, {...options, headers, credentials: 'same-origin'});
    const data = await response.json();
    if (!response.ok) { const error = new Error(data.error || 'The request could not be completed.'); error.status = response.status; throw error; }
    return data;
  }
  function invalidatePreview() {
    ++previewSequence;
    previewController?.abort(); previewController = null; previewMaterial = null;
    byId('preview-frame').removeAttribute('src'); byId('preview-frame').hidden = true;
    byId('preview-image').removeAttribute('src'); byId('preview-image').hidden = true;
    byId('preview-text').textContent = ''; byId('preview-text').hidden = true;
    byId('preview-title').textContent = '';
    message('preview-status', '');
  }
  function closePreview() {
    invalidatePreview();
    if (byId('preview-dialog').open) byId('preview-dialog').close();
  }
  function clearLibrary(full = false) {
    closePreview(); state.items.clear(); byId('material-list').replaceChildren();
    byId('material-count').textContent = ''; byId('page-info').textContent = '';
    byId('previous-page').disabled = true; byId('next-page').disabled = true;
    if (full) {
      state.group = ''; state.offset = 0; state.session = null;
      byId('library').hidden = true; byId('material-group').replaceChildren();
      byId('profile-name').textContent = ''; byId('role-badge').textContent = ''; byId('role-badge').hidden = true;
    }
  }
  function sizeLabel(bytes) {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
  function render(data) {
    state.items = new Map(data.materials.map(item => [item.id, item]));
    state.offset = data.offset; state.limit = data.limit; state.total = data.total;
    byId('material-group').replaceChildren();
    const all = node('option', '', 'All permitted groups'); all.value = ''; byId('material-group').append(all);
    for (const group of data.groups) {
      const option = node('option', '', group.name); option.value = String(group.id); byId('material-group').append(option);
    }
    byId('material-group').value = state.group;
    byId('material-group').disabled = !data.groups.length;
    byId('material-list').replaceChildren();
    for (const material of data.materials) {
      const card = node('article', 'material-card'); const details = node('div', 'material-details');
      const suffix = material.original_name.split('.').pop().slice(0, 5).toUpperCase() || 'FILE';
      details.append(node('h3', '', material.title), node('div', 'file-meta', `${material.original_name} · ${sizeLabel(material.size_bytes)}`), node('span', 'group-tag', material.folder_name ? `${material.group_name} · ${material.folder_name}` : material.group_name));
      const actions = node('div', 'material-actions');
      if (material.preview_kind) { const view = node('button', 'secondary-button', 'View ↗'); view.type = 'button'; view.dataset.view = String(material.id); actions.append(view); }
      else actions.append(node('span', 'download-only', 'Download only'));
      const download = node('button', 'primary-button', 'Download ↓'); download.type = 'button'; download.dataset.download = String(material.id); actions.append(download);
      card.append(node('span', 'file-icon', suffix), details, actions); byId('material-list').append(card);
    }
    if (!data.materials.length) byId('material-list').append(node('p', 'empty-state', data.groups.length ? 'No materials on this page yet. Choose another group or refresh after materials are shared.' : 'No study groups or materials are available for this account yet.'));
    byId('material-count').textContent = `${data.total} ${data.total === 1 ? 'material' : 'materials'}`;
    byId('page-info').textContent = data.materials.length ? `${data.offset + 1}–${data.offset + data.materials.length} of ${data.total}` : 'No materials on this page';
    byId('previous-page').disabled = data.offset === 0;
    byId('next-page').disabled = data.offset + data.materials.length >= data.total;
    byId('library').hidden = false;
  }
  async function loadUploadFolders(groupId) {
    const folderSelect = byId('upload-folder');
    folderSelect.replaceChildren();
    byId('upload-panel').hidden = true;
    if (!groupId || !state.session || !['instructor', 'administrator'].includes(state.session.user.role)) return;
    try {
      const data = await json(`/api/groups/${groupId}/folders`);
      if (!data.can_create) return;
      for (const folder of data.folders) {
        const option = node('option', '', folder.name);
        option.value = String(folder.id);
        folderSelect.append(option);
      }
      byId('upload-panel').hidden = false;
      if (!data.folders.length) {
        const option = node('option', '', 'Create a folder first from the Folders page');
        option.value = '';
        folderSelect.append(option);
        byId('upload-submit').disabled = true;
      } else {
        byId('upload-submit').disabled = false;
      }
    } catch (error) {
      message('upload-status', error.message, true);
    }
  }
  async function configureUpload(groups) {
    const select = byId('upload-group');
    select.replaceChildren();
    for (const group of groups) {
      const option = node('option', '', group.name);
      option.value = String(group.id);
      select.append(option);
    }
    if (!groups.length || !state.session || !['instructor', 'administrator'].includes(state.session.user.role)) {
      byId('upload-panel').hidden = true;
      return;
    }
    select.value = state.group && groups.some(g => String(g.id) === state.group)
      ? state.group : String(groups[0].id);
    await loadUploadFolders(select.value);
  }
  async function loadCatalog(token) {
    clearLibrary(); byId('refresh-library').disabled = true;
    message('library-status', 'Loading study materials…');
    const params = new URLSearchParams({limit: String(state.limit), offset: String(state.offset)});
    if (state.group) params.set('group_id', state.group);
    try {
      const data = await json(`/api/materials?${params}`);
      if (token !== state.revision) return false;
      render(data); await configureUpload(data.groups); message('library-status', ''); return true;
    } catch (error) {
      if (token !== state.revision) return false;
      clearLibrary(error.status === 401);
      message('library-status', error.message, true); return false;
    } finally { if (token === state.revision) byId('refresh-library').disabled = false; }
  }
  async function loadAccount(token) {
    clearLibrary(true); message('library-status', 'Opening your library…');
    try {
      const session = await json('/api/session');
      if (token !== state.revision) return false;
      state.session = session; byId('profile-name').textContent = session.user.name;
      byId('role-badge').textContent = session.user.role; byId('role-badge').hidden = false;
      return await loadCatalog(token);
    } catch (error) {
      if (token !== state.revision) return false;
      clearLibrary(true); message('library-status', error.status === 401 ? 'Sign in to access your study materials. In local demo mode, choose a sample account above.' : error.message, error.status !== 401);
      return false;
    }
  }
  async function release(response) { try { await response.body?.cancel(); } catch {} }
  function fileError(status) {
    return ({401: 'Your session has expired. Sign in again.', 403: 'You do not have access to this material.', 404: 'This material file is unavailable or has not finished saving.'})[status] || 'The material could not be accessed. Please try again.';
  }
  async function preview(material) {
    closePreview(); previewMaterial = material;
    const sequence = previewSequence; const revision = state.revision;
    previewController = globalThis.AbortController ? new AbortController() : null;
    byId('preview-title').textContent = material.title;
    byId('preview-download').disabled = false;
    if (!byId('preview-dialog').open) byId('preview-dialog').showModal();
    message('preview-status', 'Loading preview…');
    try {
      const response = await fetch(`/api/materials/${material.id}/view`, {credentials: 'same-origin', signal: previewController?.signal});
      if (sequence !== previewSequence || revision !== state.revision) { await release(response); return; }
      if (!response.ok) { await release(response); throw new Error(fileError(response.status)); }
      const type = response.headers.get('Content-Type') || '';
      const disposition = response.headers.get('Content-Disposition') || '';
      if (disposition.startsWith('attachment')) { await release(response); message('preview-status', 'This format is available as a download.'); return; }
      if (type.startsWith('text/plain')) {
        const length = response.headers.get('Content-Length');
        if (length === null || !Number.isFinite(Number(length)) || Number(length) > 2 * 1024 * 1024) { await release(response); message('preview-status', 'This text file is too large for the preview. Use Download to read it.'); return; }
        const text = await response.text();
        if (sequence !== previewSequence || revision !== state.revision) return;
        byId('preview-text').textContent = text || '(This file is empty.)'; byId('preview-text').hidden = false;
      } else {
        await release(response);
        if (sequence !== previewSequence || revision !== state.revision) return;
        const url = `/api/materials/${material.id}/view`;
        if (type === 'application/pdf') { byId('preview-frame').src = url; byId('preview-frame').hidden = false; }
        else if (['image/png', 'image/jpeg', 'image/gif', 'image/webp'].includes(type)) { byId('preview-image').src = url; byId('preview-image').hidden = false; }
        else { message('preview-status', 'This format is available as a download.'); return; }
      }
      message('preview-status', '');
    } catch (error) { if (sequence === previewSequence && revision === state.revision) message('preview-status', error.message, true); }
  }
  async function download(material, button) {
    const revision = state.revision;
    button.disabled = true;
    try {
      const url = `/api/materials/${material.id}/download`;
      const response = await fetch(url, {method: 'HEAD', credentials: 'same-origin'});
      if (revision !== state.revision) return;
      if (!response.ok) throw new Error(fileError(response.status));
      const link = node('a'); link.href = url; link.download = '';
      document.body.append(link); link.click(); link.remove();
      message('library-status', 'Your download has been requested.');
    } catch (error) { if (revision === state.revision) message('library-status', error.message, true); }
    finally { if (revision === state.revision) button.disabled = false; }
  }
  byId('material-list').addEventListener('click', event => {
    const view = event.target.closest('[data-view]');
    const save = event.target.closest('[data-download]');
    const button = view || save; if (!button || button.disabled) return;
    const material = state.items.get(Number(view ? view.dataset.view : save.dataset.download));
    if (material) return view ? preview(material) : download(material, button);
  });
  byId('preview-download').addEventListener('click', () => { if (previewMaterial) return download(previewMaterial, byId('preview-download')); });
  byId('close-preview').addEventListener('click', closePreview);
  byId('preview-dialog').addEventListener('cancel', invalidatePreview);
  byId('preview-dialog').addEventListener('close', () => { if (!byId('preview-dialog').open) invalidatePreview(); });
  byId('material-group').addEventListener('change', () => {
    if (!state.session || state.switching) return;
    state.group = byId('material-group').value; state.offset = 0;
    return loadCatalog(++state.revision);
  });
  byId('refresh-library').addEventListener('click', () => {
    if (!state.session || state.switching || byId('refresh-library').disabled) return;
    state.offset = 0; return loadCatalog(++state.revision);
  });
  for (const [id, direction] of [['previous-page', -1], ['next-page', 1]]) byId(id).addEventListener('click', () => {
    if (!state.session || state.switching || byId(id).disabled) return;
    state.offset = Math.max(0, state.offset + direction * state.limit);
    return loadCatalog(++state.revision);
  });
  byId('upload-group').addEventListener('change', () => loadUploadFolders(byId('upload-group').value));
  byId('upload-form').addEventListener('submit', async event => {
    event.preventDefault();
    const groupId = byId('upload-group').value;
    const folderId = byId('upload-folder').value;
    const file = byId('upload-file').files[0];
    if (!groupId || !folderId || !file || !state.session) {
      message('upload-status', 'Choose a group, destination folder, and file.', true);
      return;
    }
    const form = new FormData();
    form.append('folder_id', folderId);
    form.append('file', file);
    const button = byId('upload-submit');
    button.disabled = true;
    message('upload-status', 'Uploading…');
    try {
      const response = await fetch(`/api/groups/${groupId}/materials`, {
        method: 'POST', body: form, credentials: 'same-origin',
        headers: {'X-CSRF-Token': state.session.csrf_token}
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'Upload failed.');
      byId('upload-file').value = '';
      message('upload-status', 'Upload successful! Your material is now in the selected folder.');
      state.group = groupId;
      byId('material-group').value = groupId;
      state.offset = 0;
      await loadCatalog(++state.revision);
      message('upload-status', 'Upload successful! Your material is now in the selected folder.');
    } catch (error) {
      message('upload-status', error.message, true);
    } finally {
      button.disabled = false;
    }
  });
  byId('sample-accounts').addEventListener('click', async event => {
    const button = event.target.closest('[data-account]');
    if (!button || !state.initialized || !state.demo || state.switching) return;
    state.switching = true; const token = ++state.revision;
    const buttons = [...byId('sample-accounts').querySelectorAll('button')];
    buttons.forEach(item => { item.disabled = true; item.classList.remove('selected'); });
    clearLibrary(true);
    try {
      await json('/api/demo/session', {method: 'POST', body: JSON.stringify({user_id: Number(button.dataset.account)})});
      const loaded = await loadAccount(token);
      if (token === state.revision) buttons.forEach(item => item.classList.toggle('selected', loaded && item === button));
    } catch (error) { if (token === state.revision) message('library-status', error.message, true); }
    finally { state.switching = false; buttons.forEach(item => item.disabled = false); }
  });
  (async () => {
    try {
      const health = await json('/api/health'); state.demo = health.demo;
      byId('demo-banner').hidden = !health.demo;
      await loadAccount(state.revision);
      state.initialized = true; byId('sample-panel').hidden = !health.demo;
    } catch { clearLibrary(true); message('library-status', 'Cannot reach the application. Start the server and refresh.', true); }
  })();
})();
