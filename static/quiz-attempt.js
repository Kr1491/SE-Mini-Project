"use strict";
(() => {
  const byId = id => document.getElementById(id);
  let revision = 0;
  let active = null;
  function message(text, error = false) { byId('attempt-message').textContent = text; byId('attempt-message').classList.toggle('error', error); }
  function inputs(disabled) { for (const input of byId('attempt-questions').querySelectorAll('input')) input.disabled = disabled; }
  function reset() {
    ++revision; active = null;
    byId('quiz-attempt-panel').hidden = true; byId('group-quizzes').hidden = false;
    byId('attempt-questions').replaceChildren(); byId('attempt-quiz-title').textContent = '';
    byId('attempt-result').hidden = true; byId('attempt-score').textContent = ''; byId('attempt-result-summary').textContent = '';
    byId('attempt-confirmation').hidden = true; byId('attempt-confirmation-text').textContent = '';
    byId('quiz-attempt-form').onsubmit = null; byId('confirm-quiz-submit').onclick = null; byId('edit-quiz-answers').onclick = null;
    byId('close-quiz-attempt').onclick = null; byId('close-quiz-attempt').disabled = false;
    byId('submit-quiz-attempt').disabled = false; byId('submit-quiz-attempt').textContent = 'Submit answers';
    message('');
  }
  function open(attempt, options) {
    reset();
    const state = {attempt, options, revision, saving: false, submitted: false, confirming: false, payload: null};
    active = state;
    const current = () => active === state && state.revision === revision;
    const form = byId('quiz-attempt-form');
    const container = byId('attempt-questions');
    const submit = byId('submit-quiz-attempt');
    const confirm = byId('confirm-quiz-submit');
    const edit = byId('edit-quiz-answers');
    const close = byId('close-quiz-attempt');
    byId('group-quizzes').hidden = true; byId('quiz-attempt-panel').hidden = false;
    byId('attempt-quiz-title').textContent = attempt.quiz.title;
    for (const [index, question] of attempt.quiz.questions.entries()) {
      const fieldset = document.createElement('fieldset'); fieldset.className = 'attempt-question';
      const legend = document.createElement('legend'); legend.textContent = `${index + 1}. ${question.question}`; fieldset.append(legend);
      for (const option of question.options) {
        const label = document.createElement('label'); label.className = 'attempt-option';
        const input = document.createElement('input'); input.type = 'radio'; input.name = `question-${question.id}`; input.value = String(option.id);
        const text = document.createElement('span'); text.textContent = option.text;
        label.append(input, text); fieldset.append(label);
      }
      container.append(fieldset);
    }
    close.onclick = () => { if (current() && !state.saving) reset(); };
    function allowEditing() {
      state.confirming = false; state.payload = null;
      byId('attempt-confirmation').hidden = true;
      inputs(false); submit.disabled = false; submit.textContent = 'Submit answers';
    }
    function showReceipt(response) {
      state.submitted = true; state.confirming = false;
      byId('attempt-confirmation').hidden = true;
      if (Array.isArray(response.answers)) {
        const saved = new Map(response.answers.map(answer => [String(answer.question_id), String(answer.option_id)]));
        for (const question of attempt.quiz.questions) {
          for (const input of container.querySelectorAll(`input[name="question-${question.id}"]`)) input.checked = saved.get(String(question.id)) === input.value;
        }
      }
      inputs(true); submit.disabled = true; submit.textContent = 'Submitted';
      byId('attempt-result').hidden = false;
      if (response.result) {
        byId('attempt-score').textContent = `${response.result.score} / ${response.result.max_score}`;
        byId('attempt-result-summary').textContent = `${response.result.answered_count} answered · ${response.result.unanswered_count} unanswered. Your score is saved.`;
      } else {
        byId('attempt-score').textContent = 'Score unavailable';
        byId('attempt-result-summary').textContent = 'This earlier submission has saved answers but no recorded score.';
      }
      message(response.message || 'Your quiz was submitted successfully.');
      byId('attempt-result-heading').focus?.();
    }
    async function send(payload) {
      if (!current() || state.saving || state.submitted) return;
      state.saving = true; state.payload = payload; state.confirming = false;
      inputs(true); submit.disabled = true; submit.textContent = 'Submitting…';
      confirm.disabled = true; edit.disabled = true; close.disabled = true;
      message('Saving your answers and calculating your score…');
      try {
        const response = await options.request(`/api/quiz-attempts/${attempt.attempt_id}/submit`, {method: 'POST', body: JSON.stringify(payload)});
        if (!current()) return;
        showReceipt(response);
      } catch (error) {
        if (!current()) return;
        byId('attempt-confirmation').hidden = true;
        if ([401, 403].includes(error.status)) {
          reset(); options.onDenied?.(error); return;
        }
        if (error.status === 400) { allowEditing(); message(error.message, true); }
        else if (error.status === 409) {
          submit.disabled = true; submit.textContent = 'Start a new attempt';
          message(error.message + ' Use Back to quizzes to continue.', true);
        } else {
          // Keep the confirmed payload unchanged when delivery is uncertain.
          // A retry returns the same server receipt if the first request won.
          submit.disabled = false; submit.textContent = 'Retry submission';
          message('Could not confirm the submission. Retry to check your saved result; your selected answers are kept here.', true);
        }
      } finally {
        if (current()) { state.saving = false; confirm.disabled = false; edit.disabled = false; close.disabled = false; }
      }
    }
    form.onsubmit = event => {
      event.preventDefault();
      if (!current() || state.saving || state.submitted || state.confirming || submit.disabled) return;
      if (state.payload) return send(state.payload);
      const answers = [];
      for (const question of attempt.quiz.questions) {
        const selected = form.querySelector(`input[name="question-${question.id}"]:checked`);
        if (selected) answers.push({question_id: question.id, option_id: Number(selected.value)});
      }
      state.payload = {answers}; state.confirming = true;
      const unanswered = attempt.quiz.questions.length - answers.length;
      byId('attempt-confirmation-text').textContent = unanswered
        ? `${unanswered} ${unanswered === 1 ? 'question is' : 'questions are'} unanswered and will receive 0 points. Submit this quiz?`
        : 'Submit this quiz? You cannot change your answers after submission.';
      byId('attempt-confirmation').hidden = false;
      inputs(true); submit.disabled = true; confirm.focus?.();
    };
    confirm.onclick = () => { if (current() && state.confirming) return send(state.payload); };
    edit.onclick = () => { if (current() && !state.saving && !state.submitted) { allowEditing(); message(''); } };
  }
  globalThis.StudyQuizAttempt = {open, reset};
})();
