import { chromium } from 'playwright';

const EXEC = "/opt/hermes/.playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell";
const url = "https://uroweb.org/guidelines/prostate-cancer/chapter/diagnostic-evaluation";

(async () => {
  const browser = await chromium.launch({ 
    executablePath: EXEC,
    headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
  });
  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  
  // Go to page
  await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await page.waitForTimeout(3000); // let Vue hydrate
  
  // Navigate to anchor directly via JS (more reliable than page.goto)
  await page.evaluate(async () => {
    const el = document.getElementById('5-2-diagnostic-tools');
    if (el) {
      el.scrollIntoView();
      return { found: true, tag: el.tagName, text: el.innerText.substring(0,50), top: el.getBoundingClientRect().top };
    }
    return { found: false };
  }).then(r => console.log('JS scroll to #5-2-diagnostic-tools:', JSON.stringify(r)));
  
  // Try page.goto then check scroll position
  await page.goto(url + '#5-2-diagnostic-tools', { waitUntil: 'networkidle', timeout: 30000 });
  await page.waitForTimeout(2000);
  
  const scrollPos = await page.evaluate(() => ({
    scrollY: window.scrollY,
    hash: window.location.hash,
    targetExists: !!document.getElementById('5-2-diagnostic-tools'),
    targetTop: document.getElementById('5-2-diagnostic-tools')?.getBoundingClientRect().top
  }));
  console.log('After goto with anchor:', JSON.stringify(scrollPos));
  
  // Check all headings with IDs and their positions
  const headingPositions = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('h2[id], h3[id], h4[id]'))
      .map(el => ({ id: el.id, tag: el.tagName, top: el.getBoundingClientRect().top, text: el.innerText.substring(0,40) }))
      .sort((a, b) => a.top - b.top);
  });
  console.log('\nHeadings sorted by position (viewport height=800):');
  headingPositions.forEach(h => {
    const inView = h.top >= 0 && h.top <= 800 ? '✓' : ' ';
    console.log(`  ${inView} top=${String(h.top).padStart(5)} ${h.tag} id="${h.id}" → ${h.text}`);
  });
  
  await browser.close();
})();
