import { chromium } from 'playwright';

const EXEC = "/opt/hermes/.playwright/chromium_headless_shell-1217/chrome-headless-shell-linux64/chrome-headless-shell";
const url = "https://uroweb.org/guidelines/prostate-cancer/chapter/diagnostic-evaluation";

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ 
      executablePath: EXEC,
      headless: true,
      args: ['--no-sandbox', '--disable-dev-shm-usage']
    });
    const page = await browser.newPage();
    
    const errors = [];
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()); });
    
    console.log(`Navigating to ${url}...`);
    const resp = await page.goto(url, { waitUntil: 'networkidle', timeout: 30000 });
    console.log(`HTTP status: ${resp.status()}`);
    
    await page.waitForTimeout(2000);
    
    // Get all headings with IDs (rendered by Vue)
    const headings = await page.$$eval('[id]', els => 
      els.filter(el => /^H[1-6]$/.test(el.tagName))
         .map(el => ({ tag: el.tagName, id: el.id, text: el.innerText.substring(0,60) }))
    );
    
    console.log(`\nHeadings with IDs: ${headings.length}`);
    headings.forEach(h => console.log(`  ${h.tag} id="${h.id}" → ${h.text}`));
    
    // Check target
    const target = headings.find(h => h.id === '5-2-diagnostic-tools');
    console.log(`\n${target ? '✓' : '✗'} #5-2-diagnostic-tools: ${target ? 'FOUND' : 'NOT FOUND'}`);
    
    // Test scroll-to for first 5
    console.log("\nScroll-to tests (first 8):");
    for (const h of headings.slice(0, 8)) {
      const anchor = `#${h.id}`;
      try {
        await page.goto(`${url}${anchor}`, { timeout: 10000 });
        await page.waitForTimeout(300);
        const visible = await page.$eval(`#${h.id}`, el => {
          const r = el.getBoundingClientRect();
          return r.top >= 0 && r.top <= window.innerHeight;
        }).catch(() => false);
        console.log(`  ${anchor}: ${visible ? '✓ visible' : '✗ off-screen/not found'}`);
      } catch(e) {
        console.log(`  ${anchor}: ✗ ${e.message.substring(0,60)}`);
      }
    }
    
    if (errors.length) console.log(`\nConsole errors: ${errors.slice(0,3)}`);
  } catch(e) {
    console.error(`Error: ${e.message}`);
  } finally {
    if (browser) await browser.close();
  }
})();
