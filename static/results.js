"use strict";
(() => {
  const el = id => document.getElementById(id);
  let revision = 0;
  function node(tag, text, className) {
    const item = document.createElement(tag);
    if (text !== undefined) item.textContent = text;
    if (className) item.className = className;
    return item;
  }
  function reset() {
    ++revision;
    el('results-panel').hidden = true;
    el('results-list').replaceChildren();
    el('results-status').textContent = '';
    el('results-status').classList.remove('error');
    el('results-description').textContent = '';
    el('performance-group').replaceChildren();
    el('performance-group').onchange = null;
    el('performance-group-control').hidden = true;
  }
  async function load(session, {groups = [], request, onDenied = () => {}}) {
    reset();
    if (!session?.user) return;
    const token = revision;
    let sequence = 0;
    const student = session.user.role === 'student';
    el('results-heading').textContent = student ? 'Your results' : 'Student performance';
    el('results-description').textContent = student
      ? 'Your submitted quizzes and saved scores.'
      : 'Submitted quiz results for a study group you manage.';
    el('results-panel').hidden = false;
    async function fetchResults(path) {
      const selected = ++sequence;
      el('results-list').replaceChildren();
      el('results-status').textContent = path ? 'Loading results…' : 'Choose a study group to view results.';
      el('results-status').classList.remove('error');
      if (!path) return;
      try {
        const data = await request(path);
        if (token !== revision || selected !== sequence) return;
        for (const result of data.results) {
          const card = node('article', undefined, 'result-card');
          card.append(node('h3', result.quiz_title));
          if (!student) card.append(node('p', result.student_name));
          const graded = result.score !== null && result.total_questions !== null;
          card.append(node('p', graded ? `${result.score} / ${result.total_questions}` : 'Score unavailable', 'score-summary'));
          if (graded && result.percentage !== null) card.append(node('p', `${result.percentage}%`, 'result-percentage'));
          const date = new Date(result.submitted_at);
          card.append(node('p', Number.isNaN(date.getTime()) ? 'Submitted' : `Submitted ${date.toLocaleString()}`, 'result-date'));
          if (!graded) card.append(node('p', 'This earlier submission has no saved grade.'));
          el('results-list').append(card);
        }
        el('results-status').textContent = data.results.length ? `${data.results.length} submitted ${data.results.length === 1 ? 'quiz' : 'quizzes'}` : 'No submitted quizzes yet.';
      } catch (error) {
        if (token !== revision || selected !== sequence) return;
        el('results-list').replaceChildren();
        if (error.status === 401 || error.status === 403) {
          reset(); onDenied(error); return;
        }
        el('results-status').textContent = error.message || 'Results could not be loaded. Refresh to try again.';
        el('results-status').classList.add('error');
      }
    }
    if (student) return fetchResults('/api/results/me');
    el('performance-group-control').hidden = false;
    const select = el('performance-group');
    const placeholder = node('option', 'Choose a study group'); placeholder.value = '';
    select.append(placeholder);
    const permitted = new Set();
    for (const group of groups.filter(group => group.can_manage)) {
      permitted.add(String(group.id));
      const option = node('option', group.name); option.value = String(group.id); select.append(option);
    }
    select.value = '';
    select.onchange = () => fetchResults(permitted.has(select.value) ? `/api/groups/${select.value}/results` : null);
    return fetchResults(null);
  }
  globalThis.StudyResults = {load, reset};
})();
