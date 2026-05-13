/**
 * app.js
 * Main SPA router and view dispatcher.
 * Hash-based routing: #, #quiz/<slug>, #quiz/<slug>/<section>, #results, #export
 */

const ROUTES = {
  LANDING: '',
  QUIZ: 'quiz',
  RESULTS: 'results',
  EXPORT: 'export'
};

let guidelinesData = null;
let questionsData = null;   // slug -> question JSON

// ─── Router ────────────────────────────────────────────────────────────────
function getRoute() {
  const hash = window.location.hash.slice(1) || '';
  const parts = hash.split('/').filter(Boolean);
  return parts;
}

function navigate(path) {
  window.location.hash = path;
}

function renderAll() {
  const parts = getRoute();
  const route = parts[0] || '';
  const app = document.getElementById('app');

  (async () => {
    if (!guidelinesData) {
      guidelinesData = await DataLoader.getGuidelines();
    }

    switch (route) {
      case 'quiz': {
        const slug = parts[1];
        const section = parts[2];
        if (slug) {
          app.innerHTML = renderQuizView(slug, section);
          await loadQuiz(slug, section);
        } else {
          app.innerHTML = renderSectionPicker();
        }
        break;
      }
      case 'results':
        app.innerHTML = renderResultsView();
        break;
      case 'export':
        app.innerHTML = renderExportView();
        break;
      default:
        app.innerHTML = renderLandingView();
    }
  })();
}

// ─── Views ────────────────────────────────────────────────────────────────
function renderLandingView() {
  const guidelineCards = (guidelinesData || []).map(g => `
    <div class="card" style="cursor:pointer" onclick="navigate('quiz/${g.slug}')">
      <div class="guideline-name">${g.name}</div>
      <div class="guideline-meta">${g.year} · ${g.chapters?.length || 0} chapters</div>
    </div>
  `).join('');

  return `
    <div class="container">
      <header class="header">
        <h1>EAU Guidelines Quiz</h1>
        <p>Multiple choice questions from <a href="https://uroweb.org/guidelines" target="_blank">European Association of Urology</a> guidelines</p>
        <div class="flex gap-1 mt-2" style="justify-content:center">
          <button class="btn btn-ghost" onclick="navigate('export')">📦 Export Anki Deck</button>
        </div>
      </header>
      <div class="guideline-list">${guidelineCards || '<div class="loading">Loading guidelines...</div>'}</div>
    </div>
  `;
}

function renderSectionPicker() {
  if (!guidelinesData) return '<div class="loading">Loading...</div>';
  return `
    <div class="container">
      <a class="nav-back" onclick="navigate('')">← Back to guidelines</a>
      <h2 style="margin-top:1rem">Select a guideline</h2>
      <div class="section-grid mt-1">
        ${guidelinesData.map(g => `
          <a class="section-chip" onclick="navigate('quiz/${g.slug}')">${g.name}</a>
        `).join('')}
      </div>
    </div>
  `;
}

async function loadQuiz(slug, sectionFilter) {
  const container = document.getElementById('quiz-container');
  if (!container) return;

  container.innerHTML = '<div class="loading">Loading questions...</div>';

  try {
    if (!questionsData) questionsData = {};
    if (!questionsData[slug]) {
      questionsData[slug] = await DataLoader.getQuestionsForGuideline(slug);
    }
    const data = questionsData[slug];

    if (!data || !data.questions || data.questions.length === 0) {
      container.innerHTML = '<div class="empty">No questions found for this guideline.<br>Data may not be generated yet.</div>';
      return;
    }

    let questions = data.questions;
    if (sectionFilter) {
      questions = questions.filter(q => q.chapter === sectionFilter);
    }

    QuizEngine.init(questions);
    renderQuizQuestion();
  } catch (e) {
    container.innerHTML = `<div class="empty">Error loading questions: ${e.message}</div>`;
  }
}

function renderQuizView(slug, sectionFilter) {
  const guideline = guidelinesData?.find(g => g.slug === slug);
  const name = guideline?.name || slug;

  return `
    <div class="container">
      <a class="nav-back" onclick="navigate('')">← All Guidelines</a>
      <div class="quiz-header mt-1">
        <div>
          <h2 style="font-size:1.2rem">${name}</h2>
          ${sectionFilter ? `<div style="font-size:0.8rem;color:var(--text-muted)">Section: ${sectionFilter}</div>` : ''}
        </div>
        <div class="quiz-progress text-right">
          <span id="progress-text">0 / 0</span>
          <div class="quiz-progress-bar" style="width:120px"><div class="quiz-progress-fill" id="progress-fill" style="width:0%"></div></div>
        </div>
      </div>
      <div id="quiz-container">
        <div class="loading">Loading...</div>
      </div>
    </div>
  `;
}

function renderQuizQuestion() {
  const container = document.getElementById('quiz-container');
  if (!container) return;

  const q = QuizEngine.current();
  if (!q) return;

  container.innerHTML = QuizEngine.renderQuestion(q);
  updateProgressBar();

  // Attach event listeners
  container.querySelectorAll('.option').forEach(opt => {
    opt.addEventListener('click', () => {
      QuizEngine.selectAnswer(q.id, opt.dataset.option);
      renderQuizQuestion();
    });
  });

  const checkBtn = container.querySelector('#check-answer');
  if (checkBtn) checkBtn.addEventListener('click', () => {
    QuizEngine.checkAnswer(q.id);
    renderQuizQuestion();
  });

  const nextBtn = container.querySelector('#next-question');
  if (nextBtn) nextBtn.addEventListener('click', () => {
    QuizEngine.next();
    renderQuizQuestion();
  });

  const finishBtn = container.querySelector('#finish-quiz');
  if (finishBtn) finishBtn.addEventListener('click', () => {
    navigate('results');
  });
}

function updateProgressBar() {
  const p = QuizEngine.progress();
  const el = document.getElementById('progress-text');
  const fill = document.getElementById('progress-fill');
  if (el) el.textContent = `${p.current} / ${p.total}`;
  if (fill) fill.style.width = `${(p.current / p.total) * 100}%`;
}

function renderResultsView() {
  const results = QuizEngine.getAllResults();
  const score = QuizEngine.score();
  const pct = score.total > 0 ? Math.round((score.correct / score.total) * 100) : 0;

  const resultItems = results.filter(r => r.answered).map(r => {
    const q = r.question;
    const res = r.result;
    return `
      <div class="card result-item">
        <div class="question-text">${q.question}</div>
        <div class="options">
          ${q.options.map(opt => {
            let cls = 'option';
            if (opt.id === q.correct) cls += ' correct';
            if (res && opt.id === res.your && opt.id !== q.correct) cls += ' wrong';
            return `<div class="${cls}">
              <span class="option-id">${opt.id}.</span>
              <span class="option-text">${opt.text}</span>
            </div>`;
          }).join('')}
        </div>
        ${res ? `<div class="result-answer">
          ${res.correct ? '<span style="color:var(--correct)">✓ Correct</span>' : `<span class="your-answer wrong">✗ Wrong (your answer: ${res.your})</span> — <span class="correct-text">Correct: ${q.correct}</span>`}
          <div style="font-size:0.82rem;margin-top:0.4rem;color:var(--text-muted)">${q.explanation} <a href="${q.source_url || '#'}" target="_blank">Source</a></div>
        </div>` : ''}
      </div>
    `;
  }).join('');

  return `
    <div class="container">
      <a class="nav-back" onclick="navigate('')">← Back to Guidelines</a>
      <div class="results-header mt-2">
        <div class="results-score">${pct}%</div>
        <div class="results-sub">${score.correct} / ${score.total} correct</div>
      </div>
      <div class="mt-2">${resultItems}</div>
      <div class="text-center mt-2">
        <button class="btn btn-primary" onclick="navigate('')">Try Another Guideline</button>
        <button class="btn btn-ghost" onclick="navigate('export')">📦 Export to Anki</button>
      </div>
    </div>
  `;
}

function renderExportView() {
  if (!guidelinesData) return '<div class="loading">Loading...</div>';

  const checks = guidelinesData.map(g => `
    <div class="card export-item">
      <input type="checkbox" id="cb-${g.slug}" value="${g.slug}" />
      <label for="cb-${g.slug}">
        <div class="guideline-name">${g.name}</div>
        <div class="guideline-meta">${g.year} · ${g.chapters?.length || 0} chapters</div>
      </label>
    </div>
  `).join('');

  return `
    <div class="container">
      <a class="nav-back" onclick="navigate('')">← Back</a>
      <h2 class="mt-1">Export Anki Deck</h2>
      <p style="font-size:0.85rem;color:var(--text-muted);margin-top:0.4rem">Select the guidelines you want to include in your Anki deck.</p>
      <div class="export-grid mt-1">${checks}</div>
      <div style="margin-top:1.5rem">
        <input type="text" id="deck-name" value="EAU Guidelines Quiz" placeholder="Deck name"
          style="background:var(--surface);border:1px solid var(--border);color:var(--text);padding:0.6rem 1rem;border-radius:8px;font-size:0.9rem;width:100%;max-width:320px" />
      </div>
      <div class="mt-1">
        <button class="btn btn-primary" id="export-btn" onclick="doExport()">📦 Download .apkg</button>
      </div>
      <div id="export-status" style="margin-top:1rem;font-size:0.85rem;color:var(--text-muted)"></div>
    </div>
  `;
}

window.doExport = async function() {
  const btn = document.getElementById('export-btn');
  const status = document.getElementById('export-status');
  const deckName = document.getElementById('deck-name')?.value || 'EAU Guidelines Quiz';

  const checked = [...document.querySelectorAll('#export-view input[type=checkbox]:checked')].map(cb => cb.value);
  if (checked.length === 0) {
    status.textContent = 'Please select at least one guideline.';
    return;
  }

  btn.disabled = true;
  status.textContent = 'Generating deck...';

  try {
    // Load all selected guideline question data
    const data = {};
    for (const slug of checked) {
      if (!questionsData?.[slug]) {
        try {
          questionsData[slug] = await DataLoader.getQuestionsForGuideline(slug);
        } catch {}
      }
      data[slug] = questionsData?.[slug];
    }

    await AnkiExport.exportAndDownload(data, checked, deckName);
    status.textContent = '✓ Deck downloaded!';
  } catch (e) {
    status.textContent = `✗ Error: ${e.message}`;
  } finally {
    btn.disabled = false;
  }
};

// ─── Init ─────────────────────────────────────────────────────────────────
window.addEventListener('hashchange', renderAll);
window.addEventListener('DOMContentLoaded', renderAll);

// Initial render
renderAll();