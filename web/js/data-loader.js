/**
 * data-loader.js
 * Fetches JSON data files and exposes a cache.
 */

const DataLoader = (() => {
  const cache = {};
  const BASE = 'data';  // relative to index.html in web/

  async function fetchJSON(file) {
    if (cache[file]) return cache[file];
    const res = await fetch(`${BASE}/${file}`);
    if (!res.ok) throw new Error(`Failed to load ${file}: ${res.status}`);
    const data = await res.json();
    cache[file] = data;
    return data;
  }

  async function getGuidelines() {
    return fetchJSON('guidelines.json');
  }

  async function getIndex() {
    return fetchJSON('index.json');
  }

  async function getAllQuestions() {
    // Load all data/questions/*.json
    const index = await getIndex();
    const all = {};
    for (const g of index.guidelines) {
      const file = `questions/${g.slug}.json`;
      try {
        const data = await fetchJSON(file);
        all[g.slug] = data;
      } catch {
        // skip if not available
      }
    }
    return all;
  }

  async function getQuestionsForGuideline(slug) {
    // Try merged file first
    try {
      return await fetchJSON(`questions/${slug}.json`);
    } catch {
      return null;
    }
  }

  return { getGuidelines, getIndex, getAllQuestions, getQuestionsForGuideline };
})();