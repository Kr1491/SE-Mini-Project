
"use strict";

(() => {
  const byId = id => document.getElementById(id);

  let initialized = false;
  let demoMode = false;
  let switching = false;
  let revision = 0;
  let currentSession = null;
  let quizQuestionCounter = 0;
  let selectedQuiz = null;

  const rolePath = (globalThis.location?.pathname || '').match(
    /^\/dashboard\/(student|instructor|administrator)$/
  );

  const dashboardApi = rolePath
    ? `/api/dashboard/${rolePath[1]}`
    : '/api/dashboard';

  function node(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }

  async function request(path, options = {}) {
    const headers = { ...options.headers };

    if (options.body !== undefined) {
      headers['Content-Type'] = 'application/json';
    }

    if (currentSession) {
      headers['X-CSRF-Token'] = currentSession.csrf_token;
    }

    const response = await fetch(path, {
      ...options,
      headers,
      credentials: 'same-origin'
    });

    const data = await response.json();

    if (!response.ok) {
      const error = new Error(
        data.error || 'Your workspace could not be loaded.'
      );
      error.status = response.status;
      throw error;
    }

    return data;
  }

  function status(message, error = false) {
    byId('dashboard-status').textContent = message;
    byId('dashboard-status').classList.toggle('error', error);
  }

  function setMessage(element, message, error = false) {
    element.textContent = message;
    element.classList.toggle('error', error);
  }

  function clearWorkspace() {
    document.title = 'StudySpace · Your workspace';

    byId('dashboard-content').hidden = true;
    byId('profile').hidden = true;
    byId('signed-out').hidden = true;

    for (const id of [
      'dashboard-stats',
      'study-groups',
      'tools',
      'dashboard-nav'
    ]) {
      byId(id).replaceChildren();
    }

    for (const id of [
      'profile-name',
      'profile-email',
      'profile-avatar',
      'dashboard-title',
      'dashboard-description',
      'dashboard-role',
      'updated-at'
    ]) {
      byId(id).textContent = '';
    }

    byId('create-group-panel').hidden = true;
    byId('quiz-creation-panel').hidden = true;
    byId('quiz-attempts-panel').hidden = true;
    byId('results-panel').hidden = true;

    for (const id of [
      'group-name',
      'group-description',
      'quiz-title'
    ]) {
      byId(id).value = '';
    }

    for (const id of [
      'create-group-status',
      'create-quiz-status',
      'quiz-attempt-status',
      'results-status'
    ]) {
      setMessage(byId(id), '');
    }

    byId('quiz-questions').replaceChildren();
    byId('quiz-group').replaceChildren();
    byId('available-quizzes').replaceChildren();
    byId('attempt-questions').replaceChildren();
    byId('results-list').replaceChildren();
    byId('performance-group').replaceChildren();

    byId('quiz-attempt-form').hidden = true;
    byId('submit-quiz-button').disabled = false;

    byId('create-quiz-button').disabled = false;
    byId('add-quiz-question').disabled = false;
    byId('quiz-title').disabled = false;
    byId('quiz-group').disabled = false;

    quizQuestionCounter = 0;
    selectedQuiz = null;

    delete document.body.dataset.role;
  }

  function safeHref(value) {
    return typeof value === 'string' && (
      /^#[a-z0-9-]+$/.test(value) ||
      value === '/access' ||
      value === '/access#folders-panel' ||
      value === '/materials' ||
      value === '/admin/users' ||
      value === '/quizzes' ||
      value === '/results'
    ) ? value : null;
  }

  function render(data) {
    document.body.dataset.role = data.role;

    document.title =
      `StudySpace · ${data.role[0].toUpperCase() + data.role.slice(1)} dashboard`;

    byId('dashboard-eyebrow').textContent =
      `${data.role.toUpperCase()} WORKSPACE`;

    byId('dashboard-title').textContent = data.title;
    byId('dashboard-description').textContent = data.description;
    byId('dashboard-role').textContent = data.role;

    byId('profile-name').textContent = data.user.name;
    byId('profile-email').textContent = data.user.email;
    byId('profile-avatar').textContent =
      data.user.name.trim().slice(0, 1).toUpperCase() || 'S';

    byId('profile').hidden = false;

    for (const [index, entry] of data.navigation.entries()) {
      const href = safeHref(entry.href);
      if (!href) continue;

      const link = node('a', 'nav-link');
      link.href = href;

      link.append(
        node('span', 'nav-marker', ['▦', '▱', '↗'][index] || '·'),
        node('span', '', entry.label)
      );

      byId('dashboard-nav').append(link);
    }

    for (const [index, stat] of data.stats.entries()) {
      const card = node('article', 'stat-card');
      const content = node('div');

      content.append(
        node('p', 'stat-label', stat.label),
        node('strong', 'stat-value', String(stat.value))
      );

      card.append(
        node('span', 'stat-icon', ['▦', '↗', '✓'][index] || '·'),
        content
      );

      byId('dashboard-stats').append(card);
    }

    byId('create-group-panel').hidden =
      data.role !== 'instructor';

    const isQuizPage = globalThis.location?.pathname === '/quizzes';
    const isResultsPage = globalThis.location?.pathname === '/results';

    byId('quiz-creation-panel').hidden =
      !isQuizPage || data.role !== 'instructor';

    byId('quiz-attempts-panel').hidden =
      !isQuizPage || data.role !== 'student';

    byId('results-panel').hidden =
      !isResultsPage ||
      !['student', 'instructor'].includes(data.role);

    const quizGroupSelect = byId('quiz-group');
    const placeholder = node('option', '', 'Choose a study group');
    placeholder.value = '';
    quizGroupSelect.replaceChildren(placeholder);

    const manageableGroups = data.groups.filter(
      group => group.can_manage
    );

    for (const group of manageableGroups) {
      const option = node('option', '', group.name);
      option.value = String(group.id);
      quizGroupSelect.append(option);
    }

    if (!manageableGroups.length) {
      const option = node(
        'option',
        '',
        'Create a study group first'
      );
      option.disabled = true;
      quizGroupSelect.append(option);
    }

    if (
      isQuizPage &&
      data.role === 'instructor' &&
      !byId('quiz-questions').children.length
    ) {
      addQuizQuestion();
    }

    byId('groups-heading').textContent = data.group_heading;
    byId('groups-count').textContent =
      `${data.groups.length} ${data.groups.length === 1 ? 'group' : 'groups'}`;

    for (const group of data.groups) {
      const card = node('article', 'group-card');

      card.append(
        node('span', 'group-icon', '▱'),
        node('h3', '', group.name),
        node('p', '', group.relationship),
        node(
          'span',
          'group-tag',
          group.can_manage ? 'Management access' : 'Read access'
        )
      );

      byId('study-groups').append(card);
    }

    if (!data.groups.length) {
      byId('study-groups').append(
        node(
          'p',
          'empty-state',
          'No study groups are available for this account yet. Your groups will appear here when access is granted.'
        )
      );
    }

    byId('tools-heading').textContent = data.tools_heading;

    for (const action of data.actions) {
      const card = node('article', 'tool-card');
      const content = node('div');

      content.append(
        node('h3', '', action.label),
        node('p', '', action.description)
      );

      const href = action.available && safeHref(action.href);

      if (href) {
        const link = node('a', 'tool-link', 'Open workspace ↗');
        link.href = href;
        content.append(link);
      } else {
        content.append(node('span', 'coming-soon', 'Coming soon'));
      }

      card.append(
        node('span', 'tool-icon', action.available ? '↗' : '▱'),
        content
      );

      byId('tools').append(card);
    }

    const updated = new Date(data.updated_at);

    byId('updated-at').textContent =
      Number.isNaN(updated.getTime())
        ? ''
        : `Updated ${updated.toLocaleTimeString([], {
            hour: '2-digit',
            minute: '2-digit'
          })}`;

    byId('signed-out').hidden = true;
    byId('dashboard-content').hidden = false;

    if (isQuizPage && data.role === 'student') {
      loadAvailableQuizzes(data.groups);
    }

    if (isResultsPage && data.role === 'student') {
      loadStudentResults();
    }

    if (isResultsPage && data.role === 'instructor') {
      loadInstructorResults(data.groups);
    }
  }

  // ------------------------------
  // Student: available quizzes
  // ------------------------------

  async function loadAvailableQuizzes(groups) {
    const container = byId('available-quizzes');

    container.replaceChildren();
    setMessage(byId('quiz-attempt-status'), 'Loading available quizzes…');

    let foundQuiz = false;

    for (const group of groups) {
      try {
        const data = await request(
          `/api/groups/${group.id}/quizzes`
        );

        for (const quiz of data.quizzes || []) {
          foundQuiz = true;

          const card = node('article', 'quiz-card');

          card.append(
            node('h3', '', quiz.title),
            node('p', '', group.name),
            node(
              'p',
              'quiz-meta',
              `${(quiz.questions || []).length} questions`
            )
          );

          const button = node('button', 'button', 'Take quiz');
          button.type = 'button';

          button.addEventListener('click', () => {
            showQuiz(quiz);
          });

          card.append(button);
          container.append(card);
        }
      } catch (error) {
        console.error('Could not load quizzes for group:', error);
      }
    }

    if (!foundQuiz) {
      container.append(
        node(
          'p',
          'empty-state',
          'No quizzes are available in your study groups yet.'
        )
      );
    }

    setMessage(byId('quiz-attempt-status'), '');
  }

  function showQuiz(quiz) {
    selectedQuiz = quiz;
    byId('quiz-attempt-container').hidden = false;

    byId('attempt-quiz-title').textContent = quiz.title;
    byId('attempt-questions').replaceChildren();

    for (const [index, question] of (quiz.questions || []).entries()) {
      const section = node('fieldset', 'attempt-question');

      section.append(
        node('legend', '', `${index + 1}. ${question.question}`)
      );

      for (const option of question.options || []) {
        const label = node('label', 'attempt-option');

        const radio = node('input');
        radio.type = 'radio';
        radio.name = `question-${question.id}`;
        radio.value = String(option.id);
        radio.required = true;

        label.append(
          radio,
          node('span', '', option.text)
        );

        section.append(label);
      }

      byId('attempt-questions').append(section);
    }

    byId('quiz-attempt-form').hidden = false;
    setMessage(byId('quiz-attempt-status'), '');

    byId('quiz-attempt-form').scrollIntoView({
      behavior: 'smooth',
      block: 'start'
    });
  }

  byId('quiz-attempt-form').addEventListener('submit', async event => {
    event.preventDefault();

    if (
      !currentSession ||
      currentSession.user.role !== 'student' ||
      !selectedQuiz
    ) {
      return;
    }

    const button = byId('submit-quiz-button');
    if (button.disabled || switching) return;

    const answers = [];

    for (const question of selectedQuiz.questions || []) {
      const selected = document.querySelector(
        `input[name="question-${question.id}"]:checked`
      );

      if (!selected) {
        setMessage(
          byId('quiz-attempt-status'),
          'Please answer every question before submitting.',
          true
        );
        return;
      }

      answers.push({
        question_id: question.id,
        option_id: Number(selected.value)
      });
    }

    button.disabled = true;
    setMessage(byId('quiz-attempt-status'), 'Submitting your answers…');

    try {
      const result = await request(
        `/api/quizzes/${selectedQuiz.id}/attempts`,
        {
          method: 'POST',
          body: JSON.stringify({ answers })
        }
      );

      const score = result.attempt.score;
const total = result.attempt.total_questions;
const percentage = result.attempt.percentage;

      byId('attempt-questions').replaceChildren();

      byId('attempt-questions').append(
        node('h3', 'score-summary', 'Quiz submitted successfully!'),
        node('p', '', `Your score: ${score} / ${total}`),
        node('p', '', `Percentage: ${percentage}%`)
      );

      button.hidden = true;

      setMessage(
        byId('quiz-attempt-status'),
        result.message || 'Your result has been saved.'
      );
    } catch (error) {
      setMessage(byId('quiz-attempt-status'), error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  // ------------------------------
  // Student: own quiz results
  // ------------------------------

  async function loadStudentResults() {
    const container = byId('results-list');

    container.replaceChildren();
    byId('results-heading').textContent = 'My quiz results';
    byId('results-description').textContent =
      'View your submitted quiz scores and performance.';

    byId('performance-group-control').hidden = true;

    setMessage(byId('results-status'), 'Loading your results…');

    try {
      const data = await request('/api/results/me');

      if (!data.results || !data.results.length) {
        container.append(
          node(
            'p',
            'empty-state',
            'You have not submitted any quizzes yet.'
          )
        );
      } else {
        for (const result of data.results) {
          const card = node('article', 'result-card');

          card.append(
            node('h3', '', result.quiz_title),
            node(
              'p',
              '',
              `Score: ${result.score} / ${result.total_questions}`
            ),
            node(
              'p',
              'result-percentage',
              `${result.percentage}%`
            ),
            node(
              'p',
              'result-date',
              `Submitted: ${formatDate(result.submitted_at)}`
            )
          );

          container.append(card);
        }
      }

      setMessage(byId('results-status'), '');
    } catch (error) {
      setMessage(byId('results-status'), error.message, true);
    }
  }

  // ------------------------------
  // Instructor: group performance
  // ------------------------------

  async function loadInstructorResults(groups) {
    const select = byId('performance-group');
    const container = byId('results-list');

    container.replaceChildren();

    byId('results-heading').textContent = 'Group performance';
    byId('results-description').textContent =
      'Select a study group to view submitted quiz results.';

    byId('performance-group-control').hidden = false;

    select.replaceChildren();

    const manageableGroups = groups.filter(
      group => group.can_manage
    );

    const placeholder = node('option', '', 'Choose a study group');
    placeholder.value = '';
    select.append(placeholder);

    for (const group of manageableGroups) {
      const option = node('option', '', group.name);
      option.value = String(group.id);
      select.append(option);
    }

    if (!manageableGroups.length) {
      setMessage(
        byId('results-status'),
        'You do not manage any study groups.'
      );
      return;
    }

    setMessage(
      byId('results-status'),
      'Choose a group to view its results.'
    );
  }

  byId('performance-group').addEventListener('change', async event => {
    const groupId = event.target.value;
    const container = byId('results-list');

    container.replaceChildren();

    if (!groupId) {
      setMessage(
        byId('results-status'),
        'Choose a group to view its results.'
      );
      return;
    }

    setMessage(byId('results-status'), 'Loading group results…');

    try {
      const data = await request(
        `/api/groups/${groupId}/results`
      );

      const results = data.results || [];

      if (!results.length) {
        container.append(
          node(
            'p',
            'empty-state',
            'No quiz submissions have been recorded for this group yet.'
          )
        );
      } else {
        for (const result of results) {
          const card = node('article', 'result-card');

          card.append(
            node('h3', '', result.quiz_title),
            node('p', '', `Student: ${result.student_name}`),
            node(
              'p',
              '',
              `Score: ${result.score} / ${result.total_questions}`
            ),
            node(
              'p',
              'result-percentage',
              `${result.percentage}%`
            ),
            node(
              'p',
              'result-date',
              `Submitted: ${formatDate(result.submitted_at)}`
            )
          );

          container.append(card);
        }
      }

      setMessage(byId('results-status'), '');
    } catch (error) {
      setMessage(byId('results-status'), error.message, true);
    }
  });

  function formatDate(value) {
    const date = new Date(value);

    return Number.isNaN(date.getTime())
      ? String(value || 'Not available')
      : date.toLocaleString();
  }

  // ------------------------------
  // Instructor: create quiz
  // ------------------------------

  function addQuizQuestion() {
    if (
      !currentSession ||
      currentSession.user.role !== 'instructor' ||
      switching ||
      byId('create-quiz-button').disabled ||
      globalThis.location?.pathname !== '/quizzes'
    ) {
      return;
    }

    const questionNumber = ++quizQuestionCounter;
    const card = node('fieldset', 'quiz-question-card');

    card.dataset.question = String(questionNumber);

    const heading = node('legend', '', `Question ${questionNumber}`);

    const questionInput = node('textarea', 'quiz-question-input');
    questionInput.placeholder = 'Enter your question';
    questionInput.required = true;
    questionInput.maxLength = 1000;

    card.append(heading, questionInput);

    const optionsContainer = node('div', 'quiz-options');

    for (let index = 0; index < 4; index++) {
      const optionRow = node('label', 'quiz-option-row');

      const radio = node('input');
      radio.type = 'radio';
      radio.name = `correct-answer-${questionNumber}`;
      radio.value = String(index);
      radio.required = true;

      if (index === 0) radio.checked = true;

      const optionInput = node('input', 'quiz-option-input');
      optionInput.type = 'text';
      optionInput.placeholder = `Option ${index + 1}`;
      optionInput.maxLength = 500;
      optionInput.required = true;

      optionRow.append(radio, optionInput);
      optionsContainer.append(optionRow);
    }

    card.append(optionsContainer);

    const removeButton = node('button', 'text-button', 'Remove question');
    removeButton.type = 'button';
    removeButton.addEventListener('click', () => card.remove());

    card.append(removeButton);
    byId('quiz-questions').append(card);
  }

  byId('add-quiz-question').addEventListener(
    'click',
    addQuizQuestion
  );

  byId('create-quiz-form').addEventListener('submit', async event => {
    event.preventDefault();

    if (
      !currentSession ||
      currentSession.user.role !== 'instructor'
    ) {
      return;
    }

    const form = event.currentTarget;
    const button = byId('create-quiz-button');

    if (button.disabled || switching) return;

    const token = revision;
    const message = byId('create-quiz-status');
    const groupId = Number(byId('quiz-group').value);
    const title = byId('quiz-title').value.trim();

    const questionCards = [
      ...byId('quiz-questions').querySelectorAll('.quiz-question-card')
    ];

    setMessage(message, '');

    if (!groupId || !title || !questionCards.length) {
      setMessage(
        message,
        'Choose a group, enter a title, and add at least one question.',
        true
      );
      return;
    }

    const questions = questionCards.map(card => {
      const question = card.querySelector(
        '.quiz-question-input'
      ).value.trim();

      const optionRows = [
        ...card.querySelectorAll('.quiz-option-row')
      ];

      return {
        question,
        options: optionRows.map(row => ({
          text: row.querySelector('.quiz-option-input').value.trim(),
          is_correct: row.querySelector('input[type="radio"]').checked
        }))
      };
    });

    if (
      questions.some(question =>
        !question.question ||
        question.options.length < 2 ||
        question.options.some(option => !option.text) ||
        question.options.filter(option => option.is_correct).length !== 1
      )
    ) {
      setMessage(
        message,
        'Complete every question and option, and select exactly one correct answer per question.',
        true
      );
      return;
    }

    button.disabled = true;

    for (const id of [
      'quiz-group',
      'quiz-title',
      'add-quiz-question'
    ]) {
      byId(id).disabled = true;
    }

    for (const card of questionCards) {
      card.disabled = true;
    }

    try {
      const result = await request(
        `/api/groups/${groupId}/quizzes`,
        {
          method: 'POST',
          body: JSON.stringify({ title, questions })
        }
      );

      if (token !== revision) return;

      form.reset();
      byId('quiz-questions').replaceChildren();
      quizQuestionCounter = 0;

      button.disabled = false;
      addQuizQuestion();

      setMessage(
        message,
        result.quiz.message || 'Quiz created successfully.'
      );
    } catch (error) {
      if (token === revision) {
        setMessage(message, error.message, true);
      }
    } finally {
      if (token === revision) {
        button.disabled = false;

        for (const id of [
          'quiz-group',
          'quiz-title',
          'add-quiz-question'
        ]) {
          byId(id).disabled = false;
        }

        for (const card of byId('quiz-questions').children) {
          card.disabled = false;
        }
      }
    }
  });

  // ------------------------------
  // Load dashboard and session
  // ------------------------------

  async function load(token) {
    clearWorkspace();
    status('Loading your workspace…');

    try {
      const authenticated = await request('/api/session');

      if (token !== revision) return false;

      currentSession = authenticated;

      const data = await request(dashboardApi);

      if (token !== revision) return false;

      render(data);
      status('');

      return true;
    } catch (error) {
      if (token !== revision) return false;

      currentSession = null;
      clearWorkspace();

      byId('signed-out').hidden = false;

      byId('signed-out-description').textContent =
        error.status === 403
          ? 'This page is for another role. Open your own dashboard to continue.'
          : 'Sign in to see your groups and role-specific tools. In local demo mode, select a sample account above.';

      status(error.message, error.status !== 401);

      return false;
    }
  }

  // ------------------------------
  // Demo account switching
  // ------------------------------

  byId('sample-accounts').addEventListener('click', async event => {
    const button = event.target.closest('[data-account]');

    if (
      !button ||
      !initialized ||
      !demoMode ||
      switching
    ) {
      return;
    }

    switching = true;

    const token = ++revision;

    const buttons = [
      ...byId('sample-accounts').querySelectorAll('button')
    ];

    buttons.forEach(item => {
      item.disabled = true;
      item.classList.remove('selected');
    });

    byId('refresh-dashboard').disabled = true;

    currentSession = null;
    clearWorkspace();
    status('Opening the selected workspace…');

    try {
      await request('/api/demo/session', {
        method: 'POST',
        body: JSON.stringify({
          user_id: Number(button.dataset.account)
        })
      });

      const loaded = await load(token);

      if (token === revision) {
        buttons.forEach(item => {
          item.classList.toggle(
            'selected',
            loaded && item === button
          );
        });
      }
    } catch (error) {
      if (token === revision) {
        clearWorkspace();
        byId('signed-out').hidden = false;
        status(error.message, true);
      }
    } finally {
      switching = false;
      buttons.forEach(item => item.disabled = false);

      if (token === revision) {
        byId('refresh-dashboard').disabled = false;
      }
    }
  });

  // ------------------------------
  // Logout
  // ------------------------------

  byId('logout').addEventListener('click', async () => {
    if (!currentSession || switching) return;

    switching = true;
    ++revision;

    byId('logout').disabled = true;

    clearWorkspace();
    status('Signing out…');

    try {
      await request('/api/logout', {
        method: 'POST',
        body: '{}'
      });

      currentSession = null;
      globalThis.location?.replace?.('/login');
    } catch (error) {
      currentSession = null;

      if (error.status === 401) {
        globalThis.location?.replace?.('/login');
      } else {
        byId('signed-out').hidden = false;
        status(error.message, true);
      }
    } finally {
      switching = false;
      byId('logout').disabled = false;
    }
  });

  // ------------------------------
  // Refresh dashboard
  // ------------------------------

  byId('refresh-dashboard').addEventListener('click', async () => {
    if (
      !initialized ||
      switching ||
      byId('refresh-dashboard').disabled
    ) {
      return;
    }

    const token = ++revision;

    byId('refresh-dashboard').disabled = true;

    await load(token);

    if (token === revision) {
      byId('refresh-dashboard').disabled = false;
    }
  });

  // ------------------------------
  // Create study group
  // ------------------------------

  byId('create-group-form').addEventListener('submit', async event => {
    event.preventDefault();

    if (
      !currentSession ||
      currentSession.user.role !== 'instructor'
    ) {
      return;
    }

    const form = event.currentTarget;
    const button = byId('create-group-button');
    const message = byId('create-group-status');

    const name = byId('group-name').value.trim();
    const description = byId('group-description').value.trim();

    setMessage(message, '');

    if (!name) {
      setMessage(message, 'Please enter a group name.', true);
      return;
    }

    button.disabled = true;

    try {
      await request('/api/groups', {
        method: 'POST',
        body: JSON.stringify({ name, description })
      });

      form.reset();

      const token = ++revision;
      const loaded = await load(token);

      if (loaded && token === revision) {
        setMessage(
          byId('create-group-status'),
          'Study group created successfully.'
        );
      }
    } catch (error) {
      setMessage(message, error.message, true);
    } finally {
      button.disabled = false;
    }
  });

  // ------------------------------
  // Start application
  // ------------------------------

  (async () => {
    try {
      const health = await request('/api/health');

      demoMode = health.demo;

      byId('demo-banner').hidden = !health.demo;

      await load(revision);

      initialized = true;

      byId('sample-panel').hidden = !health.demo;
    } catch (error) {
      clearWorkspace();
      byId('signed-out').hidden = false;

      status(
        'Cannot reach the application. Start the server and refresh.',
        true
      );
    }
  })();

})();
