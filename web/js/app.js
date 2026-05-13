/**
 * EAU Guidelines Quiz — single-file SPA
 * All logic in one file for simplicity.
 */

const BASE = 'data';
const STORAGE_KEY = 'eau-quiz-session';
const REPO_ISSUES = 'https://github.com/Jhyrachy/eau-quiz/issues/new';

// ─── Storage ────────────────────────────────────────────────────────────────

function saveSession(session) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
}

function loadSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch { return null; }
}

function clearSession() {
  localStorage.removeItem(STORAGE_KEY);
}

// ─── Data Loading ───────────────────────────────────────────────────────────

async function fetchJSON(file) {
  const res = await fetch(`${BASE}/${file}`);
  if (!res.ok) throw new Error(`Failed to load ${file}: ${res.status}`);
  return res.json();
}

async function loadIndex() {
  return fetchJSON('index.json');
}

async function loadQuestionFile(slug) {
  return fetchJSON(`questions/${slug}.json`);
}

// ─── Router ─────────────────────────────────────────────────────────────────

function getRoute() {
  const hash = window.location.hash.slice(1) || '';
  const parts = hash.split('/').filter(Boolean);
  return { parts, route: parts[0] || 'landing' };
}

function navigate(path) {
  window.location.hash = path;
}

window.addEventListener('hashchange', render);

// ─── App State ──────────────────────────────────────────────────────────────

let state = {
  view: 'landing',     // landing | quiz | results
  guidelines: [],      // loaded index
  selected: [],         // slugs checked on landing
  questions: [],        // all questions for current session
  current: 0,           // current question index
  answers: {},          // question_id -> selected option
  startTime: null,
  elapsed: 0,
  timerInterval: null,
};

// ─── Shuffle ─────────────────────────────────────────────────────────────────

function shuffle(arr) {
  const a = [...arr];
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [a[i], a[j]] = [a[j], a[i]];
  }
  return a;
}

// ─── Render ─────────────────────────────────────────────────────────────────

function render() {
  const { route, parts } = getRoute();
  const app = document.getElementById('app');

  switch (route) {
    case 'quiz':
      renderQuiz(app, parts[1]);
      break;
    case 'results':
      renderResults(app);
      break;
    default:
      renderLanding(app);
  }
}

// ─── Landing ─────────────────────────────────────────────────────────────────

async function renderLanding(app) {
  state.view = 'landing';

  let index;
  try {
    index = await loadIndex();
  } catch {
    app.innerHTML = `<div class="container"><p class="error">Failed to load guidelines index.</p></div>`;
    return;
  }

  // Load availability (which have question files)
  const available = [];
  for (const g of index) {
    try {
      await loadQuestionFile(g.slug);
      available.push(g);
    } catch { /* skip */ }
  }

  const session = loadSession();
  const hasSession = session && session.questions && session.questions.length > 0;

  app.innerHTML = `
    <div class="container">
      <header class="header">
        <h1>EAU Guidelines Quiz</h1>
        <p>Select guidelines and start quizzing — all client-side.</p>
        ${hasSession ? `<button class="btn btn-ghost" id="resume-btn">Resume session</button>` : ''}
      </header>

      ${available.length === 0
        ? `<p class="empty">No question sets available yet.</p>`
        : `
        <div class="controls-row">
          <button class="btn btn-ghost btn-sm" id="select-all">Select all</button>
          <button class="btn btn-ghost btn-sm" id="clear-all">Clear</button>
        </div>
        <div class="checklist" id="checklist">
          ${available.map(g => `
            <label class="check-item">
              <input type="checkbox" value="${g.slug}" class="guideline-check" />
              <span class="check-name">${g.name}</span>
              <span class="check-slug">${g.slug}</span>
            </label>
          `).join('')}
        </div>
        <button class="btn btn-primary start-btn" id="start-btn" disabled>Start Quiz</button>
        `}
    </div>
  `;

  // Wire up checklist
  const checks = document.querySelectorAll('.guideline-check');
  const startBtn = document.getElementById('start-btn');

  function updateStart() {
    const sel = [...checks].filter(c => c.checked).map(c => c.value);
    startBtn.disabled = sel.length === 0;
    state.selected = sel;
  }

  checks.forEach(c => c.addEventListener('change', updateStart));
  document.getElementById('select-all')?.addEventListener('click', () => {
    checks.forEach(c => { c.checked = true; });
    updateStart();
  });
  document.getElementById('clear-all')?.addEventListener('click', () => {
    checks.forEach(c => { c.checked = false; });
    updateStart();
  });

  startBtn?.addEventListener('click', startQuiz);

  document.getElementById('resume-btn')?.addEventListener('click', () => {
    restoreSession(loadSession());
    navigate('quiz');
  });
}

// ─── Start Quiz ─────────────────────────────────────────────────────────────

async function startQuiz() {
  if (state.selected.length === 0) return;

  // Load all selected question files
  const allQuestions = [];
  for (const slug of state.selected) {
    try {
      const data = await loadQuestionFile(slug);
      const qs = data.questions || [];
      allQuestions.push(...qs);
    } catch (e) {
      console.warn(`Failed to load ${slug}:`, e);
    }
  }

  if (allQuestions.length === 0) {
    alert('No questions found for selected guidelines.');
    return;
  }

  const shuffled = shuffle(allQuestions);

  state.questions = shuffled;
  state.current = 0;
  state.answers = {};
  state.startTime = Date.now();
  state.elapsed = 0;

  clearInterval(state.timerInterval);
  state.timerInterval = setInterval(() => {
    state.elapsed = Math.floor((Date.now() - state.startTime) / 1000);
    const el = document.getElementById('elapsed-display');
    if (el) el.textContent = formatElapsed(state.elapsed);
  }, 1000);

  saveSession({
    questions: shuffled,
    current: 0,
    answers: {},
    startTime: state.startTime,
  });

  navigate('quiz');
}

// ─── Quiz View ──────────────────────────────────────────────────────────────

function renderQuiz(app, action) {
  if (action === 'end') {
    endQuiz();
    return;
  }

  if (state.questions.length === 0) {
    navigate('');
    return;
  }

  state.view = 'quiz';
  const q = state.questions[state.current];
  const answered = state.answers[q.id];
  const isCorrect = answered ? answered === q.correct : null;

  app.innerHTML = `
    <div class="container quiz-container">
      <div class="quiz-topbar">
        <span class="elapsed" id="elapsed-display">${formatElapsed(state.elapsed)}</span>
        <span class="counter">${state.current + 1} / ${state.questions.length}</span>
        <button class="btn btn-ghost btn-sm" id="end-btn">End quiz</button>
      </div>

      <div class="question-block">
        <div class="q-meta">${q.chapter ? q.chapter.replace(/-/g, ' ') : ''} · ${q.difficulty || 'medium'}</div>
        <div class="q-text">${q.question}</div>
      </div>

      <div class="options" id="options">
        ${['A','B','C','D'].map(opt => {
          const text = q.options.find(o => o.id === opt)?.text || '';
          const cls = answered
            ? opt === q.correct ? 'correct'
              : opt === answered ? 'wrong'
              : ''
            : '';
          const dis = answered ? 'disabled' : '';
          return `
            <div class="option ${cls}" data-opt="${opt}" ${dis}>
              <span class="opt-id">${opt}</span>
              <span class="opt-text">${text}</span>
            </div>`;
        }).join('')}
      </div>

      ${answered ? `
        <div class="explanation">
          <strong>Explanation:</strong> ${q.explanation}
          <div class="src-link">
            Source: <a href="${q.source_url || '#'}" target="_blank">${q.section || ' guideline'}</a>
          </div>
        </div>
        <button class="btn btn-primary next-btn" id="next-btn">
          ${state.current < state.questions.length - 1 ? 'Next →' : 'Show results'}
        </button>
      ` : ''}

      <div class="report-row">
        <a class="report-link" href="${buildIssueURL(q)}" target="_blank" title="Report an issue with this question">
          Report issue
        </a>
      </div>
    </div>
  `;

  // Wire up options (if not yet answered)
  if (!answered) {
    document.querySelectorAll('.option').forEach(el => {
      el.addEventListener('click', () => selectOption(el.dataset.opt));
    });
  }

  document.getElementById('next-btn')?.addEventListener('click', nextQuestion);
  document.getElementById('end-btn')?.addEventListener('click', () => {
    if (confirm('End quiz now?')) endQuiz();
  });

  // Keyboard: 1-4 select, Enter next, E explanation
  document.onkeydown = (e) => {
    if (['A','B','C','D'].includes(answered)) {
      if (e.key === 'Enter') nextQuestion();
    } else {
      const map = { '1': 'A', '2': 'B', '3': 'C', '4': 'D' };
      if (map[e.key]) selectOption(map[e.key]);
    }
  };
}

function selectOption(opt) {
  const q = state.questions[state.current];
  state.answers[q.id] = opt;
  saveSession({ questions: state.questions, current: state.current, answers: state.answers, startTime: state.startTime });
  renderQuiz(document.getElementById('app'));
}

function nextQuestion() {
  if (state.current < state.questions.length - 1) {
    state.current++;
    saveSession({ questions: state.questions, current: state.current, answers: state.answers, startTime: state.startTime });
    renderQuiz(document.getElementById('app'));
  } else {
    endQuiz();
  }
}

function endQuiz() {
  clearInterval(state.timerInterval);
  state.elapsed = Math.floor((Date.now() - state.startTime) / 1000);
  navigate('results');
}

// ─── Results ─────────────────────────────────────────────────────────────────

function renderResults(app) {
  state.view = 'results';
  const total = state.questions.length;
  const answers = state.answers;
  const correct = Object.entries(answers).filter(([id, opt]) => {
    const q = state.questions.find(q => q.id === id);
    return q && q.correct === opt;
  }).length;
  const score = Math.round((correct / total) * 100);

  const mistakes = state.questions.filter(q => {
    const a = answers[q.id];
    return a && a !== q.correct;
  });

  app.innerHTML = `
    <div class="container">
      <header class="header">
        <h1>Results</h1>
        <p>${correct} / ${total} correct (${score}%) — ${formatElapsed(state.elapsed)}</p>
        <div class="flex gap-1 mt-2">
          <button class="btn btn-ghost" id="review-btn" ${mistakes.length === 0 ? 'disabled' : ''}>
            Review mistakes (${mistakes.length})
          </button>
          <button class="btn btn-ghost" id="new-btn">New session</button>
          <button class="btn btn-ghost" id="export-btn">Export Anki</button>
        </div>
      </header>

      ${mistakes.length > 0 ? `
        <h2 class="section-title">Review mistakes</h2>
        ${mistakes.map((q, i) => `
          <div class="result-card">
            <div class="q-text">${q.question}</div>
            <div class="q-answers">
              <span class="your wrong">Your answer: ${q.options.find(o=>o.id===answers[q.id])?.text}</span>
              <span class="correct-text">Correct: ${q.options.find(o=>o.id===q.correct)?.text}</span>
            </div>
            <div class="explanation-sm">${q.explanation}</div>
            <a class="report-link" href="${buildIssueURL(q)}" target="_blank">Report issue</a>
          </div>
        `).join('')}
      ` : `<p class="empty">Perfect score! 🎉</p>`}
    </div>
  `;

  document.getElementById('review-btn')?.addEventListener('click', () => {
    state.questions = shuffle(mistakes);
    state.current = 0;
    state.answers = {};
    state.startTime = Date.now();
    state.elapsed = 0;
    navigate('quiz');
  });

  document.getElementById('new-btn')?.addEventListener('click', () => {
    clearSession();
    navigate('');
  });

  document.getElementById('export-btn')?.addEventListener('click', exportAnki);
}

// ─── Anki Export ─────────────────────────────────────────────────────────────

function exportAnki() {
  const qs = state.questions;
  // Build TSV: front, back, tags
  const lines = qs.map(q => {
    const front = q.question.replace(/\t/g, ' ').replace(/\n/g, ' ');
    const back = `${q.options.find(o=>o.id===q.correct)?.text}\n\n${q.explanation}`.replace(/\t/g, ' ').replace(/\n/g, '<br>');
    const tags = `${q.guideline} ${q.chapter || ''} ${q.difficulty || ''}`.trim().replace(/\s+/g, ' ');
    return [front, back, tags].join('\t');
  });

  const tsv = lines.join('\n');
  const blob = new Blob([tsv], { type: 'text/tab-separated-values' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `eau-quiz-${Date.now()}.txt`;
  a.click();
  URL.revokeObjectURL(url);
}

// ─── Restore Session ─────────────────────────────────────────────────────────

function restoreSession(session) {
  if (!session) return;
  state.questions = session.questions || [];
  state.current = session.current || 0;
  state.answers = session.answers || {};
  state.startTime = session.startTime || Date.now();
  state.elapsed = Math.floor((Date.now() - state.startTime) / 1000);

  clearInterval(state.timerInterval);
  state.timerInterval = setInterval(() => {
    state.elapsed = Math.floor((Date.now() - state.startTime) / 1000);
    const el = document.getElementById('elapsed-display');
    if (el) el.textContent = formatElapsed(state.elapsed);
  }, 1000);
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function formatElapsed(s) {
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}:${sec.toString().padStart(2, '0')}`;
}

function buildIssueURL(q) {
  const title = encodeURIComponent(`Issue with question: ${q.id}`);
  const body = encodeURIComponent(
`## Question\n${q.question}\n\n**ID:** \`${q.id}\`\n**Guideline:** ${q.guideline}\n**Chapter:** ${q.chapter}\n**Difficulty:** ${q.difficulty}\n\n## Problem\n- [ ] Factually incorrect\n- [ ] Wrong answer marked correct\n- [ ] Explanation is wrong\n- [ ] Other: ___


**Correct answer should be:** ${q.correct}
`
  );
  return `${REPO_ISSUES}?title=${title}&body=${body}&labels=question-error`;
}

// ─── Boot ─────────────────────────────────────────────────────────────────────

render();