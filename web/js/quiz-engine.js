/**
 * quiz-engine.js
 * Handles quiz state, question navigation, answer checking.
 */

const QuizEngine = (() => {
  let questions = [];
  let currentIndex = 0;
  let answers = {};   // id -> selected option id
  let results = {};   // id -> {correct: bool, your: id}

  function init(qs) {
    questions = qs;
    currentIndex = 0;
    answers = {};
    results = {};
  }

  function current() {
    return questions[currentIndex] || null;
  }

  function total() { return questions.length; }

  function progress() { return { current: currentIndex + 1, total: questions.length }; }

  function selectAnswer(questionId, optionId) {
    answers[questionId] = optionId;
  }

  function checkAnswer(questionId) {
    const q = questions.find(q => q.id === questionId);
    if (!q) return null;
    const selected = answers[questionId];
    if (!selected) return null;
    const correct = q.correct;
    results[questionId] = { correct: selected === correct, your: selected, correctAnswer: correct };
    return results[questionId];
  }

  function isAnswered(questionId) {
    return questionId in answers;
  }

  function isCorrect(questionId) {
    return results[questionId]?.correct ?? null;
  }

  function next() {
    if (currentIndex < questions.length - 1) currentIndex++;
    return current();
  }

  function prev() {
    if (currentIndex > 0) currentIndex--;
    return current();
  }

  function goTo(index) {
    if (index >= 0 && index < questions.length) currentIndex = index;
    return current();
  }

  function getAllResults() {
    return questions.map(q => ({
      question: q,
      result: results[q.id] || null,
      answered: q.id in answers
    }));
  }

  function score() {
    const answered = Object.keys(results);
    const correct = answered.filter(id => results[id].correct).length;
    return { correct, total: questions.length, answered: answered.length };
  }

  function getAnswer(questionId) {
    return answers[questionId] || null;
  }

  function renderQuestion(q) {
    const sel = getAnswer(q.id);
    const res = results[q.id];

    let optionsHtml = q.options.map(opt => {
      let cls = 'option';
      if (sel === opt.id) cls += ' selected';
      if (res) {
        if (opt.id === q.correct) cls += ' correct';
        else if (sel === opt.id && opt.id !== q.correct) cls += ' wrong';
      }
      return `<div class="${cls}" data-id="${q.id}" data-option="${opt.id}">
        <span class="option-id">${opt.id}.</span>
        <span class="option-text">${opt.text}</span>
      </div>`;
    }).join('');

    let explanationHtml = '';
    if (res) {
      const expLink = q.source_url ? `<a href="${q.source_url}" target="_blank" rel="noopener">Source</a>` : '';
      explanationHtml = `<div class="explanation">
        <strong>Explanation:</strong> ${q.explanation} ${expLink}
      </div>`;
    }

    return `<div class="card">
      <div class="question-number">Question ${currentIndex + 1} of ${total()}</div>
      ${q.section ? `<div style="font-size:0.78rem;color:var(--text-muted);margin-bottom:0.3rem">${q.section} — ${q.section_title || ''}</div>` : ''}
      <div class="question-text">${q.question}</div>
      <div class="options">${optionsHtml}</div>
      ${explanationHtml}
      ${!res ? `<button class="btn btn-primary next-btn" id="check-answer">Check Answer</button>` : ''}
      ${res && currentIndex < total() - 1 ? `<button class="btn btn-primary next-btn" id="next-question">Next Question →</button>` : ''}
      ${res && currentIndex === total() - 1 ? `<button class="btn btn-primary next-btn" id="finish-quiz">See Results →</button>` : ''}
    </div>`;
  }

  return { init, current, total, progress, selectAnswer, checkAnswer, isAnswered, isCorrect, next, prev, goTo, getAllResults, score, getAnswer, renderQuestion };
})();