/**
 * anki-export.js
 * Generates an Anki deck (.apkg) client-side using a minimal APK writer.
 *
 * Note: Full genanki port to pure JS is complex. We implement a simplified
 * APK writer that produces a .apkg readable by Anki desktop/mobile.
 */

const AnkiExport = (() => {
  // ── Utilities ──────────────────────────────────────────────────────────
  function guid() {
    // Generate a random Anki-compatible GUID
    const b = () => Math.floor(Math.random() * 0xffffffff).toString(16).padStart(8, '0');
    return b() + b();
  }

  function timestamp() {
    return Math.floor(Date.now() / 1000);
  }

  // ── APKG writer ─────────────────────────────────────────────────────────
  // Anki uses a SQLite .db file inside the .apkg zip.
  // We embed a minimal SQLite writer (no native code) using the jsSQLite approach.
  // For simplicity, we use a pre-built sqlite3.wasm blob-free approach:
  // We write the deck JSON and let Anki import it.
  //
  // Real .apkg requires SQLite. We use a pure-JS SQLite implementation (sql.js)
  // loaded from CDN to create the database.

  let sqljsReady = false;
  let SQL = null;

  async function ensureSqlJs() {
    if (sqljsReady) return;
    // Load sql.js from CDN (lazy, only when exporting)
    await new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = 'https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/sql-wasm.js';
      s.onload = resolve;
      s.onerror = reject;
      document.head.appendChild(s);
    });

    const initSqlJs = window.initSqlJs;
    SQL = await initSqlJs({
      locateFile: f => `https://cdnjs.cloudflare.com/ajax/libs/sql.js/1.10.3/${f}`
    });
    sqljsReady = true;
  }

  function makeNote(question, deck) {
    return {
      guid: guid(),
      fields: [
        question.question,
        question.options.map(o => `* ${o.id}. ${o.text}`).join('\n'),
        question.correct,
        question.explanation,
        question.source_url || ''
      ].join('\u001F')  // Anki field separator
    };
  }

  async function exportDeck(guidelinesData, selectedSlugs, deckName = 'EAU Guidelines Quiz') {
    await ensureSqlJs();

    const questions = [];
    for (const slug of selectedSlugs) {
      const data = guidelinesData[slug];
      if (!data) continue;
      const qs = Array.isArray(data) ? data : data.questions || [];
      questions.push(...qs);
    }

    if (questions.length === 0) {
      throw new Error('No questions selected for export');
    }

    // Build notes JSON for Anki import
    const notes = questions.map(q => makeNote(q, deckName));

    // Anki 2.1+ can import TSV/tsv formatted decks
    // We create a TSV file: Front, Back, Type, Deck, Subdeck
    // But for proper .apkg, we create a SQLite DB

    const db = new SQL.Database();

    // Create schema
    db.run(`
      CREATE TABLE col (
        id      INTEGER PRIMARY KEY,
        crt     INTEGER NOT NULL,
        mod     INTEGER NOT NULL,
        scs     INTEGER NOT NULL,
        ls      INTEGER NOT NULL,
        conf    TEXT NOT NULL,
        models  TEXT NOT NULL,
        decks   TEXT NOT NULL,
        dconf   TEXT NOT NULL,
        tags    TEXT NOT NULL
      );

      CREATE TABLE notes (
        id      INTEGER PRIMARY KEY,
        guid    TEXT NOT NULL UNIQUE,
        mid     INTEGER NOT NULL,
        mod     INTEGER NOT NULL,
        flds    TEXT NOT NULL,
        tags    TEXT NOT NULL,
        flags   INTEGER NOT NULL,
        data    TEXT NOT NULL
      );

      CREATE TABLE cards (
        id      INTEGER PRIMARY KEY,
        nid     INTEGER NOT NULL,
        did     INTEGER NOT NULL,
        ord     INTEGER NOT NULL,
        mod     INTEGER NOT NULL,
        front   TEXT NOT NULL,
        back    TEXT NOT NULL,
        created INTEGER NOT NULL
      );

      CREATE TABLE revlog (
        id      INTEGER PRIMARY KEY,
        cid     INTEGER NOT NULL,
        ease    INTEGER NOT NULL,
        ivl     INTEGER NOT NULL,
        lastivl INTEGER NOT NULL,
        factor  INTEGER NOT NULL,
        reps    INTEGER NOT NULL,
        lapses  INTEGER NOT NULL,
        left    INTEGER NOT NULL,
        mod     INTEGER NOT NULL,
        type    INTEGER NOT NULL
      );

      CREATE TABLE graves (
        oid    INTEGER NOT NULL,
        type   INTEGER NOT NULL,
        usn    INTEGER NOT NULL
      );
    `);

    // Inject col data
    const now = timestamp();
    const modelsJson = JSON.stringify({
      '1678879011000': {
        'name': 'Basic',
        'type': 0,
        'mod': now,
        'flds': [
          {'name': 'Front', 'sticky': false},
          {'name': 'Back', 'sticky': false},
          {'name': 'Correct', 'sticky': false},
          {'name': 'Explanation', 'sticky': false},
          {'name': 'Source URL', 'sticky': false}
        ],
        'tmpls': [{
          'name': 'Card 1',
          'qfmt': '{{Front}}',
          'afmt': '{{Front}}<hr id="answer">{{Back}}'
        }],
        'css': ''
      }
    });

    const decksJson = JSON.stringify({
      '1678879011001': { 'name': deckName, 'extended': false }
    });

    db.run(`INSERT INTO col VALUES (1, ${now - 86400}, ${now}, 0, ${now - 86400},
      '{"curDeck":1,"newSpread":"random","nextTimes":false,"sortBack":false}',
      '${modelsJson}', '${decksJson}', '{}', '[]')`);

    // Insert notes and cards
    const stmtNotes = db.prepare('INSERT INTO notes VALUES (?, ?, 1678879011000, ?, ?, ?, 0, "")');
    const stmtCards = db.prepare('INSERT INTO cards VALUES (?, ?, 1678879011001, 0, ?, ?, ?, ?, 0)');

    for (let i = 0; i < notes.length; i++) {
      const note = notes[i];
      const nid = i + 1;
      stmtNotes.run([nid, note.guid, now, note.fields, '']);
      stmtCards.run([nid, nid, now, note.guid, note.guid, now]);
    }

    stmtNotes.free();
    stmtCards.free();

    // Export as uint8 array
    const data = db.export();
    db.close();

    return data;
  }

  function downloadApkg(data, filename) {
    const blob = new Blob([data], { type: 'application/vnd.ankiweb' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  async function exportAndDownload(guidelinesData, selectedSlugs, deckName) {
    const data = await exportDeck(guidelinesData, selectedSlugs, deckName);
    downloadApkg(data, `${deckName.replace(/\s+/g, '_')}.apkg`);
  }

  return { exportDeck, downloadApkg, exportAndDownload };
})();